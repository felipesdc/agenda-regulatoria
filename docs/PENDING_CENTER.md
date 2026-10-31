# Central de pendências

Disponível em `/pendencias`, no menu **Central de pendências** e no atalho do Painel inicial. A rota exige sessão válida e conserva o retorno após login.

## Indicadores e listas

- **Atrasados:** ocorrências em aberto com vencimento anterior à data atual.
- **Próximos 7 dias:** ocorrências em aberto com vencimento entre hoje e hoje + 7 dias, inclusive; inclui o dia atual.
- **Aguardando validação:** ocorrências no estado `awaiting_validation`, em qualquer data de vencimento.

Em aberto significa pendente, em andamento, rejeitado ou aguardando validação. Concluídos e cancelados não entram na central. Uma mesma ocorrência pode pertencer a um grupo por prazo e ao grupo de validação: os totais dos cartões não são somáveis.

Os cálculos usam a data institucional em `America/Sao_Paulo`. Cada grupo tem paginação de 50 registros, ordenados por vencimento, identificador e ID para desempate estável. Os contadores consideram todo o conjunto autorizado, independentemente da página exibida. Se uma página deixa de existir após alterações, a central volta à primeira página.

Selecione um cartão para trocar de grupo. **Atualizar pendências** refaz a consulta. Abrir uma ocorrência apresenta os detalhes em diálogo, com os mesmos controles de edição, execução e validação existentes. Ao fechar, a central atualiza contadores e registros, preservando o grupo e a página quando possível. As validações exibidas são as consultáveis pelo usuário; aprovar/rejeitar depende das permissões da ocorrência e da separação entre execução e validação.

## API e autorização

`GET /api/v1/pending-center/?bucket=overdue&page=1`

`bucket` aceita `overdue` (padrão), `upcoming` ou `validation`. A resposta inclui `count`, `next`, `previous`, `results`, `as_of`, `bucket` e `counts` com o total dos três grupos. Parâmetros desconhecidos e grupos inválidos são rejeitados. A descrição da resposta está no OpenAPI/Swagger.

A API reaplica o escopo existente em todas as consultas: demandantes veem as unidades autorizadas; executores veem suas atribuições em unidades com papel ativo; administradores têm acesso global explícito. Unidades inativas ficam excluídas. Há autenticação obrigatória e `Cache-Control: no-store, private`. Não há nova tabela, migração, mudança de papéis ou concessão de acesso. Os guards da interface complementam a autorização do backend.

## Verificação

Os testes de backend cobrem limites de hoje/+7/+8, sobreposição entre grupos, exclusão de concluídos/cancelados, ausência de duplicação por responsáveis, escopo entre unidades, unidade inativa, revogação de papel, administrador, autenticação e paginação.

`frontend/pending.spec.ts` verifica os grupos e suas respostas reais, contadores, paginação, detalhes, rota direta/recarregamento, link do painel, axe e ausência de transbordamento em desktop e celular. Registros fictícios são criados pela API; uma sessão separada de executor registra providência e submete a conclusão. O demandante aprova pela interface, e a central confirma a saída da ocorrência do grupo de validação ao fechar os detalhes. Os registros fictícios permanecem no ambiente local para preservar a trilha de auditoria.

Durante a regressão foi corrigida uma corrida na verificação da sessão após login: o sucesso da autenticação agora exige uma nova consulta de sessão, mesmo quando existe uma consulta anônima anterior em andamento. O teste em `routing.spec.ts` atrasa uma resposta anônima real até depois do login e confirma a entrada no painel com a nova sessão.
