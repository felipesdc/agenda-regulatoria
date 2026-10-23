# ADR 0003 — Toolchain e ambiente
Aceita. Django 5.2 LTS com Python 3.12; Angular 21 com Node 22. Node local permite verificar sem substituir versão global. PostgreSQL 17 no Compose/CI; SQLite somente fallback explicitamente habilitado localmente e não valida concorrência PostgreSQL. Lockfiles versionados. Assets Swagger locais via sidecar; redis/mailpit preparados sem workers antes da Fase 5.
