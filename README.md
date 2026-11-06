# Justintunsday iOS Repo

A GitHub Pages APT source for rootless iOS packages: Node.js 26, OpenCode,
iOSRemoteBridge and iOS Control Bridge.

Source URL: **https://justintunsday.github.io/ios-repo/**

Packages use the `iphoneos-arm64` architecture and `/var/jb` prefix. The tested
device is an iPhone SE (2nd generation) on iOS 16.1.1. Each package retains its
own compatibility and upstream license. The source repositories remain separate.

Package inputs are pinned in `sources.lock.json`. The Control Bridge build
workflow compiles its native helpers and optional tweaks from the pinned source.
Publication validates package identity, checksums and signed APT indices before
deploying the static repository to GitHub Pages. Device credentials and pairing
files are not distribution inputs.
