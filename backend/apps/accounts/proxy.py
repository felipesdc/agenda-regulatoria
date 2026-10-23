"""Trust only a gateway-overwritten IP header on an isolated backend."""

from ipaddress import ip_address
from django.conf import settings


def client_ip(request):
    fallback = request.META.get("REMOTE_ADDR")
    if not getattr(settings, "TRUST_PROXY_HTTPS", False):
        return fallback
    value = request.META.get("HTTP_X_AGENDA_CLIENT_IP", "")
    try:
        return str(ip_address(value))
    except ValueError:
        return fallback
