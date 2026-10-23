# ADR-0009 — Entrega verificável e recuperação isolada

Status: aceita na Fase 8.

## Decisão

Separar validação local de autorização institucional. Criar ferramentas reproduzíveis que usam base/container/role/certificados descartáveis para carga e TLS; backup nunca restaura sobre a origem. Dumps/manifestos privados, hash e teste de imutabilidade na cópia. Retenção da outbox restaurada exige base nova confirmada e motivo; não é tentativa de SMTP nem garantia de exactly-once externo.

Otimizar escopo com EXISTS, evitando joins que duplicam ocorrências; filtros de responsável também EXISTS, demais filtros singulares. Evitar materializar IDs e carregamentos redundantes nos relatórios. Adicionar índices e preservar autorização/denominadores, verificados por regressão. Medir cenários sem/com histórico e registrar resultados/limites de concentração, sem extrapolar SLA.

Axe/teclado/segurança de sessão entram no pipeline. Gateway sobrescreve identidade/protocolo apenas em fronteira privada explicitamente confiada; cookies seguros/hosts/origins e schema migrado exigidos. Perfil institucional usa imagens aprovadas, TLS montado, PostgreSQL externo com CA e usuário runtime sem DDL; migrations fora do runtime, sem seed. HSTS preload/subdomínios ficam sob política institucional.

## Consequências

A entrega é apta à homologação local demonstrada, sem declaração de conformidade/WCAG/HA. Avaliação manual, pentest/imagens, SSO/SMTP/anexos/antivírus/retenção/RPO/RTO e desempenho na infraestrutura alvo continuam pendentes. Consultas amplas com histórico permanecem mais custosas sob concentração; métricas publicadas guiam o próximo dimensionamento. Source/.env e base em uso são preservadas nos ensaios.
