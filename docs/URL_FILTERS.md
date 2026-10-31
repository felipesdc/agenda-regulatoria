# Filtros na URL

A consulta aplicada aparece no endereço da página. Copie esse endereço para compartilhar ou salvar nos favoritos do navegador. Recarregar restaura a consulta, e voltar/avançar percorre os filtros e páginas aplicados. Os dados são consultados novamente na API, com as permissões atuais de quem abriu o link.

## Seções contempladas

| Seção | Parâmetros |
| --- | --- |
| Compromissos, minhas atribuições e validações | `q`, `status`, `overdue`, `page` |
| Auditoria | `record_id`, `page` |
| Calendário | `q`, `unit`, `entity`, `category`, `requester`, `assignee`, `status`, `priority`, `periodicity`, `date_start`, `date_end`, `anchor`, `scale` |
| Relatórios | Filtros comuns do calendário, `overdue`, `page`, `group_page`, `group_by` |
| Notificações | `q`, `status`, `page` |
| Central de pendências | `bucket`, `page` |

Exemplos:

- `/compromissos?q=REG-000001&status=pending&overdue=true&page=2`
- `/calendario?scale=week&anchor=2028-02-29&priority=high`
- `/relatorios?date_start=2028-02-01&date_end=2028-02-29&group_by=entity`
- `/notificacoes?status=failed`
- `/pendencias?bucket=validation`

No calendário, `anchor` define a data base do período e `scale` aceita `month`, `week` ou `year`. Os períodos do calendário e dos relatórios ficam explícitos para que um favorito não mude de mês ao ser reaberto no futuro. Relatórios possuem paginação independente para ocorrências e agrupamentos.

## Aplicação e histórico

Somente a consulta aplicada entra na URL; digitar uma pesquisa sem aplicar não altera o endereço. Paginação, exportação e navegação entre períodos usam os filtros aplicados. Consultas bem-sucedidas criam entradas no histórico; normalização inicial, atualização após ações e correção de página inválida substituem a entrada atual.

Uma URL com parâmetros explícitos prevalece sobre a consulta memorizada da lista. Abrir a lista sem parâmetros ainda permite recuperar a consulta anterior da sessão; a URL é então atualizada para refletir o que está sendo exibido. Uma página que deixou de existir retorna à primeira página mantendo os filtros, inclusive nas duas paginações dos relatórios.

Voltar durante uma requisição aguarda sua conclusão antes de aplicar a consulta escolhida no histórico. A resposta antiga não pode sobrescrever a URL escolhida. Trocar apenas parâmetros na mesma seção preserva formulários em edição; mudar de seção mantém os avisos de descarte existentes. Ao restaurar outra consulta, os resultados antigos são removidos para não serem confundidos com resultados novos em caso de falha.

## Validação e acesso

Cada rota aceita apenas os parâmetros previstos. São normalizados valores de situação, prioridade, periodicidade, agrupamento, escala e grupo de pendências; identificadores de filtros organizacionais usam UUID. Páginas devem ser inteiros positivos com até seis dígitos; datas devem existir no calendário ISO. Parâmetros desconhecidos, repetidos ou com formato inválido são ignorados. Valores padrão são omitidos: página 1, atraso falso, mês, agrupamento por unidade e grupo de atrasados. Restrições adicionais de período e de negócio continuam sendo verificadas pela API.

Os destinos após login preservam somente filtros reconhecidos de rotas internas conhecidas. Destinos externos continuam bloqueados. Auditoria exige administrador, e todos os resultados continuam limitados por usuário, papel e unidade. Compartilhar um link não transfere permissões; outro usuário pode obter resultados diferentes ou vazios.

A aplicação não serializa credenciais, formulários de criação/edição, providências, justificativas, políticas de notificações ou valores de campos personalizados. URLs contêm os termos e identificadores dos filtros e podem permanecer no histórico do navegador; compartilhe os links considerando esse conteúdo. O logout limpa o estado em memória, mas não apaga o histórico do navegador. Não foi introduzido localStorage/sessionStorage nem alteração de API ou de banco de dados.

## Verificação

`frontend/url-filters.spec.ts` cobre caracteres especiais na pesquisa, consulta aplicada versus rascunho, recarregamento, voltar/avançar, retomada após login, limpeza de parâmetros inválidos/repetidos, isolamento entre unidades, recuperação de páginas inválidas, período/escala do calendário, período e agrupamento de relatórios, notificações e pendências. Um teste retém uma resposta real da API e usa voltar enquanto a requisição está em andamento: a consulta do histórico e o formulário em edição devem ser preservados. O teste existente de navegação com uma série fictícia de 51 ocorrências confirma página 2 na URL e restauração após recarregar.
