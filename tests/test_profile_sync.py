import contextlib
import importlib.util
import io
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

import test_packaging


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "scripts"))
SPEC = importlib.util.spec_from_file_location(
    "profile_sync_under_test",
    PROJECT_ROOT / "scripts/sync_to_qgis_profiles.py",
)
SYNC = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = SYNC
SPEC.loader.exec_module(SYNC)
PACKAGER = test_packaging.PACKAGER


class ProfileSyncTests(unittest.TestCase):
    write = test_packaging.PackagingTests.write
    tearDown = test_packaging.PackagingTests.tearDown

    def setUp(self):
        test_packaging.PackagingTests.setUp(self)
        self.roots = [self.base / generation / "profiles"
                      for generation in ("QGIS3", "QGIS4")]
        self.profiles = [root / "default" for root in self.roots]
        self.targets = []
        for profile in self.profiles:
            target = profile / "python/plugins/favourite_layers"
            target.mkdir(parents=True)
            (target / "old.py").write_bytes(b"previous plugin copy")
            (profile / "preferences.ini").write_bytes(b"keep favourites")
            self.targets.append(target)
        (self.roots[0] / "clean").mkdir()
        PACKAGER.package_plugin(self.root, self.output)

    def sync(self, **kwargs):
        return SYNC.sync_profiles(self.root, self.output, self.roots, **kwargs)

    def assert_old_copies(self):
        for target in self.targets:
            self.assertEqual(
                (target / "old.py").read_bytes(), b"previous plugin copy"
            )
            self.assertEqual([p.name for p in target.iterdir()], ["old.py"])
            self.assertEqual(
                list(target.parent.glob(SYNC.STAGE_PREFIX + "*")), []
            )

    def test_dry_run_lists_only_installed_profiles_without_writes(self):
        before = sorted(str(p.relative_to(self.base))
                        for p in self.base.rglob("*"))
        results = self.sync(dry_run=True)
        self.assertEqual(len(results), 2)
        self.assertEqual({r["target"] for r in results},
                         {str(path) for path in self.targets})
        self.assertEqual(
            before, sorted(str(p.relative_to(self.base))
                           for p in self.base.rglob("*"))
        )
        self.assert_old_copies()

    def test_updates_keep_backups_settings_and_exact_runtime_files(self):
        results = self.sync()
        manifest = PACKAGER.plugin_files(self.root)
        for result, profile, target in zip(
            results, self.profiles, self.targets
        ):
            backup = Path(result["backup"])
            self.assertEqual((backup / "old.py").read_bytes(),
                             b"previous plugin copy")
            self.assertEqual((profile / "preferences.ini").read_bytes(),
                             b"keep favourites")
            self.assertFalse((target / "old.py").exists())
            for relative in manifest:
                self.assertEqual((target / relative).read_bytes(),
                                 (self.root / relative).read_bytes())
            self.assertEqual(
                list(target.parent.glob(SYNC.STAGE_PREFIX + "*")), []
            )

    def test_explicit_profile_allows_first_install(self):
        results = self.sync(profile_names=("clean",))
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["action"], "install")
        self.assertIsNone(results[0]["backup"])
        installed_metadata = Path(results[0]["target"]) / "metadata.txt"
        self.assertTrue(installed_metadata.is_file())
        self.assert_old_copies()

    def test_stale_package_is_rejected_before_profile_writes(self):
        (self.root / "storage.py").write_bytes(b"newer source")
        with self.assertRaisesRegex(ValueError, "stale"):
            self.sync()
        self.assert_old_copies()

    def test_second_profile_failure_rolls_back_the_entire_batch(self):
        original = SYNC._verify_files

        def fail_second(directory, payload):
            if directory == self.targets[1]:
                raise OSError("synthetic verification failure")
            return original(directory, payload)

        with patch.object(SYNC, "_verify_files", side_effect=fail_second):
            with self.assertRaises(OSError):
                self.sync()
        self.assert_old_copies()

    def test_keyboard_interrupt_rolls_back_the_entire_batch(self):
        original = SYNC._verify_files

        def interrupt_second(directory, payload):
            if directory == self.targets[1]:
                raise KeyboardInterrupt
            return original(directory, payload)

        with patch.object(SYNC, "_verify_files", side_effect=interrupt_second):
            with self.assertRaises(KeyboardInterrupt):
                self.sync()
        self.assert_old_copies()

    def test_failure_before_publish_restores_the_displaced_copy(self):
        original = Path.rename

        def fail_stage_replace(path, target):
            if path.name.startswith(SYNC.STAGE_PREFIX):
                raise OSError("synthetic publish failure")
            return original(path, target)

        with patch.object(Path, "rename", new=fail_stage_replace):
            with self.assertRaises(OSError):
                self.sync()
        self.assert_old_copies()

    def test_unsafe_and_missing_profile_names_are_rejected(self):
        for name in ("../default", "..", "a\\b", "C:other", "missing"):
            with self.subTest(name=name):
                with self.assertRaises(ValueError):
                    self.sync(profile_names=(name,))
        self.assert_old_copies()

    def test_linked_profile_target_is_rejected(self):
        original = SYNC._is_link
        with patch.object(
            SYNC, "_is_link",
            side_effect=lambda path: path == self.targets[0] or original(path),
        ):
            with self.assertRaisesRegex(ValueError, "Linked"):
                self.sync()
        self.assert_old_copies()

    def test_backup_inside_plugin_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "Backups must be outside"):
            self.sync(backup_root=self.targets[0] / "backup")
        self.assert_old_copies()

    def test_directory_move_retries_temporary_windows_lock(self):
        source = self.base / "locked"
        destination = self.base / "moved"
        source.mkdir()
        original = Path.rename
        attempts = []

        def locked_once(path, target):
            attempts.append(path)
            if len(attempts) == 1:
                raise PermissionError("synthetic temporary lock")
            return original(path, target)

        with patch.object(Path, "rename", new=locked_once):
            with patch.object(SYNC.time, "sleep"):
                SYNC._move_directory(source, destination)
        self.assertTrue(destination.is_dir())
        self.assertEqual(len(attempts), 2)

    def test_cleanup_refuses_unowned_directory(self):
        unrelated = self.targets[0].parent / "unrelated"
        unrelated.mkdir()
        (unrelated / "keep.txt").write_bytes(b"keep")
        update = SYNC.ProfileUpdate(self.profiles[0], self.targets[0], True)
        update.stage = unrelated
        with self.assertRaisesRegex(ValueError, "unowned"):
            SYNC._discard_stage(update)
        self.assertEqual((unrelated / "keep.txt").read_bytes(), b"keep")

    def test_cli_dry_run_uses_explicit_roots_without_writes(self):
        arguments = ["--dry-run", "--archive", str(self.output),
                     "--profiles-root", str(self.roots[0])]
        output = io.StringIO()
        with patch.object(SYNC, "project_root", return_value=self.root):
            with contextlib.redirect_stdout(output):
                self.assertEqual(SYNC.main(arguments), 0)
        self.assertIn("DRY RUN: update", output.getvalue())
        self.assert_old_copies()


if __name__ == "__main__":
    unittest.main()
