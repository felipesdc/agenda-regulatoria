# Fase 2 — Núcleo de compromissos
## Implementado
- Entidades e categorias: consulta autenticada; criação por administrador, com auditoria. Nomes únicos e estado ativo.
- Unidades hierárquicas: consulta no escopo; manutenção por superusuário no Django Admin, com auditoria e validação de ciclos. Sem herança de acesso.
- Usuários/papéis: administração restrita a superusuários, criação/alteração de usuários, atribuições por unidade e alteração de senha auditadas sem guardar segredo. Exclusão de usuários/associações/unidades desabilitada; revogação por inativação ou edição de papel/unidade.
- Definição e ocorrência separadas. Criação gera uma ocorrência pontual independente. UUID técnico; identificador REG sequencial sob bloqueio de linha no PostgreSQL; ordinal /0001 estável.
- Um ou vários demandados ativos na unidade; edição de responsáveis somente com motivo e revisão esperada.
- Lista paginada, pesquisa, situação, apenas atrasados, minhas atribuições e validações pendentes.
- Providências append-only, transições backend e segregação executor/validador, inclusive administrador.
- Edição de título, descrição, fundamentação, referência, vencimento, prioridade e responsáveis pela API; interface permite título, descrição, vencimento, prioridade e responsáveis. Definição original permanece preservada.
- Histórico de versões, transições e auditoria; triggers PostgreSQL/SQLite bloqueiam UPDATE/DELETE comuns em auditoria, providências, transições e snapshots.
- Concorrência: revisão esperada e bloqueio da ocorrência; rollback integral quando auditoria falha.
- Interface responsiva para criação, execução, aprovação/rejeição, cancelamento/reabertura e consulta de histórico. Auditoria global somente para administrador.

## Regras
Demandante vê ocorrências da unidade em que possui papel, mas gerencia somente as próprias; administrador global gerencia todas as unidades ativas. Demandado vê/executa apenas atribuições próprias em unidades ativas com papel de executor. Não basta estar na unidade. Atribuição inicial não concede papel automaticamente.

Fluxo: pending → in_progress → awaiting_validation → completed. Rejeição com justificativa → rejected → in_progress; nova providência após rejeição é obrigatória para ressubmeter. Cancelamento exige motivo em estados não terminais; completed permite reabertura justificada para in_progress, preservando histórico. Cancelled é terminal nesta fase. Registro concluído ou aguardando validação não admite edição comum. Aprovação/rejeição indisponível se o ator é demandado ou submeteu a própria execução.

Atraso é derivado: due_date anterior à data corrente em America/Sao_Paulo e situação diferente de completed/cancelled. Não há regra universal de due_date >= reference_date; as datas têm finalidades independentes e calendário regulatório não é presumido.

Versão de conteúdo é um snapshot dos dados editáveis; revisão de concorrência aumenta também nas transições, portanto os números dos snapshots podem ter intervalos. Histórico de transições é separado. Catálogos são globais autenticados e não contêm obrigações legais reais no seed.

## Uso
Ambiente local já atualizado. Para instalação nova/atualização:
```sh
docker compose up --build -d
docker compose exec backend python manage.py seed_foundation
docker compose exec backend python manage.py seed_commitments
```
Seed Fase 2 cria cinco entidades fictícias, categoria demonstrativa e três compromissos, sem alterar registros existentes. Ele requer contas/unidades do seed da fundação. Dados E2E são claramente fictícios, têm título único e permanecem com auditoria; não são apagados ao concluir o teste.

Na aplicação: demandante1 → Compromissos → Novo compromisso → unidade Riscos → demandado1. Demandado1 → Minhas atribuições → Iniciar execução → Registrar providência → Submeter conclusão. Demandante1 → Validações pendentes → aprovar/rejeitar. Administrador → Auditoria; Usuários e papéis abre /admin/.

## Fora desta entrega
Calendário Fase 3, motor de recorrência Fase 4, notificações/outbox/SMTP Fase 5, campos dinâmicos Fase 6, relatórios/exportações Fase 7 e evidências protegidas/avaliações amplas de segurança na evolução do produto. Não existem anexos, e-mails automáticos ou geração de séries nesta fase. Payloads não podem alterar status diretamente.

## Limites operacionais
Proteção por triggers impede alterações comuns, mas não impede DBA/owner de desabilitar triggers ou executar TRUNCATE. Produção requer credenciais runtime sem DDL/TRUNCATE, papel separado de migrations, retenção, backup e trilha externa conforme política corporativa. Docker de desenvolvimento não representa alta disponibilidade. Manutenção da árvore valida ciclos no Admin; alterações simultâneas de hierarquia ainda requerem serialização operacional, não há bloqueio global da árvore.
