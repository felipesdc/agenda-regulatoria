from concurrent.futures import ThreadPoolExecutor
from datetime import date, timedelta
from io import StringIO
from unittest import skipUnless
from unittest.mock import patch
import smtplib
from django.test import TestCase, TransactionTestCase, override_settings
from django.db import connection, connections, transaction, DatabaseError
from django.utils import timezone
from django.core import mail
from django.core.management import call_command, CommandError
from apps.commitments import tests as core_tests
from apps.commitments import services as commitments
from apps.commitments.models import Holiday, CommitmentOccurrence
from apps.audit.models import AuditEvent
from .models import NotificationEvent, NotificationDelivery, NotificationAttempt, NotificationPolicy
from .services import emit, claim, recover_expired, requeue, scan_deadlines, alert_date, wake_outbox
from .tasks import deliver, dispatch, deadlines, classify_error


@override_settings(EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend")
class NotificationTests(TestCase):
    def setUp(self):
        core_tests.CommitmentTests.setUp(self)
        self.executor.email = "executor@agenda.invalid"
        self.executor.save()
        self.requester.email = "requester@agenda.invalid"
        self.requester.save()
        self.delivery = NotificationDelivery.objects.get(event__occurrence=self.occ)

    def test_atomic_outbox_idempotence_and_rollback(self):
        self.assertEqual(NotificationEvent.objects.count(), 1)
        emit(self.occ, "assigned", self.requester)
        self.assertEqual(NotificationDelivery.objects.count(), 1)
        before = CommitmentOccurrence.objects.count()
        with patch(
            "apps.notifications.services.record", side_effect=RuntimeError("audit unavailable")
        ):
            with self.assertRaises(RuntimeError):
                commitments.create_commitment(self.requester, self.data)
        self.assertEqual(CommitmentOccurrence.objects.count(), before)
        self.assertEqual(NotificationEvent.objects.count(), 1)

    def test_workflow_events_recipients(self):
        commitments.transition(self.executor, self.occ, "start", "", 1)
        commitments.add_action(self.executor, self.occ, "Feito")
        self.occ.refresh_from_db()
        commitments.transition(self.executor, self.occ, "submit", "", self.occ.revision)
        event = NotificationEvent.objects.get(kind="validation_requested")
        self.assertEqual(
            list(event.deliveries.values_list("recipient_id", flat=True)), [self.requester.pk]
        )
        self.occ.refresh_from_db()
        commitments.transition(self.requester, self.occ, "reject", "Complemente", self.occ.revision)
        self.assertEqual(NotificationEvent.objects.get(kind="rejected").deliveries.count(), 2)
        self.occ.refresh_from_db()
        commitments.transition(
            self.requester, self.occ, "cancel", "Cancelamento", self.occ.revision
        )
        self.assertTrue(NotificationEvent.objects.filter(kind="cancelled").exists())

    def test_changed_event_and_old_deadline_obsolete(self):
        commitments.update_occurrence(
            self.requester, self.occ, {"title": "Atualizado", "reason": "x", "revision": 1}
        )
        self.assertTrue(NotificationEvent.objects.filter(kind="changed").exists())
        event = emit(self.occ, "deadline", extra={"offset": 0})
        self.occ.due_date += timedelta(days=1)
        self.occ.save()
        delivery = event.deliveries.filter(recipient=self.executor).get()
        deliver(str(delivery.pk))
        delivery.refresh_from_db()
        self.assertEqual(delivery.status, "skipped")
        self.assertEqual(delivery.last_error, "obsolete_deadline")

    def test_current_permissions_and_email_revalidated(self):
        self.executor.email = ""
        self.executor.save()
        deliver(str(self.delivery.pk))
        self.delivery.refresh_from_db()
        self.assertEqual(self.delivery.last_error, "recipient_email_missing_or_invalid")
        self.assertEqual(self.delivery.attempts, 0)
        requeue(self.delivery.pk, self.admin, "E-mail corrigido")
        self.executor.email = "executor@agenda.invalid"
        self.executor.save()
        self.executor.memberships.all().delete()
        deliver(str(self.delivery.pk))
        self.delivery.refresh_from_db()
        self.assertEqual(self.delivery.last_error, "recipient_no_longer_authorized")
        self.assertEqual(self.client.get("/api/v1/notifications/").status_code, 403)

    def test_smtp_acceptance_multipart_escape_and_link(self):
        self.occ.title = "<script>malicious</script>"
        self.occ.description = "A descrição segura."
        self.occ.save()
        event = emit(self.occ, "changed", self.requester)
        row = event.deliveries.get(recipient=self.executor)
        deliver(str(row.pk))
        deliver(str(row.pk))
        row.refresh_from_db()
        self.assertEqual(row.status, "accepted")
        self.assertEqual(row.attempts, 1)
        self.assertEqual(row.history.count(), 2)
        self.assertEqual(len(mail.outbox), 1)
        msg = mail.outbox[0]
        self.assertIn(str(self.occ.pk), msg.body)
        self.assertIn("&lt;script&gt;", msg.alternatives[0].content)
        self.assertNotIn("<script>", msg.alternatives[0].content)
        self.assertEqual(msg.extra_headers["Message-ID"], row.message_id)
        self.assertIsNotNone(row.accepted_at)
        self.assertTrue(AuditEvent.objects.filter(operation="notification.accepted").exists())

    def test_transient_retry_backoff_exhaustion_and_manual_cycle(self):
        with patch(
            "apps.notifications.tasks.EmailMultiAlternatives.send",
            side_effect=ConnectionRefusedError(),
        ):
            for n in range(1, 6):
                NotificationDelivery.objects.filter(pk=self.delivery.pk).update(
                    next_attempt_at=timezone.now() - timedelta(seconds=1)
                )
                deliver(str(self.delivery.pk))
                self.delivery.refresh_from_db()
                self.assertEqual(self.delivery.attempts, n)
                self.assertEqual(self.delivery.status, "retry" if n < 5 else "failed")
                if n < 5:
                    self.assertGreater(
                        (self.delivery.next_attempt_at - timezone.now()).total_seconds(),
                        60 * 2 ** (n - 1) - 2,
                    )
                    deliver(str(self.delivery.pk))
                    self.delivery.refresh_from_db()
                    self.assertEqual(self.delivery.attempts, n)
            requeue(self.delivery.pk, self.admin, "SMTP corrigido")
            deliver(str(self.delivery.pk))
            self.delivery.refresh_from_db()
            self.assertEqual(self.delivery.status, "retry")
            self.assertEqual(self.delivery.retry_limit, 10)
            self.assertLess((self.delivery.next_attempt_at - timezone.now()).total_seconds(), 61)

    def test_permanent_and_unknown_results(self):
        with patch(
            "apps.notifications.tasks.EmailMultiAlternatives.send",
            side_effect=smtplib.SMTPDataError(550, b"sensitive text"),
        ):
            deliver(str(self.delivery.pk))
        self.delivery.refresh_from_db()
        self.assertEqual(self.delivery.status, "failed")
        self.assertEqual(self.delivery.last_error, "smtp_response_550")
        self.assertNotIn("sensitive", str(list(self.delivery.history.values())))
        requeue(self.delivery.pk, self.admin, "Verificar SMTP")
        with patch(
            "apps.notifications.tasks.EmailMultiAlternatives.send", side_effect=TimeoutError()
        ):
            deliver(str(self.delivery.pk))
        self.delivery.refresh_from_db()
        self.assertEqual(self.delivery.status, "unknown")
        with patch("apps.notifications.tasks.EmailMultiAlternatives.send") as send:
            deliver(str(self.delivery.pk))
            send.assert_not_called()

    def test_claim_lease_recovery_and_append_only(self):
        row = claim(self.delivery.pk)
        self.assertIsNotNone(row)
        self.assertIsNone(claim(self.delivery.pk))
        self.assertFalse(recover_expired(self.delivery.pk))
        NotificationDelivery.objects.filter(pk=row.pk).update(
            lease_until=timezone.now() - timedelta(seconds=1)
        )
        self.assertTrue(recover_expired(row.pk))
        row.refresh_from_db()
        self.assertEqual(row.status, "unknown")
        for model in [NotificationEvent, NotificationAttempt]:
            obj = model.objects.first()
            with self.assertRaises(DatabaseError), transaction.atomic():
                model.objects.filter(pk=obj.pk).delete()
        self.assertEqual(NotificationEvent.objects.count(), 1)

    def test_dispatch_and_broker_failure_recovery(self):
        with patch("apps.notifications.tasks.deliver.delay", side_effect=ConnectionError()):
            dispatch()
        self.delivery.refresh_from_db()
        self.assertEqual(self.delivery.status, "pending")
        with patch("apps.notifications.tasks.deliver.delay") as publish:
            dispatch()
            publish.assert_called_once_with(str(self.delivery.pk))
        with patch("apps.notifications.tasks.dispatch.delay", side_effect=ConnectionError()):
            wake_outbox()

    def test_error_classification(self):
        self.assertEqual(
            classify_error(smtplib.SMTPAuthenticationError(535, b"secret"))[0], "failed"
        )
        self.assertEqual(
            classify_error(smtplib.SMTPRecipientsRefused({"x": (450, b"temporary")}))[0], "retry"
        )
        self.assertEqual(
            classify_error(smtplib.SMTPRecipientsRefused({"x": (550, b"permanent")}))[0], "failed"
        )
        self.assertEqual(classify_error(smtplib.SMTPDataError(451, b"temporary"))[0], "retry")
        self.assertEqual(classify_error(smtplib.SMTPServerDisconnected())[0], "unknown")
        self.assertEqual(classify_error(smtplib.SMTPException())[0], "unknown")

    def test_deadline_days_business_holidays_and_idempotence(self):
        today = date(2028, 2, 28)
        self.occ.due_date = date(2028, 2, 29)
        self.occ.save()
        NotificationPolicy.objects.create(
            definition=self.occ.definition,
            offsets=[1, 0, -1],
            basis="business",
            calendar="institution",
        )
        Holiday.objects.create(date="2028-02-28", kind="institution", name="Fictício")
        self.assertEqual(
            alert_date(self.occ.due_date, 1, "business", {"2028-02-28"}), date(2028, 2, 25)
        )
        self.assertEqual(scan_deadlines(today), 1)
        self.assertEqual(scan_deadlines(today), 0)
        self.assertEqual(scan_deadlines(date(2028, 2, 29)), 1)
        self.assertEqual(scan_deadlines(date(2028, 3, 1)), 1)
        self.occ.status = "completed"
        self.occ.save()
        self.assertEqual(scan_deadlines(date(2028, 3, 2)), 0)

    def test_policy_precedence_disabled_and_elapsed_early_alerts(self):
        today = timezone.localdate()
        self.occ.due_date = today
        self.occ.save()
        NotificationPolicy.objects.create(category=self.category, offsets=[0], enabled=False)
        self.assertEqual(scan_deadlines(today), 0)
        p = NotificationPolicy.objects.create(
            definition=self.occ.definition, offsets=[1, 0], enabled=True
        )
        self.assertEqual(scan_deadlines(today), 1)
        p.enabled = False
        p.save()
        self.assertEqual(scan_deadlines(today + timedelta(days=1)), 0)
        self.assertEqual(deadlines(), 0)

    def test_policy_api_permissions_revision_and_validation(self):
        payload = {
            "definition": str(self.occ.definition_id),
            "offsets": [3, 0, -1],
            "reason": "Política fictícia",
            "revision": 0,
        }
        self.client.force_authenticate(self.peer)
        self.assertEqual(
            self.client.post("/api/v1/notification-policies/", payload, format="json").status_code,
            403,
        )
        self.client.force_authenticate(self.requester)
        self.assertEqual(
            self.client.post("/api/v1/notification-policies/", payload, format="json").status_code,
            200,
        )
        self.assertEqual(
            self.client.post("/api/v1/notification-policies/", payload, format="json").status_code,
            400,
        )
        self.assertEqual(self.client.get("/api/v1/notification-policies/").data["count"], 1)
        for bad in [[True], [0, 0], [366], [], ["3"]]:
            self.assertEqual(
                self.client.post(
                    "/api/v1/notification-policies/",
                    {**payload, "offsets": bad, "revision": 1},
                    format="json",
                ).status_code,
                400,
            )
        self.assertEqual(
            self.client.post(
                "/api/v1/notification-policies/",
                {**payload, "category": str(self.category.pk)},
                format="json",
            ).status_code,
            400,
        )
        self.assertEqual(
            self.client.post(
                "/api/v1/notification-policies/",
                {"category": str(self.category.pk), "offsets": [0], "reason": "x"},
                format="json",
            ).status_code,
            403,
        )
        self.client.force_authenticate(self.admin)
        self.assertEqual(
            self.client.post(
                "/api/v1/notification-policies/",
                {"category": str(self.category.pk), "offsets": [0], "reason": "x"},
                format="json",
            ).status_code,
            200,
        )

    def test_delivery_isolation_monitor_email_and_retry_api(self):
        self.client.force_authenticate(self.executor)
        self.assertEqual(self.client.get("/api/v1/notifications/").data["count"], 1)
        self.assertEqual(self.client.get("/api/v1/notification-monitor/").status_code, 403)
        self.assertEqual(
            self.client.post(
                f"/api/v1/notifications/{self.delivery.pk}/requeue/", {"reason": "x"}
            ).status_code,
            403,
        )
        self.assertEqual(
            self.client.patch(
                "/api/v1/notification-email/", {"email": "updated@agenda.invalid"}
            ).status_code,
            200,
        )
        self.assertEqual(
            self.client.get("/api/v1/notification-email/").data["email"], "updated@agenda.invalid"
        )
        self.client.force_authenticate(self.stranger)
        self.assertEqual(self.client.get("/api/v1/notifications/").data["count"], 0)
        self.assertEqual(
            self.client.get(f"/api/v1/notifications/{self.delivery.pk}/").status_code, 404
        )
        self.client.force_authenticate(self.admin)
        self.assertEqual(self.client.get("/api/v1/notification-monitor/").status_code, 200)
        self.assertEqual(self.client.get("/api/v1/notifications/?status=bogus").status_code, 400)
        self.assertEqual(self.client.get("/api/v1/notifications/?occurrence=bad").status_code, 400)
        self.assertEqual(
            self.client.get("/api/v1/notifications/", {"occurrence": str(self.occ.pk)}).data[
                "count"
            ],
            1,
        )
        self.assertEqual(
            self.client.post(
                f"/api/v1/notifications/{self.delivery.pk}/requeue/", {"reason": "x"}
            ).status_code,
            400,
        )
        NotificationDelivery.objects.filter(pk=self.delivery.pk).update(status="unknown")
        self.assertEqual(
            self.client.post(
                f"/api/v1/notifications/{self.delivery.pk}/requeue/", {"reason": "x"}
            ).status_code,
            400,
        )
        self.assertEqual(
            self.client.post(
                f"/api/v1/notifications/{self.delivery.pk}/requeue/",
                {"reason": "Análise manual", "acknowledge_duplicate_risk": True},
            ).status_code,
            200,
        )
        with patch("apps.notifications.tasks.deadlines.delay", side_effect=ConnectionError()):
            self.assertEqual(self.client.post("/api/v1/notification-jobs/").status_code, 503)
        with (
            patch("apps.notifications.tasks.deadlines.delay"),
            patch("apps.notifications.tasks.dispatch.delay"),
        ):
            self.assertEqual(self.client.post("/api/v1/notification-jobs/").status_code, 202)

    @override_settings(DEBUG=True, EMAIL_HOST="mailpit")
    def test_demo_seed_does_not_overwrite_existing_email(self):
        from apps.accounts.models import User

        user = User.objects.create_user("demandante1")
        out = StringIO()
        call_command("seed_notification_demo", stdout=out)
        user.refresh_from_db()
        self.assertEqual(user.email, "demandante1@agenda.invalid")
        user.email = "custom@agenda.invalid"
        user.save()
        call_command("seed_notification_demo", stdout=out)
        user.refresh_from_db()
        self.assertEqual(user.email, "custom@agenda.invalid")
        with override_settings(EMAIL_HOST="corporate"):
            with self.assertRaises(CommandError):
                call_command("seed_notification_demo")


@skipUnless(connection.vendor == "postgresql", "Claims concorrentes exigem PostgreSQL")
@override_settings(EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend")
class ConcurrentDeliveryTests(TransactionTestCase):
    def setUp(self):
        core_tests.CommitmentTests.setUp(self)
        self.executor.email = "executor@agenda.invalid"
        self.executor.save()

    def test_duplicate_tasks_claim_once(self):
        delivery = NotificationDelivery.objects.get(event__occurrence=self.occ)

        def run(_):
            try:
                deliver(str(delivery.pk))
            finally:
                connections.close_all()

        with patch("apps.notifications.tasks.EmailMultiAlternatives.send", return_value=1) as send:
            with ThreadPoolExecutor(max_workers=4) as pool:
                list(pool.map(run, range(8)))
            self.assertEqual(send.call_count, 1)
        delivery.refresh_from_db()
        self.assertEqual(delivery.status, "accepted")
        self.assertEqual(delivery.attempts, 1)


@override_settings(EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend")
class NotificationGuardTests(TestCase):
    def setUp(self):
        core_tests.CommitmentTests.setUp(self)
        self.executor.email = "executor@agenda.invalid"
        self.executor.save()

    def test_invalid_policy_pending_alert_suppressed(self):
        policy = NotificationPolicy.objects.create(
            definition=self.occ.definition, offsets=[0], enabled=True
        )
        event = emit(
            self.occ,
            "deadline",
            extra={
                "offset": 0,
                "policy": {
                    "enabled": True,
                    "offsets": [0],
                    "basis": "calendar",
                    "calendar": "institution",
                    "revision": 1,
                },
            },
        )
        row = event.deliveries.get(recipient=self.executor)
        policy.enabled = False
        policy.save()
        deliver(str(row.pk))
        row.refresh_from_db()
        self.assertEqual(row.last_error, "obsolete_deadline_policy")

    def test_resolved_validation_and_inactive_scope_suppressed(self):
        event = emit(self.occ, "validation_requested")
        row = event.deliveries.get()
        deliver(str(row.pk))
        row.refresh_from_db()
        self.assertEqual(row.last_error, "obsolete_validation_request")
        row = NotificationDelivery.objects.get(event__kind="assigned")
        self.unit.active = False
        self.unit.save()
        deliver(str(row.pk))
        row.refresh_from_db()
        self.assertEqual(row.last_error, "recipient_no_longer_authorized")

    def test_accepted_is_not_requeued_and_empty_send_is_failed(self):
        row = NotificationDelivery.objects.get(event__kind="assigned")
        with patch("apps.notifications.tasks.EmailMultiAlternatives.send", return_value=0):
            deliver(str(row.pk))
        row.refresh_from_db()
        self.assertEqual(row.status, "failed")
        self.assertEqual(row.last_error, "smtp_did_not_accept")
        requeue(row.pk, self.admin, "Corrigido")
        deliver(str(row.pk))
        from rest_framework.exceptions import ValidationError

        with self.assertRaises(ValidationError):
            requeue(row.pk, self.admin, "Duplicar")

    def test_bound_calendar_search_and_snapshot_guards(self):
        from rest_framework.exceptions import PermissionDenied

        holidays = {(date(2028, 1, 1) + timedelta(days=n)).isoformat() for n in range(1465)}
        with self.assertRaises(ValueError):
            alert_date(date(2028, 1, 1), -1, "business", holidays)
        # Previous-business search uses dates before the due date.
        holidays = {(date(2028, 1, 1) - timedelta(days=n)).isoformat() for n in range(1465)}
        with self.assertRaises(ValueError):
            alert_date(date(2028, 1, 1), 1, "business", holidays)
        row = NotificationDelivery.objects.get(event__kind="assigned")
        NotificationDelivery.objects.filter(pk=row.pk).update(status="failed")
        with self.assertRaises(PermissionDenied):
            requeue(row.pk, self.requester, "Não autorizado")
        self.client.force_authenticate(self.executor)
        self.assertEqual(
            self.client.get("/api/v1/notifications/", {"q": "Fictitious obligation"}).data["count"],
            1,
        )
        self.assertEqual(
            self.client.get("/api/v1/notifications/", {"q": "not found"}).data["count"], 0
        )
        self.assertEqual(
            self.client.get("/api/v1/notifications/", {"q": "x" * 201}).status_code, 400
        )

    def test_email_profile_uses_real_session(self):
        self.client.force_login(self.executor, backend="django.contrib.auth.backends.ModelBackend")
        self.assertEqual(self.client.get("/api/v1/notification-email/").status_code, 200)
        self.assertEqual(
            self.client.patch(
                "/api/v1/notification-email/", {"email": "session@agenda.invalid"}
            ).status_code,
            200,
        )
        self.executor.refresh_from_db()
        self.assertEqual(self.executor.email, "session@agenda.invalid")
        self.assertTrue(
            AuditEvent.objects.filter(operation="user.notification_email_updated").exists()
        )

    def test_acceptance_then_database_failure_is_uncertain_and_never_auto_duplicated(self):
        row = NotificationDelivery.objects.get(event__kind="assigned")
        with patch(
            "apps.notifications.tasks.finish", side_effect=RuntimeError("Database unavailable")
        ):
            with self.assertRaises(RuntimeError):
                deliver(str(row.pk))
        self.assertEqual(len(mail.outbox), 1)
        NotificationDelivery.objects.filter(pk=row.pk).update(
            lease_until=timezone.now() - timedelta(seconds=1)
        )
        recover_expired(row.pk)
        row.refresh_from_db()
        self.assertEqual(row.status, "unknown")
        deliver(str(row.pk))
        self.assertEqual(len(mail.outbox), 1)
        # A late confirmed result may resolve uncertainty before any manual requeue.
        from .services import finish

        finish(row.pk, row.attempts, "accepted")
        row.refresh_from_db()
        self.assertEqual(row.status, "accepted")

    @skipUnless(connection.vendor == "postgresql", "Probe SMTP real usa o ambiente PostgreSQL")
    def test_real_smtp_connection_refused_is_retryable(self):
        import socket

        row = NotificationDelivery.objects.get(event__kind="assigned")
        with socket.socket() as reserved:
            reserved.bind(("127.0.0.1", 0))
            port = reserved.getsockname()[1]
            with override_settings(
                EMAIL_BACKEND="django.core.mail.backends.smtp.EmailBackend",
                EMAIL_HOST="127.0.0.1",
                EMAIL_PORT=port,
                EMAIL_TIMEOUT=1,
                EMAIL_USE_SSL=False,
                EMAIL_USE_TLS=False,
            ):
                deliver(str(row.pk))
        row.refresh_from_db()
        self.assertEqual(row.status, "retry")
        self.assertEqual(row.last_error, "smtp_connection_unavailable")

    def test_reassignment_and_deadline_labels(self):
        from apps.accounts.models import Membership
        from .services import event_label

        Membership.objects.create(user=self.peer, unit=self.unit, role="executor")
        commitments.update_occurrence(
            self.requester,
            self.occ,
            {"assignees": [self.peer], "revision": 1, "reason": "Reatribuição"},
        )
        self.assertTrue(NotificationEvent.objects.filter(kind="reassigned").exists())
        row = NotificationDelivery.objects.get(event__kind="assigned")
        deliver(str(row.pk))
        row.refresh_from_db()
        self.assertEqual(row.last_error, "recipient_no_longer_authorized")
        for offset, label in [
            (1, "Vencimento próximo"),
            (0, "Vencimento no dia"),
            (-1, "Compromisso atrasado"),
        ]:
            self.assertEqual(
                event_label(NotificationEvent(kind="deadline", snapshot={"offset": offset})), label
            )

    def test_attempt_destinations_preserved_after_contact_change(self):
        row = NotificationDelivery.objects.get(event__kind="assigned")
        with patch(
            "apps.notifications.tasks.EmailMultiAlternatives.send",
            side_effect=ConnectionRefusedError(),
        ):
            deliver(str(row.pk))
        old = self.executor.email
        self.executor.email = "new-contact@agenda.invalid"
        self.executor.save()
        NotificationDelivery.objects.filter(pk=row.pk).update(
            next_attempt_at=timezone.now() - timedelta(seconds=1)
        )
        deliver(str(row.pk))
        row.refresh_from_db()
        self.assertEqual(row.status, "accepted")
        self.assertEqual(row.history.get(number=1, stage="started").recipient_email, old)
        self.assertEqual(
            row.history.get(number=2, stage="accepted").recipient_email,
            "new-contact@agenda.invalid",
        )
