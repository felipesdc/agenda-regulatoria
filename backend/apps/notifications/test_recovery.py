from unittest.mock import patch
from django.test import TestCase
from django.core.management import call_command
from django.core.management.base import CommandError
from rest_framework.exceptions import ValidationError
from apps.commitments import tests as fixtures
from apps.audit.models import AuditEvent
from .models import NotificationDelivery
from .recovery import hold_restored_outbox


class OutboxRecoveryTests(TestCase):
    def setUp(self):
        fixtures.CommitmentTests.setUp(self)

    def test_hold_is_audited_idempotent_and_not_an_smtp_attempt(self):
        delivery = NotificationDelivery.objects.get()
        self.assertEqual(hold_restored_outbox("Restore verification"), 1)
        delivery.refresh_from_db()
        self.assertEqual(delivery.status, "unknown")
        self.assertEqual(delivery.attempts, 0)
        self.assertEqual(delivery.history.get().stage, "recovery_hold")
        self.assertEqual(hold_restored_outbox("Repeated hold"), 0)
        self.assertEqual(
            AuditEvent.objects.filter(operation="notification.recovery_hold").count(), 1
        )
        delivery.status = "accepted"
        delivery.save()
        self.assertEqual(hold_restored_outbox("Keep known acceptance"), 0)

    def test_recovery_reason_atomicity_and_source_guard(self):
        with self.assertRaises(ValidationError):
            hold_restored_outbox(" ")
        with patch("apps.notifications.recovery.record", side_effect=RuntimeError("Audit failed")):
            with self.assertRaises(RuntimeError):
                hold_restored_outbox("Rollback")
        self.assertEqual(NotificationDelivery.objects.get().status, "pending")
        with self.assertRaises(CommandError):
            call_command(
                "hold_restored_outbox",
                expected_database="agenda",
                reason="Refuse source",
                apply=True,
            )
        self.assertEqual(NotificationDelivery.objects.get().status, "pending")
