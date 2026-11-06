"""Small, dependency-free reader/writer for the gzip/xz Debian packages we publish."""
import gzip
import hashlib
import io
import lzma
import posixpath
from pathlib import Path, PurePosixPath
import re
import tarfile


def sha256(data):
    return hashlib.sha256(data).hexdigest()


def fields(data):
    result = {}
    key = None
    for line in data.decode("utf8").splitlines():
        if not line:
            continue
        if line.startswith((" ", "\t")):
            if key is None:
                raise ValueError("invalid continuation")
            result[key] += "\n" + line
        else:
            key, separator, value = line.partition(":")
            if not separator or key in result or not re.fullmatch(r"[A-Za-z][A-Za-z0-9-]*", key):
                raise ValueError("invalid control field")
            result[key] = value.lstrip()
    return result


def encode_fields(data):
    for key, value in data.items():
        if not isinstance(value, str) or "\r" in value or any(not part.startswith((" ", "\t")) for part in value.split("\n")[1:]):
            raise ValueError("invalid control value")
    return ("\n".join(f"{key}: {value}" for key, value in data.items()) + "\n").encode()


def members(data):
    if not data.startswith(b"!<arch>\n"):
        raise ValueError("not a Debian ar archive")
    offset = 8
    result = {}
    while offset < len(data):
        header = data[offset:offset + 60]
        if len(header) != 60 or header[-2:] != b"`\n":
            raise ValueError("invalid ar header")
        name = header[:16].decode("ascii").strip().rstrip("/")
        size = int(header[48:58])
        offset += 60
        if size < 0 or offset + size > len(data) or name in result:
            raise ValueError("invalid ar member")
        result[name] = data[offset:offset + size]
        offset += size + size % 2
    if result.get("debian-binary") != b"2.0\n":
        raise ValueError("unsupported Debian format")
    return result


def tar_entries(archive):
    with tarfile.open(fileobj=io.BytesIO(archive), mode="r:*") as stream:
        for info in stream:
            name = info.name
            while name.startswith("./"):
                name = name[2:]
            if not name or name == ".":
                continue
            path = PurePosixPath(name)
            if path.is_absolute() or ".." in path.parts or "\\" in name:
                raise ValueError("unsafe archive path")
            if not (info.isfile() or info.isdir() or info.issym()):
                raise ValueError("unsupported archive entry")
            yield info, name, stream.extractfile(info).read() if info.isfile() else None


def inspect(data, audit_payload=True):
    archive = members(data)
    controls = [name for name in archive if name.startswith("control.tar.")]
    payloads = [name for name in archive if name.startswith("data.tar.")]
    if len(controls) != 1 or len(payloads) != 1:
        raise ValueError("invalid Debian member inventory")
    control = None
    for info, name, body in tar_entries(archive[controls[0]]):
        if name == "control":
            control = fields(body)
    if not control or control.get("Architecture") != "iphoneos-arm64":
        raise ValueError("a rootless iphoneos-arm64 package is required")
    if not re.fullmatch(r"[a-z0-9][a-z0-9+.-]+", control.get("Package", "")):
        raise ValueError("invalid package ID")
    if audit_payload:
        forbidden = {".env", ".device-password", "server-password", "client-config.json", "auth.json", "service.json", ".ssh", ".gnupg"}
        for info, name, body in tar_entries(archive[payloads[0]]):
            if name not in ("var", "var/jb") and not name.startswith("var/jb/"):
                raise ValueError("non-rootless payload: " + name)
            if forbidden.intersection(PurePosixPath(name).parts):
                raise ValueError("private configuration in package")
            if info.isfile() and info.mode & 0o022:
                raise ValueError("group/world-writable payload")
            if info.issym():
                target = posixpath.normpath(posixpath.join(posixpath.dirname(name), info.linkname)).lstrip("/")
                if target != "var/jb" and not target.startswith("var/jb/"):
                    raise ValueError("symlink escapes the rootless prefix")
    return control


def _tar(files, epoch):
    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode="w", format=tarfile.GNU_FORMAT) as archive:
        for name, (body, mode) in sorted(files.items()):
            info = tarfile.TarInfo("./" + name)
            info.size, info.mode, info.mtime = len(body), mode, epoch
            info.uid = info.gid = 0
            info.uname = info.gname = "root"
            archive.addfile(info, io.BytesIO(body))
    return gzip.compress(buffer.getvalue(), mtime=epoch)


def build(control, payload, epoch, scripts=None):
    control_files = {"control": (encode_fields(control), 0o644)}
    control_files.update({name: (value, 0o755) for name, value in (scripts or {}).items()})
    return rebuild({"debian-binary": b"2.0\n", "control.tar.gz": _tar(control_files, epoch), "data.tar.gz": _tar(payload, epoch)}, epoch)


def rebuild(archive, epoch):
    output = bytearray(b"!<arch>\n")
    for name, body in archive.items():
        if len(name) > 15:
            raise ValueError("long ar names are not supported")
        header = f"{name + '/':<16}{epoch:<12}{0:<6}{0:<6}{'100644':<8}{len(body):<10}`\n".encode("ascii")
        output.extend(header + body + (b"\n" if len(body) % 2 else b""))
    return bytes(output)


def revise_version(data, version, epoch):
    archive = members(data)
    control_name = next(name for name in archive if name.startswith("control.tar."))
    files = {}
    for info, name, body in tar_entries(archive[control_name]):
        if info.isfile():
            if name == "control":
                control = fields(body)
                control["Version"] = version
                body = encode_fields(control)
            files[name] = (body, info.mode)
    del archive[control_name]
    return rebuild({"debian-binary": archive.pop("debian-binary"), "control.tar.gz": _tar(files, epoch), **archive}, epoch)
