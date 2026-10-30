# Continuidade das consultas — 29/10/2026

Compromissos, Minhas atribuições, Validações pendentes e Auditoria lembram a última consulta aplicada e sua página ao trocar de seção e retornar. Abrir/fechar detalhes mantém a consulta existente.

- Cada usuário/lista tem estado separado, em memória da aba. Não se armazenam resultados, credenciais ou consultas em localStorage/sessionStorage.
- Texto/estado alterados no formulário só passam a definir a consulta após Filtrar; a paginação usa os filtros aplicados, sem aplicar um rascunho implicitamente.
- Consulta com erro preserva os últimos filtros aplicados/página; se uma página salva retornar 404 por deixar de existir, a aplicação busca a primeira página e mantém os filtros.
- Retornar à lista sempre consulta o backend e reaplica autorização atual. Não há cache de registros.
- Logout bem-sucedido limpa o estado. Recarregar/fechar a aba também o descarta. Relatórios/calendário continuam com seus fluxos/favoritos próprios; não foram alterados nesta melhoria.

Implementação: CommitmentQueryStore fornecido na raiz da aplicação, com cópia de estados por usuário/modo; consultas aplicadas separadas dos controles de formulário em Commitments e limpeza no logout.

Verificação Playwright desktop/mobile: cria série fictícia de 51 ocorrências pelo backend real; filtra, altera rascunho, pagina, troca de seção e retorna à página 2; abre/fecha detalhe; testa página salva inválida com resposta HTTP 404 simulada; confirma isolamento entre listas e limpeza após logout/login. A simulação 404 existe apenas no teste; os demais dados/consultas usam API e PostgreSQL locais. Resultados da regressão em TESTING.md.

Durante a regressão foi corrigido também um bloqueio indevido no scanner de vencimentos: a consulta usava FOR UPDATE nas tabelas relacionadas (unidade/demandante) junto com a ocorrência. Agora bloqueia somente a ocorrência (`of=("self",)`), evitando o ciclo de locks com gravações concorrentes de auditoria. Um teste PostgreSQL pausa o scanner dentro da transação e confirma que unidade/demandante continuam disponíveis para lock independente.

O teste de calendário foi ajustado para navegar além dos dias adjacentes da grade de 42 dias; a aplicação continua mostrando os dias de meses vizinhos normalmente.
