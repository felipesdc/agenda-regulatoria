from concurrent.futures import ThreadPoolExecutor
from unittest import skipUnless
from django.test import TransactionTestCase
from django.db import connection, connections
from rest_framework.exceptions import ValidationError
from apps.audit.models import AuditEvent
from . import tests as fixtures
from .services import update_occurrence


@skipUnless(connection.vendor == "postgresql", "Requires real PostgreSQL row locks")
class ConcurrentEditTests(TransactionTestCase):
    def setUp(self):
        fixtures.CommitmentTests.setUp(self)

    def test_eight_stale_editors_produce_one_new_version(self):
        def edit(index):
            try:
                update_occurrence(
                    self.requester,
                    self.occ,
                    {
                        "title": f"Concurrent fictitious edit {index}",
                        "revision": 1,
                        "reason": "Concurrent edit verification",
                    },
                )
                return True
            except ValidationError:
                return False
            finally:
                connections.close_all()

        with ThreadPoolExecutor(max_workers=4) as pool:
            results = list(pool.map(edit, range(8)))
        self.assertEqual(sum(results), 1)
        self.occ.refresh_from_db()
        self.assertEqual(self.occ.revision, 2)
        self.assertEqual(self.occ.versions.count(), 2)
        self.assertEqual(AuditEvent.objects.filter(operation="occurrence.updated").count(), 1)
