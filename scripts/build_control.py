"""Build the pinned client-neutral bridge and assemble its rootless Debian package."""
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tarfile
import urllib.request

from deb import build, inspect, sha256

ROOT = Path(__file__).resolve().parents[1]


def run(args, cwd=None):
    subprocess.run([str(arg) for arg in args], cwd=cwd, check=True, timeout=300)


def main():
    lock = json.loads((ROOT / "sources.lock.json").read_text())
    pin = lock["control_bridge"]
    work = ROOT / "_work/control"
    work.mkdir(parents=True, exist_ok=False)
    archive = work / "source.tar.gz"
    url = f"https://github.com/{pin['repository']}/archive/{pin['commit']}.tar.gz"
    with urllib.request.urlopen(url, timeout=60) as response, archive.open("wb") as output:
        shutil.copyfileobj(response, output)
    with tarfile.open(archive) as source:
        source.extractall(work, filter="data")
    project, = [path for path in work.iterdir() if path.is_dir()]
    sdk = subprocess.check_output(["xcrun", "--sdk", "iphoneos", "--show-sdk-path"], text=True).strip()
    run([sys.executable, "-m", "unittest", "discover", "-s", "tests", "-q"], project)
    run([sys.executable, "tools/build_native.py", "--sdk", sdk], project)
    native = project / "build/native"
    shim = native / "icbridge.dylib"
    run(["xcrun", "--sdk", "iphoneos", "clang", "-target", "arm64e-apple-ios16.1", "-isysroot", sdk,
         "-dynamiclib", "-fno-objc-arc", "-O1", "-Wall", "native/ellekit/SpringBridge.m", "-framework", "Foundation", "-o", shim], project)
    run(["ldid", "-S", shim])
    siri_slices = []
    for arch in ("arm64", "arm64e"):
        path = native / f"SiriNative.{arch}.dylib"
        run(["xcrun", "--sdk", "iphoneos", "clang", "-target", arch + "-apple-ios16.1", "-isysroot", sdk,
             "-fobjc-arc", "-Wall", "-Wextra", "-Werror", "-dynamiclib", "native/siri/NativeTransport.m", "-framework", "Foundation", "-o", path], project)
        siri_slices.append(path)
    siri_library = native / "SiriNative.dylib"
    run(["xcrun", "lipo", "-create", *siri_slices, "-output", siri_library])
    run(["ldid", "-S", siri_library])
    prefix = "var/jb/usr/lib/ios-control-bridge/"
    payload = {}
    def add(path, target, mode=0o644):
        payload[target] = (Path(path).read_bytes(), mode)
    for folder in ("src", "bin", "skills", "docs", "integrations/siri"):
        for path in sorted((project / folder).rglob("*")):
            if path.is_file() and "__pycache__" not in path.parts and path.suffix in (".py", ".md", ".json", ".sh", ".plist", ""):
                add(path, prefix + path.relative_to(project).as_posix(), 0o755 if folder == "bin" or path.suffix == ".sh" else 0o644)
    add(project / "README.md", prefix + "README.md")
    helpers = ("icb-activities", "icb-settings", "icb-open-url", "icb-alarms", "icb-calendar", "icb-reminders", "icb-siri-language")
    for name in helpers:
        add(native / name, prefix + "build/native/" + name, 0o755)
    add(native / "icb-siri-language", "var/jb/usr/local/bin/icb-siri-language", 0o755)
    add(shim, "var/jb/usr/lib/TweakInject/icbridge.dylib", 0o755)
    add(project / "native/ellekit/icbridge.plist", "var/jb/usr/lib/TweakInject/icbridge.plist")
    add(siri_library, prefix + "integrations/siri/NativeBridge.dylib", 0o755)
    payload["var/jb/usr/bin/iosctl"] = (b'#!/var/jb/bin/sh\nexec /var/jb/usr/bin/python3 -B /var/jb/usr/lib/ios-control-bridge/bin/iosctl "$@"\n', 0o755)
    payload["var/jb/usr/share/doc/ios-control-bridge/source.json"] = ((json.dumps({**pin, "archive_sha256": sha256(archive.read_bytes()), "new_package_installation_device_verified": False}, indent=2) + "\n").encode(), 0o644)
    control = {"Package": pin["package"], "Name": "iOS Control Bridge", "Version": pin["version"], "Architecture": "iphoneos-arm64",
        "Maintainer": "Justintunsday <162324843+Justintunsday@users.noreply.github.com>", "Author": "Justintunsday", "Section": "Development", "Priority": "optional",
        "Depends": "firmware (= 16.1.1), python3 (>= 3.9), ellekit", "Homepage": "https://github.com/" + pin["repository"],
        "Installed-Size": str((sum(len(data) for data, _ in payload.values()) + 1023) // 1024),
        "Description": "System-service tools for rootless iOS 16.1.1\n Fixed adapters for settings, alarms, reminders, calendar, Live Activities,\n browser, weather and Siri language. Includes the optional native Siri adapter;\n Siri/OpenCode configuration is not enabled automatically. Respring once\n to load the settings shim. Other OS builds remain unsupported."}
    postinst = b'''#!/var/jb/bin/sh
set -eu
state=/var/jb/var/run/ios-control-bridge
if [ -L "$state" ]; then echo 'Refusing a symbolic-link IPC directory.' >&2; exit 1; fi
if [ ! -d "$state" ]; then /var/jb/usr/bin/install -d -o mobile -g mobile -m 700 "$state"; fi
echo 'iOS Control Bridge installed. Respring once to load the settings shim.'
echo 'Run iosctl capabilities. Optional Siri/OpenCode setup remains disabled.'
'''
    data = build(control, payload, lock["source_date_epoch"], {"postinst": postinst})
    inspect(data)
    output = ROOT / "dist"
    output.mkdir(exist_ok=True)
    filename = f"{pin['package']}_{pin['version']}_iphoneos-arm64.deb"
    (output / filename).write_bytes(data)
    report = {"package": pin["package"], "version": pin["version"], "file": filename, "bytes": len(data), "sha256": sha256(data), "source": pin,
              "native_build": "passed", "source_regression_tests": "passed", "new_package_installation_device_verified": False,
              "payload_files": [{"path": name, "sha256": sha256(body), "mode": oct(mode)} for name, (body, mode) in sorted(payload.items())]}
    (output / "control-build.json").write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps({key: report[key] for key in ("file", "bytes", "sha256", "native_build")}))


if __name__ == "__main__":
    main()
