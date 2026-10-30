# Verificação — Fases 1 e 2
Story: demandante cadastra/atribui pela SPA → API valida escopo e grava PostgreSQL com auditoria → demandado executa → demandante rejeita/aprova → interface mostra história preservada.

| Fronteira | Evidência executada |
|---|---|
| Browser → Nginx | Playwright desktop/mobile usa http://localhost:8080 com CSS/JS e CSP de produção do frontend |
| Cliente → API | Login/sessão/CSRF reais em todas as ações |
| API → PostgreSQL | Migrations/seed, 30 testes e concorrência de identificadores |
| Mutação → auditoria | Eventos na mesma transação; rollback testado quando auditoria falha |
| Dados → UI | Compromisso, providências, rejeição, nova providência, aprovação e história |
| Autorização | Outra unidade não encontra registro; backend confirma 404 e bloqueios de papéis |
| História | Edição/DELETE comuns impedidos por triggers, sem endpoint de exclusão |

Resultado: 30 testes backend e 4 testes funcionais aprovados, schema/lint/tipos/build/migrations aprovados. Cobertura 99% no conjunto medido. Proteção SQL é contra operações comuns; não contra DBA/DDL/TRUNCATE. Sem testes de SMTP, recorrência ou carga nesta fase. Screenshots e resultados estão descritos em TESTING.md.

Corrigidos durante validação: labels acessíveis de navegação e fechamento das conexões do teste concorrente. Correção de CSS/CSP da Fase 1 permanece: inlineCritical desativado para evitar onload inline bloqueado.

## Fase 3 — Calendário
Fluxo verificado: SPA solicita somente o período → queryset autorizado → PostgreSQL agrupa e amostra → calendário apresenta contagens/cartões → drilldown pagina e modal reutiliza ações da Fase 2. API de favoritos fixa owner no servidor; UUID de favorito de outro usuário não é acessível.

37 testes backend aprovados no PostgreSQL e 8 testes Playwright aprovados, incluindo utilitários de datas. Testes funcionais incluem três escalas, navegação/Hoje, contagens, três cartões e itens adicionais, filtros combinados, favoritos, detalhes e regressão das fases anteriores. Grade desktop/mobile examinada em screenshots calendar-desktop.png e calendar-mobile.png. Rótulo acessível Hoje passou a ser posicionado dentro do botão, evitando overflow do documento no celular; teste de largura foi incluído. Horários, recorrência, carga e certificação WCAG permanecem fora desta entrega.

## Fase 4 — Recorrência
Fluxo: formulário/prévia autenticados → regra validada → definição bloqueada no PostgreSQL → geração + atribuições + versões + auditoria na mesma transação → lista/calendário/detalhe. Extensão da regra e geração são atômicas; concluídos e execução iniciada são preservados na mudança coletiva. Feriados são copiados para a versão e não recalculam retrospectivamente datas.

53 testes backend passaram, incluindo concorrência real no PostgreSQL; cobertura do motor 100%, conjunto crítico 98%. Schema/migrations/lint/tipos/build aprovados. Nova funcionalidade verificada por Playwright nas duas larguras e screenshot mobile. Sem ensaios de carga, calendário legal importado ou agendador periódico; geração inicial é completa dentro dos limites definidos em PHASE4.md.

Rodada final de navegador: 10/10 aprovados com os containers finais. Corrigidos rótulo acessível de periodicidade e botão de edição habilitado durante carregamento. PostgreSQL/backend saudáveis; frontend atualizado em http://localhost:8080.

## Fase 5 — Notificações
Fluxo completo verificado: sessão/CSRF → criação/política → evento e outbox transacionais no PostgreSQL → despacho Redis → claim único Celery → SMTP Mailpit → persistência da aceitação/tentativas → consulta pessoal/admin e link interno autorizado. Falha de broker mantém outbox; falha de conexão SMTP real agenda retry; timeout/worker perdido produzem resultado incerto. Falha de banco depois de aceitação não inicia automaticamente outro envio.

Resultado final: 78/78 testes PostgreSQL e 12/12 Playwright aprovados; conjunto crítico 98%. OpenAPI, migrations, lint, formato, tipos e build aprovados. Uma mensagem de atribuição por evento no Mailpit, multipart e link verificados nas duas larguras. O servidor confirmou aceitação SMTP; entrega em caixa postal permanece não confirmada. SMTP corporativo/DSN/carga não certificados nesta fase. Screenshots e limites em TESTING.md e PHASE5.md.

## Fase 6 — Campos dinâmicos

Fluxo verificado: administrador/sessão/CSRF → campo auditado → publicação de metadados imutáveis por categoria → demandante/carregamento do schema → preenchimento dos treze tipos → validação backend → JSONB/FK em definição e ocorrência → edição justificada/snapshot/auditoria → republicação preservando interpretação original → isolamento por unidade. Recorrência mantém formulário/valores originais e edições independentes.

Resultado final: **90/90 PostgreSQL, 14/14 Playwright, 97% do conjunto crítico medido**. SQLite 90 testes com quatro skips específicos de PostgreSQL. OpenAPI, migrations, lint, formato, tipos e build aprovados. Containers locais atualizados; frontend http://localhost:8080. Detalhe mobile examinado e layout sem overflow nas duas larguras. Contratos/limitações em PHASE6.md e decisão em ADR-0007-dynamic-form-versions.md. Não há adoção/migração automática de formulários em registros antigos; a próxima etapa é gestão e relatórios.

## Fase 7 — Gestão e relatórios

Fluxo verificado: sessão/escopo → painel autorizado → filtros combinados por vencimento → agregação sem duplicação → paginação → favorito pessoal auditado → exportações CSV/XLSX com autorização reaplicada e auditoria/hash → downloads reais → detalhe mantendo consulta → catálogo administrativo justificado/auditado. Unidades não autorizadas ficam fora de resultados/arquivos; unidade inativa bloqueia escopo.

Resultado final: **103/103 PostgreSQL, 16/16 Playwright e 97% do conjunto crítico**. SQLite 103 com quatro skips específicos de PostgreSQL. Lint, formato, tipos, OpenAPI, migrations e build aprovados. Backend/PostgreSQL/Redis/worker/Mailpit saudáveis; scheduler/frontend em execução. Sistema atualizado em http://localhost:8080, painel inicial e menu Relatórios. Fórmulas, denominadores, isolação e limites de exportação em PHASE7.md; decisão em ADR-0008-scoped-reporting.md. Próxima etapa: robustez, incluindo carga/segurança/acessibilidade/recuperação, sem certificação antecipada desses itens.

## Fase 8 — Entrega local para homologação

**113 PostgreSQL, 20 Playwright e 97% do conjunto crítico** aprovados. SQLite 113/cinco skips específicos; tipos/build/lint/formato/OpenAPI/migrations/Compose aprovados. Dependências sem avisos conhecidos nesta consulta. Backup/restore em cópia, oito proteções históricas e retenção auditada da outbox restaurada verificados. Ensaio HTTPS real com CA temporária, cookies seguros, login, backend read-only e DB runtime sem DDL; source preservada.

Carga HTTP isolada com 100 clientes/100000 ocorrências e variante de 40000 transições passou sem erros; p95 com histórico até 6,919 s, a homologar no alvo. Fonte de resultados em PHASE8_RESULTS.json; critérios/limites em PHASE8.md. Todos os recursos de teste temporários removidos. Aplicação local saudável em http://localhost:8080; intranet institucional não foi ativada. SSO/certificados/SMTP/anexos/antivírus/retenção/RPO/RTO/manual WCAG/pentest/HA exigem o processo RELEASE.md/RECOVERY.md.

## Melhoria incremental — Continuidade das consultas (29/10/2026)

Listas restauram última consulta aplicada/página por usuário/modo ao retornar de outra seção. Recarregam os dados/autorização no backend; logout limpa a memória da aba. Paginação não aplica rascunhos implicitamente e se recupera de página inválida. Regressores: 22/22 navegador e 114/114 PostgreSQL; tipos/build/lint/formato/OpenAPI/migrations aprovados. Scanner de alertas passou a bloquear apenas a ocorrência, corrigindo bloqueio indevido de unidade/demandante. Documentação em NAVIGATION.md.
