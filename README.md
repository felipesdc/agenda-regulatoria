# Agenda Regulatória
Aplicação corporativa em construção incremental. **Fases 1 a 8 implementadas e verificadas localmente:** autenticação, escopos por unidade, cadastro/atribuições, providências, workflow, auditoria e calendário mensal/semanal/anual com filtros e favoritos. Recorrência versionada, feriados e geração idempotente implementados. Notificações com outbox, Celery/Redis, SMTP e políticas de alerta implementadas. Campos dinâmicos com treze tipos, formulários por categoria e valores versionados implementados. Evidências ainda são uma extensão pendente. Veja [plano](docs/PLAN.md).

## Requisitos
Docker Engine + Compose v2 para o ambiente completo; ou Python 3.12 e Node 22.12+ para execução local. Não usa CDN em runtime. Downloads são necessários na preparação das imagens/dependências; para intranet isolada, preparar artefatos em ambiente conectado autorizado.

## Ambiente completo
1. Copie `.env.example` para `.env`.
2. Preencha `DJANGO_SECRET_KEY` com segredo aleatório (`python3 -c "import secrets; print(secrets.token_urlsafe(64))"`), `POSTGRES_PASSWORD` e `DEMO_PASSWORD` forte. Não versionar `.env`.
3. Execute `docker compose up --build -d`.
4. Execute `docker compose exec backend python manage.py seed_foundation` e `docker compose exec backend python manage.py seed_commitments`.
5. Abra http://localhost:8080. Mailpit: http://localhost:8025. Swagger após login: http://localhost:8080/api/v1/docs/.

Contas fictícias: `admin`, `demandante1` a `demandante3`, `demandado1` a `demandado6`. A senha vem de `DEMO_PASSWORD`. O seed é transacional/idempotente e não modifica senhas existentes. Para outras contas use `createsuperuser` ou provisionamento controlado; Usuários, papéis e unidades possuem administração auditada no Django Admin.

## Execução local sem Docker
```sh
python3 -m venv .venv
.venv/bin/pip install -r backend/requirements.txt
export DJANGO_SECRET_KEY="$(python3 -c 'import secrets; print(secrets.token_urlsafe(64))')"
export DJANGO_DEBUG=true DATABASE_ENGINE=sqlite
# Informe uma senha forte, sem colocar segredo no código:
read -s DEMO_PASSWORD
export DEMO_PASSWORD
.venv/bin/python backend/manage.py migrate
.venv/bin/python backend/manage.py seed_foundation
.venv/bin/python backend/manage.py seed_commitments
.venv/bin/python backend/manage.py runserver 127.0.0.1:8000
```
Em outro terminal:
```sh
cd frontend
npm ci
npm start
```
Abra http://localhost:4200. Caso o Node global seja antigo, o pacote `node` instalado pelo projeto permite `./node_modules/.bin/node node_modules/@angular/cli/bin/ng.js serve --proxy-config proxy.conf.json`. SQLite é alternativa explícita de desenvolvimento/testes, nunca produção. Para PostgreSQL local remova `DATABASE_ENGINE` e configure variáveis `POSTGRES_*`.

## Verificação
```sh
export DJANGO_SECRET_KEY=test-only-not-production DJANGO_DEBUG=true DATABASE_ENGINE=sqlite
cd backend
../.venv/bin/coverage run --rcfile=../pyproject.toml manage.py test
../.venv/bin/coverage report --rcfile=../pyproject.toml
../.venv/bin/python manage.py makemigrations --check --dry-run
cd ..
.venv/bin/ruff check backend
.venv/bin/ruff format --check backend
cd frontend
npm run typecheck
npm run build
```
Consulte [arquitetura](docs/ARCHITECTURE.md), [segurança](docs/SECURITY.md), [testes](docs/TESTING.md) e [implantação](docs/DEPLOYMENT.md).

Resultados executados estão em [TESTING.md](docs/TESTING.md). Testes funcionais: `DEMO_PASSWORD` deve corresponder ao seed, então `cd frontend` e `npm run test:e2e` após instalar Chromium com Playwright.

Veja [entrega da Fase 2](docs/PHASE2.md) para regras, uso e limitações. Para testar PostgreSQL: `docker compose exec backend python manage.py test --noinput`.

Calendário e limitações documentados em [PHASE3.md](docs/PHASE3.md).

Recorrência, feriados, prévia e alterações de séries: [PHASE4.md](docs/PHASE4.md). Containers locais atualizados pela implementação.

Notificações, fila e SMTP: [PHASE5.md](docs/PHASE5.md). Menu **Notificações**; captura local em Mailpit (http://localhost:8025). Para e-mails fictícios ausentes das contas de demonstração, execute `docker compose exec backend python manage.py seed_notification_demo`.

## Fase 6 — Campos personalizados
Administrador: abra **Campos personalizados**, cadastre campos e publique um formulário por categoria. O cadastro e a edição renderizam os campos dinamicamente, preservando a versão e os valores históricos. Treze tipos, validação no backend e auditoria. Veja [PHASE6.md](docs/PHASE6.md).

## Fase 7 — Gestão e relatórios
O Painel inicial apresenta indicadores reais do seu escopo. Abra **Relatórios** para consultar por vencimento, combinar filtros, salvar favoritos e exportar CSV/XLSX com auditoria. Administradores podem editar entidades/categorias justificadamente. Ver [PHASE7.md](docs/PHASE7.md) para fórmulas e limites.

## Fase 8 — Robustez e entrega
Regressão funcional/segurança/axe e carga HTTP isolada, consultas/indexação otimizadas, dump/restauração em cópia e ensaio HTTPS com papel de banco sem DDL. Execute `python3 tools/backup.py --restore-check`; não restaura sobre sua base. Para intranet, [RELEASE.md](docs/RELEASE.md), [RECOVERY.md](docs/RECOVERY.md) e [PHASE8.md](docs/PHASE8.md) descrevem perfil separado, resultados e pendências de homologação. A configuração local permanece em compose.yaml/.env.

## Continuidade da navegação
As listas de compromissos preservam a última consulta aplicada e a página ao alternar seções, durante a sessão da aba. A paginação respeita os filtros aplicados; logout limpa esse estado. Detalhes em [NAVIGATION.md](docs/NAVIGATION.md).

Cada seção possui sua própria URL, como `/calendario`, `/compromissos` e `/relatorios`, com suporte a atualização, favoritos do navegador e voltar/avançar. Rotas protegidas verificam a sessão e áreas administrativas exigem administrador. Links antigos de notificações continuam funcionando. Mapa de rotas e comportamento de sessão em [NAVIGATION.md](docs/NAVIGATION.md).
