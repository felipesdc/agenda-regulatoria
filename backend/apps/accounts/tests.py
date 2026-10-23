from django.test import SimpleTestCase, override_settings
import json
from unittest.mock import patch
from django.test import TestCase, Client
from django.db import IntegrityError, transaction
from django.urls import reverse
from .models import User, Membership
from .permissions import has_role, visible_units
from apps.organizations.models import OrganizationalUnit


class FoundationTests(TestCase):
    def setUp(self):
        self.password = "Local-test-Complex!739"
        self.user = User.objects.create_user("executor", password=self.password)
        self.admin = User.objects.create_superuser("admin", password=self.password)
        self.parent = OrganizationalUnit.objects.create(code="P", name="Parent")
        self.unit = OrganizationalUnit.objects.create(code="A", name="Alpha", parent=self.parent)
        self.other = OrganizationalUnit.objects.create(code="B", name="Beta")
        Membership.objects.create(user=self.user, unit=self.unit, role="executor")

    def test_scope_no_hierarchy_inheritance(self):
        self.assertEqual(list(visible_units(self.user)), [self.unit])
        self.assertTrue(has_role(self.user, self.unit.pk, "executor"))
        self.assertFalse(has_role(self.user, self.unit.pk, "requester"))
        self.assertFalse(has_role(self.user, self.parent.pk, "executor"))
        self.assertEqual(visible_units(self.admin).count(), 3)
        self.assertTrue(has_role(self.admin, self.other.pk, "requester"))

    def test_anonymous_and_inactive(self):
        from django.contrib.auth.models import AnonymousUser

        self.assertFalse(has_role(AnonymousUser(), self.unit.pk, "executor"))
        self.assertEqual(visible_units(AnonymousUser()).count(), 0)
        self.user.is_active = False
        self.user.save()
        self.assertEqual(visible_units(self.user).count(), 0)
        self.assertFalse(has_role(self.user, self.unit.pk, "executor"))

    def test_inactive_unit(self):
        self.unit.active = False
        self.unit.save()
        self.assertFalse(has_role(self.user, self.unit.pk, "executor"))
        self.assertEqual(visible_units(self.user).count(), 0)

    def test_duplicate_role(self):
        with self.assertRaises(IntegrityError), transaction.atomic():
            Membership.objects.create(user=self.user, unit=self.unit, role="executor")
        Membership.objects.create(user=self.user, unit=self.unit, role="requester")

    def test_login_csrf_logout(self):
        client = Client(enforce_csrf_checks=True)
        data = {"username": "executor", "password": self.password}
        self.assertEqual(
            client.post(
                "/api/v1/auth/login/", data=data, content_type="application/json"
            ).status_code,
            403,
        )
        client.get("/api/v1/auth/csrf/")
        response = client.post(
            "/api/v1/auth/login/",
            data=data,
            content_type="application/json",
            HTTP_X_CSRFTOKEN=client.cookies["csrftoken"].value,
        )
        self.assertEqual(response.status_code, 200)
        self.assertTrue(client.cookies["sessionid"]["httponly"])
        self.assertEqual(client.get("/api/v1/auth/me/").json()["username"], "executor")
        self.assertEqual(client.get("/api/v1/units/").json()["count"], 1)
        self.assertEqual(client.get("/api/v1/users/").status_code, 403)
        self.assertEqual(
            client.post("/api/v1/auth/logout/", {}, content_type="application/json").status_code,
            403,
        )
        self.assertEqual(
            client.post(
                "/api/v1/auth/logout/",
                {},
                content_type="application/json",
                HTTP_X_CSRFTOKEN=client.cookies["csrftoken"].value,
            ).status_code,
            200,
        )
        self.assertEqual(client.get("/api/v1/auth/me/").status_code, 403)

    def test_invalid_inputs(self):
        for payload in [
            "broken",
            "[]",
            '{"username":5,"password":"x"}',
            '{"username":"x","password":false}',
        ]:
            self.assertEqual(
                self.client.post(
                    "/api/v1/auth/login/", payload, content_type="application/json"
                ).status_code,
                400,
            )
        for username in ["executor", "unknown"]:
            response = self.client.post(
                "/api/v1/auth/login/",
                json.dumps({"username": username, "password": "wrong"}),
                content_type="application/json",
            )
            self.assertEqual(response.status_code, 401)
            self.assertNotIn(username, response.json()["detail"])

    def test_lockout(self):
        for _ in range(5):
            self.client.post(
                "/api/v1/auth/login/",
                {"username": "executor", "password": "wrong"},
                content_type="application/json",
            )
        self.assertEqual(
            self.client.post(
                "/api/v1/auth/login/",
                {"username": "executor", "password": self.password},
                content_type="application/json",
            ).status_code,
            429,
        )

    def test_admin_listing_and_schema(self):
        self.client.force_login(self.admin)
        self.assertEqual(self.client.get("/api/v1/users/").json()["count"], 2)
        self.assertEqual(self.client.get(reverse("schema")).status_code, 200)
        self.assertEqual(self.client.get("/api/v1/docs/").status_code, 200)

    def test_health_readiness(self):
        self.assertEqual(self.client.get("/health/").status_code, 200)
        self.assertEqual(self.client.get("/ready/").status_code, 200)
        with patch("apps.accounts.views.connection.cursor", side_effect=RuntimeError()):
            self.assertEqual(self.client.get("/ready/").status_code, 503)

    def test_seed_idempotent_preserves_password(self):
        import os
        from django.core.management import call_command

        with patch.dict(os.environ, {"DEMO_PASSWORD": self.password}):
            call_command("seed_foundation", verbosity=0)
            call_command("seed_foundation", verbosity=0)
        self.assertEqual(User.objects.filter(username__startswith="demandante").count(), 3)
        self.assertEqual(User.objects.filter(username__startswith="demandado").count(), 6)
        with patch.dict(os.environ, {"DEMO_PASSWORD": "Another-strong-password!773"}):
            call_command("seed_foundation", verbosity=0)
        self.assertTrue(User.objects.get(username="demandado1").check_password(self.password))

    def test_seed_requires_external_valid_password(self):
        import os
        from django.core.management import call_command, CommandError

        for password in ["", "123"]:
            with patch.dict(os.environ, {"DEMO_PASSWORD": password}):
                with self.assertRaises(CommandError):
                    call_command("seed_foundation")

    def test_data_endpoints_require_session(self):
        for path in [
            "/api/v1/auth/me/",
            "/api/v1/units/",
            "/api/v1/users/",
            "/api/v1/docs/",
            "/api/v1/schema/",
        ]:
            self.assertEqual(self.client.get(path).status_code, 403)


class ProductionConfigurationTests(SimpleTestCase):
    def test_production_deploy_checks_and_explicit_configuration(self):
        import os
        import secrets
        import subprocess
        from pathlib import Path
        import sys

        backend = Path(__file__).resolve().parents[2]
        env = {
            **os.environ,
            "DJANGO_DEBUG": "false",
            "DATABASE_ENGINE": "postgresql",
            "DJANGO_SECRET_KEY": secrets.token_urlsafe(64),
            "DJANGO_ALLOWED_HOSTS": "agenda.intranet,backend",
            "CSRF_TRUSTED_ORIGINS": "https://agenda.intranet",
            "TRUST_PROXY_HTTPS": "true",
        }
        result = subprocess.run(
            [
                sys.executable,
                str(backend / "manage.py"),
                "check",
                "--deploy",
                "--fail-level",
                "ERROR",
            ],
            env=env,
            capture_output=True,
            text=True,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        import re

        self.assertEqual(set(re.findall(r"security\.(W\d+)", result.stderr)), {"W005", "W021"})
        for key, value in [
            ("DJANGO_SECRET_KEY", "short"),
            ("DJANGO_ALLOWED_HOSTS", "*"),
            ("CSRF_TRUSTED_ORIGINS", "http://agenda.intranet"),
        ]:
            result = subprocess.run(
                [sys.executable, str(backend / "manage.py"), "check"],
                env={**env, key: value},
                capture_output=True,
                text=True,
            )
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("ImproperlyConfigured", result.stderr)

    @override_settings(SECURE_SSL_REDIRECT=True, SECURE_PROXY_SSL_HEADER=None)
    def test_untrusted_forwarded_https_cannot_bypass_redirect(self):
        from django.test import Client

        response = Client().get("/health/", HTTP_X_FORWARDED_PROTO="https")
        self.assertEqual(response.status_code, 301)

    @override_settings(
        SECURE_SSL_REDIRECT=True, SECURE_PROXY_SSL_HEADER=("HTTP_X_FORWARDED_PROTO", "https")
    )
    def test_explicit_trusted_gateway_supports_https(self):
        from django.test import Client

        response = Client().get("/health/", HTTP_X_FORWARDED_PROTO="https")
        self.assertEqual(response.status_code, 200)


class GatewayClientIPTests(SimpleTestCase):
    @override_settings(TRUST_PROXY_HTTPS=False)
    def test_header_spoof_is_ignored_without_explicit_gateway_trust(self):
        from django.test import RequestFactory
        from .proxy import client_ip

        self.assertEqual(
            client_ip(
                RequestFactory().get(
                    "/", REMOTE_ADDR="192.0.2.1", HTTP_X_AGENDA_CLIENT_IP="192.0.2.2"
                )
            ),
            "192.0.2.1",
        )

    @override_settings(TRUST_PROXY_HTTPS=True)
    def test_trusted_gateway_requires_a_single_valid_ip(self):
        from django.test import RequestFactory
        from .proxy import client_ip

        for header, expected in [
            ("192.0.2.2", "192.0.2.2"),
            ("2001:db8::1", "2001:db8::1"),
            ("bad", "192.0.2.1"),
            ("192.0.2.2, 192.0.2.3", "192.0.2.1"),
        ]:
            self.assertEqual(
                client_ip(
                    RequestFactory().get(
                        "/", REMOTE_ADDR="192.0.2.1", HTTP_X_AGENDA_CLIENT_IP=header
                    )
                ),
                expected,
            )


class ReadinessSchemaTests(TestCase):
    def test_pending_migrations_do_not_report_readiness(self):
        from unittest.mock import patch
        from django.test import Client

        with patch("django.db.migrations.executor.MigrationExecutor") as executor:
            executor.return_value.migration_plan.return_value = [("pending", False)]
            self.assertEqual(Client().get("/ready/").status_code, 503)
        self.assertEqual(Client().get("/ready/").status_code, 200)
