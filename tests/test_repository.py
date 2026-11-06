import copy
import gzip
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest
from urllib.parse import quote

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from deb import build, fields, inspect, members, revise_version, sha256
from repository import build_site, validate, verify


class RepositoryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.packages = self.root / "packages"
        self.packages.mkdir()
        self.config = json.loads((Path(__file__).resolve().parents[1] / "repo.json").read_text())
        self.control = {"Package": "example-bridge", "Version": "1.0+repo.1", "Architecture": "iphoneos-arm64", "Maintainer": "Example", "Description": "Example\n A package fixture."}
        self.body = build(self.control, {"var/jb/usr/bin/example": (b"example", 0o755)}, 1000000000)
        self.filename = "example-bridge_1.0+repo.1_iphoneos-arm64.deb"
        (self.packages / self.filename).write_bytes(self.body)
        self.item = {"package": "example-bridge", "version": "1.0+repo.1", "architecture": "iphoneos-arm64", "file": self.filename,
                     "url": "https://github.com/Justintunsday/ios-repo/releases/download/test/" + quote(self.filename),
                     "sha256": sha256(self.body), "title": "Example <bridge>", "description": "Fixture", "category": "Test"}

    def test_archive_roundtrip_and_version_revision_preserve_payload(self):
        self.assertEqual(inspect(self.body)["Version"], "1.0+repo.1")
        revised = revise_version(self.body, "1.0+repo.2", 1000000000)
        self.assertEqual(inspect(revised)["Version"], "1.0+repo.2")
        self.assertEqual(members(revised)["data.tar.gz"], members(self.body)["data.tar.gz"])

    def test_catalog_rejects_unpinned_or_unsafe_inputs(self):
        changes = [{"sha256": "bad"}, {"url": "http://example.invalid/file.deb"}, {"url": self.item["url"] + "?token=x"},
                   {"file": "../file.deb"}, {"architecture": "iphoneos-arm"}, {"package": "bad\nName"}]
        for change in changes:
            with self.subTest(change=change), self.assertRaises(ValueError):
                validate([{**self.item, **change}], self.config)

    def test_duplicate_ids_are_rejected(self):
        with self.assertRaises(ValueError):
            validate([self.item, self.item], self.config)

    def test_private_or_non_rootless_payload_is_rejected(self):
        for name in ("var/mobile/private", "var/jb/var/root/.ssh/key", "var/jb/server-password"):
            with self.subTest(name=name), self.assertRaises(ValueError):
                inspect(build(self.control, {name: (b"private", 0o600)}, 1000000000))

    def test_writable_payload_is_rejected(self):
        with self.assertRaises(ValueError):
            inspect(build(self.control, {"var/jb/usr/bin/example": (b"data", 0o777)}, 1000000000))

    def test_package_index_hashes_and_depictions_are_consistent(self):
        site = self.root / "site"
        build_site([self.item], self.config, self.packages, site)
        self.assertEqual(verify(site, [self.item], self.config), 1)
        self.assertEqual(gzip.decompress((site / "Packages.gz").read_bytes()), (site / "Packages").read_bytes())
        self.assertIn("Example &lt;bridge&gt;", (site / "index.html").read_text())
        self.assertTrue((site / "depictions/example-bridge.html").is_file())
        release = fields((site / "Release").read_bytes())
        self.assertEqual(release["Components"], "main")
        self.assertIn("iphoneos-arm64", release["Architectures"].split())

    def test_tampered_package_fails_before_publication(self):
        (self.packages / self.filename).write_bytes(self.body + b"tampered")
        with self.assertRaises(ValueError):
            build_site([self.item], self.config, self.packages, self.root / "site")

    def test_binary_identity_must_match_catalog(self):
        changed = copy.deepcopy(self.item)
        changed.update(package="another-bridge", file="another-bridge_1.0+repo.1_iphoneos-arm64.deb")
        changed["url"] = self.item["url"].rsplit("/", 1)[0] + "/" + quote(changed["file"])
        (self.packages / changed["file"]).write_bytes(self.body)
        with self.assertRaises(ValueError):
            build_site([changed], self.config, self.packages, self.root / "site")

    def test_modified_index_is_detected(self):
        site = self.root / "site"
        build_site([self.item], self.config, self.packages, site)
        (site / "Packages.gz").write_bytes(gzip.compress(b"different"))
        with self.assertRaises(ValueError):
            verify(site, [self.item], self.config)

    def test_release_cannot_omit_index_checksums(self):
        site = self.root / "site"
        build_site([self.item], self.config, self.packages, site)
        release = site / "Release"
        text = release.read_text()
        start = text.index("SHA256:")
        end = text.index("SHA512:")
        release.write_text(text[:start] + "SHA256:\n" + text[end:])
        with self.assertRaises(ValueError):
            verify(site, [self.item], self.config)

    def test_github_asset_normalization_does_not_change_debian_version(self):
        item = {**self.item, "version": "1.0~dev+repo.1", "file": "example-bridge_1.0.dev+repo.1_iphoneos-arm64.deb"}
        item["url"] = self.item["url"].rsplit("/", 1)[0] + "/" + quote(item["file"])
        validate([item], self.config)
        with self.assertRaises(ValueError):
            validate([{**self.item, "url": self.item["url"].replace("%2B", "+")}], self.config)

    def test_sileo_rejects_release_without_components_even_for_flat_source(self):
        site = self.root / "site"
        build_site([self.item], self.config, self.packages, site)
        release = site / "Release"
        release.write_text(release.read_text().replace("Components: main\n", ""))
        with self.assertRaisesRegex(ValueError, "Sileo-compatible"):
            verify(site, [self.item], self.config)

    def test_sileo_release_must_advertise_the_package_architecture(self):
        site = self.root / "site"
        build_site([self.item], self.config, self.packages, site)
        release = site / "Release"
        release.write_text(release.read_text().replace("Architectures: iphoneos-arm64", "Architectures: iphoneos-arm"))
        with self.assertRaisesRegex(ValueError, "Sileo-compatible"):
            verify(site, [self.item], self.config)


if __name__ == "__main__":
    unittest.main()
