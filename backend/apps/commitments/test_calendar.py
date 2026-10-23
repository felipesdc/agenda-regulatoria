from datetime import timedelta
from django.test import TestCase
from django.db import connection
from django.test.utils import CaptureQueriesContext
from rest_framework.test import APIClient
from . import tests as core_tests
from . import services
from .models import CommitmentAssignment
from apps.accounts.models import User, Membership


class CalendarTests(TestCase):
    setUp = core_tests.CommitmentTests.setUp

    def request(self, user=None, **params):
        self.client.force_authenticate(user or self.requester)
        values = {
            "date_start": str(self.occ.due_date - timedelta(days=1)),
            "date_end": str(self.occ.due_date + timedelta(days=1)),
        }
        values.update(params)
        return self.client.get("/api/v1/calendar/", values)

    def test_period_scope_and_inclusive_boundaries(self):
        self.assertEqual(self.request().data["total"], 1)
        self.assertEqual(self.request(self.stranger).data["total"], 0)
        self.assertEqual(self.request(self.executor).data["total"], 1)
        self.assertEqual(self.request(self.admin).data["total"], 1)
        response = self.request(date_start=str(self.occ.due_date), date_end=str(self.occ.due_date))
        self.assertEqual(response.data["days"][0]["date"], str(self.occ.due_date))
        self.assertEqual(
            self.request(date_start=str(self.occ.due_date + timedelta(days=1))).data["total"], 0
        )
        self.unit.active = False
        self.unit.save()
        self.assertEqual(self.request(self.admin).data["total"], 0)

    def test_daily_samples_and_summary_no_duplicates(self):
        second = User.objects.create_user("second")
        Membership.objects.create(user=second, unit=self.unit, role="executor")
        CommitmentAssignment.objects.create(user=second, occurrence=self.occ)
        for _ in range(4):
            services.create_commitment(self.requester, self.data)
        with CaptureQueriesContext(connection) as captured:
            response = self.request()
        self.assertLessEqual(len(captured), 12)
        self.assertEqual(response.data["total"], 5)
        day = response.data["days"][0]
        self.assertEqual(day["status_counts"], {"pending": 5})
        self.assertEqual(len(day["events"]), 3)
        self.assertEqual(len({event["id"] for event in day["events"]}), 3)
        summary = self.request(summary="true")
        self.assertEqual(summary.data["total"], 5)
        self.assertEqual(summary.data["days"][0]["events"], [])

    def test_filters_combine_and_daily_drilldown(self):
        filters = {
            "unit": str(self.unit.pk),
            "entity": str(self.entity.pk),
            "category": str(self.category.pk),
            "requester": str(self.requester.pk),
            "assignee": str(self.executor.pk),
            "priority": "normal",
            "status": "pending",
            "periodicity": "once",
            "q": "Fictitious",
        }
        self.assertEqual(self.request(**filters).data["total"], 1)
        self.assertEqual(self.request(**{**filters, "priority": "critical"}).data["total"], 0)
        self.client.force_authenticate(self.requester)
        response = self.client.get(
            "/api/v1/occurrences/",
            {**filters, "date_start": str(self.occ.due_date), "date_end": str(self.occ.due_date)},
        )
        self.assertEqual(response.data["count"], 1)
        self.assertEqual(
            self.client.get(
                "/api/v1/occurrences/", {"date_end": str(self.occ.due_date - timedelta(days=1))}
            ).data["count"],
            0,
        )

    def test_invalid_dates_values_and_bounded_year(self):
        self.client.force_authenticate(self.requester)
        self.assertEqual(self.client.get("/api/v1/calendar/").status_code, 400)
        for params in [
            {"date_start": "bad"},
            {"date_start": "2028-12-31", "date_end": "2028-01-01"},
            {"date_start": "2027-01-01", "date_end": "2028-12-31"},
            {"unit": "bad"},
            {"assignee": "bad"},
            {"priority": "bad"},
            {"periodicity": "invalid"},
            {"summary": "bad"},
        ]:
            self.assertEqual(self.request(**params).status_code, 400, params)
        self.assertEqual(
            self.request(
                date_start="2028-01-01", date_end="2028-12-31", summary="true"
            ).status_code,
            200,
        )

    def test_calendar_people_are_scoped(self):
        other = services.create_commitment(
            self.stranger,
            {**self.data, "unit": self.other, "assignees": [self.make_other_executor()]},
        )
        self.client.force_authenticate(self.executor)
        response = self.client.get("/api/v1/calendar/people/")
        self.assertEqual([p["id"] for p in response.data["requesters"]], [str(self.requester.pk)])
        self.assertNotIn(str(other.definition.requester_id), str(response.data))
        self.client.force_authenticate(self.stranger)
        self.assertEqual(len(self.client.get("/api/v1/calendar/people/").data["requesters"]), 1)

    def make_other_executor(self):
        user = User.objects.create_user("otherexecutor")
        Membership.objects.create(user=user, unit=self.other, role="executor")
        return user

    def test_favorites_owner_validation_and_duplicate_names(self):
        self.client.force_authenticate(self.requester)
        payload = {
            "name": "My favorite",
            "filters": {"unit": str(self.unit.pk), "status": "pending"},
            "owner": str(self.stranger.pk),
        }
        response = self.client.post("/api/v1/calendar-favorites/", payload, format="json")
        self.assertEqual(response.status_code, 201, response.data)
        id = response.data["id"]
        self.assertEqual(
            self.client.post("/api/v1/calendar-favorites/", payload, format="json").status_code, 400
        )
        for filters in [
            [],
            {"secret": "x"},
            {"unit": "bad"},
            {"date_start": "bad"},
            {"date_start": "2028-12-31", "date_end": "2028-01-01"},
        ]:
            self.assertEqual(
                self.client.post(
                    "/api/v1/calendar-favorites/",
                    {"name": "Invalid", "filters": filters},
                    format="json",
                ).status_code,
                400,
            )
        self.assertEqual(self.client.get("/api/v1/calendar-favorites/").data["count"], 1)
        self.client.force_authenticate(self.stranger)
        self.assertEqual(self.client.get("/api/v1/calendar-favorites/").data["count"], 0)
        self.assertEqual(self.client.delete(f"/api/v1/calendar-favorites/{id}/").status_code, 404)
        self.client.force_authenticate(self.requester)
        self.assertEqual(self.client.delete(f"/api/v1/calendar-favorites/{id}/").status_code, 204)

    def test_calendar_requires_login(self):
        self.client = APIClient()
        for endpoint in [
            "/api/v1/calendar/",
            "/api/v1/calendar/people/",
            "/api/v1/calendar-favorites/",
        ]:
            self.assertEqual(self.client.get(endpoint).status_code, 403)
