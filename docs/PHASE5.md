# Fase 5 — Notificações

## Uso local
Os containers `worker` (Celery/Redis) e `scheduler` (Celery Beat) processam automaticamente os avisos. Abra **Notificações** na aplicação: usuários veem seus próprios avisos dentro do escopo atual; administradores veem a fila global, tentativas, contagens e últimas execuções. A pesquisa aceita título ou identificador e pode combinar situação do envio. **Abrir ocorrência** reutiliza os detalhes e o workflow. Links dos e-mails funcionam também após o login.

Atribuição, alterações relevantes, reatribuição, solicitação de validação, aprovação, rejeição, cancelamento e reabertura geram eventos. Atribuição avisa executores; validação solicitada avisa o demandante; demais eventos avisam demandante e executores atuais, sem repetir o mesmo usuário. Geração de séries cria avisos individuais por nova ocorrência, respeitando a idempotência da Fase 4. Providências e fundamentação normativa não são incluídas em e-mails.

Mailpit captura as mensagens locais em http://localhost:8025. Os destinatários fictícios usam `@agenda.invalid`. Para preparar contas de demonstração com e-mail ausente:
```sh
docker compose exec backend python manage.py seed_notification_demo
```
O comando só funciona com DEBUG e host SMTP `mailpit`; preserva e-mails existentes. **Meu e-mail para notificações** permite ao usuário atualizar seu próprio endereço, com auditoria. Endereço válido não implica endereço verificado; provisionamento corporativo/SSO e validação de contato são decisões de implantação.

## Políticas
Configuração em **Políticas de alerta de vencimento**. Uma política por definição de compromisso prevalece sobre a de categoria; categoria é administrada somente pelo administrador global. O demandante proprietário pode configurar seu compromisso na unidade ativa. Política requer motivo e revisão otimista e conserva valores anteriores na auditoria.

Sem configuração: 30, 15, 7, 3 e 1 dia antes, no vencimento e 1 dia depois, em dias corridos. Intervalos positivos indicam antecedência; zero é o vencimento; negativos indicam atraso. Permitidos 1–16 inteiros únicos entre -365 e 365. Contagem em dias corridos ou úteis, com calendário nacional ou nacional + institucional configurado na Fase 4. Offset zero mantém a data de vencimento, mesmo quando não é útil. A contagem útil exclui o vencimento ao caminhar para frente/trás. Datas de alertas podem atravessar meses e anos.

Desativação de política afeta somente alertas de vencimento; atribuições/workflow continuam ativos. A verificação roda a cada cinco minutos e recupera datas de alerta dos últimos sete dias. Antecedências já ultrapassadas não são enviadas quando o vencimento passou; avisos de vencimento/atraso que estejam na janela podem ser recuperados. Depois de uma indisponibilidade maior que sete dias, é necessária revisão operacional; não se presume recuperação ilimitada nem reenvio retroativo de todo o histórico.

Cada alerta guarda política e feriados usados no evento. Chave única combina ocorrência, vencimento, intervalo, base de contagem e calendário; repetir a verificação não gera outro evento. Mudanças de título/status que não alterem o marco de vencimento não repetem o alerta. Alterar vencimento produz novos marcos; alertas pendentes incompatíveis com o vencimento/política atual são dispensados no envio. Eventos não são gerados retroativamente para antigas atribuições; a implantação passa a registrar novas mutações e os alertas da janela definida.

## Outbox e confiabilidade
Evento + destinatários são persistidos na mesma transação da mutação. Se a auditoria/outbox falhar, a mutação é revertida. Nenhum publish no broker faz parte da transação de negócio: o despachante consulta a outbox a cada 30 segundos e publica até 100 IDs elegíveis por rodada. Falha de Redis mantém eventos no banco; a próxima rodada recupera o despacho. Publish repetido ou tarefas concorrentes não iniciam duas tentativas simultâneas: claim é protegido por lock da entrega no PostgreSQL.

Estados conhecidos:
- `pending`: gravado na outbox, aguardando processamento.
- `sending`: tentativa iniciada, com lease de três minutos.
- `retry`: rejeição temporária ou conexão recusada; nova tentativa com backoff.
- `accepted`: backend de e-mail informou aceitação SMTP. **Entrega na caixa postal não confirmada.**
- `failed`: falha permanente, envio não aceito ou limite atingido.
- `skipped`: destinatário sem e-mail/acesso ativo, alerta desatualizado, política alterada ou validação já resolvida.
- `unknown`: conexão interrompida/timeout ou worker perdido; pode ter ocorrido aceitação sem confirmação local.

Até cinco tentativas por ciclo, com intervalos de 60, 120, 240 e 480 segundos (algoritmo limitado a uma hora). Agenda de retry persiste no PostgreSQL, sem depender de timer em memória do worker. Autenticação e SMTP 5xx são falhas definitivas; SMTP 4xx e conexão recusada são retentáveis. Timeout/desconexão genéricos são incertos e não são reenviados automaticamente.

Admin pode reprocessar `failed`, `skipped` ou `unknown` com motivo. Resultado desconhecido requer confirmação explícita do risco de duplicidade. O ciclo manual concede cinco novas tentativas e reinicia o backoff, conservando o contador/histórico anteriores. `Message-ID` permanece estável por entrega e cada e-mail inclui o ID do evento; o servidor externo não é obrigado a deduplicar por esse cabeçalho. **Não há garantia de exatamente uma entrega externa:** SMTP e commit de banco não são uma única transação. Caso haja aceitação seguida de falha antes do registro local, a entrega será tratada como incerta. Um resultado tardio confirmado pode resolver essa incerteza se a tentativa não tiver sido substituída por um reprocessamento manual.

Antes do SMTP, revalidam-se usuário/unidade ativos, papel e atribuição atuais, endereço e validade do alerta. A outbox mantém snapshot do evento; o e-mail orienta consultar o estado atual na aplicação. Tentativas conservam o endereço efetivamente usado naquele envio, mesmo quando o contato muda entre retentativas. Erros são guardados apenas por código, sem resposta SMTP bruta ou credenciais. Eventos e tentativas têm triggers append-only; estados da outbox/políticas são mutáveis e auditados. Proteção não cobre DBA/DDL/TRUNCATE.

## SMTP e operação
Configuração externa, descrita em `.env.example`: `SMTP_HOST`, `SMTP_PORT`, `SMTP_USER`, `SMTP_PASSWORD`, `SMTP_TLS` (STARTTLS), `SMTP_SSL` (TLS implícito), `SMTP_TIMEOUT`, `SMTP_FROM_EMAIL`, `NOTIFICATION_BASE_URL` e `CELERY_BROKER_URL`. Não habilitar TLS e SSL ao mesmo tempo. URL interna deve corresponder à aplicação acessível aos destinatários. Templates responsivos em HTML, com alternativa em texto simples, incluem aplicação, identificador, título, vencimento, estado do evento, responsáveis, resumo de até 240 caracteres e link autorizado.

```sh
docker compose up --build -d
docker compose logs --tail=50 worker scheduler
docker compose exec worker celery -A config inspect ping
```

Manter **um único scheduler Beat**; múltiplos workers são possíveis. Saúde do worker é verificada por ping Celery; Redis tem healthcheck. Monitor na aplicação mostra contagens e última execução do despachante/verificador; um timestamp antigo indica ausência de processamento e deve ser investigado. **Verificar alertas e processar fila** solicita uma rodada extra, sem ignorar backoff ou reprocessar envios aceitos. SMTP corporativo, autenticação, certificados, remetente autorizado e bounces precisam ser validados pela instituição. Não há integração de DSN/webhook de entrega nesta fase; Mailpit é somente desenvolvimento.

## API
- `GET /api/v1/notifications/?q=&status=&occurrence=` e `GET /api/v1/notifications/{id}/`: avisos/tentativas paginados, escopo pessoal ou administrador.
- `POST /api/v1/notifications/{id}/requeue/`: administrador; `{reason, acknowledge_duplicate_risk}`.
- `GET/PATCH /api/v1/notification-email/`: e-mail do usuário autenticado; `{email}`.
- `GET/POST /api/v1/notification-policies/`: `{definition OU category, enabled, offsets, basis: calendar|business, calendar: national|institution, revision, reason}`; revisão zero cria, revisão atual atualiza.
- `GET /api/v1/notification-monitor/`: administrador; contagens, pendência mais antiga e checkpoints.
- `POST /api/v1/notification-jobs/`: administrador; solicita tarefas, retorna 202 ou 503 quando a fila não está acessível. Eventos permanecem na outbox.

## Referências de implementação
[Integração Django/Celery](https://docs.celeryq.dev/en/stable/django/first-steps-with-django.html), [tarefas e idempotência](https://docs.celeryq.dev/en/stable/userguide/tasks.html), [agendador periódico](https://docs.celeryq.dev/en/stable/userguide/periodic-tasks.html) e [API do Mailpit](https://mailpit.axllent.org/docs/api-v1/). A aplicação usa polling de outbox persistida, além da integração padrão, para recuperar falhas entre banco e broker.
