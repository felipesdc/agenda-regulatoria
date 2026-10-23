#!/usr/bin/env python3
"""HTTPS/session/least-privilege rehearsal with temporary DB, role, containers, CA."""

import json
import os
import secrets
import ssl
import subprocess
import tempfile
import time
import uuid
from http.cookies import SimpleCookie
from pathlib import Path
from urllib.request import Request, urlopen
from backup import ROOT, DOCKER, BASE, command


def run(args, **kwargs):
    result = subprocess.run(
        args, cwd=ROOT, stdout=subprocess.PIPE, stderr=subprocess.PIPE, **kwargs
    )
    if result.returncode and args[1] == "run" and "--env-file" not in args:
        raise RuntimeError(result.stderr.decode()[:600])
    if result.returncode:
        raise RuntimeError("Comando isolado falhou; dados/segredos não foram impressos.")
    return result.stdout.decode().strip()


def sql(query, db):
    return run(
        BASE
        + [
            "sh",
            "-c",
            'exec psql -X -v ON_ERROR_STOP=1 -At -U "$POSTGRES_USER" -d "${1:-$POSTGRES_DB}"',
            "probe",
            db,
        ],
        input=query.encode(),
    )


def main():
    suffix = uuid.uuid4().hex
    target = "phase8_tls_" + suffix
    role = "phase8_app_" + suffix
    backend_name = "phase8-tls-back-" + suffix
    frontend_name = "phase8-tls-front-" + suffix
    created = False
    role_created = False
    containers = []
    with tempfile.TemporaryDirectory(prefix="agenda-intranet-", dir="/tmp") as directory:
        temp = Path(directory)
        try:
            command_result = command(
                'exec createdb -U "$POSTGRES_USER" "$1"', target, stdout=subprocess.PIPE
            )
            if command_result.returncode:
                raise RuntimeError("Base temporária não criada")
            created = True
            dump = temp / "copy.dump"
            with dump.open("wb") as output:
                if command(
                    'exec pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" -Fc', stdout=output
                ).returncode:
                    raise RuntimeError("Cópia falhou")
            with dump.open("rb") as source:
                if command(
                    'exec pg_restore --exit-on-error --no-owner --no-acl -U "$POSTGRES_USER" -d "$1"',
                    target,
                    stdin=source,
                    stdout=subprocess.PIPE,
                ).returncode:
                    raise RuntimeError("Restore falhou")
            password = secrets.token_urlsafe(32)
            sql(
                f"CREATE ROLE {role} LOGIN PASSWORD '{password}' NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION; GRANT CONNECT ON DATABASE {target} TO {role}; REVOKE CREATE ON SCHEMA public FROM PUBLIC; GRANT USAGE ON SCHEMA public TO {role}; GRANT SELECT,INSERT,UPDATE,DELETE ON ALL TABLES IN SCHEMA public TO {role}; GRANT USAGE,SELECT,UPDATE ON ALL SEQUENCES IN SCHEMA public TO {role};",
                target,
            )
            role_created = True
            backend_id = run([DOCKER, "compose", "ps", "-q", "backend"])
            networks = json.loads(
                run(
                    [
                        DOCKER,
                        "inspect",
                        "--format",
                        "{{json .NetworkSettings.Networks}}",
                        backend_id,
                    ]
                )
            )
            network = next(iter(networks))
            backend_image = run([DOCKER, "inspect", "--format", "{{.Config.Image}}", backend_id])
            frontend_id = run([DOCKER, "compose", "ps", "-q", "frontend"])
            frontend_image = run([DOCKER, "inspect", "--format", "{{.Config.Image}}", frontend_id])
            values = {
                "DJANGO_DEBUG": "false",
                "DJANGO_SECRET_KEY": secrets.token_urlsafe(64),
                "DJANGO_ALLOWED_HOSTS": "agenda.intranet,backend",
                "CSRF_TRUSTED_ORIGINS": "https://agenda.intranet",
                "TRUST_PROXY_HTTPS": "true",
                "POSTGRES_HOST": "db",
                "POSTGRES_PORT": "5432",
                "POSTGRES_DB": target,
                "POSTGRES_USER": role,
                "POSTGRES_PASSWORD": password,
                "SMTP_HOST": "smtp.intranet",
                "NOTIFICATION_BASE_URL": "https://agenda.intranet",
            }
            env = temp / "runtime.env"
            env.write_text("".join(k + "=" + v + "\n" for k, v in values.items()))
            os.chmod(env, 0o600)
            run(
                [
                    DOCKER,
                    "run",
                    "-d",
                    "--rm",
                    "--name",
                    backend_name,
                    "--network",
                    network,
                    "--read-only",
                    "--tmpfs",
                    "/tmp",
                    "--cap-drop",
                    "ALL",
                    "--security-opt",
                    "no-new-privileges:true",
                    "--env-file",
                    str(env),
                    backend_image,
                    "gunicorn",
                    "config.wsgi:application",
                    "--bind",
                    "0.0.0.0:8000",
                    "--workers",
                    "1",
                ]
            )
            containers.append(backend_name)
            run(
                [
                    "openssl",
                    "req",
                    "-x509",
                    "-newkey",
                    "rsa:2048",
                    "-nodes",
                    "-days",
                    "1",
                    "-subj",
                    "/CN=agenda.intranet",
                    "-addext",
                    "subjectAltName=DNS:localhost,DNS:agenda.intranet,IP:127.0.0.1",
                    "-keyout",
                    str(temp / "privkey.pem"),
                    "-out",
                    str(temp / "fullchain.pem"),
                ]
            )
            os.chmod(temp / "privkey.pem", 0o600)
            config = (
                (ROOT / "infrastructure/intranet/nginx.conf.template")
                .read_text()
                .replace("${INTRANET_HOST}", "agenda.intranet")
                .replace("http://backend:8000", "http://" + backend_name + ":8000")
            )
            (temp / "nginx.conf").write_text(config)
            run(
                [
                    DOCKER,
                    "run",
                    "-d",
                    "--rm",
                    "--name",
                    frontend_name,
                    "--network",
                    network,
                    "-p",
                    "127.0.0.1::443",
                    "-v",
                    str(temp / "nginx.conf") + ":/etc/nginx/conf.d/default.conf:ro",
                    "-v",
                    str(temp) + ":/etc/nginx/tls:ro",
                    frontend_image,
                ]
            )
            containers.append(frontend_name)
            port = run(
                [
                    DOCKER,
                    "inspect",
                    "--format",
                    '{{(index (index .NetworkSettings.Ports "443/tcp") 0).HostPort}}',
                    frontend_name,
                ]
            )
            context = ssl.create_default_context(cafile=str(temp / "fullchain.pem"))
            base = "https://127.0.0.1:" + port

            def fetch(path, headers=None, data=None):
                req = Request(
                    base + path, headers={"Host": "agenda.intranet", **(headers or {})}, data=data
                )
                return urlopen(req, context=context, timeout=10)

            for _ in range(60):
                try:
                    with fetch("/ready/") as r:
                        if r.status == 200:
                            break
                except Exception:
                    time.sleep(0.5)
            else:
                raise RuntimeError("HTTPS readiness falhou")
            with fetch("/") as r:
                hsts = r.headers.get("Strict-Transport-Security", "")
                csp = r.headers.get("Content-Security-Policy", "")
            if "max-age=31536000" not in hsts or "script-src 'self'" not in csp:
                raise RuntimeError("Headers HTTPS ausentes")
            with fetch("/api/v1/auth/csrf/") as r:
                cookie = SimpleCookie()
                cookie.load(r.headers.get("Set-Cookie"))
            csrf = cookie["csrftoken"].value
            if not cookie["csrftoken"]["secure"]:
                raise RuntimeError("CSRF cookie não é Secure")
            demo = None
            for line in (ROOT / ".env").read_text().splitlines():
                if line.startswith("DEMO_PASSWORD="):
                    demo = line.split("=", 1)[1].strip().strip("\"'")
            if not demo:
                raise RuntimeError("Demo password ausente")
            with fetch(
                "/api/v1/auth/login/",
                {
                    "Content-Type": "application/json",
                    "Origin": "https://agenda.intranet",
                    "Cookie": "csrftoken=" + csrf,
                    "X-CSRFToken": csrf,
                },
                json.dumps({"username": "demandante1", "password": demo}).encode(),
            ) as r:
                cookies = SimpleCookie()
                for value in r.headers.get_all("Set-Cookie"):
                    cookies.load(value)
            session = cookies["sessionid"]
            if not session["secure"] or not session["httponly"]:
                raise RuntimeError("Session cookie inseguro")
            with fetch("/api/v1/auth/me/", {"Cookie": "sessionid=" + session.value}) as r:
                profile = json.load(r)
            if profile["username"] != "demandante1" or profile.get("environment") != "intranet":
                raise RuntimeError("Sessão real não validada")

            run(
                [
                    DOCKER,
                    "exec",
                    backend_name,
                    "python",
                    "manage.py",
                    "hold_restored_outbox",
                    "--expected-database",
                    target,
                    "--reason",
                    "Isolated restore rehearsal",
                    "--apply",
                ]
            )

            def rejected(query):
                result = subprocess.run(
                    BASE
                    + [
                        "sh",
                        "-c",
                        'exec psql -X -v ON_ERROR_STOP=1 -At -U "$POSTGRES_USER" -d "$1"',
                        "probe",
                        target,
                    ],
                    cwd=ROOT,
                    input=(f"SET ROLE {role}; " + query).encode(),
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                )
                return result.returncode != 0

            if not rejected("DROP TRIGGER protect_history ON audit_auditevent;") or not rejected(
                "CREATE TABLE public.unauthorized(x int);"
            ):
                raise RuntimeError("Runtime conseguiu DDL")
            if not rejected(
                "UPDATE audit_auditevent SET reason=reason WHERE id=(SELECT id FROM audit_auditevent LIMIT 1);"
            ):
                raise RuntimeError("Auditoria alterável")
            print(
                json.dumps(
                    {
                        "tls_verified_with_temporary_ca": True,
                        "https_readiness": True,
                        "secure_csrf_cookie": True,
                        "secure_httponly_session": True,
                        "real_login": True,
                        "csp_hsts": True,
                        "runtime_ddl_blocked": True,
                        "history_update_blocked": True,
                        "recovered_outbox_held": True,
                        "source_database_untouched": True,
                    }
                )
            )
        finally:
            for name in reversed(containers):
                subprocess.run(
                    [DOCKER, "rm", "-f", name], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
                )
            if created:
                command('exec dropdb -U "$POSTGRES_USER" "$1"', target, stdout=subprocess.PIPE)
            if role_created:
                sql(f"DROP ROLE {role};", "")


if __name__ == "__main__":
    main()
