# Implantação
Compose fornecido é de desenvolvimento: HTTP em loopback, DEBUG=true, PostgreSQL sem porta pública e volumes persistentes. Build obtém dependências; imagens finais funcionam sem CDN. Redis/worker/Beat atendem a outbox; Mailpit é apenas captura de desenvolvimento.

Produção requer preparar imagens/registro interno, lockfiles e wheelhouse/cache npm em rede autorizada, certificados, DEBUG=false, segredo e senha DB via cofre corporativo. Publicar SPA/API na mesma origem HTTPS. Não usar compose de desenvolvimento como promessa de alta disponibilidade. Revisar forwarding de HTTPS/IP no proxy antes de habilitar SECURE_SSL_REDIRECT (configuração não confia por padrão; opt-in exige gateway privado que sobrescreve os headers). Não há integração SSO ainda.

Executar migrations como job único antes de escalar backend; o comando Compose migra automaticamente apenas para conveniência local. Nginx serve assets locais coletados durante build. Rodar seed exclusivamente em desenvolvimento e não copiar contas demonstrativas para produção.

Backup/restauração: usar `python3 tools/backup.py --restore-check` para ensaio local protegido em base nova. Procedimento institucional em [RECOVERY.md](RECOVERY.md); nunca executar --clean sobre a origem. Dumps exigem cifra/retenção/cópia externa aprovadas.

Health/readiness disponíveis; monitorar erros e latência, banco e posteriormente outbox/filas. Para metas formais de disponibilidade será necessário redundância, failover PostgreSQL, balanceamento, gestão de sessões, observabilidade e exercícios de recuperação. Ensaios locais de leitura estão em PHASE8.md; homologação de capacidade/latência alvo permanece necessária.

Atualização Fase 2: rebuild backend/frontend aplica migrations aditivas de compromissos e auditoria, incluindo triggers. Fazer backup antes de migração em ambientes corporativos. `seed_commitments` é opcional e somente para demonstração. Testes usam banco separado test_agenda; credencial dev necessita criar/remover banco para o test runner, sem afetar agenda. Em produção runtime não deve possuir essas permissões.

## Worker e notificações
A Fase 5 adiciona `worker` e `scheduler` no Compose. Migrations/readiness do backend precedem workers; Redis tem healthcheck. Use apenas um scheduler Beat. Configure SMTP e URL interna pelo ambiente e acompanhe os checkpoints no menu Notificações. DEBUG/Mailpit e destinatários fictícios são somente desenvolvimento. Ver [PHASE5.md](PHASE5.md) para comandos, limites de catch-up, resultados incertos e reprocessamento.

## Fase 6
Reconstrua backend/frontend/worker/scheduler com docker compose up -d --build backend frontend worker scheduler. As migrations acrescentam campos JSONB/FKs e proteção de versões; legado permanece sem formulário. Não requer variáveis novas nem mudanças em .env. Novos campos são cadastrados pela UI, sem migrations individuais.

## Fase 7
Reconstruir backend/frontend/worker/scheduler; migration reports cria favoritos privados. Sem variáveis/dependências novas. Exportação síncrona até 5.000 ocorrências/20 MiB; observar memória/tempo conforme política institucional e verificar dimensionamento na Fase 8. Em requisição normal PostgreSQL, exportação usa REPEATABLE READ; não configura isolação global.

## Entrega para intranet — Fase 8
Perfil independente compose.intranet.yaml/.env.intranet.example, TLS e CA PostgreSQL montados, hosts/origins HTTPS, runtime sem DDL/read-only e migrations separadas. Readiness exige schema migrado. Instruções/limites/gates em [RELEASE.md](RELEASE.md). Não foi ativado ambiente institucional nem feito seed de produção.
