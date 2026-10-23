# Backup e recuperação

## Desenvolvimento: ensaio seguro

```sh
python3 tools/backup.py --restore-check
```

Requer Docker/Compose ativo e permissões locais para exec no serviço db. Dump/manifesto novos, sem sobrescrever arquivos, em .backups (0700/0600). pg_dump usa credenciais do serviço sem imprimi-las; SHA-256 registra integridade do arquivo. Cópia em base phase8_restore_UUID, nunca agenda; pg_restore --exit-on-error/sem --clean, comparação de tabelas estáveis e proteção de auditoria. A cópia é removida. Alterações legítimas na origem durante dump podem excluir uma tabela da comparação de fingerprints; pg_dump continua fornecendo snapshot consistente.

Não copiar dump para git, e-mail ou suporte. Contém hashes de senha/dados de negócio. Compressão não é cifra. Cofre/cifra, armazenamento externo, retenção e testes periódicos precisam de política institucional. Volumes de Docker não são backup.

## Recuperação institucional controlada

1. Definir janela de manutenção, responsáveis, RPO/RTO e ponto de recuperação. Suspender alterações no gateway e parar worker/Beat antes da mudança. Preservar logs SMTP/auditoria externa e evidências disponíveis desde o snapshot.
2. Verificar SHA-256 do dump e preparar **base nova recovery_DATA**, com proprietário de migrations. Não restaurar sobre agenda nem usar --clean na origem. Configurar credenciais por serviço/cofre, sem senha em argv/logs.
3. Restaurar com pg_restore --exit-on-error --no-owner --no-acl contra a base nova. Validar contagens/fingerprints, FKs, versões e triggers. Aplicar migrations da imagem a homologar com usuário separado; conceder privilégios do runtime depois.
4. Subir somente backend para verificação, mantendo frontend em manutenção, worker/Beat desligados. Confirmar ambiente/hosts/TLS e schema pelo /ready/. Validar login, escopos, amostras de históricos e limites de RPO.
5. Reter fila copiada antes de retomar envio. O comando verifica current_database e recusa nomes comuns/origem:

```sh
python manage.py hold_restored_outbox --expected-database recovery_DATA --reason "Recuperação autorizada: chamado institucional"
# Após revisar a prévia, executar na MESMA base nova:
python manage.py hold_restored_outbox --expected-database recovery_DATA --reason "Recuperação autorizada: chamado institucional" --apply
```

6. pending/retry/sending copiados passam a unknown com registro administrativo (não uma tentativa de SMTP). Accepted/failed/skipped/unknown existentes não são reenviados pelo hold. Reconcilie Message-ID/eventos com SMTP e atividade desde o snapshot; requeue administrativo exige motivo/ack do risco de duplicidade. Não inferir entrega à caixa postal por accepted.
7. Só após reconciliação habilitar worker/Beat e gateway. Verificar políticas/catch-up: o scanner pode recriar eventos ausentes do snapshot, portanto reter a fila copiada **não impede todas as duplicidades externas** após rollback. Atividade fora do RPO e mensagens posteriores ao backup exigem tratamento institucional. Redis/Beat e tarefas antigas também precisam de revisão; não reutilizar fila cegamente.
8. Monitorar autenticação, latência, outbox/leases/jobs, erros e integridade. Registrar decisão/timestamp/base/imagens e resultados; preservar a base anterior para investigação conforme retenção. Não a apagar como parte automática do procedimento.

O ensaio local prova restauração/schema/immutabilidade e uso da fila retida em cópia. Não substitui PITR/WAL, replicação, recuperação de anexos (ainda não implementados), recuperação do cofre/SSO, teste em infraestrutura corporativa ou aprovação de RPO/RTO.
