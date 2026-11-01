"""Retention must preserve recent, corrupt, unrelated and minimum recovery copies."""

import hashlib
import json
import subprocess
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

from tools import scheduled_backup as job


class ScheduledBackupTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.directory = Path(self.temporary.name).resolve()

    def copy(self, age, index, valid=True):
        date = datetime.now(timezone.utc) - timedelta(days=age)
        manifest = self.directory / f"agenda-{date:%Y%m%dT%H%M%SZ}-{index:08x}.json"
        dump = manifest.with_suffix(".dump")
        dump.write_bytes(b"private test fixture")
        manifest.write_text(
            json.dumps(
                {
                    "created_utc": date.isoformat(),
                    "bytes": dump.stat().st_size,
                    "sha256": hashlib.sha256(dump.read_bytes()).hexdigest() if valid else "invalid",
                    "restore_checked": True,
                    "evidence_integrity_checked": True,
                }
            )
        )
        return manifest, dump

    def test_retention_preserves_minimum_recent_corrupt_and_unrelated(self):
        recent = self.copy(1, 1)
        old_kept = self.copy(40, 2)
        old_removed = self.copy(50, 3)
        corrupt = self.copy(60, 4, valid=False)
        unrelated = self.directory / "manual.dump"
        unrelated.write_bytes(b"manual")
        self.assertEqual(job.prune(self.directory, days=30, keep=2), 1)
        self.assertTrue(all(p.exists() for p in recent + old_kept + corrupt))
        self.assertTrue(unrelated.exists())
        self.assertFalse(any(p.exists() for p in old_removed))

    def test_symlink_is_not_a_retention_candidate(self):
        manifest, dump = self.copy(50, 1)
        original = self.directory / "original"
        dump.rename(original)
        dump.symlink_to(original)
        self.assertEqual(job.verified(self.directory), [])
        self.assertTrue(manifest.exists())
        self.assertTrue(original.exists())

    def test_failure_never_prunes_and_writes_private_status(self):
        self.copy(50, 1)
        with (
            patch("sys.argv", ["backup", "--directory", str(self.directory)]),
            patch.object(job.subprocess, "run", return_value=subprocess.CompletedProcess([], 1)),
            patch.object(job, "prune") as prune,
        ):
            self.assertEqual(job.main(), 1)
        prune.assert_not_called()
        status = self.directory / "last-run.json"
        self.assertFalse(json.loads(status.read_text())["success"])
        self.assertEqual(status.stat().st_mode & 0o777, 0o600)

    def test_concurrent_run_does_not_start_another_backup(self):
        with (
            patch("sys.argv", ["backup", "--directory", str(self.directory)]),
            patch.object(job.fcntl, "flock", side_effect=BlockingIOError),
            patch.object(job.subprocess, "run") as run,
        ):
            self.assertEqual(job.main(), 0)
        run.assert_not_called()
        self.assertFalse((self.directory / "last-run.json").exists())

    def test_corrupt_new_copy_blocks_retention_despite_zero_exit(self):
        manifest, dump = self.copy(0, 1, valid=False)
        output = json.dumps(
            {"manifest": str(manifest), "backup": str(dump), "restore_checked": True}
        )
        with (
            patch("sys.argv", ["backup", "--directory", str(self.directory)]),
            patch.object(
                job.subprocess, "run", return_value=subprocess.CompletedProcess([], 0, output)
            ),
            patch.object(job, "prune") as prune,
        ):
            self.assertEqual(job.main(), 1)
        prune.assert_not_called()

    def test_success_requires_verified_new_manifest_before_retention(self):
        manifest, dump = self.copy(0, 1)
        output = json.dumps(
            {"manifest": str(manifest), "backup": str(dump), "restore_checked": True}
        )
        with (
            patch("sys.argv", ["backup", "--directory", str(self.directory)]),
            patch.object(
                job.subprocess, "run", return_value=subprocess.CompletedProcess([], 0, output)
            ),
            patch.object(job, "prune", return_value=0) as prune,
        ):
            self.assertEqual(job.main(), 0)
        prune.assert_called_once()
        self.assertTrue(json.loads((self.directory / "last-run.json").read_text())["success"])


if __name__ == "__main__":
    unittest.main()
