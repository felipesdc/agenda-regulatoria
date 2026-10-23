# ADR-0007 — Formulários publicados imutáveis e valores JSONB

Status: aceita na Fase 6.

## Contexto

Administradores precisam acrescentar campos sem migrations por campo. Alterar rótulo, opções ou regra de validação não pode modificar a interpretação de registros históricos. Regras de autorização/workflow não podem depender de conteúdo arbitrário em JSON.

## Decisão

Manter catálogo relacional de campos revisados e publicar FormVersion imutável por categoria. Cada publicação copia os metadados completos dos campos e registra autor/justificativa. Triggers protegem publicações; catálogo permanece editável e auditado. Identificador/tipo são estáveis.

Definição e ocorrência têm FK PROTECT para a versão aplicada e objeto JSONB de valores adicionais. Snapshots incluem versão e valores; templates de recorrência congelam os mesmos dados. Datas essenciais, estado, unidades e responsabilidades permanecem relacionais. Criar usa apenas a versão vigente confirmada pelo cliente, sob bloqueio da categoria; editar usa a original. Novas publicações nunca migram silenciosamente registros ou séries.

Validação estrita dos 13 tipos e limites no backend, decimal como texto para preservar precisão, datetime com fuso e referências limitadas à unidade responsável. Não executar regex/código fornecido pelo administrador. Catálogo mutável e publicação exigem administrador; acesso aos valores segue o escopo da ocorrência. Referências não são permissões.

## Consequências

Metadados completos são duplicados deliberadamente em publicações para interpretação histórica. Mudança de tipo exige novo campo. Desativação do catálogo exige republicação para retirar campo de novos compromissos. Não há adoção retroativa, migração automática de valores nem edição em massa de dados adicionais da série nesta etapa. Consulta/exportação destes valores pode ser evoluída com índices específicos quando os usos justificarem.
