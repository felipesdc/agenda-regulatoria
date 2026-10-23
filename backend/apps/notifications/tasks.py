import errno
import logging
import smtplib
from celery import shared_task
from django.core.mail import EmailMultiAlternatives
from django.conf import settings
from django.template.loader import render_to_string
from django.utils import timezone
from apps.commitments.models import CommitmentOccurrence
from .models import NotificationDelivery, NotificationJob
from .services import claim, finish, recover_expired, scan_deadlines, event_label, internal_link

logger = logging.getLogger(__name__)


def classify_error(error):
    # Never store SMTP text: it can contain credentials or sensitive recipient data.
    if isinstance(error, smtplib.SMTPAuthenticationError):
        return "failed", "smtp_authentication_failed"
    if isinstance(error, smtplib.SMTPRecipientsRefused):
        codes = [v[0] for v in error.recipients.values()]
        return (
            "retry" if codes and all(400 <= code < 500 for code in codes) else "failed"
        ), "smtp_recipient_refused"
    if isinstance(error, smtplib.SMTPResponseException):
        return (
            "retry" if 400 <= error.smtp_code < 500 else "failed"
        ), f"smtp_response_{error.smtp_code}"
    if isinstance(error, ConnectionRefusedError) or (
        isinstance(error, OSError)
        and error.errno in [errno.ECONNREFUSED, errno.ENETUNREACH, errno.EHOSTUNREACH]
    ):
        return "retry", "smtp_connection_unavailable"
    if isinstance(error, (TimeoutError, smtplib.SMTPServerDisconnected, OSError)):
        return "unknown", "smtp_result_uncertain"
    return "failed", "smtp_error"


@shared_task(acks_late=True, ignore_result=True)
def deliver(delivery_id):
    delivery = claim(delivery_id)
    if not delivery:
        return
    try:
        context = {
            "event": delivery.event.snapshot,
            "kind": event_label(delivery.event),
            "recipient": delivery.recipient.get_full_name() or delivery.recipient.username,
            "link": internal_link(delivery.event),
            "status_label": dict(CommitmentOccurrence.Status.choices).get(
                delivery.event.snapshot["status"], delivery.event.snapshot["status"]
            ),
        }
        subject = f"[Agenda Regulatória] {event_label(delivery.event)} · {delivery.event.snapshot['identifier']}"
        message = EmailMultiAlternatives(
            subject,
            render_to_string("notifications/message.txt", context),
            settings.DEFAULT_FROM_EMAIL,
            [delivery.recipient_email],
            headers={
                "Message-ID": delivery.message_id,
                "X-Agenda-Event-ID": str(delivery.event_id),
            },
        )
        message.attach_alternative(
            render_to_string("notifications/message.html", context), "text/html"
        )
        sent = message.send(fail_silently=False)
        status, error = ("accepted", "") if sent == 1 else ("failed", "smtp_did_not_accept")
    except (smtplib.SMTPException, OSError) as exc:
        status, error = classify_error(exc)
    finish(delivery.pk, delivery.attempts, status, error)
    logger.info(
        "notification_result id=%s status=%s attempt=%s", delivery.pk, status, delivery.attempts
    )


@shared_task(ignore_result=True)
def dispatch():
    now = timezone.now()
    for pk in NotificationDelivery.objects.filter(
        status="sending", lease_until__lte=now
    ).values_list("pk", flat=True)[:100]:
        recover_expired(pk)
    ids = list(
        NotificationDelivery.objects.filter(
            status__in=["pending", "retry"], next_attempt_at__lte=now
        )
        .order_by("next_attempt_at", "id")
        .values_list("pk", flat=True)[:100]
    )
    for pk in ids:
        try:
            deliver.delay(str(pk))
        except Exception:
            logger.warning("notification_publish_failed id=%s; durable outbox retained", pk)
            return
    NotificationJob.objects.update_or_create(
        name="dispatch", defaults={"last_success_at": timezone.now(), "processed": len(ids)}
    )


@shared_task(ignore_result=True)
def deadlines():
    return scan_deadlines()
