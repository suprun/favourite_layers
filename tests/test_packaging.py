import importlib.util
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
import zipfile


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "test_packager", PROJECT_ROOT / "scripts" / "package_plugin.py"
)
PACKAGER = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(PACKAGER)


class PackagingTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(
            prefix="favourite-layers-packaging-test-"
        )
        self.base = Path(self.temporary.name).resolve()
        self.root = self.base / "favourite_layers"
        self.root.mkdir()
        for relative in PACKAGER.PACKAGE_FILES:
            path = self.root / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(b"fixture runtime resource\n")
        metadata = (
            "[general]\nname=Fixture\nqgisMinimumVersion=3.28\n"
            "description=Fixture\nabout=Fixture\nversion=1.0.0\n"
            "author=Fixture\nemail=test@example.invalid\n"
            "repository=https://example.invalid/source\n"
            "description[en]=Unicode \u0428\u0430\u0440\n"
            "about[en]=Unicode \u65e5\u672c\u8a9e\n"
        )
        (self.root / "metadata.txt").write_text(metadata, encoding="utf-8")
        self.write("icons/runtime.svg", b"<svg/>")
        self.write("i18n/favourite_layers_en.qm", b"compiled fixture")
        self.write("docs/example.PNG", b"image fixture")
        self.output = self.root / "repo" / "favourite_layers.zip"

    def tearDown(self):
        if self.base.parent != Path(tempfile.gettempdir()).resolve():
            raise RuntimeError("Unexpected test cleanup directory")
        self.temporary.cleanup()

    def write(self, name, data):
        path = self.root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        return path

    def test_allowlist_excludes_secrets_and_development_files(self):
        excluded = (
            ".env", ".env.production", ".env.example", ".gitignore",
            "plugins.xml", "unexpected.py", "i18n/source.ts",
            "i18n/source.pro", "icons/.hidden.svg",
            "scripts/private.py", "repo/previous.zip",
            "resources/source.png", "node_modules/private.js",
            "settings/__pycache__/cache.pyc",
        )
        for name in excluded:
            self.write(name, b"SYNTHETIC_TEST_FIXTURE")
        original_write = zipfile.ZipFile.write

        def guarded_write(archive, filename, *args, **kwargs):
            relative = Path(filename).relative_to(self.root).as_posix()
            self.assertNotIn(relative, excluded)
            return original_write(archive, filename, *args, **kwargs)

        with patch.object(zipfile.ZipFile, "write", new=guarded_write):
            manifest = PACKAGER.package_plugin(self.root, self.output)
        for name in excluded:
            self.assertNotIn(Path(name), manifest)
        with zipfile.ZipFile(self.output) as archive:
            self.assertEqual(len(archive.namelist()), len(manifest) + 1)
            self.assertIsNone(archive.testzip())

    def test_metadata_round_trip_preserves_unicode(self):
        PACKAGER.package_plugin(self.root, self.output)
        with zipfile.ZipFile(self.output) as archive:
            archived = archive.read("favourite_layers/metadata.txt")
        self.assertEqual(
            archived, (self.root / "metadata.txt").read_bytes()
        )
        self.assertIn("\u0428\u0430\u0440".encode("utf-8"), archived)
        self.assertIn("\u65e5\u672c\u8a9e".encode("utf-8"), archived)

    def test_write_failure_preserves_existing_archive_and_unrelated_temp(self):
        self.write("repo/favourite_layers.zip", b"previous artifact")
        unrelated = self.write(
            "repo/favourite_layers.zip.tmp", b"unrelated temporary"
        )
        with patch.object(zipfile.ZipFile, "write", side_effect=OSError):
            with self.assertRaises(OSError):
                PACKAGER.package_plugin(self.root, self.output)
        self.assertEqual(self.output.read_bytes(), b"previous artifact")
        self.assertEqual(unrelated.read_bytes(), b"unrelated temporary")
        self.assertEqual(
            list(self.output.parent.glob(".favourite_layers.zip.*.tmp")), []
        )

    def test_validation_failure_preserves_existing_archive(self):
        self.write("repo/favourite_layers.zip", b"previous artifact")
        with patch.object(
            PACKAGER, "validate_archive", side_effect=ValueError
        ):
            with self.assertRaises(ValueError):
                PACKAGER.package_plugin(self.root, self.output)
        self.assertEqual(self.output.read_bytes(), b"previous artifact")
        self.assertEqual(
            list(self.output.parent.glob(".favourite_layers.zip.*.tmp")), []
        )

    def test_failed_replacement_preserves_existing_archive(self):
        self.write("repo/favourite_layers.zip", b"previous artifact")
        with patch.object(Path, "replace", side_effect=PermissionError):
            with self.assertRaises(PermissionError):
                PACKAGER.package_plugin(self.root, self.output)
        self.assertEqual(self.output.read_bytes(), b"previous artifact")
        self.assertEqual(
            list(self.output.parent.glob(".favourite_layers.zip.*.tmp")), []
        )

    def test_missing_runtime_file_prevents_replacement(self):
        self.write("repo/favourite_layers.zip", b"previous artifact")
        (self.root / "storage.py").unlink()
        with self.assertRaises(ValueError):
            PACKAGER.package_plugin(self.root, self.output)
        self.assertEqual(self.output.read_bytes(), b"previous artifact")

    def test_damaged_metadata_prevents_replacement(self):
        self.write("repo/favourite_layers.zip", b"previous artifact")
        metadata_path = self.root / "metadata.txt"
        data = metadata_path.read_text(encoding="utf-8")
        data = data.replace("Unicode \u0428\u0430\u0440", "????")
        metadata_path.write_text(data, encoding="utf-8")
        with self.assertRaises(ValueError):
            PACKAGER.package_plugin(self.root, self.output)
        self.assertEqual(self.output.read_bytes(), b"previous artifact")

    def test_missing_locale_prevents_replacement(self):
        self.write("i18n/favourite_layers_uk.qm", b"compiled fixture")
        with self.assertRaises(ValueError):
            PACKAGER.package_plugin(self.root, self.output)
        self.assertFalse(self.output.exists())

    def test_linked_resource_and_directory_are_not_packaged(self):
        original = PACKAGER._is_link
        blocked = self.root / "icons"
        with patch.object(
            PACKAGER, "_is_link",
            side_effect=lambda path: path == blocked or original(path),
        ):
            manifest = PACKAGER.package_plugin(self.root, self.output)
        self.assertFalse(any(path.parts[0] == "icons" for path in manifest))
        blocked = self.root / "storage.py"
        with patch.object(
            PACKAGER, "_is_link",
            side_effect=lambda path: path == blocked or original(path),
        ):
            with self.assertRaises(ValueError):
                PACKAGER.package_plugin(self.root, self.output)

    def test_unexpected_member_is_rejected_before_contents_are_read(self):
        manifest = PACKAGER.plugin_files(self.root)
        candidate = self.base / "unexpected.zip"
        with zipfile.ZipFile(candidate, "w") as archive:
            archive.writestr("favourite_layers/.env", b"synthetic fixture")
        with patch.object(
            zipfile.ZipFile, "testzip", side_effect=AssertionError
        ), patch.object(
            zipfile.ZipFile, "read", side_effect=AssertionError
        ):
            with self.assertRaises(ValueError):
                PACKAGER.validate_archive(candidate, self.root, manifest)

    def test_duplicate_and_unsafe_members_are_rejected(self):
        manifest = PACKAGER.plugin_files(self.root)
        for index, names in enumerate((
            ["favourite_layers/icon.png", "favourite_layers/ICON.PNG"],
            ["favourite_layers/../outside"],
            ["/absolute"], ["C:/outside"],
        )):
            candidate = self.base / f"invalid-{index}.zip"
            with zipfile.ZipFile(candidate, "w") as archive:
                for name in names:
                    archive.writestr(name, b"synthetic fixture")
            with self.assertRaises(ValueError):
                PACKAGER.validate_archive(candidate, self.root, manifest)

    def test_crc_failure_preserves_existing_archive(self):
        self.write("repo/favourite_layers.zip", b"previous artifact")
        with patch.object(
            zipfile.ZipFile, "testzip", return_value="damaged member"
        ):
            with self.assertRaises(ValueError):
                PACKAGER.package_plugin(self.root, self.output)
        self.assertEqual(self.output.read_bytes(), b"previous artifact")
        self.assertEqual(
            list(self.output.parent.glob(".favourite_layers.zip.*.tmp")), []
        )

    def test_changed_archived_metadata_is_rejected(self):
        manifest = PACKAGER.plugin_files(self.root)
        candidate = self.base / "modified-metadata.zip"
        with zipfile.ZipFile(candidate, "w") as archive:
            archive.writestr("favourite_layers/", b"")
            for path in manifest:
                data = (self.root / path).read_bytes()
                if path == Path("metadata.txt"):
                    data = data.replace(b"version=1.0.0", b"version=9.9.9")
                archive.writestr(
                    f"favourite_layers/{path.as_posix()}", data
                )
        with self.assertRaisesRegex(ValueError, "metadata differs"):
            PACKAGER.validate_archive(candidate, self.root, manifest)

    def test_both_cli_commands_have_identical_contents(self):
        for relative in ("scripts/package_plugin.py", "repo/restore.py"):
            target = self.root / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(PROJECT_ROOT / relative, target)
        commands = (
            (self.root / "repo" / "restore.py", self.output),
            (self.root / "scripts" / "package_plugin.py",
             self.base / "alternative.zip"),
        )
        snapshots = []
        for script, output in commands:
            command = [sys.executable, "-B", str(script)]
            if script.name != "restore.py":
                command.extend(["--output", str(output)])
            result = subprocess.run(
                command, cwd=self.base, capture_output=True, text=True,
                encoding="utf-8", timeout=30, check=True,
            )
            self.assertIn("validated runtime files", result.stdout)
            with zipfile.ZipFile(output) as archive:
                snapshots.append({
                    name: archive.read(name) for name in archive.namelist()
                })
        self.assertEqual(snapshots[0], snapshots[1])


if __name__ == "__main__":
    unittest.main()
