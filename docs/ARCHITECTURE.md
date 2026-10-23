# Arquitetura
Monólito modular Django/DRF + SPA Angular servida por Nginx na mesma origem. PostgreSQL é a fonte de verdade; Redis e Mailpit estão preparados para a Fase 5. Sessão de servidor com cookie HTTP-only e CSRF evita persistir tokens no browser. Frontend consulta perfil e unidades autorizadas, nunca decide a autorização do backend.

Módulos atuais: `accounts` (identidade, sessão, papéis), `organizations` (estrutura), `commitments` (catálogos, definições, ocorrências, serviços transacionais e workflow) e `audit` (eventos protegidos). Módulos futuros surgirão quando houver código correspondente. Angular usa signals e formulários reativos, sem biblioteca global de estado. Componentes visuais SCSS locais equivalem ao layout básico solicitado; não foi adicionado Angular Material nesta fase.

Django 5.2 LTS suporta Python 3.12: https://docs.djangoproject.com/en/5.2/releases/5.2/. Angular 21 requer Node >=20.19 ou >=22.12: https://angular.dev/reference/versions. Toolchain local usa Node 22; verificar ciclo de suporte a cada atualização.

Swagger usa `drf-spectacular-sidecar`: assets locais copiados para Nginx. API é versionada e paginada. Health testa processo e readiness verifica conexão DB. Não mede filas nesta fase. Ver ADRs para justificativas.

Serviços de domínio centralizam operações com atomic e select_for_update. Views filtram escopo antes da consulta de objeto e não expõem CRUD genérico de status/histórico. Prefetch das atribuições e cache de papéis por resposta reduzem consultas repetidas na lista. Componente Angular de compromissos é separado do shell e usa contratos TypeScript, formulários reativos e dados paginados.

Fase 3: calendar_filters centraliza validação/filtros compartilhados por calendário e drilldown. calendar_views agrega no PostgreSQL e amostra por janela, com subquery de IDs para deduplicar relações. SPA usa utilitários puros de datas e componente Calendar; Commitments tem modo detail reutilizado no dialog para manter um único workflow de UI. Favoritos são preferências JSON com proprietário relacional e escopo aplicado a cada leitura.

## Recorrência
Motor puro `commitments/recurrence_engine.py`, API de regra/prévia/feriados e serviços transacionais separados. A definição é o lock de geração; constraints garantem data nominal/ordinal únicos. Regras versionadas incluem snapshot do calendário. Geração limitada do período completo na criação/extensão e comando idempotente de reprocessamento; nenhum worker periódico nesta fase. Detalhes e limites em PHASE4.md.

## Notificações (Fase 5)
Aplicação modular `notifications`, outbox no mesmo PostgreSQL e transação do evento de negócio. Beat despacha IDs via Redis; worker faz claim com lock, envia fora da transação de banco e registra o resultado. Polling recupera falhas de publish; lease perdido produz resultado incerto, sem resend automático. Tentativas e eventos imutáveis, estados/políticas auditados. Ver PHASE5.md para semântica SMTP e operação.

## Campos dinâmicos (Fase 6)
apps.customfields contém catálogo relacional, publicações imutáveis e validação limitada dos treze tipos. Definições/ocorrências possuem versão FK PROTECT e valores JSONB adicionais; autorização/workflow permanecem estruturados. Publicações copiam os metadados e são protegidas por triggers. Ver ADR-0007 e PHASE6.md.

## Fase 7 — Relatórios
apps.reports reutiliza scoped_occurrences e CalendarFilters, normaliza IDs antes de agregar, calcula métricas no banco e pagina grupos/ocorrências. Favoritos privados relacionais; exportações CSV/OOXML síncronas limitadas, auditadas e privadas. Frontend Reports atende painel/consulta, reutilizando detalhes existentes. Ver ADR-0008 e PHASE7.md.

## Fase 8
Escopo/filtros de responsável com EXISTS, relatórios sem materialização duplicada, índices e readiness de schema. Proxy DNS dinâmico, confiança explícita do gateway, perfil institucional independente, TLS PostgreSQL configurável. Operação/testes isolados em tools; app continua monólito. Ver ADR-0009/PHASE8/RELEASE/RECOVERY.
