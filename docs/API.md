# API v1
Todos os endpoints de dados exigem sessão. Respostas de lista: `{count,next,previous,results}`, 50 itens por página. Sem ordenação/filtros de domínio nesta fase. Falhas DRF usam `detail`; login inválido 401, sem sessão 403, CSRF inválido 403, bloqueio de login 429.

| Método | Endpoint | Uso |
|---|---|---|
| GET | /api/v1/auth/csrf/ | Inicializa cookie csrftoken |
| POST | /api/v1/auth/login/ | JSON username/password + X-CSRFToken |
| GET | /api/v1/auth/me/ | Perfil e associações ativas |
| POST | /api/v1/auth/logout/ | Encerra sessão + X-CSRFToken |
| GET | /api/v1/units/ | Unidades no escopo do usuário |
| GET | /api/v1/users/ | Lista global, somente administrador |
| GET | /api/v1/schema/ | OpenAPI YAML autenticado |
| GET | /api/v1/docs/ | Swagger autenticado, assets locais |
| GET | /health/ | Processo vivo |
| GET | /ready/ | Conexão DB; 503 quando indisponível |

Exemplo de login: `{"username":"demandante1","password":"<senha configurada externamente>"}`. Preservar cookies e enviar header CSRF com valor do cookie; login rotaciona token, portanto usar o novo valor no logout. Resposta de login: `{"detail":"Autenticado."}`. Perfil: `{"id":"<uuid>","username":"demandante1","name":"Demandante1","administrator":false,"memberships":[{"unit_id":"<uuid>","unit__name":"Riscos","role":"requester"}]}`.

Login/CSRF são views Django protegidas, documentadas nesta tabela; OpenAPI gerado cobre endpoints DRF. Os endpoints da Fase 2 estão abaixo.

## Fase 2
| Método | Endpoint | Uso |
|---|---|---|
| GET/POST | /api/v1/entities/ | Catálogo; criação somente admin |
| GET/POST | /api/v1/categories/ | Categorias; criação somente admin |
| GET | /api/v1/assignable-users/?unit=UUID | Demandados ativos; requer demandante no escopo |
| GET/POST | /api/v1/definitions/ | Definições visíveis; criar definição e primeira ocorrência |
| GET | /api/v1/definitions/UUID/ | Definição preservada |
| GET | /api/v1/occurrences/ | Lista paginada no escopo |
| GET | /api/v1/occurrences/UUID/ | Dados, ações, transições e versões |
| PATCH | /api/v1/occurrences/UUID/edit/ | Alteração com motivo e revisão |
| POST | /api/v1/occurrences/UUID/actions/ | Providência append-only |
| POST | /api/v1/occurrences/UUID/transition/ | Operação de workflow autorizada |
| GET | /api/v1/audit/ | Auditoria global admin; filtro record_id |

Filtros combináveis de ocorrências: q, status, unit, entity, category, mine=true, validation=true, overdue=true e page. Ordenação estável por due_date/identifier. Respostas incluem available_transitions, can_edit e can_add_action para UI, sem substituir controles backend. Não existe DELETE de domínio, PUT/PATCH genérico de status nem CRUD de histórico.

Criação:
```json
{"title":"Exemplo fictício","description":"Demonstração sem validade normativa","legal_basis":"","unit":"<uuid autorizado>","entity":"<uuid ativo>","category":"<uuid ativo>","assignees":["<uuid demandado>"],"reference_date":"2026-10-11","due_date":"2026-12-15","priority":"normal"}
```
Retorna 201 e ocorrência detalhada, com identifier REG-000001/0001 e revision=1. Identificador sequencial é gerado sob lock; usuário não escolhe status, demandante, UUID ou identificador. Campos inesperados são rejeitados.

Providência: `{"text":"Conferência efetuada"}`. Transição: `{"operation":"submit","revision":2,"reason":""}`. Operações: start, submit, approve, reject, cancel, reopen. Rejeição/cancelamento/reabertura exigem reason não vazio. Edição: `{"title":"Título corrigido","revision":1,"reason":"Correção documentada"}`; também permite description, legal_basis, reference_date, due_date, priority, assignees. Revisão obsoleta retorna 400. Operação sem permissão/transição disponível retorna 403; objeto fora do escopo retorna 404. Reabrir é necessário antes de editar conclusão; cancelamento é terminal nesta fase.

Administração de usuários/unidades/associações ocorre no Django Admin com CSRF e auditoria. Catálogos são criados pelo app/API; manutenção adicional de catálogos fica para a expansão administrativa. OpenAPI validado inclui serviços DRF.

## Fase 3 — Calendário e favoritos
| Método | Endpoint | Uso |
|---|---|---|
| GET | /api/v1/calendar/?date_start=2026-10-01&date_end=2026-11-11 | Contagens por dia e até três eventos/dia; limite detalhado 62 dias |
| GET | /api/v1/calendar/?date_start=2026-01-01&date_end=2026-12-31&summary=true | Apenas contagens; limite de 366 dias |
| GET | /api/v1/calendar/people/ | Demandantes/demandados presentes em ocorrências visíveis |
| GET/POST | /api/v1/calendar-favorites/ | Favoritos do usuário autenticado, paginação padrão |
| DELETE | /api/v1/calendar-favorites/UUID/ | Remove favorito próprio; UUID de outro usuário retorna 404 |

Resposta: `{date_start,date_end,total,days:[{date,total,status_counts,events:[{id,identifier,title,due_date,status,priority,overdue}]}]}`. Dias sem compromissos são omitidos; frontend completa a grade. summary=true retorna events vazio. Datas inválidas/invertidas ou excesso de período retornam 400. Datas são inclusivas.

Filtros adicionais combináveis: q, unit, entity, category, requester, assignee (UUID), priority, status e periodicity=once. GET /occurrences/ aceita os mesmos filtros, inclusive date_start/date_end, para drilldown paginado. Não há periodicidade mensal ativa nesta fase; valor não suportado retorna 400.

Favorito: `{"name":"Pendências de Riscos","filters":{"status":"pending","priority":"high"}}`. Owner é definido no servidor, não pelo payload. Filtros são normalizados/validados, e nome deve ser único por usuário. A aplicação de favorito não evita filtros de autorização. Preferências pessoais não alteram história regulatória. OpenAPI cobre essas operações.

## Fase 4
Regras, payloads e endpoints de recorrência/feriados em [PHASE4.md](PHASE4.md). Listas e calendário filtram `periodicity`; detalhe inclui data nominal, versão geradora, revisão atual e histórico da série.

## Fase 5
Endpoints e payloads de avisos, políticas, e-mail pessoal, monitor/reprocessamento em [PHASE5.md](PHASE5.md). Sessão/CSRF e escopo obrigatórios; administração global para monitor, reprocessamento e política de categoria.

## Fase 6 — Campos e formulários
GET/POST custom-fields/, GET/PUT custom-fields/{id}/ (admin, revision/reason, sem DELETE). GET/POST form-versions/, GET form-versions/{id}/; filtros category/latest. GET custom-field-users/?unit= (demandante/admin). Definitions POST recebe form_version/custom_values; ocorrência GET detalhada retorna form_schema/custom_values; PATCH edit recebe custom_values inteiro e preserva form_version. Consulte [PHASE6.md](PHASE6.md) para formatos dos treze tipos e contratos de revisão.

## Fase 7
GET dashboard/, reports/summary/, reports/occurrences/, reports/groups/ e reports/export/. Relatórios exigem date_start/date_end e aceitam os filtros combinados; group_by=unit/entity/assignee/periodicity, output=csv/xlsx. GET/POST report-favorites/, DELETE report-favorites/{id}/ são privados/auditados. PATCH entities/{id}/ e categories/{id}/ exige name, active, expected_name, expected_active e reason (admin). [PHASE7.md](PHASE7.md) descreve denominadores, métodos e limites.

## Fase 8
Perfil auth/me inclui environment=development|intranet. ready/ exige DB/schema migrado, sem mutação. Contratos dos relatórios/denominadores preservados pela otimização de escopo. Comando operacional hold_restored_outbox não é endpoint: somente base nova de recuperação com nome confirmado/motivo, preview antes de --apply.
