# ADR-0008 — Relatórios por conjunto de vencimentos e exportações limitadas

Status: aceita na Fase 7.

## Contexto

Indicadores com joins de múltiplos responsáveis podem duplicar ocorrências. Estatísticas ambíguas ou exportações que confiam no cliente podem produzir conclusões erradas/expor outras unidades.

## Decisão

Aplicar o escopo de ocorrências existente antes dos filtros; normalizar UUIDs em subconsulta antes de agregações. Relatórios usam conjunto por vencimento e mostram denominadores/amostras. Percentual no prazo usa aprovação final conhecida, em data local; média de conclusão inclui criação/espera, validação usa última submissão anterior à aprovação. Grupos por responsável não são somáveis. Painel mostra conclusões do mês por timestamp separadamente.

Favoritos de relatório privados e auditados, separados do calendário por exigirem período e poderem guardar atraso. Reaplicar autorização a cada consulta/exportação. CSV com proteção de fórmulas; XLSX mínimo OOXML com texto explícito e sem fórmulas/macros. JSON adicional fica em coluna própria para preservar versão/precisão, sem inferir autorização.

Exportações síncronas, limitadas a 5.000 registros/20 MiB e tamanho de célula XLSX; rejeitar excesso, não cortar. Leitura em lotes; transação PostgreSQL normal REPEATABLE READ e auditoria antes da resposta. Registrar filtros/quantidade/hash, não conteúdo duplicado. Não prometer recebimento ou abertura do arquivo por gerar auditoria.

## Consequências

Consulta de grupos e ocorrências é paginada; datas necessárias e intervalo máximo de 366 dias. Métricas de criação/atribuição histórica ou ciclos anteriores exigem outro contrato. Arquivos tratam colunas como texto e não contêm fórmulas analíticas; grandes exportações exigem processo assíncrono futuro. Testes de carga permanecem na Fase 8.
