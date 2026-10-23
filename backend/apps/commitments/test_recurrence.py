from django.test import TransactionTestCase
from django.db import connection, connections
from concurrent.futures import ThreadPoolExecutor
from unittest import skipUnless
from datetime import date
from django.test import SimpleTestCase, TestCase
from django.db import transaction, DatabaseError, IntegrityError
from . import tests as core_tests
from .models import Holiday, RecurrenceVersion, CommitmentOccurrence
from .recurrence_engine import scheduled_dates
from .recurrence_serializers import RuleSerializer
from .recurrence_services import generate, change_series
from .services import create_commitment, transition, add_action


def rule(**kwargs):
    s = RuleSerializer(
        data={"frequency": "monthly", "start": "2028-01-31", "end": "2028-04-30", **kwargs}
    )
    s.is_valid(raise_exception=True)
    return s.validated_data


class DateEngineTests(SimpleTestCase):
    def dates(self, r, holidays=()):
        return list(scheduled_dates(r, date.fromisoformat(r["end"]), holidays))

    def test_month_end_no_drift_and_leap_year(self):
        dates = self.dates(rule())
        self.assertEqual([d.day for d, _ in dates], [31, 29, 31, 30])
        self.assertEqual(
            [d.day for d, _ in self.dates(rule(start="2027-01-31", end="2027-03-31"))], [31, 28, 31]
        )

    def test_yearly_leap_anchor(self):
        ds = self.dates(rule(frequency="yearly", start="2028-02-29", end="2032-02-29"))
        self.assertEqual([d.day for d, _ in ds], [29, 28, 28, 28, 29])

    def test_all_intervals(self):
        for frequency, step in [("daily", 1), ("weekly", 7), ("fortnightly", 14), ("custom", 3)]:
            ds = self.dates(rule(frequency=frequency, interval=3, count=3))
            self.assertEqual((ds[1][0] - ds[0][0]).days, step)
            self.assertEqual(len(ds), 3)
        for frequency, month in [
            ("bimonthly", 3),
            ("quarterly", 4),
            ("semiannual", 7),
            ("yearly", 1),
        ]:
            ds = self.dates(rule(frequency=frequency, end="2030-12-31", count=2))
            self.assertEqual(ds[1][0].month, month)
        self.assertEqual(len(self.dates(rule(frequency="once"))), 1)

    def test_business_and_weekday_rules(self):
        ds = self.dates(
            rule(start="2028-01-01", end="2028-01-31", month_mode="business_day", ordinal=1),
            ["2028-01-03"],
        )
        self.assertEqual(ds[0][0], date(2028, 1, 4))
        ds = self.dates(
            rule(start="2028-01-01", end="2028-01-31", month_mode="last_business_day"),
            ["2028-01-31"],
        )
        self.assertEqual(ds[0][0], date(2028, 1, 28))
        ds = self.dates(
            rule(start="2028-01-01", end="2028-02-29", month_mode="weekday", weekday=0, ordinal=5)
        )
        self.assertEqual([d for d, _ in ds], [date(2028, 1, 31)])
        ds = self.dates(
            rule(start="2028-01-01", end="2028-01-31", month_mode="last_weekday", weekday=4)
        )
        self.assertEqual(ds[0][0], date(2028, 1, 28))
        ds = self.dates(rule(start="2028-01-01", end="2028-01-31", month_mode="last_day"))
        self.assertEqual(ds[0][0], date(2028, 1, 31))

    def test_adjustments_exceptions_count_and_business_interval(self):
        r = rule(
            frequency="daily",
            start="2028-01-01",
            end="2028-01-10",
            count=3,
            adjustment="next",
            exceptions=["2028-01-02"],
        )
        ds = self.dates(r, ["2028-01-03"])
        self.assertEqual(
            ds, [(date(2028, 1, 1), date(2028, 1, 4)), (date(2028, 1, 3), date(2028, 1, 4))]
        )
        r = rule(
            frequency="custom",
            start="2028-01-07",
            end="2028-01-20",
            interval=1,
            interval_unit="business_days",
            count=2,
        )
        self.assertEqual(self.dates(r, ["2028-01-10"])[1][0], date(2028, 1, 11))
        self.assertEqual(
            self.dates(rule(frequency="once", start="2028-01-01", adjustment="previous"))[0][1],
            date(2027, 12, 31),
        )

    def test_first_day_and_weekday_start(self):
        ds = self.dates(rule(start="2028-01-01", end="2028-02-29", month_mode="first_day"))
        self.assertEqual([d.day for d, _ in ds], [1, 1])
        ds = self.dates(rule(frequency="weekly", start="2028-01-01", end="2028-01-20", weekday=2))
        self.assertEqual(ds[0][0], date(2028, 1, 5))

    def test_closed_business_calendar_reports_validation_error(self):
        from datetime import timedelta
        from rest_framework.exceptions import ValidationError
        from .recurrence_services import validated_dates

        holidays = [(date(2028, 1, 1) + timedelta(days=n)).isoformat() for n in range(400)]
        with self.assertRaises(ValidationError):
            validated_dates(
                rule(frequency="once", start="2028-01-01", adjustment="next"),
                date(2028, 4, 30),
                holidays,
            )

    def test_invalid_rules(self):
        for changes in [
            {"end": "2027-01-01"},
            {"end": "2040-01-01"},
            {"month_mode": "weekday", "ordinal": 6},
            {"exceptions": ["2020-01-01"]},
            {"interval": 0},
            {"bogus": 1},
            {"start": "1800-01-01", "end": "1800-02-01"},
        ]:
            s = RuleSerializer(
                data={"frequency": "monthly", "start": "2028-01-01", "end": "2028-04-01", **changes}
            )
            self.assertFalse(s.is_valid())


class RecurrenceTests(TestCase):
    setUp = core_tests.CommitmentTests.setUp

    def create_series(self, **changes):
        data = {
            **self.data,
            "due_date": date(2028, 1, 31),
            "reference_date": date(2028, 1, 30),
            "recurrence": rule(**changes),
        }
        return create_commitment(self.requester, data)

    def test_idempotence_reference_and_holiday_snapshot(self):
        Holiday.objects.create(date="2028-01-31", name="Fictício")
        first = self.create_series(adjustment="next")
        self.assertEqual(first.due_date, date(2028, 2, 1))
        self.assertEqual(first.reference_date, date(2028, 1, 30))
        Holiday.objects.all().update(active=False)
        self.assertEqual(generate(first.definition, date(2030, 1, 1), self.requester), 0)
        self.assertEqual(first.definition.occurrences.count(), 4)
        self.assertEqual(first.definition.recurrence_versions.get().holidays, ["2028-01-31"])
        with self.assertRaises(IntegrityError), transaction.atomic():
            CommitmentOccurrence.objects.create(
                definition=first.definition,
                number=99,
                identifier="duplicate",
                scheduled_date=first.scheduled_date,
                title="x",
                description="x",
                reference_date=first.reference_date,
                due_date=first.due_date,
            )

    def test_series_update_preserves_workflow_and_history(self):
        first = self.create_series()
        transition(self.executor, first, "start", "", 1)
        add_action(self.executor, first, "feito")
        first.refresh_from_db()
        transition(self.executor, first, "submit", "", first.revision)
        first.refresh_from_db()
        transition(self.requester, first, "approve", "", first.revision)
        rv = change_series(
            self.requester,
            first,
            {"revision": 1, "reason": "novo texto", "scope": "pending", "title": "Novo"},
        )
        first.refresh_from_db()
        self.assertEqual(first.status, "completed")
        self.assertNotEqual(first.title, "Novo")
        pending = first.definition.occurrences.filter(status="pending")
        self.assertEqual(pending.filter(title="Novo").count(), 3)
        self.assertEqual(pending.first().versions.count(), 2)
        self.assertEqual(rv.revision, 2)
        with self.assertRaises(DatabaseError), transaction.atomic():
            RecurrenceVersion.objects.filter(pk=rv.pk).update(reason="fraude")

    def test_new_rule_only_after_generated_and_future_scope(self):
        first = self.create_series()
        rv = change_series(
            self.requester,
            first,
            {
                "revision": 1,
                "scope": "future",
                "reason": "extensão",
                "title": "Futuro",
                "rule": rule(start="2028-05-31", end="2028-07-31"),
            },
        )
        self.assertEqual(generate(first.definition, date(2028, 7, 31), self.requester), 0)
        self.assertEqual(
            first.definition.occurrences.filter(recurrence_version=rv, title="Futuro").count(), 3
        )
        self.assertEqual(first.definition.occurrences.filter(title=first.title).count(), 4)
        self.assertEqual(generate(first.definition, date(2028, 7, 31), self.requester), 0)

    def test_api_permissions_validation_preview_and_filters(self):
        first = self.create_series()
        self.client.force_authenticate(self.executor)
        url = f"/api/v1/occurrences/{first.pk}/series/"
        payload = {"revision": 1, "scope": "pending", "reason": "x", "title": "x"}
        self.assertEqual(self.client.post(url, payload).status_code, 403)
        self.assertEqual(
            self.client.post(
                f"/api/v1/occurrences/{first.pk}/generate/", {"through": "2028-07-01"}
            ).status_code,
            403,
        )
        self.assertEqual(
            self.client.post(
                "/api/v1/holidays/", {"date": "2028-01-01", "name": "Fictício"}
            ).status_code,
            403,
        )
        self.client.force_authenticate(self.requester)
        self.assertEqual(self.client.post(url, {**payload, "revision": 99}).status_code, 400)
        self.assertEqual(
            self.client.post(url, {**payload, "rule": rule()}, format="json").status_code, 400
        )
        self.assertEqual(
            self.client.get("/api/v1/occurrences/?periodicity=monthly").data["count"], 4
        )
        self.assertEqual(self.client.get("/api/v1/occurrences/?periodicity=once").data["count"], 1)
        self.assertEqual(
            self.client.post(
                f"/api/v1/occurrences/{first.pk}/generate/", {"through": "2028-07-01"}
            ).data["created"],
            0,
        )
        response = self.client.post(
            "/api/v1/recurrence/preview/", {"rule": rule(), "through": "2028-04-30"}, format="json"
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.data["dates"]), 4)
        self.client.force_authenticate(self.admin)
        response = self.client.post("/api/v1/holidays/", {"date": "2028-01-01", "name": "Fictício"})
        self.assertEqual(response.status_code, 201)
        self.assertEqual(
            self.client.patch(
                f"/api/v1/holidays/{response.data['id']}/", {"active": False}
            ).status_code,
            200,
        )

    def test_adjusted_dates_can_coincide_and_invalid_creation_rolls_back(self):
        first = self.create_series(
            frequency="daily", count=3, adjustment="next", start="2028-01-31"
        )
        self.assertEqual(first.definition.occurrences.count(), 3)
        before = CommitmentOccurrence.objects.count()
        from rest_framework.exceptions import ValidationError

        with self.assertRaises(ValidationError):
            self.create_series(start="2028-02-01")
        self.assertEqual(CommitmentOccurrence.objects.count(), before)
        with self.assertRaises(ValidationError):
            self.create_series(frequency="once", exceptions=["2028-01-31"])
        self.assertEqual(CommitmentOccurrence.objects.count(), before)

    def test_calendars_and_series_atomic_validation(self):
        from rest_framework.exceptions import ValidationError

        Holiday.objects.create(date="2028-01-31", name="Institucional", kind="institution")
        first = self.create_series(calendar="national", adjustment="next")
        self.assertEqual(first.due_date, date(2028, 1, 31))
        self.assertEqual(first.definition.recurrence_versions.get().holidays, [])
        self.executor.is_active = False
        self.executor.save()
        with self.assertRaises(ValidationError):
            change_series(
                self.requester,
                first,
                {
                    "revision": 1,
                    "scope": "pending",
                    "reason": "x",
                    "title": "x",
                    "rule": rule(start="2028-05-31", end="2028-06-30"),
                },
            )
        self.assertEqual(first.definition.recurrence_versions.count(), 1)
        self.assertEqual(first.definition.occurrences.filter(title="x").count(), 0)

    def test_command_is_idempotent(self):
        from django.core.management import call_command
        from io import StringIO

        self.create_series()
        out = StringIO()
        call_command("generate_occurrences", through="2028-12-31", stdout=out)
        self.assertIn("criadas: 0", out.getvalue())


@skipUnless(connection.vendor == "postgresql", "Bloqueio concorrente exige PostgreSQL")
class ConcurrentGenerationTests(TransactionTestCase):
    setUp = core_tests.CommitmentTests.setUp

    def test_parallel_generation_produces_exactly_one_occurrence_per_nominal_date(self):
        first = create_commitment(
            self.requester,
            {**self.data, "due_date": date(2028, 1, 31), "recurrence": rule(frequency="once")},
        )
        rv = first.definition.recurrence_versions.get()
        RecurrenceVersion.objects.create(
            definition=first.definition,
            revision=2,
            effective_from="2028-02-01",
            rule=rule(frequency="daily", start="2028-02-01", end="2028-02-10"),
            holidays=[],
            template=rv.template,
            actor=self.requester,
            reason="Teste concorrente",
        )

        def run(_):
            try:
                return generate(first.definition, date(2028, 2, 10), self.requester)
            finally:
                connections.close_all()

        with ThreadPoolExecutor(max_workers=4) as pool:
            results = list(pool.map(run, range(8)))
        self.assertEqual(sum(results), 10)
        self.assertEqual(first.definition.occurrences.count(), 11)
        self.assertEqual(
            first.definition.occurrences.values("scheduled_date").distinct().count(), 11
        )
