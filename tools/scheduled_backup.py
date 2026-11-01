#!/usr/bin/env python3
"""Run verified Compose backups under a lock, then retain recent verified copies."""

import argparse
import fcntl
import hashlib
import json
import os
import re
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
NAME = re.compile(r"agenda-\d{8}T\d{6}Z-[0-9a-f]{8}\.json")


def verified(directory):
    copies = []
    for manifest in directory.iterdir():
        if not NAME.fullmatch(manifest.name) or manifest.is_symlink():
            continue
        dump = manifest.with_suffix(".dump")
        try:
            data = json.loads(manifest.read_text())
            created = datetime.fromisoformat(data["created_utc"])
            if (
                created.tzinfo is None
                or not data.get("restore_checked")
                or not data.get("evidence_integrity_checked")
                or dump.is_symlink()
                or not dump.is_file()
                or dump.stat().st_size != data["bytes"]
            ):
                continue
            with dump.open("rb") as source:
                digest = hashlib.file_digest(source, "sha256").hexdigest()
            if digest == data["sha256"]:
                copies.append((created, manifest, dump))
        except (OSError, ValueError, KeyError, TypeError):
            continue
    return sorted(copies, reverse=True)


def prune(directory, days, keep):
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    removed = 0
    for created, manifest, dump in verified(directory)[keep:]:
        if created < cutoff:
            dump.unlink()
            manifest.unlink()
            removed += 1
    return removed


def write_status(directory, data):
    temporary = directory / ".last-run.tmp"
    with os.fdopen(os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600), "w") as out:
        json.dump(data, out, indent=2)
    temporary.replace(directory / "last-run.json")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--directory", type=Path, default=ROOT / ".backups")
    parser.add_argument("--retention-days", type=int, default=30)
    parser.add_argument("--keep-at-least", type=int, default=7)
    parser.add_argument("--timeout-seconds", type=int, default=3600)
    args = parser.parse_args()
    if min(args.retention_days, args.keep_at_least, args.timeout_seconds) < 1:
        parser.error("Retenção, mínimo de cópias e timeout devem ser positivos.")
    directory = args.directory.resolve()
    directory.mkdir(parents=True, exist_ok=True, mode=0o700)
    directory.chmod(0o700)
    with os.fdopen(
        os.open(directory / ".schedule.lock", os.O_RDWR | os.O_CREAT, 0o600), "w"
    ) as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            print("Backup já em execução; tentativa ignorada.")
            return 0
        status = {"started_utc": datetime.now(timezone.utc).isoformat(), "success": False}
        try:
            result = subprocess.run(
                [
                    sys.executable,
                    str(ROOT / "tools/backup.py"),
                    "--restore-check",
                    "--directory",
                    str(directory),
                ],
                cwd=ROOT,
                capture_output=True,
                timeout=args.timeout_seconds,
                check=False,
            )
            if result.returncode:
                raise RuntimeError("Backup/restauração falhou; retenção não executada.")
            summary = json.loads(result.stdout)
            manifest = Path(summary["manifest"])
            if not summary.get("restore_checked") or not any(
                entry[1] == manifest for entry in verified(directory)
            ):
                raise RuntimeError(
                    "Cópia recém-gerada não passou na verificação; retenção suspensa."
                )
            status.update(
                success=True,
                backup=Path(summary["backup"]).name,
                removed_copies=prune(directory, args.retention_days, args.keep_at_least),
            )
        except (OSError, ValueError, KeyError, RuntimeError, subprocess.TimeoutExpired):
            # Do not persist raw subprocess output: dumps/logs may contain sensitive data.
            status["error"] = (
                "Falha no backup verificado; confira Docker e execute o ensaio manual."
            )
        status["finished_utc"] = datetime.now(timezone.utc).isoformat()
        write_status(directory, status)
        print(json.dumps(status))
        return 0 if status["success"] else 1


if __name__ == "__main__":
    sys.exit(main())
