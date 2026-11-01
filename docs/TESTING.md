# Testes e evidências — Fase 1
Executados localmente em 09/10/2026 (America/Sao_Paulo):

| Verificação | Resultado |
|---|---|
| Django TestCase, SQLite explícito | 12 testes aprovados |
| Coverage permissions.py + views.py | 100%, 84 statements; mínimo configurado 80% |
| Playwright Chromium desktop 1440×900 | 1 teste aprovado |
| Playwright Chromium mobile 390×844 | 1 teste aprovado |
| Angular production build | aprovado; 192,61 kB raw / 53,56 kB estimados comprimidos |
| TypeScript estrito | aprovado |
| Ruff lint/format | aprovado |
| OpenAPI validate --fail-on-warn | aprovado |
| Migrations --check --dry-run | nenhuma alteração pendente |
| Seed + migrations locais | aprovados |
| npm audit na instalação | zero vulnerabilidades reportadas |

Backend cobre CSRF inclusive login/logout, sessão, respostas uniformes de credenciais inválidas, bloqueio de tentativas, autenticação obrigatória, escopo sem herança, unidade/usuário inativos, múltiplos papéis, constraint de duplicidade, administrador, health/readiness, schema, seed idempotente e proteção de senhas existentes.

Cobertura reportada é restrita à lógica de autorização/API da fundação; não significa cobertura do produto completo, dependências ou módulos futuros. Testes unitários de recorrência e workflow serão implementados junto às respectivas fases. Nenhum resultado de carga, conformidade WCAG ou auditoria externa foi medido.

## Reexecução
Veja README para backend e build. Para Playwright, iniciar backend e frontend contra banco local semeado, definir `DEMO_PASSWORD` correspondente ao seed e executar:
```sh
cd frontend
npx playwright install chromium
npm run test:e2e
```
Com Node global antigo:
```sh
./node_modules/.bin/node node_modules/@playwright/test/cli.js test
```
Screenshots desktop/mobile são gravadas em `tests/e2e/artifacts/` (ignoradas no Git). O teste faz login por UI, confere uma única unidade autorizada para demandado1, exibe papel e encerra sessão. Não usa mock de API.

## Limitações históricas da Fase 1 (resolvidas na validação da Fase 2)
Docker não disponível na máquina de validação: build das imagens, Compose, PostgreSQL, Redis e Mailpit não executados localmente. CI configura PostgreSQL real, migrations, backend, lint, coverage, OpenAPI e frontend; pipeline ainda não foi executado remotamente. Os 12 testes locais usaram SQLite e não comprovam concorrência PostgreSQL. Incluir teste end-to-end de Compose e smoke test SMTP antes da entrega operacional.

# Fase 2 — Resultados executados em 11/10/2026
| Verificação | Resultado |
|---|---|
| Backend no PostgreSQL 17 via Compose | 30 testes aprovados, sem skips |
| Concorrência PostgreSQL | 8 criações em 4 threads; identificadores únicos |
| Cobertura serviços/endpoints medidos | 99% total; serviços de compromissos 100% |
| Playwright contra Nginx/API/PostgreSQL reais | 4 testes aprovados: regressão e workflow, desktop/mobile |
| Build Angular em Docker | aprovado |
| TypeScript estrito | aprovado |
| Ruff lint/format | aprovado |
| OpenAPI validado sem warnings | aprovado |
| Migrations --check | nenhuma mudança pendente |
| Migrations/seed Fase 2 no PostgreSQL | executados |

O teste de workflow cria um registro fictício, edita com motivo, registra execução, rejeita, complementa providências, aprova, verifica bloqueio de edição, consulta auditoria como administrador e confirma invisibilidade a demandante de outra unidade. Browser usa endereço http://localhost:8080, preservando CSP do Nginx; sem mocks. Screenshots examinadas em tests/e2e/artifacts/phase2-desktop.png e phase2-mobile.png.

Testes de domínio também cobrem aprovação própria (inclusive administrador), responsáveis sem papel, rollback se auditoria falha, transições inválidas, revisão obsoleta, snapshots preservados, reatribuição com revogação do acesso anterior, cancelamento/reabertura, atraso derivado, bloqueio de UPDATE/DELETE de história por trigger, administração auditada e ciclos de unidades. Teste concorrente fecha explicitamente conexões de threads antes de destruir o banco de teste.

Cobertura medida via `--source=apps.accounts.permissions,apps.accounts.views,apps.commitments.services,apps.commitments.views,apps.audit.services,apps.audit.views`; não representa cobertura de todo o framework, Admin, frontend ou futuras fases. Lógica de compromissos teve 100% de statements executados; não é garantia de ausência de defeitos.

## Reexecução com containers
```sh
docker compose exec backend python manage.py test --noinput
docker compose exec backend coverage run --source=apps.accounts.permissions,apps.accounts.views,apps.commitments.services,apps.commitments.views,apps.audit.services,apps.audit.views manage.py test --noinput
docker compose exec backend coverage report --fail-under=80
```
O test runner usa banco separado test_agenda; migrations/fixtures da base agenda não são apagadas. Para UI, inicializar seed_foundation/seed_commitments, exportar DEMO_PASSWORD correspondente aos usuários já criados e E2E_BASE_URL=http://localhost:8080; em frontend rodar npm run test:e2e. Dados fictícios E2E permanecem por exigência de histórico; as execuções usam títulos únicos. Pipeline atualizado também inclui job Compose/Playwright em ambiente descartável; configuração validada, sem execução remota nesta entrega.

A limitação anterior de Docker/PostgreSQL foi resolvida nesta fase com execução real do Compose. Continuam sem validação: desempenho de carga, SMTP, recorrência, backup/restauração, WCAG formal e segurança externa. Os resultados da Fase 1 acima são registro histórico do ambiente anterior.

# Fase 3 — Resultados executados em 11/10/2026
| Verificação | Resultado |
|---|---|
| Backend PostgreSQL 17, incluindo fases anteriores | 37 testes aprovados, sem skips |
| Cobertura do conjunto medido | 99%; calendar_filters 100%, calendar_views 96% |
| OpenAPI --validate --fail-on-warn | aprovado |
| Migrations --check --dry-run | nenhuma alteração pendente |
| Build Angular em Docker + TypeScript estrito | aprovados, sem warnings de compilação |
| Playwright, desktop e mobile, com regressões anteriores | 8 testes aprovados |
| Ruff lint/format | aprovados |

Testes adicionais de backend verificam período inclusivo, unidade inativa, autenticação, pessoas no escopo, deduplicação com vários executores, três amostras/dia, summary anual sem eventos, filtros combinados, limites/intervalos inválidos, drilldown e favoritos privados. Teste de consultas impõe limite para evitar crescimento por evento na resposta amostrada. Períodos detalhados limitados a 62 dias e summary a 366 dias.

Playwright acrescenta dois cenários por projeto (desktop/mobile): utilitários de datas para anos bissextos, fim de mês e semanas entre anos; navegação calendário/filtros/favoritos/overflow/modal contra os containers reais. Inclui verificação de largura da página mobile para conter a rolagem à grade. Os dados CAL fictício são criados em API protegida, não são mocks e permanecem auditados.

Cobertura atual inclui os módulos anteriores mais apps.commitments.calendar_filters e apps.commitments.calendar_views. Não cobre todos os componentes Angular/Admin/framework e não substitui auditoria de segurança ou carga. Job E2E existente no CI inclui automaticamente calendar.spec.ts; pipeline remoto não foi executado nesta sessão.

## Fase 4 — 2026-10-11
53 testes backend aprovados no PostgreSQL 17, incluindo oito geradores em quatro threads: dez novas datas e nenhuma duplicata. Motor de datas: cobertura 100%; serviços de recorrência: 94%; conjunto crítico medido: 98% (não cobertura de toda a aplicação). Schema OpenAPI validado sem avisos, migrations sem mudanças pendentes, Ruff/tipos/build aprovados. Migrations aplicadas preservando registros das fases anteriores.

Casos: todas as frequências, fim de mês sem deriva, ano bissexto, primeiro/último dia, enésimo útil/semana e posição ausente; intervalos úteis, feriados, calendário nacional/institucional, exceções e datas ajustadas coincidentes; regras inválidas e calendário bloqueado; snapshot de feriados, geração repetida/concorrente, revisões otimistas, autorização, append-only, histórico de aprovação preservado e rollback da mudança coletiva quando a geração falha. Comando de reprocessamento idempotente testado.

Playwright `recurrence.spec.ts` valida criação pela interface, prévia com 29/02, quatro ocorrências, edição individual, mudança das pendentes e extensão para seis ocorrências, em desktop e celular. Capturas `tests/e2e/artifacts/recurrence-desktop.png` e `recurrence-mobile.png`; mobile examinado visualmente e sem overflow horizontal. Dados de navegador usam rótulos fictícios e permanecem no ambiente de desenvolvimento.

Rodada final: **10/10 testes Playwright aprovados**, incluindo login, núcleo/workflow, calendário e recorrência nas duas larguras. Corrigida condição de corrida no botão Editar ocorrência: agora aguarda o término da atualização da lista antes de permitir a ação.

## Fase 5 — 2026-10-11
**78 testes backend aprovados no PostgreSQL 17** (sem skips). SQLite: 78 testes, quatro skips explícitos para concorrência/probe SMTP real. Cobertura do conjunto crítico medido: **98%**; serviços de notificações 96%, tarefas 96%, views 99%. Schema OpenAPI sem avisos, migrations sem pendências, Ruff/format/tipos/build aprovados. Backend, PostgreSQL, Redis, Mailpit e worker saudáveis; scheduler ativo.

Validação cobre outbox na mesma transação e rollback em falha de auditoria, unicidade de eventos/destinatários, revalidação de autorização/endereço, supressão de alerta/validação obsoletos, políticas por definição/categoria e revisão otimista, cálculo de dias úteis/feriados/leap day, base e catch-up, erros SMTP transitórios/permanentes/incertos, backoff durável e limite, novo ciclo manual, destino preservado por tentativa, lease perdido, aceitação seguida de falha de banco, resultado tardio confirmado, append-only, broker indisponível e escopo privado/admin. Probe SMTP real contra porta local reservada sem listener comprovou `retry` por conexão recusada. Concorrência: oito tarefas em quatro threads produziram uma única chamada de envio/tentativa.

**12/12 testes Playwright aprovados** em Chromium nas larguras desktop/mobile, preservando os fluxos das fases anteriores. Notificações usam API autenticada → outbox → Redis → worker → SMTP Mailpit → UI/histórico. Captura confirmou uma única mensagem de atribuição, HTML/texto, título/link correto e estado `accepted` (sem inferir caixa postal). Políticas configuradas pela UI, link direto após sessão, consulta privada e 404 para outro usuário/unidade. Repetição dos dois casos de notificações também passou, aguardando o término da pesquisa antes de capturar a tela.

Capturas `tests/e2e/artifacts/notifications-desktop.png` (1440×1581) e `notifications-mobile.png` (390×2178); mobile examinado visualmente e sem overflow horizontal. Dados de teste são rotulados fictícios e e-mails de demonstração usam domínio `.invalid`, capturados somente no Mailpit.

Correções encontradas na verificação: acesso ao modelo User com sessão real (SimpleLazyObject), fixture do contador independente da ordem de flush de TransactionTestCase e filtro de auditoria por registro para evitar que volume de envios oculte transições da primeira página. Tentativas armazenam destino original mesmo após alteração do contato. Não houve ensaio com SMTP corporativo, comprovação de entrega/bounce ou teste de carga em grande escala.

## Fase 6 — Campos dinâmicos

**90/90 testes no PostgreSQL aprovados**, incluindo 12 novos de metadados/valores/API. SQLite: 90 testes aprovados, com quatro casos explicitamente específicos de PostgreSQL ignorados. Cobertura do conjunto crítico ampliado: **97%** (1369 instruções, 38 não cobertas), validadores de campos 93% e views 97%; não representa cobertura de todo o repositório.

Novos casos verificam os treze tipos, defaults, false/zero obrigatórios, inteiros seguros, precisão decimal, limites, datas inválidas/ano bissexto, comparação de instantes/fuso, opções/duplicatas, referências por unidade e preservação de referência inativa já existente. Integração cobre CRUD administrativo/revisão/identificador estável, publicação imutável e rollback por auditoria, rejeição de schema antigo/campos desconhecidos, snapshots de valores, estados bloqueados, isolamento, legado e independência da recorrência após republicação.

**14/14 Playwright aprovados**, desktop 1440×900/mobile 390×844, incluindo fluxos das fases anteriores. A Fase 6 cria campo na UI, publica os treze tipos, cadastra/edita ocorrência, testa rejeição pela API, precisão decimal, false, escaping de texto e referências. Republicação muda metadados para novos formulários e preserva versão/rótulos/valores da ocorrência antiga. Edição de outro campo preserva timestamp com offset e seis casas fracionárias. Outro usuário sem unidade recebe 404. Sem overflow horizontal na administração/detalhe em mobile.

Capturas em tests/e2e/artifacts/fields-admin-{desktop,mobile}.png e fields-detail-{desktop,mobile}.png. Detalhe mobile examinado visualmente. Ajustes encontrados: seletores reais de controles múltiplos Angular nos testes; proteção do nome durante carregamento de categoria; quebra de linhas de identificadores longos; preservação de precisão temporal no editor. Lint, formato, TypeScript, Angular produção, OpenAPI sem warnings e migrations sem pendências aprovados. Dados de verificação são fictícios e permanecem no ambiente local; não houve teste de carga de catálogos grandes.

## Fase 7 — Gestão e relatórios

**103/103 testes PostgreSQL aprovados**; SQLite 103 testes, com quatro skips explicitamente específicos de PostgreSQL. Treze novos testes cobrem métricas, isolamento, agrupamentos, filtros, favoritos, exportações e administração. Conjunto crítico ampliado: **97%** (1623 instruções, 44 não cobertas); services de relatórios 100%, exports/views 98%. Não representa cobertura de todo o repositório.

Verificações incluem deduplicação por UUID com dois responsáveis, agrupamentos não somáveis, filtros combinados, período inválido, unidade inativa, ausência de amostra/data final, ressumbissão com última submissão, aprovação no limite de meia-noite de America/Sao_Paulo, médias/amostras, painel mensal, paginação sem sobreposição e exportação de todas as páginas. CSV foi lido para verificar quoting/UTF-8/precisão/proteção de fórmula; XLSX foi descompactado e todos os XMLs analisados, com células explícitas e ausência de fórmulas. Excesso de registros/célula rejeitado; falha de auditoria impede resposta de exportação. Favoritos privados/auditados; catálogo editável só por admin, com comparação do estado anterior e preservação das referências.

**16/16 Playwright aprovados** em desktop/mobile com containers estabilizados, incluindo todas as fases anteriores. Dois cenários de relatórios criam dados fictícios em duas unidades, consultam conjunto autorizado, agrupam, salvam/aplicam/removem favorito, baixam CSV/XLSX reais e verificam seleção conforme última consulta aplicada. Detalhe em diálogo preserva filtros/resultados ao fechar. Administração altera catálogo e verifica auditoria. Capturas dashboard-{desktop,mobile}.png e reports-{desktop,mobile}.png em tests/e2e/artifacts; relatório mobile examinado visualmente e sem overflow horizontal.

Lint, formato, TypeScript estrito, build Angular produção, OpenAPI sem warnings e migrations sem mudanças pendentes aprovados. A primeira regressão coincidiu com reinício de backend e foi descartada; a rodada final estável passou integralmente. Não foi executado teste em Microsoft Excel instalado, teste de carga ou certificação WCAG; estrutura OOXML, downloads reais e XMLs foram verificados. Não houve envio externo: SMTP confirmado como Mailpit. Dados fictícios de testes permanecem no ambiente local.

## Fase 8 — 12/10/2026

**113/113 testes PostgreSQL aprovados**, incluindo oito editores concorrentes sobre uma mesma revisão (uma versão/auditoria nova), preservação dos casos concorrentes de identificadores/outbox, schema-readiness, configuração de produção, fronteira de IP/HTTPS, Unicode inválido e hold da fila restaurada. **113 SQLite**, cinco skips exclusivamente PostgreSQL. Conjunto crítico: **97%**, 1678 instruções/44 não cobertas; autorização/proxy/readiness/recuperação 100%. Não é cobertura de todo o repositório/framework/tooling.

**20/20 Playwright aprovados** em desktop/mobile contra Nginx/API/PostgreSQL/Celery/Mailpit reais. Inclui os fluxos anteriores, validação dinâmica com mensagem por campo, CSP/nosniff/frame denial/no-store, CSRF login/logout, conta comum sem acesso administrativo, cookie HTTP-only e invalidação após logout. Axe-core 4.13.0: zero violações nos critérios/tag selecionados nas telas examinadas, incluindo diálogo. Sem regras excluídas. Skip link/Tab/ciclo de foco/Escape verificados; não certifica WCAG nem substitui leitor de tela/manual.

npm audit/pip-audit: **zero avisos conhecidos reportados** nas dependências declaradas, nesta consulta. Não houve scan de imagens/base OS/pentest. Lint/formato de backend/tools, TypeScript, build produção Angular, OpenAPI sem warnings, migrations sem pendências e sintaxe do Compose institucional aprovados. Checks de produção deixam W005/W021 explícitos para política de HSTS, com teste que rejeita outros avisos inesperados. CI atualizado; execução remota não realizada.

Backup final protegido, **920.734 bytes**, restaurado em base nova/descartada; oito triggers e bloqueio de mutação da auditoria. Primeira cópia estável comparou doze tabelas; na rodada final com testes criando dados, três tabelas permaneceram estáveis para comparação (demais corretamente não comparadas entre snapshots distintos). Fonte preservada, pg_restore completo bem-sucedido. Dumps/manifestos ficam privados em .backups e não são artefatos públicos.

Ensaio de intranet sobre cópia: TLS com CA temporária e hostname verificados, login real em DEBUG=false, cookies Secure/HTTP-only, HSTS/CSP, filesystem somente leitura/capabilities removidas e runtime sem DDL/alteração do histórico. Hold da fila copiada executado/auditado. Todos os recursos temporários foram removidos; infraestrutura/certificados corporativos não ativados.

Carga: 1000 usuários/10000 séries/100000 ocorrências, 100 clientes/300 GETs, Gunicorn 3×4. Sem histórico: 62,37 req/s, p95 máximo 2,406 s, zero erros; referência inicial 7,71 req/s/p95 máximo 19,273 s. Complementar com datas do motor e 40000 transições: 19,38 req/s, p95 painel 5,779 s/lista 5,851 s/resumo 6,919 s, zero erros. Docker 8 vCPUs/3,82 GiB/aarch64, host compartilhado. Não mede carga prolongada, escrita simultânea, SMTP/anexos/failover nem aprova SLA de produção. PHASE8_RESULTS.json contém resultados agregados, sem tokens/dados pessoais.

A revisão corrigiu contrastes, foco modal, mensagens aninhadas, carregamento duplicado de relações ao otimizar consultas e dependência de IP fixo do proxy. Rodadas com essas falhas/reinícios foram corrigidas e não representam os resultados finais acima. Restrições remanescentes e operação em PHASE8.md/RELEASE.md/RECOVERY.md.

## Continuidade de consultas — 29/10/2026

**22/22 Playwright** em desktop/mobile aprovados, incluindo dois cenários novos de restauração dos filtros/página, separação de rascunho/aplicado, retorno à página 1 após 404 e limpeza no logout. Dados de navegação são fictícios, criados pela API; apenas o 404 de página inválida é simulado no teste. Todo estado do cliente fica em memória da aba, separado por usuário/lista, sem armazenar resultados.

**114/114 testes PostgreSQL** aprovados. Caso novo mantém o scanner de vencimentos com a transação aberta e verifica locks independentes em unidade/demandante: o scanner deve bloquear só a ocorrência. Esse teste cobre a correção de um deadlock intermitente encontrado na regressão real. Teste antigo de calendário corrigido para considerar dias adjacentes da grade mensal, relevante perto do fim do mês.

TypeScript estrito, build frontend, Ruff/formato, OpenAPI sem warnings e migrations sem pendências aprovados. Containers locais atualizados. Uso e limites em NAVIGATION.md. Relatórios/calendário não receberam memória de consultas nova; permanecem seus fluxos próprios. Fixtures fictícias permanecem no banco conforme histórico existente.

### Formulários e criação por data — 29/10/2026

Compilação de produção Angular/Docker e TypeScript aprovados. Suíte Playwright completa: **24/24 testes aprovados** em desktop e celular, incluindo criação real pelo calendário, edição com justificativa, atualização da agenda e análise axe do formulário de criação. Regressão cobre os fluxos existentes de execução/validação, recorrência, campos personalizados, notificações, relatórios, navegação e segurança. Nenhum backend ou esquema de banco foi alterado nesta melhoria. Registros fictícios gerados pelos testes permanecem no ambiente local.

### Rotas protegidas — 29/10/2026

Suíte Playwright completa: **32/32 testes aprovados** em desktop e celular. Inclui seis cenários novos para links diretos, recarregamento, URLs do menu, voltar/avançar, logout/histórico, rota administrativa negada, administrador autorizado, destino externo rejeitado, sessão expirada detectada por operação da interface, links antigos de e-mail, UUID inválido e acesso a ocorrência de outra unidade. Os testes existentes usam links do menu e aguardam a URL de destino antes da próxima interação. Build Angular/Docker e TypeScript aprovados; o npm não apontou vulnerabilidades na instalação do Router. Nenhuma alteração de backend ou esquema de dados foi necessária para as rotas da interface.

### Central de pendências — 30/10/2026

- PostgreSQL: **117/117 testes aprovados**; após o ajuste de consistência do cartão selecionado, **16/16 testes de relatórios/pendências** novamente aprovados.
- Interface: **36/36 testes Playwright aprovados** em desktop e celular, incluindo o ciclo real de submissão/aprovação na central, escopo, contadores, paginação, detalhes, recarregamento, axe e regressão dos fluxos anteriores.
- Build Angular/Docker, TypeScript, Ruff e OpenAPI com `--validate --fail-on-warn` aprovados. Nenhuma migração necessária.
- Corrida de login reproduzida com uma consulta anônima real atrasada: a verificação após autenticação agora força uma consulta nova. Os dois testes específicos passaram antes da regressão completa.

Redis/Mailpit estavam parados no início da regressão de notificações; foram iniciados e worker/agendador reiniciados. Na execução final, os serviços estavam saudáveis e os testes de SMTP passaram. Registros fictícios criados pelos testes permanecem no ambiente local com trilha de auditoria, conforme [PENDING_CENTER.md](PENDING_CENTER.md).

### Formulários de compromissos — 30/10/2026

**38/38 testes Playwright aprovados** na versão final em desktop e celular. Cobertura nova: mensagens de erro por campo e correção, busca de responsáveis com preservação/remoção de seleção, recusa de descarte por rota/painel, tentativa real de fechamento da aba cancelada, descarte aprovado, reinício de cadastro limpo e Enter na busca sem submissão. Criação e edição reais continuam verificadas, inclusive o cancelamento da desistência durante edição. Axe no formulário aberto e ausência de transbordamento aprovados.

Compilação de produção Angular/Docker, TypeScript e `git diff --check` aprovados. Sem novas dependências, alterações de API ou migração nesta melhoria. A proteção de rascunhos foi aplicada à criação/edição de ocorrências; veja [FORMS.md](FORMS.md).

### Filtros na URL — 30/10/2026

**46/46 testes Playwright aprovados** na versão final em desktop e celular. Os oito cenários novos (quatro por viewport) verificam consultas aplicadas, caracteres especiais, recarregamento, histórico, retomada após login, parâmetros inválidos/repetidos, escopo entre unidades, recuperação de páginas, calendário, relatórios, notificações e pendências. Incluem uma resposta real atrasada durante voltar e a preservação de formulário em edição. A série fictícia de 51 ocorrências existente confirma página 2 na URL e restauração ao recarregar.

Regressão inclui criação/edição, rascunhos, campos personalizados, recorrência, relatórios/exportações, SMTP, permissões, Swagger e axe. Build Angular/Docker, TypeScript e `git diff --check` aprovados. Não houve nova dependência, alteração de API ou migração. Uso e limites em [URL_FILTERS.md](URL_FILTERS.md).

### Anexos comprobatórios — 30/10/2026

- **125/125 testes PostgreSQL aprovados**, incluindo arquivos válidos/falsos, PDF ativo recusado, DOCX/XLSX, limites de tamanho/quantidade/retenção, autorização/revogação/unidade inativa, integridade, retirada lógica, rollback e triggers append-only.
- **48/48 testes Playwright aprovados** na versão final, desktop/celular: envio real, recusa de falso PDF, download com comparação de bytes/SHA-256, retirada justificada, usuário sem sessão/outra unidade, axe e regressão dos fluxos anteriores.
- Testes TCP do protocolo clamd verificam resposta limpa, detecção e erro com servidor de teste. Não foi executado um scanner ClamAV real com assinaturas; DEBUG local sem scanner informa validação estrutural, e fora de DEBUG os arquivos exigem inspeção registrada.
- Backup/restauração em base temporária aprovado: comparação das três tabelas de anexos estáveis, seis arquivos recuperados com tamanho/SHA-256 corretos e **11 triggers** de proteção. Base original preservada; dumps privados em `.backups`.
- Build Angular/Docker, TypeScript, Ruff/check/format, OpenAPI (`--validate --fail-on-warn`), migrações sem divergência e whitespace aprovados. `pip-audit` não encontrou vulnerabilidades conhecidas nas dependências fixadas, incluindo Pillow 13.0.0 e pypdf 6.21.4.

A regressão identificou e corrigiu uma corrida preexistente no carregamento inicial do calendário: ações agora ficam bloqueadas até o carregamento terminar. O teste segura uma resposta real de catálogo para verificar esse bloqueio. Guia e limites em [EVIDENCE.md](EVIDENCE.md).

## Automação de backup

`python -m unittest tools.test_scheduled_backup` verifica retenção/mínimo de cópias, arquivos corrompidos/manuais, links simbólicos e falha sem limpeza. Incluído no CI. `python3 tools/scheduled_backup.py` executa o ensaio real de backup/restauração com integridade dos anexos; requer Docker/Compose ativo.
