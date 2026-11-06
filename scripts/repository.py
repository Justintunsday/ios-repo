"""Validate pinned packages and generate a flat, signed APT repository."""
import argparse
from datetime import datetime, timezone
import gzip
import hashlib
import html
import json
import lzma
from pathlib import Path
import re
import shutil
import subprocess
import urllib.parse
import urllib.request
from email.utils import format_datetime

from deb import encode_fields, fields, inspect, sha256

ROOT = Path(__file__).resolve().parents[1]


def validate(catalog, config):
    seen = set()
    if not isinstance(catalog, list) or not catalog:
        raise ValueError("empty package catalog")
    prefix = f"https://github.com/{config['repository']}/releases/download/"
    for item in catalog:
        package, version = item.get("package", ""), item.get("version", "")
        if not re.fullmatch(r"[a-z0-9][a-z0-9+.-]+", package) or package in seen:
            raise ValueError("invalid or duplicate package ID")
        seen.add(package)
        if not re.fullmatch(r"[0-9][A-Za-z0-9.+~_-]*", version):
            raise ValueError("unsupported package version")
        if item.get("architecture") != "iphoneos-arm64":
            raise ValueError("unsupported architecture")
        filename = f"{package}_{version}_iphoneos-arm64.deb"
        if item.get("file") != filename or not re.fullmatch(r"[0-9a-f]{64}", item.get("sha256", "")):
            raise ValueError("invalid filename or checksum")
        url = urllib.parse.urlsplit(item.get("url", ""))
        if (not item.get("url", "").startswith(prefix) or url.username or url.password
                or url.query or url.fragment or urllib.parse.unquote(url.path.rsplit("/", 1)[-1]) != filename):
            raise ValueError("package URL must refer to a pinned asset in this repository")


def obtain(item, directory):
    path = directory / item["file"]
    if path.exists():
        if path.is_symlink() or sha256(path.read_bytes()) != item["sha256"]:
            raise ValueError("cached package differs from pinned checksum")
        return path
    partial = path.with_suffix(".download")
    with urllib.request.urlopen(item["url"], timeout=90) as response, partial.open("xb") as output:
        while block := response.read(1024 * 1024):
            output.write(block)
    if sha256(partial.read_bytes()) != item["sha256"]:
        partial.unlink()
        raise ValueError("download checksum mismatch")
    partial.replace(path)
    return path


def page(title, body, prefix=""):
    return ("<!doctype html><html lang=\"en\"><head><meta charset=\"utf-8\">"
            "<meta name=\"viewport\" content=\"width=device-width, initial-scale=1\">"
            f"<title>{html.escape(title)}</title><link rel=\"icon\" href=\"{prefix}assets/icon.svg\">"
            f"<link rel=\"stylesheet\" href=\"{prefix}assets/style.css\">"
            f"<script src=\"{prefix}assets/app.js\" defer></script></head><body>{body}</body></html>")


def render(site, catalog, controls, config):
    escape = html.escape
    source = config["url"]
    rows = []
    symbols = ["N", ">_", "R", "C"]
    for index, item in enumerate(catalog):
        package, title = item["package"], escape(item["title"])
        control = controls[package]
        depiction = "depictions/" + package + ".html"
        rows.append(f'''<li class="package-row"><span class="package-icon tone-{index}">{escape(symbols[index % 4])}</span>
<div class="package-copy"><a class="package-name" href="{depiction}">{title}</a><p>{escape(item['description'])}</p><span class="category">{escape(item['category'])}</span></div>
<a class="package-version" href="{depiction}">{escape(item['version'])}<span>Details</span></a></li>''')
        upstream = item.get("source_url") or "https://github.com/Justintunsday/" + ("ios-control-bridge" if package == "ios-control-bridge" else "iOSRemoteBridge")
        upstream = upstream.split("/releases/download/", 1)[0]
        if item.get("source_commit"):
            upstream += "/tree/" + item["source_commit"]
        note = "Respring once after installation to load the settings shim. Optional Siri/OpenCode setup is manual." if package == "ios-control-bridge" else ("Provision owner credentials and respring once. Remote access starts only after pairing and setup." if "iosremotebridge" in package else "Use the upstream setup guide after installation. Your own model account is required for OpenCode requests." if package == "opencode" else "Includes the iOS runtime and launcher; npm and npx are not bundled.")
        detail = f'''<main class="detail"><a class="back" href="../">All packages</a><header><span class="package-icon tone-{index}">{escape(symbols[index % 4])}</span><h1>{title}</h1><p>{escape(item['description'])}</p></header>
<dl><div><dt>Version</dt><dd>{escape(item['version'])}</dd></div><div><dt>Architecture</dt><dd>iphoneos-arm64</dd></div><div><dt>Dependencies</dt><dd>{escape(control.get('Depends','None'))}</dd></div></dl>
<p>{escape(note)}</p><p>Preview package. Source functionality was tested on iPhone SE 2 with iOS 16.1.1; this newly assembled package has not been installed as part of repository verification.</p>
<div class="actions"><a class="button primary" href="../pool/{escape(item['file'])}">Download .deb</a><a class="button" href="{escape(upstream)}">Upstream source</a></div>
<h2>SHA-256</h2><code class="checksum">{item['sha256']}</code></main>'''
        (site / depiction).write_text(page(item["title"], detail, "../"), encoding="utf8")
    fingerprint = " ".join(config["fingerprint"][index:index + 4] for index in range(0, 40, 4))
    body = f'''<main><header class="intro"><a class="brand" href="https://github.com/{config['repository']}"><img src="assets/icon.svg" width="42" height="42" alt="">Justintunsday</a>
<h1>Tools for your<br>rootless iPhone.</h1><p class="lead">Node.js, OpenCode and the bridges that connect your tools to iOS.</p>
<div class="source"><code id="source-url">{escape(source)}</code><button id="copy-source" type="button">Copy URL</button></div><span id="copy-status" role="status" aria-live="polite"></span>
<div class="actions"><a class="button primary" href="sileo://source/{escape(source)}">Add to Sileo</a><a class="button" href="zbra://sources/add/{escape(source)}">Add to Zebra</a></div>
<p class="compatibility">Open on your iPhone to add the source. Rootless only, with preview builds tested on iOS 16.1.1.</p></header>
<section class="packages" aria-labelledby="packages-title"><div class="section-heading"><h2 id="packages-title">Packages</h2><span>iphoneos-arm64</span></div><ul>{''.join(rows)}</ul></section>
<section class="installation"><h2>Install from a terminal</h2><p>Add the signing key and source once, then choose the packages you need.</p><details><summary>Show commands and signing key</summary>
<pre><code>sudo mkdir -p /var/jb/etc/apt/keyrings
curl -fsSL {escape(source)}repo-key.gpg -o /var/mobile/justintunsday-ios.gpg
sudo install -m 644 /var/mobile/justintunsday-ios.gpg /var/jb/etc/apt/keyrings/justintunsday-ios.gpg
echo 'deb [signed-by=/var/jb/etc/apt/keyrings/justintunsday-ios.gpg] {escape(source)} ./' | sudo tee /var/jb/etc/apt/sources.list.d/justintunsday-ios.list
sudo apt-get update
sudo apt-get install opencode ios-control-bridge io.github.justintunsday.iosremotebridge</code></pre><p>OpenCode pulls in its exact Node.js runtime dependency. Pair iOSRemoteBridge using its upstream instructions. Installing these packages does not configure provider keys or enable the optional root OpenCode or Siri services.</p>
<h3>Signing key</h3><code class="checksum">{fingerprint}</code><p><a href="repo-key.gpg">Download public key</a></p></details></section>
<footer><span>Justintunsday iOS Repo</span><nav aria-label="Repository"><a href="https://github.com/{config['repository']}">GitHub</a><a href="Packages">Package index</a><a href="provenance.json">Build provenance</a></nav></footer></main>'''
    (site / "index.html").write_text(page(config["name"], body), encoding="utf8")


def build_site(catalog, config, package_dir, site):
    validate(catalog, config)
    if site.exists() and any(site.iterdir()):
        raise ValueError("output directory must be empty")
    (site / "pool").mkdir(parents=True)
    (site / "depictions").mkdir()
    controls, stanzas = {}, []
    for item in catalog:
        data = obtain(item, package_dir).read_bytes()
        control = inspect(data)
        if any(control.get(key) != item[field] for key, field in (("Package", "package"), ("Version", "version"), ("Architecture", "architecture"))):
            raise ValueError("catalog and Debian package identity mismatch")
        controls[item["package"]] = control.copy()
        control.setdefault("Name", item["title"])
        control.update(Filename="pool/" + item["file"], Size=str(len(data)),
                       MD5sum=hashlib.md5(data).hexdigest(), SHA1=hashlib.sha1(data).hexdigest(),
                       SHA256=sha256(data), SHA512=hashlib.sha512(data).hexdigest(),
                       Depiction=config["url"] + "depictions/" + item["package"] + ".html")
        stanzas.append(encode_fields(control))
        (site / "pool" / item["file"]).write_bytes(data)
    if "opencode" in controls and "node26" in controls:
        required = "node26 (= " + controls["node26"]["Version"] + ")"
        if required not in controls["opencode"].get("Depends", ""):
            raise ValueError("OpenCode and Node runtime dependencies differ")
    packages = b"\n".join(stanzas) + b"\n"
    indices = {"Packages": packages, "Packages.gz": gzip.compress(packages, mtime=0), "Packages.xz": lzma.compress(packages)}
    release = {"Origin": config["origin"], "Label": config["name"], "Suite": "experimental", "Codename": "rootless",
               "Date": format_datetime(datetime.now(timezone.utc), usegmt=True), "Architectures": config["architecture"],
               "Description": "Rootless iOS packages maintained by Justintunsday"}
    text = encode_fields(release).decode()
    for label, algorithm in (("MD5Sum", "md5"), ("SHA256", "sha256"), ("SHA512", "sha512")):
        text += label + ":\n" + "".join(f" {hashlib.new(algorithm, body).hexdigest()} {len(body)} {name}\n" for name, body in indices.items())
    for name, body in indices.items():
        (site / name).write_bytes(body)
    (site / "Release").write_text(text, encoding="utf8", newline="\n")
    for name in ("repo-key.gpg", "repo-key.asc"):
        shutil.copyfile(ROOT / name, site / name)
    shutil.copytree(ROOT / "web/assets", site / "assets")
    (site / ".nojekyll").touch()
    (site / "packages.json").write_text(json.dumps(catalog, indent=2) + "\n", encoding="utf8")
    (site / "provenance.json").write_text(json.dumps({"packages": [{key: value for key, value in item.items() if key not in ("title", "description", "category")} for item in catalog]}, indent=2) + "\n", encoding="utf8")
    render(site, catalog, controls, config)
    return controls


def verify(site, catalog, config):
    validate(catalog, config)
    packages = (site / "Packages").read_bytes()
    if gzip.decompress((site / "Packages.gz").read_bytes()) != packages or lzma.decompress((site / "Packages.xz").read_bytes()) != packages:
        raise ValueError("compressed index mismatch")
    indexed = [fields(part) for part in packages.split(b"\n\n") if part.strip()]
    if {row["Package"] for row in indexed} != {item["package"] for item in catalog} or len(indexed) != len(catalog):
        raise ValueError("package inventory mismatch")
    for row in indexed:
        path = site / row["Filename"]
        if path.is_symlink() or not path.resolve().is_relative_to(site.resolve()):
            raise ValueError("unsafe indexed filename")
        data = path.read_bytes()
        if str(len(data)) != row["Size"] or sha256(data) != row["SHA256"]:
            raise ValueError("package checksum mismatch")
        inspect(data)
    release = fields((site / "Release").read_bytes())
    rows = [line.split() for line in release.get("SHA256", "").splitlines() if line.strip()]
    if len(rows) != 3 or {row[2] for row in rows} != {"Packages", "Packages.gz", "Packages.xz"}:
        raise ValueError("Release must cover every package index")
    for digest, size, name in rows:
        data = (site / name).read_bytes()
        if len(data) != int(size) or sha256(data) != digest:
            raise ValueError("Release checksum mismatch")
    return len(indexed)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("build", "verify"))
    parser.add_argument("--packages", type=Path, default=ROOT / "_work/packages")
    parser.add_argument("--site", type=Path, default=ROOT / "_site")
    args = parser.parse_args()
    catalog = json.loads((ROOT / "packages.json").read_text())
    config = json.loads((ROOT / "repo.json").read_text())
    if args.action == "build":
        args.packages.mkdir(parents=True, exist_ok=True)
        build_site(catalog, config, args.packages, args.site)
    count = verify(args.site, catalog, config)
    print(json.dumps({"packages_verified": count, "site": str(args.site)}))


if __name__ == "__main__":
    main()
