# Fase 7 — Gestão e relatórios

Painel inicial com indicadores autorizados e atenção imediata; relatórios paginados com filtros combinados, agrupamentos, favoritos pessoais, CSV/XLSX auditados e edição administrativa de entidades/categorias. Não depende de CDN, serviços de análise ou novas credenciais.

## Uso

- **Painel inicial**: pendentes, ocorrências em aberto vencendo até hoje + 7, atrasados, aguardando validação, conclusões no mês e total autorizado. Atenção imediata mostra até dez ocorrências, em ordem de vencimento, clicáveis para o detalhe existente.
- **Relatórios**: informe início/fim pelo vencimento (até 366 dias inclusive), combine pesquisa, unidade, entidade, categoria, demandante, responsável, estado, prioridade, periodicidade e atraso. Consulte para aplicar os filtros. O detalhe abre em diálogo com o workflow existente; fechar ou pressionar Escape mantém filtros/página e atualiza os indicadores.
- Grupos por unidade, entidade, responsável ou periodicidade têm paginação própria. A ocorrência é contada uma vez no total; no agrupamento por responsável, conta uma vez para cada atribuição atual. Não some esses grupos para inferir o total geral.
- **Favoritos de consulta**: salve/aplique/exclua filtros pessoais, incluindo período e atraso. São separados dos favoritos de calendário. A permissão atual é reaplicada a cada uso; um favorito não concede acesso.
- **Exportar CSV/XLSX**: exporta todas as páginas dos filtros da última consulta aplicada. Alterar um controle sem consultar não altera a seleção do arquivo. São até 5.000 ocorrências/20 MiB; excesso retorna erro, sem truncamento.
- Administrador: **Administrar entidades e categorias** no relatório permite renomear/ativar/desativar com justificativa e comparação do estado anterior. Criação continua em Compromissos; usuários/papéis/unidades continuam na administração auditada existente. Não há exclusão física de catálogos. Nomes exibidos usam o catálogo atual; identificadores, ocorrências, workflow e valores históricos não são regravados.

## Critérios e denominadores

Todos os relatórios analisam **ocorrências cujo vencimento está no período**, respeitando todos os filtros aplicados. Não misturam esse conjunto com conclusões cujo timestamp esteja no período. Data atual/fuso institucional usam as configurações Django existentes, America/Sao_Paulo por padrão.

| Indicador | Critério |
|---|---|
| Total | Uma ocorrência por UUID; inclui canceladas |
| Pendente | Estado atual pending |
| Próximos sete dias | Em aberto, de hoje a hoje + 7, inclusive (o intervalo inclui hoje) |
| Atrasado | Vencimento anterior a hoje; estados pending/in_progress/awaiting_validation/rejected |
| Aguardando validação | Estado atual awaiting_validation |
| Concluído no relatório | Estado atual completed no conjunto por vencimento |
| Concluído no painel neste mês | Estado atual completed, data local da aprovação final no mês atual, independentemente do vencimento |
| Recorrente | Periodicity diferente de once; conta ocorrências, não definições |
| Percentual no prazo | Concluídas cuja data local da aprovação final é até o vencimento / concluídas com completed_at conhecido |
| Média de conclusão | Horas da criação da ocorrência à aprovação final; somente concluídas com datas válidas, completed_at >= created_at |
| Média de validação | Horas da última submissão anterior à aprovação final até essa aprovação; somente concluídas com ambos os timestamps |

A interface/API expõem numerador, denominador e tamanho das amostras. Sem amostra, percentuais/médias são null/“Sem amostra”, nunca zero artificial. Conclusões sem timestamp ficam no contador de concluídas, mas não no denominador no prazo. Rejeições/ressubmissões usam a última submissão anterior à conclusão atual. Reabertura remove a conclusão atual conforme o workflow existente. A média de conclusão inclui espera desde a geração, inclusive em séries; não é tempo líquido de trabalho. O percentual usa aprovação final, não afirma cumprimento jurídico da obrigação.

O painel é uma visão global do escopo atual; relatórios são filtrados. As consultas separadas refletem os dados no momento em que cada resposta foi produzida, sem prometer atualização contínua.

## Exportações e segurança

O backend recompõe o escopo autorizado em cada requisição; não recebe uma lista de UUIDs confiada ao cliente. Na Fase 8, escopo/atribuição usam EXISTS para manter uma linha por ocorrência; grupos por responsável usam contagens de UUIDs distintos. Unidades inativas bloqueiam o escopo, inclusive para administrador, conforme regras existentes. Demandados veem somente suas ocorrências atribuídas.

CSV UTF-8 com BOM e separador `;`, aspas/quebras de linha escapadas. Células que possam iniciar fórmulas recebem apóstrofo protetor; conteúdo é tratado como texto. XLSX é um pacote OOXML com células inlineStr (sem fórmulas), cabeçalho congelado e autofiltro; colunas são texto para preservar identificadores/precisão decimal. Não utiliza macros, links executáveis ou conexões externas. Caracteres de controle não permitidos por XML são removidos no XLSX; uma célula acima de 32.767 caracteres retorna erro e orienta usar CSV.

Inclui campos essenciais, responsáveis atuais, data final ISO, UUID do formulário e valores adicionais como JSON em uma coluna, preservando seus identificadores técnicos e strings decimais. A interpretação histórica está no formulário versionado; a exportação não troca a versão nem promove campos JSON a permissões. Não inclui providências, evidências ou senhas.

Leitura em lotes e limite de tamanho antes da serialização final; geração é síncrona e limitada. No endpoint normal PostgreSQL, a transação de exportação utiliza REPEATABLE READ, garantindo uma seleção consistente durante contagem/leitura/prefetch. Dentro de uma transação já aberta (como TestCase), não altera a isolação externa. A auditoria report.exported registra ator, formato, filtros, atraso, quantidade e SHA-256; não duplica o conteúdo completo. Falha de geração/auditoria não entrega arquivo. Registro significa geração autorizada, não comprova abertura/salvamento do arquivo pelo usuário. Respostas de relatório/exportação são privadas e no-store.

## API

- GET `/api/v1/dashboard/`: métricas globais autorizadas, completed_this_month e atenção (até dez).
- GET `/api/v1/reports/summary/`: métricas/denominadores/métodos do conjunto filtrado.
- GET `/api/v1/reports/occurrences/`: lista de ocorrências paginada (50).
- GET `/api/v1/reports/groups/?group_by=unit|entity|assignee|periodicity`: grupos paginados (50).
- GET `/api/v1/reports/export/?output=csv|xlsx`: arquivo, com os mesmos filtros.
- GET/POST `/api/v1/report-favorites/`; DELETE `/api/v1/report-favorites/{id}/`: privados e auditados.
- PATCH `/api/v1/entities/{id}/`, `/api/v1/categories/{id}/`: administrador, name/active/expected_name/expected_active/reason.

Os endpoints de relatório exigem date_start/date_end e aceitam q, unit, entity, category, requester, assignee, status, priority, periodicity e overdue=true|false. Ordenação de ocorrências: vencimento/identificador; grupos: quantidade decrescente/nome. Parâmetros inválidos, desconhecidos, períodos invertidos e UUIDs inválidos retornam 400. Favoritos armazenam filtros normalizados.

## Implantação e limites

```sh
docker compose up -d --build backend frontend worker scheduler
docker compose exec -T backend python manage.py test --noinput
```

Migration cria ReportFavorite com chave única owner/name. Não é necessário alterar .env. OOXML/CSV usam biblioteca padrão, sem dependência nova. CI inclui os módulos críticos de relatórios na cobertura e os cenários Playwright novos.

Não há certificação de desempenho para 100 usuários simultâneos/cem mil ocorrências nesta etapa, pesquisa nos valores adicionais, relatório por ciclos antigos de aprovação ou exportação assíncrona de volumes acima dos limites. Ensaios de carga, segurança, acessibilidade e recuperação pertencem à Fase 8. Resultados executados em TESTING.md/VERIFICATION.md.
