# ADR 0004 — Workflow transacional e história protegida
Aceita. Definição original é imutável pela API e ocorrência tem conteúdo próprio. Usar UUID interno e contador sequencial transacional para REG; sufixo ordinal /0001 evita colisões futuras de ocorrências no mesmo período. Geração recorrente é Fase 4.

Workflow em serviços atomic, bloqueio de linha e revisão otimista. Aprovação própria proibida por atribuição ou submissão, mesmo para superusuário. Edição concluída exige reabertura motivada. Snapshots e eventos de história append-only protegidos por triggers PostgreSQL/SQLite contra UPDATE/DELETE; DBA/DDL/TRUNCATE exige papel runtime separado e controles corporativos. Auditoria faz parte da transação; falha implica rollback de toda mudança.

Papéis por unidade são verificáveis a cada chamada; não existe inferência de acesso pela árvore. Catálogos compartilhados, ocorrências compartimentalizadas. Administração Django de identidade/associações/unidades é restrita a superusuários com eventos sanitizados.
