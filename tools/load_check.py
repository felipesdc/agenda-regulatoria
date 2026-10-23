#!/usr/bin/env python3
"""Creates/migrates/runs/drops only a unique isolated database."""

import json
import re
import subprocess
import uuid
from backup import ROOT, DOCKER, command


def main():
    target = "phase8_load_" + uuid.uuid4().hex
    if not re.fullmatch(r"phase8_load_[0-9a-f]{32}", target):
        raise RuntimeError("Unsafe name")
    created = False
    try:
        r = command('exec createdb -U "$POSTGRES_USER" "$1"', target, stdout=subprocess.PIPE)
        if r.returncode:
            raise RuntimeError("Cannot create isolated database")
        created = True
        # Fresh, unexposed container; worker/Beat keep pointing only to the real app DB.
        r = subprocess.run(
            [
                DOCKER,
                "compose",
                "run",
                "--rm",
                "-T",
                "--no-deps",
                "-e",
                "POSTGRES_DB=" + target,
                "-e",
                "DJANGO_DEBUG=true",
                "backend",
                "sh",
                "-c",
                "python manage.py migrate --noinput >/tmp/phase8-migrate.log && python tools/load_probe.py",
            ],
            cwd=ROOT,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        lines = r.stdout.decode().splitlines()
        result = next((json.loads(line) for line in reversed(lines) if line.startswith("{")), None)
        if result:
            print(json.dumps(result))
        if r.returncode:
            raise RuntimeError("Isolated load check failed; no source data changed")
    finally:
        if created:
            r = command('exec dropdb -U "$POSTGRES_USER" "$1"', target, stdout=subprocess.PIPE)
            if r.returncode:
                raise RuntimeError("Drop only disposable database " + target)


if __name__ == "__main__":
    main()
