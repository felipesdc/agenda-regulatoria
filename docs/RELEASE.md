# Entrega e homologação de intranet

A aplicação local está verificada. A implantação institucional é uma operação separada, com infraestrutura/segurança/negócio aprovando a matriz abaixo.

| Item | Evidência local / requisito para ativação |
|---|---|
| Autenticação/escopo/workflow | Regressão real; definir SSO/provisionamento, administradores e segregação institucional |
| TLS e origens | Ensaio com CA temporária; fornecer certificado/chave corporativos, hosts/origins/URL interna exatos |
| PostgreSQL | Runtime sem DDL comprovado; provisionar proprietário de migrations separado, verify-full/CA e política de failover |
| Proxy/IP | Cabeçalhos sobrescritos; backend privado. Se houver gateway anterior, configurar real_ip apenas para CIDRs comprovadamente confiáveis |
| SMTP | Mailpit real; homologar servidor/endereço corporativo, TLS, destinatários e recebimento/DSN |
| Dados/demonstração | Não copiar contas/obrigações fictícias à produção. Migrar catálogo/usuários aprovados |
| Retenção e recuperação | Ensaio de dump/restore; aprovar cifra, cópia externa, retenção, RPO/RTO/PITR e reconciliação do SMTP |
| Capacidade | Ensaio local com 100 clientes e histórico; aprovar SLA e repetir no hardware/dados/mix de escrita alvo |
| Acessibilidade | Axe/teclado automatizados; avaliação manual com leitores de tela e estados restantes |
| Segurança | Auditoria de avisos das dependências; pentest/ASVS, imagens/base OS e controles corporativos ainda precisam de homologação |
| Evidências/anexos | Upload privado, hash, retirada lógica e backup no PostgreSQL implementados; scanner corporativo, retenção e homologação institucional seguem pendentes. Ver EVIDENCE.md |

## Preparação

1. Construir/verificar as imagens em rede autorizada e promover digests aprovados ao registro interno. Manter wheelhouse/cache npm e imagens para operação sem internet; o browser usa apenas assets locais. Não fazer npm/pip no runtime.
2. Copiar .env.intranet.example para .env.intranet e preencher via cofre (não git). Proteger o arquivo. .env de desenvolvimento permanece separado. Configure INTRANET_HOST, ALLOWED_HOSTS, origens HTTPS e NOTIFICATION_BASE_URL de forma coerente. Se usar acesso direto em 8443, origens/URL devem incluir a porta; normalmente o gateway institucional oferece 443.
3. Montar TLS_DIRECTORY com fullchain.pem/privkey.pem e POSTGRES_CA_FILE público para verify-full. Não incorporar chaves ou senhas nas imagens.
4. Provisionar agenda_migrate como proprietário controlado e agenda_app como login não superusuário, sem CREATEDB/CREATEROLE/membership do proprietário. O runtime precisa SELECT/INSERT/UPDATE/DELETE nas tabelas e USAGE/SELECT/UPDATE nas sequências; não CREATE/TRUNCATE/ALTER. Exemplos de grants devem ser revisados pelo DBA:

```sql
REVOKE CREATE ON SCHEMA public FROM PUBLIC;
GRANT USAGE ON SCHEMA public TO agenda_app;
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO agenda_app;
GRANT USAGE, SELECT, UPDATE ON ALL SEQUENCES IN SCHEMA public TO agenda_app;
ALTER DEFAULT PRIVILEGES FOR ROLE agenda_migrate IN SCHEMA public
  GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO agenda_app;
ALTER DEFAULT PRIVILEGES FOR ROLE agenda_migrate IN SCHEMA public
  GRANT USAGE, SELECT, UPDATE ON SEQUENCES TO agenda_app;
```

5. Backup/revisão da migration 0009 e execução única de migrations pelo proprietário em job controlado, antes de iniciar aplicação. O perfil institucional não migra automaticamente; runtime não possui DDL. Não executar seed.
6. Revisar gateway/rede. TRUST_PROXY_HTTPS=true é permitido somente quando o TLS gateway sobrescreve X-Forwarded-Proto e X-Agenda-Client-IP e não existe caminho público ao backend. O modelo Nginx usa seu remote_addr; um gateway adicional exige configuração explícita de IP real confiável. Não aceitar X-Forwarded-For arbitrário.

## Ativação e atualização

```sh
# Arquivo separado; não fazer merge com compose.yaml de desenvolvimento.
docker compose --env-file .env.intranet -f compose.intranet.yaml config -q
docker compose --env-file .env.intranet -f compose.intranet.yaml up -d
```

Esses comandos são para operação já homologada; não foram executados contra infraestrutura institucional nesta sessão. Porta TLS fica em loopback por padrão; exposição/balanceamento/firewall são decisões da equipe de rede. PostgreSQL é externo e não tem serviço/porta pública no manifesto. Redis não é publicado; manter uma instância de Beat. Backend/worker são somente leitura, /tmp é temporário e Beat usa volume próprio.

Após cada alteração: executar checks/testes, backup, migrations com usuário separado, atualizar imagens, verificar /ready/, login/escopo, workflow, outbox e exportação. Recriação pode produzir erro transitório/TTL de DNS; planejar manutenção ou redundância/rolling com infraestrutura própria. Docker sozinho não garante alta disponibilidade. Definir recurso/timeout/monitoramento conforme o ensaio alvo; não escalar Beat.

HSTS aplica só ao host. Preload e includeSubDomains não são habilitados automaticamente; security.W005/W021 são escolhas registradas para evitar alterar política de domínios sem aprovação. Outros avisos de deploy devem ser resolvidos. DB backup/restore em RECOVERY.md; critérios/resultados locais em PHASE8.md e TESTING.md.
