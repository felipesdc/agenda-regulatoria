# Plano incremental e situação
## Fase 1 — Fundação (implementada; validação local descrita em TESTING.md)
- Angular 21 standalone, TypeScript estrito, SCSS e formulários reativos.
- Django 5.2 LTS, DRF, sessões, CSRF e limitação persistente de login.
- Usuários UUID, unidades hierárquicas, associação de papéis por unidade.
- Migrations, PostgreSQL no Compose, testes locais com SQLite explícito.
- Layout responsivo, login, perfil e unidades autorizadas reais.
- OpenAPI, Swagger local, health/readiness, seed e CI.
## Fase 2 — Núcleo de compromissos (implementada; ver PHASE2.md)
Entidades/categorias, unidades e administração auditada, definições/ocorrências separadas, sequência transacional REG, atribuições, providências, workflow, segregação executor/validador, snapshots e auditoria append-only. Testes de aprovação, rejeição, isolamento, edição histórica e concorrência em PostgreSQL; UI funcional desktop/mobile.
## Fase 3 — Calendário (implementada; ver PHASE3.md)
Mês/semana/ano preservando contexto, consultas agregadas e limitadas ao período, amostras e drilldown paginado, filtros combinados, favoritos por usuário, modal reutilizando workflow e layout responsivo. Periodicidades ampliadas na Fase 4; horários ainda não definidos.
## Fase 4 — Recorrência (implementada; ver PHASE4.md)
Motor determinístico, dez frequências, regras mensais/semanais, dias úteis, calendários nacional/institucional, exceções e prévia. Geração transacional limitada, idempotência por data nominal, versões append-only e mudanças de séries preservando execução/história. Comando de reprocessamento; geração inicial materializa o período completo.
## Fase 5 — Notificações (implementada; ver PHASE5.md)
Outbox transacional, Celery/Redis e Beat, eventos de negócio, políticas por categoria/compromisso com dias úteis/corridos, retry/backoff durável, templates HTML/texto, monitor pessoal/admin, auditoria e reprocessamento justificado. Aceitação SMTP distinguida de entrega/resultado incerto; Mailpit local.
## Fase 6 — Campos dinâmicos (implementada; ver PHASE6.md)
Catálogo administrativo auditado, treze tipos validados, formulários imutáveis por categoria, UI reativa no cadastro/edição, valores JSONB vinculados à versão original e preservação em snapshots/recorrência. Campos essenciais permanecem relacionais.
## Fase 7 — Gestão e relatórios (implementada; ver PHASE7.md)
Painel autorizado, atenção imediata, pesquisa/filtros combinados, grupos/listas paginados, favoritos pessoais auditados, métricas com denominadores e tempos definidos, CSV/XLSX limitados e auditados, edição justificada de entidades/categorias.
## Fase 8 — Robustez (implementada e verificada localmente; ver PHASE8.md)
Regressão, concorrência de revisão/outbox, carga HTTP isolada, segurança de sessão/gateway/roles, axe/teclado, backup/restauração e ensaio HTTPS. Perfil de intranet/runbooks preparados; homologação institucional, SSO/SMTP/anexos/antivírus e metas formais seguem RELEASE.md.
## Premissas e decisões pendentes
- Administrador global = superusuário explícito; demandante/demandado são papéis acumuláveis por unidade.
- Não há herança de acesso de unidade pai; unidade inativa bloqueia o escopo.
- Nenhuma credencial embutida; seed só cria senhas a partir do ambiente e não redefine contas existentes.
- Não se presume calendário legal, obrigação real ou política corporativa de retenção.
- Antes da produção, instituição deve definir provedor SSO, matriz de permissões administrativas, retenção, armazenamento/antivírus e metas de recuperação/disponibilidade.
- Segregação será obrigatória por padrão na Fase 2; exceções exigem decisão corporativa explícita.
- Redis/Mailpit, worker Celery e scheduler Beat ativos na Fase 5. SMTP corporativo e bounces dependem da implantação institucional.

### Anexos comprobatórios — 30/10/2026
Implementados upload em providências, arquivos privados no PostgreSQL, validação estrutural, SHA-256, download autorizado, retirada lógica, auditoria, proteção append-only e inclusão na recuperação. Interface Django Storage preparada para adaptadores privados; apenas o backend de banco está implementado e verificado. Integração clamd com bloqueio obrigatório fora de DEBUG; scanner/retenção/homologação corporativos permanecem como requisitos institucionais de RELEASE.md. Ver [EVIDENCE.md](EVIDENCE.md).

## Evolução: backup automatizado

Comando agendável com restauração isolada obrigatória, lock, status e retenção conservadora implementado; modelos systemd e cron descritos em RECOVERY.md. Ativação do agendamento, cópia fora do host, alertas e homologação de RPO/RTO dependem da infraestrutura operacional.
