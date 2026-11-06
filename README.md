# Justintunsday iOS Repo

A GitHub Pages APT source for rootless iOS packages: Node.js 26, OpenCode,
iOSRemoteBridge and Control API.

Source URL: **https://justintunsday.github.io/ios-repo/**

Open that URL on your phone and choose **Add to Sileo** or **Add to Zebra**.
The page also provides commands for installing the public signing key and adding
a strict `signed-by` APT source. No `[trusted=yes]` override is needed for that path.

| Package | Version | Purpose |
| --- | --- | --- |
| `node26` | `26.13.0-2` | Standalone Node.js runtime; npm/npx are not bundled. |
| `opencode` | `2.2.5-6` | OpenCode's terminal interface, bundled skill and exact Node runtime dependency. |
| `io.github.justintunsday.iosremotebridge` | `0.1.0~dev+repo.20261106.3` | Native screen capture, touch and bundled Computer Use skill; owner pairing/setup required. |
| `ios-control-bridge` | `0.13.0+repo.1` | Control API: app management, system-service CLI, native helpers and portable skills. |

Packages use the `iphoneos-arm64` architecture and `/var/jb` prefix. The tested
device is an iPhone SE (2nd generation) on iOS 16.1.1. Each package retains its
own compatibility and upstream license. The source repositories remain separate.

Sileo requires a `Components` field in `Release` even for a flat `./` source.
The publisher emits `Components: main` and checks this before signing. This follows
the [Sileo source validator](https://github.com/Sileo/Sileo/blob/c9f70158a037dc76b91c450e72af2de0514dd3ee/Sileo/Backend/Repo%20Manager/RepoManager.swift#L651).
Zebra and standard APT accepting a source do not replace that client check.

Package inputs are pinned in `sources.lock.json`. The Control API build
workflow compiles its native helpers and optional tweaks from the pinned source.
Publication validates package identity, checksums and signed APT indices before
deploying the static repository to GitHub Pages. Device credentials and pairing
files are not distribution inputs.

## Compatibility and setup

These are preview packages. Node.js and OpenCode retain their upstream firmware
requirements. iOSRemoteBridge requires rootless iOS 16.1 or later; Control API
is restricted to iOS 16.1.1. Only iPhone SE 2 / iOS 16.1.1 was used for the
recorded source-functionality checks. This new four-package installation has not
been performed as part of the repository publication.

Respring once after installing the bridge tweaks. Installation does not respring
automatically, configure model providers, provision remote-control credentials or
enable the optional root OpenCode / native Siri services.

Upstream setup and source:

- [Node.js 26 iOS](https://github.com/Justintunsday/nodejs26-ios)
- [OpenCode iOS](https://github.com/Justintunsday/opencode-ios)
- [iOSRemoteBridge](https://github.com/Justintunsday/iOSRemoteBridge)
- [Control API](https://github.com/Justintunsday/ios-control-bridge)

Control API retains the package ID `ios-control-bridge` and command `iosctl` so
existing installations can upgrade. OpenCode's package author is `opencode`.
The complete skills, including references and agent metadata, are installed at:

- `/var/jb/usr/lib/opencode/skills/opencode-ios`
- `/var/jb/usr/lib/iosremotebridge/skills/ios-computer-use`
- `/var/jb/usr/lib/ios-control-bridge/skills/ios-control-bridge`

Control API also retains its compatible copy of `ios-computer-use`. Choose one
copy when configuring skill discovery. OpenCode v2.2.5 accepts skill directories
in its existing top-level `skills` array; see the package's `docs/IOS_BRIDGES.md`.
Installation saves these resources in the package payload and does not modify
personal skills, provider configuration or running services.

## Publishing updates

1. Update source pins in `sources.lock.json` when rebuilding a bridge. Run **Build
   Control API package** for the native helper package.
2. Review package identity, dependencies, payload and provenance. Upload approved
   `.deb` files to a public release of this repository.
3. Update `packages.json` with the exact asset URL, version and SHA-256. Keep
   OpenCode's exact Node dependency satisfied.
4. Push to `main`. **Publish APT repository** runs tests, validates every input,
   generates all three package indices, signs them and checks an isolated APT
   client before deploying Pages.

The signing private key is stored in the `APT_SIGNING_KEY` Actions secret and
never in Git. Public key fingerprint:

```text
95AE 26E9 9968 7FB1 450C DB98 6A1C 2817 E9A2 0979
```

`repo-key.gpg` and `repo-key.asc` are the public key. Package binaries live in
GitHub Releases and the deployed `pool/`, rather than Git history. The Remote
Bridge package's payload exactly matches its pinned build artifact; distribution
only revises that artifact's Debian package version. Build details and checksums are exposed in the source's
`provenance.json`.

Use the release API's `browser_download_url` when updating the catalog. GitHub
normalizes `~` in asset filenames and percent-encodes `+`; the Debian version
inside the package keeps its original value.

Run local checks with `python -m unittest discover -s tests -v`. A local build can
use `python scripts/repository.py build --packages /path/to/verified/debs`.

The MIT license covers this repository's automation and web presentation.
Distributed packages retain their upstream licensing and source ownership.

## Publication verification

The skill and branding update uses the merged `main` branches of all three source
projects. The package audit compares complete skill resources with the pinned Git
commits and checks all Control API native binaries against their build manifest.
The source integration workflow passes 193 Control API tests and 69 OpenCode
integration tests. New package assembly and signed APT checks are recorded
separately from earlier device acceptance; these new debs have not been installed
on the phone as part of publication.

The [2026-11-06 verification record](verification/2026-11-06.json) covers 15
repository tests, the 160-test upstream Control Bridge run, native builds, desktop
and mobile browser checks, both live signatures and all four live package hashes.
An isolated APT client on the actual iOS device successfully updated and found
all four package IDs without installing packages or changing its permanent sources.
The live signed metadata also passes the Sileo-specific release field checks;
confirmation after refreshing the source in Sileo is pending.

Control Bridge `0.12.0+repo.2` fixes a fresh-installation failure in `repo.1`:
the payload archive omitted directory entries, so dpkg could not create
`usr/lib/ios-control-bridge/README.md`. The archive writer now includes parent
directories, and publication rejects packages that omit them. The repaired package
installed on the test device; all 63 installed file hashes and permissions,
`iosctl capabilities`, and `siri.language.get` passed. No respring was requested.
