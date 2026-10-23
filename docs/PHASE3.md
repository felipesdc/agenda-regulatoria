# Fase 3 — Calendário
## Implementado
- Visão mensal padrão: grade de 42 dias iniciando na segunda-feira, dia atual destacado, identificação e situação em texto nos cartões, até três cartões/dia e indicador de itens adicionais.
- Visão semanal: sete dias com vencimentos de dia inteiro e acesso paginado aos demais itens.
- Visão anual: doze minicalendários, contagens por mês e indicação dos dias com vencimentos; selecionar mês retorna à visão mensal.
- Navegação anterior/próximo/Hoje. Mudar escala preserva ano/mês/data em foco. Fim de mês é ajustado ao último dia válido; ano bissexto testado. Data corrente em America/Sao_Paulo; aritmética de dias via UTC para evitar DST.
- Filtros combinados: pesquisa, entidade, unidade, demandante, demandado, categoria, prioridade, situação, periodicidade disponível e intervalo de datas. Intervalo é intersectado com o período visualizado.
- Favoritos persistentes por usuário, com nome único por proprietário, aplicação e exclusão. Favorito não concede autorização: cada consulta refaz o escopo.
- Painel modal nativo dialog com detalhes e ações reais da Fase 2, sem duplicar o workflow. Escape, navegação por teclado e foco modal nativo. Eventos alterados atualizam contagens do período.
- Layout responsivo: grade mensal com rolagem interna/hint em celular; semana em lista adaptativa; ano em 1/2/3 colunas. Textos de status complementam cores; dias anuais também são sublinhados. Respeita prefers-reduced-motion.

## Consultas e desempenho
`GET /api/v1/calendar/` exige date_start/date_end inclusivos. Consulta sempre começa pelo escopo autorizado. Ano: summary=true, máximo 366 dias, somente contagens agrupadas no banco. Mês/semana: limite de 62 dias e amostras de até três eventos por dia via ROW_NUMBER. Subquery de IDs elimina duplicações de joins antes de aplicar janela/contagem. Não carrega toda a base histórica nem descrições/históricos para os cartões.

A grade mensal consulta também os dias adjacentes exibidos; o total representa os 42 dias filtrados exibidos. Drilldown de um dia usa /occurrences/ com limite de datas igual e paginação 50. Dados completos/histórico somente ao abrir a ocorrência. Contagens refletem o estado conhecido ao consultar, sem sincronização automática entre navegadores; reconsultar/alterar período para atualizar alterações feitas por outro usuário.

## Limites assumidos
Ainda não há horário de vencimento ou séries recorrentes: todos os eventos são de dia inteiro e a única periodicidade selecionável é Único. Sem mapa de obrigações reais, feriados ou regras de negócio para recorrência nesta fase. Esses recursos pertencem à Fase 4. Não houve certificação WCAG ou teste de carga formal.

## Uso
Abra Calendário na navegação lateral. Use Ano/Mês/Semana ou Hoje. Selecione o dia para listar todos os vencimentos, ou um cartão para abrir os detalhes e executar ações autorizadas. Filtros e favoritos estão no painel expansível. Para atualização em outro ambiente:
```sh
docker compose up --build -d backend frontend
```
Migration commitments/0003 cria apenas SavedCalendarFilter; registros existentes não são reescritos.
