# Fase 4 — Recorrência

## Uso
Em **Compromissos → Novo compromisso**, informe vencimento e escolha a periodicidade na regra de recorrência. Configure término, limite e regras; **Prévia das datas** mostra data nominal → vencimento ajustado. Salvar materializa o período inteiro, limitado a mil ocorrências por definição e dez anos por regra. Não depende de um worker em execução.

Frequências: único, diário, semanal, quinzenal (14 dias), mensal, bimestral, trimestral, semestral, anual e intervalo personalizado em dias corridos ou úteis. Semanal/quinzenal permitem escolher o dia da semana; primeira data é esse dia a partir do início. Regras mensais incluem dia específico, primeiro/último dia, enésimo/último dia útil e enésimo/último dia da semana. Posições inexistentes pulam o mês. Dia 31 limita ao fim do mês sem deslocar o mês seguinte; 29/02 anual retorna a 29 em ano bissexto.

Dias úteis são segunda a sexta, exceto feriados ativos. Admin cadastra datas nacionais ou institucionais em **Administrar feriados**. Regra escolhe nacional ou nacional + institucional. Nenhum feriado real é presumido ou importado. Feriados são datas explícitas; feriados móveis devem ser cadastrados por ano. Ajustes: manter, próximo útil ou útil anterior. Exceções excluem datas nominais; o limite conta datas nominais mesmo quando excluídas. Data de referência mantém o deslocamento em dias corridos relativo à data nominal, não ao vencimento ajustado.

## Alterações e história
- **Editar ocorrência** altera somente o registro selecionado, com motivo e revisão otimista; as mesmas restrições do workflow permanecem.
- **Alterar série → Esta e próximas pendentes** aplica título/descrição/prioridade a pendentes sem providências/transições, a partir da data nominal selecionada. Registros em execução, validação, concluídos ou cancelados permanecem preservados.
- **Somente ocorrências ainda não geradas** versiona o modelo para futuras gerações, sem alterar registros existentes.
- Nova regra de datas deve iniciar depois da última data nominal materializada. Para estender a série, escolha nova periodicidade, início e fim; geração e versão são uma única transação. Reprogramações de datas já geradas são individuais e auditadas, sem remover ocorrências nem reciclar identificadores.
- Sem nova regra, conserva-se a periodicidade e o snapshot de feriados anterior. A interface permite manter a regra sem preencher novos parâmetros.

Cada regra guarda versão, vigência, modelo, responsáveis, deslocamento de referência e snapshot de feriados. A criação de novas regras consulta o calendário atual; editar um feriado não recalcula o passado. Identificadores e vínculo da ocorrência à versão geradora permanecem estáveis. Versões da série, snapshots de ocorrência, providências, transições e auditoria têm triggers append-only em PostgreSQL/SQLite (não proteção contra DBA/DDL/TRUNCATE).

## Idempotência e operação
Constraint única `(definition, scheduled_date)` usa a data nominal: datas diferentes ajustadas para o mesmo vencimento continuam sendo ocorrências distintas. Lock da definição serializa geradores concorrentes; ordinal e identificador são incrementados sob o mesmo lock. Workflow e ações pertencem à ocorrência, nunca são propagados a outras.

Reexecução manual, ou por agendador externo autorizado:
```sh
docker compose exec backend python manage.py generate_occurrences --through 2028-12-31
```
O comando processa definições ativas, revalida responsáveis e autoria, informa séries bloqueadas e não duplica registros. Não existe daemon periódico nesta fase; como todas as datas do período são geradas ao salvar, o comando serve para reprocessamento seguro. Worker e alertas pertencem à fase 5. Limite de mil é um limite de implementação e precisa ser revisto com carga antes da produção em grande escala.

## API
- `POST /api/v1/definitions/`: campo opcional `recurrence` (regra); início deve coincidir com o vencimento informado.
- `POST /api/v1/recurrence/preview/`: `{rule, through}` retorna datas nominais/ajustadas, sem persistir.
- `GET/POST /api/v1/holidays/`, `PATCH /api/v1/holidays/{id}/`: escrita só por administrador, auditada; desativação em vez de exclusão.
- `POST /api/v1/occurrences/{id}/series/`: `{revision, reason, scope: "future"|"pending", title?, description?, legal_basis?, priority?, rule?}`.
- `POST /api/v1/occurrences/{id}/generate/`: `{through}`, somente gestor responsável da série.
- Calendário/lista/favoritos aceitam as dez periodicidades; filtram o tipo da ocorrência, preservando séries com versões de frequências diferentes.

Regra: `frequency`, `calendar` (`national`/`institution`), `start`, `end`, `count` (1–1000), `month_mode`, `month_day` (1–31, opcional), `ordinal`, `weekday` (segunda=0), `interval`, `interval_unit` (`days`/`business_days`), `adjustment` (`none`/`next`/`previous`), `exceptions` (datas). Datas nominais aceitas: 1900–2200; referência a até dez anos da data nominal. Campos desconhecidos são rejeitados.
