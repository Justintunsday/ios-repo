# iOS Repo

- This is a rootless iOS APT repository hosted by GitHub Pages.
- Publish only pinned, hashed package inputs. Preserve package IDs, architecture and dependency contracts.
- Never commit signing private keys, device configuration, provider credentials, pairing files or personal device data.
- Build the site only after package identity, checksums and index validation pass. Sign Release and InRelease; verify them before deployment.
- Distinguish package assembly checks from device verification. Do not install packages or restart a connected device merely to test this repository.
- Run `python -m unittest discover -s tests -v` and the signed APT index validation in CI.
