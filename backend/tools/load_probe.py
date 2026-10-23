"""Destructive fixtures only inside a fresh phase8_load_* database, never the app DB."""

import os
import sys
import json
import time
import statistics
import subprocess
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import timedelta
from pathlib import Path
from urllib.request import Request, urlopen

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
import django  # noqa: E402

django.setup()
from django.conf import settings  # noqa: E402
from django.db import connection  # noqa: E402
from django.utils import timezone  # noqa: E402
from django.contrib.sessions.backends.db import SessionStore  # noqa: E402
from apps.accounts.models import User, Membership  # noqa: E402
from apps.organizations.models import OrganizationalUnit  # noqa: E402
from apps.commitments.recurrence_engine import scheduled_dates  # noqa: E402
from unittest.mock import patch  # noqa: E402
from apps.commitments.models import (  # noqa: E402
    CommitmentDefinition,
    CommitmentOccurrence,
    CommitmentAssignment,
    CommitmentCategory,
    RegulatoryEntity,
    RecurrenceVersion,
    WorkflowTransition,
)


def main():
    name = settings.DATABASES["default"]["NAME"]
    if (
        not name.startswith("phase8_load_")
        or connection.vendor != "postgresql"
        or not settings.DEBUG
    ):
        raise RuntimeError(
            "Load probe requires a disposable PostgreSQL phase8_load_* database and DEBUG=true."
        )
    if User.objects.exists() or CommitmentOccurrence.objects.exists():
        raise RuntimeError("Load probe refuses a populated database.")
    start = time.monotonic()
    today = timezone.localdate()
    users = User.objects.bulk_create(
        [User(username=f"load-{i}", password="!", is_active=True) for i in range(1000)]
    )
    unit = OrganizationalUnit.objects.create(code="LOAD-FICTITIOUS", name="Carga fictícia isolada")
    Membership.objects.bulk_create(
        [
            Membership(user=u, unit=unit, role="requester" if i < 100 else "executor")
            for i, u in enumerate(users)
        ]
    )
    entity = RegulatoryEntity.objects.create(name="Carga fictícia")
    category = CommitmentCategory.objects.create(name="Carga fictícia")
    definitions = CommitmentDefinition.objects.bulk_create(
        [
            CommitmentDefinition(
                identifier=f"LOAD-{i:06d}",
                title=f"Série fictícia {i}",
                description="Dados exclusivamente para ensaio isolado.",
                entity=entity,
                category=category,
                unit=unit,
                requester=users[0],
            )
            for i in range(10000)
        ],
        batch_size=1000,
    )
    rule = {
        "frequency": "monthly",
        "calendar": "institution",
        "start": str(today - timedelta(days=180)),
        "end": str(today + timedelta(days=180)),
        "count": 10,
        "month_mode": "day",
        "month_day": (today - timedelta(days=180)).day,
        "ordinal": 1,
        "weekday": 0,
        "interval": 1,
        "interval_unit": "days",
        "adjustment": "none",
        "exceptions": [],
    }
    dates = list(scheduled_dates(rule, today + timedelta(days=180), []))
    if len(dates) != 10:
        raise RuntimeError("Fixture rule did not yield ten dates")
    versions = RecurrenceVersion.objects.bulk_create(
        [
            RecurrenceVersion(
                definition=d,
                revision=1,
                effective_from=rule["start"],
                rule=rule,
                template={
                    "title": d.title,
                    "description": d.description,
                    "legal_basis": "",
                    "priority": "normal",
                    "reference_offset": 0,
                    "assignees": [str(users[100 + i % 900].pk)],
                    "form_version": None,
                    "custom_values": {},
                },
                holidays=[],
                actor=users[0],
                reason="Fixture isolada; sem notificações",
            )
            for i, d in enumerate(definitions)
        ],
        batch_size=1000,
    )
    occurrences = []
    for i, d in enumerate(definitions):
        for n, (nominal, due) in enumerate(dates, 1):
            status = [
                "pending",
                "in_progress",
                "awaiting_validation",
                "completed",
                "rejected",
                "cancelled",
            ][n % 6]
            occurrences.append(
                CommitmentOccurrence(
                    definition=d,
                    recurrence_version=versions[i],
                    periodicity="monthly",
                    number=n,
                    scheduled_date=nominal,
                    identifier=f"{d.identifier}/{n:04d}",
                    title=d.title,
                    description=d.description,
                    reference_date=due,
                    due_date=due,
                    status=status,
                    completed_at=timezone.now() if status == "completed" else None,
                )
            )
    CommitmentOccurrence.objects.bulk_create(occurrences, batch_size=2000)
    CommitmentAssignment.objects.bulk_create(
        [
            CommitmentAssignment(occurrence=o, user=users[100 + (i // 10) % 900])
            for i, o in enumerate(occurrences)
        ],
        batch_size=2000,
    )
    completed = [(i, o) for i, o in enumerate(occurrences) if o.status == "completed"]
    now = timezone.now()
    with patch("django.utils.timezone.now", return_value=now - timedelta(hours=24)):
        WorkflowTransition.objects.bulk_create(
            [
                WorkflowTransition(
                    occurrence=o,
                    actor=users[100 + (i // 10) % 900],
                    previous_status="in_progress",
                    new_status="awaiting_validation",
                )
                for i, o in completed
            ],
            batch_size=2000,
        )
    with patch("django.utils.timezone.now", return_value=now):
        WorkflowTransition.objects.bulk_create(
            [
                WorkflowTransition(
                    occurrence=o,
                    actor=users[0],
                    previous_status="awaiting_validation",
                    new_status="completed",
                )
                for _, o in completed
            ],
            batch_size=2000,
        )
    # Final approval timestamps are aligned after inserting the immutable history.
    CommitmentOccurrence.objects.filter(status="completed").update(completed_at=now)
    with connection.cursor() as cursor:
        cursor.execute(
            "UPDATE commitments_commitmentoccurrence SET created_at=COALESCE(completed_at,now())-interval '48 hours'"
        )
        cursor.execute("ANALYZE")
    cookies = []
    for u in users[:100]:
        session = SessionStore()
        session["_auth_user_id"] = str(u.pk)
        session["_auth_user_backend"] = "django.contrib.auth.backends.ModelBackend"
        session["_auth_user_hash"] = u.get_session_auth_hash()
        session.save()
        cookies.append(session.session_key)
    fixture_seconds = time.monotonic() - start
    connection.close()
    server = subprocess.Popen(
        [
            "gunicorn",
            "config.wsgi:application",
            "--bind",
            "127.0.0.1:8765",
            "--workers",
            "3",
            "--threads",
            "4",
            "--worker-class",
            "gthread",
            "--timeout",
            "120",
            "--access-logfile",
            "/dev/null",
            "--error-logfile",
            "/tmp/phase8-load-server.log",
        ],
        cwd=Path(__file__).resolve().parents[1],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    try:
        for _ in range(100):
            try:
                with urlopen("http://127.0.0.1:8765/health/", timeout=2):
                    break
            except Exception:
                time.sleep(0.2)
        else:
            raise RuntimeError("Isolated HTTP server did not start.")
        period = f"date_start={today - timedelta(days=180)}&date_end={today + timedelta(days=180)}"
        paths = [
            "/api/v1/dashboard/",
            "/api/v1/reports/occurrences/?" + period,
            "/api/v1/reports/summary/?" + period,
        ]

        def request(i):
            began = time.monotonic()
            path = paths[i % len(paths)]
            try:
                req = Request(
                    "http://127.0.0.1:8765" + path,
                    headers={"Cookie": "sessionid=" + cookies[i % 100]},
                )
                with urlopen(req, timeout=120) as response:
                    data = json.loads(response.read())
                    status = response.status
                if i % 3 == 1 and data["count"] != 100000:
                    status = 599
                if i % 3 != 1 and data["metrics"]["total"] != 100000:
                    status = 599
            except Exception:
                status = 599
            return {
                "path": path.split("?")[0],
                "seconds": time.monotonic() - began,
                "status": status,
            }

        started = time.monotonic()
        with ThreadPoolExecutor(max_workers=100) as pool:
            results = [
                f.result() for f in as_completed([pool.submit(request, i) for i in range(300)])
            ]
        elapsed = time.monotonic() - started
        grouped = {}
        for path in paths:
            key = path.split("?")[0]
            rows = [r for r in results if r["path"] == key]
            values = sorted(r["seconds"] for r in rows)
            grouped[key] = {
                "requests": len(rows),
                "errors": sum(r["status"] != 200 for r in rows),
                "p50_seconds": round(statistics.median(values), 3),
                "p95_seconds": round(values[int(len(values) * 0.95) - 1], 3),
                "max_seconds": round(max(values), 3),
            }
        print(
            json.dumps(
                {
                    "users": 1000,
                    "definitions": 10000,
                    "occurrences": 100000,
                    "workflow_transitions": 40000,
                    "concurrent_clients": 100,
                    "requests": 300,
                    "server": "gunicorn 3 workers x 4 threads",
                    "fixture_seconds": round(fixture_seconds, 2),
                    "elapsed_seconds": round(elapsed, 2),
                    "requests_per_second": round(300 / elapsed, 2),
                    "endpoints": grouped,
                }
            )
        )
        if any(r["status"] != 200 for r in results):
            raise SystemExit(1)
    finally:
        server.terminate()
        try:
            server.wait(timeout=10)
        except subprocess.TimeoutExpired:
            server.kill()
            server.wait()


if __name__ == "__main__":
    main()
