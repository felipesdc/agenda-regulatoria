# Fase 8 — Robustez e entrega para homologação

Camada de verificação e operação implementada sobre as fases 1–7: regressão funcional, PostgreSQL concorrente, acessibilidade automatizada/teclado, segurança de sessão/proxy, revisão de dependências, ensaios HTTP de carga, backup/restauração isolada e configuração de intranet. A aplicação local foi atualizada; ativação institucional depende dos itens de RELEASE.md.

## Mudanças

- Escopo de ocorrências usa EXISTS para atribuição, evitando multiplicação de linhas. Relatórios removem carregamentos não necessários e usam filtros singulares sem materializar/ordenar o conjunto inteiro de IDs. O painel calcula os contadores que apresenta, sem recalcular médias globais não exibidas.
- Migration 0009 adiciona índices por vencimento/identificador, estado/data final e ocorrência/estado/timestamp da transição. Preserva os dados e os critérios dos indicadores.
- Proxy resolve backend dinamicamente pelo DNS Docker (TTL de dez segundos), limita corpo a 3 MiB, entrega HTML sem cache e assets JS/CSS versionados com cache longo. Cabeçalhos de segurança continuam herdados por todas as rotas. Pode haver erro transitório durante troca do backend; não é disponibilidade contínua.
- Produção exige segredo longo, hosts explícitos e origens HTTPS. Confiança em HTTPS/IP do gateway é opt-in; o gateway sobrescreve os cabeçalhos. IP inválido/lista é recusado como identidade confiável. Ver SECURITY.md para a fronteira de rede e gateways adicionais.
- Suporte a POSTGRES_SSLMODE/POSTGRES_SSLROOTCERT. Exemplo de intranet usa verify-full com CA montada; PostgreSQL corporativo/TLS de banco não foi conectado nesta sessão.
- Readiness exige conexão e schema migrado; não aplica migrations. HSTS não habilita preload/subdomínios automaticamente: warnings W005/W021 são escolhas explícitas, sem silenciar outros checks.
- Contraste dos textos secundários ajustado; ciclo de Tab em diálogos, Escape e retorno à consulta verificados. Erros de campos dinâmicos identificam o campo; Unicode inválido/caractere nulo é rejeitado antes da gravação.
- Interface identifica desenvolvimento/intranet pelo perfil retornado pelo backend, sem exibir números internos de fase.
- Recuperação da fila copiada: comando hold_restored_outbox retém pending/retry/sending como unknown, com motivo/auditoria, sem incrementar tentativa SMTP. Reconciliação administrativa deve preceder reprocessamento. Aceitações conhecidas são preservadas.

## Segurança e acessibilidade verificadas

Playwright verifica CSP, frame denial, nosniff, HTML no-store, CSRF no login/logout, usuário comum sem acesso à lista administrativa, cookie de sessão HTTP-only e invalidação do cookie após logout. Ensaios HTTPS separados verificam cadeia/hostname com CA temporária, cookies Secure, login real, HSTS/CSP, backend não-root com filesystem somente leitura/capabilities removidas e papel de banco que pode operar mas não executar DDL/alterar história.

Axe-core 4.13.0 examina login, painel, relatório, calendário mensal, compromissos, notificações, administração de campos e diálogo de detalhe, em desktop/mobile, com tags WCAG 2 A/AA, 2.1 A/AA e 2.2 AA. Não há exclusões de regras. Teclado verifica skip link, ciclo de foco e Escape. Isso não substitui avaliação manual completa, leitor de tela ou certificação WCAG. Referências: [axe-core Playwright](https://github.com/dequelabs/axe-core-npm/blob/develop/packages/playwright/README.md), [guia de testes de acessibilidade do Playwright](https://github.com/microsoft/playwright/blob/main/docs/src/accessibility-testing-js.md).

npm audit e pip-audit não reportaram vulnerabilidades nas dependências declaradas na consulta de 12/10/2026. É uma consulta a avisos conhecidos, não auditoria de código, pentest, scan de imagens/base OS ou garantia futura. Pipeline inclui essas verificações; execução remota do CI não foi realizada nesta sessão.

## Desempenho observado

Ensaio isolado de dados: 1.000 usuários, 10.000 séries, 100.000 ocorrências; 100 clientes concorrentes/300 GETs autenticados, Gunicorn 3 workers × 4 threads. Clientes compartilham uma unidade e consultam todo o período, caso concentrado de leitura. Sessões reais Django são provisionadas só na base descartável, sem credenciais utilizáveis. Ensaio não mede login simultâneo, execução escrita, upload, SMTP, failover ou carga sustentada prolongada.

| Variante | Erros / 300 | Tempo total | Requisições/s | Maior p95 |
|---|---:|---:|---:|---:|
| Inicial, sem histórico de workflow | 0 | 38,89 s | 7,71 | 19,27 s |
| Otimizada, mesma leitura sem histórico | 0 | 4,81 s | 62,37 | 2,41 s |
| Complementar, datas do motor + 40.000 transições | 0 | 15,48 s | 19,38 | 6,92 s |

Complementar: painel p95=5,779 s; lista p95=5,851 s; resumo p95=6,919 s. Séries têm regras completas, datas calculadas pelo motor e histórico de submissão/aprovação; relatório exerce o índice de transições. Dados são fixtures sintéticas e não são registros institucionais. Docker Desktop: 8 vCPUs, 4.106.604.544 bytes de RAM (aprox. 3,82 GiB), aarch64. Host local/recursos compartilhados; essas medições não são uma comparação de infraestrutura dedicada nem SLA. O resultado com histórico mostra custo de consultas amplas sob concentração: capacidade/latência devem ser homologadas na infraestrutura alvo antes de produção.

Ferramenta: `python3 tools/load_check.py`. Cria/migra/usa/remove apenas phase8_load_UUID, em container de HTTP sem porta publicada. Recusa base já populada/sem prefixo. Não usa a base agenda, não inicia workers na cópia e não gera notificações. Repita quando código/infra/perfil de carga mudar; não infira performance de produção por usar Docker.

## Backup, restauração e intranet

`python3 tools/backup.py --restore-check` cria dump custom PostgreSQL em .backups (diretório 0700, arquivos 0600), SHA-256/manifesto e testa recuperação em phase8_restore_UUID. Compara fingerprints de tabelas de negócio estáveis, verifica oito triggers e bloqueio de UPDATE da auditoria. Base de origem preservada; cópia descartada. Dump contém dados sensíveis, é comprimido mas não cifrado: retenção, cifra, cópia externa e RPO/RTO são atribuições institucionais. Ver RECOVERY.md.

`python3 tools/intranet_probe.py` testa TLS/cookies/login/papel DB restrito/hold da fila sobre cópia phase8_tls_UUID. Usa CA/chave/role/containers temporários e os remove. Não instala certificados corporativos nem envia e-mails. Testa o transporte web; não homologa SSO, SMTP/DSN ou TLS do PostgreSQL externo.

compose.intranet.yaml e .env.intranet.example são separados do desenvolvimento. Não expõem backend/banco, não incluem Mailpit/seed; frontend usa certificado montado e loopback por padrão. Backend/worker sem capabilities e somente leitura; Beat tem volume próprio e uma instância. PostgreSQL externo/runtime sem DDL; migrations com credenciais separadas antes de subir aplicação. A sintaxe do Compose foi validada sem carregar segredos. Não foi ativado o ambiente institucional.

## Reexecução

```sh
# Desenvolvimento local
docker compose up -d --build backend frontend worker scheduler
docker compose exec -T backend python manage.py test --noinput
python3 tools/backup.py --restore-check
python3 tools/load_check.py
python3 tools/intranet_probe.py

# Browser: DEMO_PASSWORD no ambiente, igual ao seed existente
cd frontend
E2E_BASE_URL=http://localhost:8080 npm run test:e2e
```

Migrations, OpenAPI, lint/formato e TypeScript/build entram no pipeline. Resultados finais em TESTING.md/VERIFICATION.md e PHASE8_RESULTS.json. Runbook de atualização/homologação em RELEASE.md; recuperação em RECOVERY.md. Limitações de anexos/SSO/antivírus/retenção/infraestrutura continuam explícitas; não há declaração de conformidade legal, ASVS ou disponibilidade formal.
