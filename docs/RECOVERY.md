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

O ensaio local prova restauração/schema/immutabilidade e uso da fila retida em cópia. Não substitui PITR/WAL, replicação, recuperação de provedores externos de anexos, recuperação do cofre/SSO, teste em infraestrutura corporativa ou aprovação de RPO/RTO.

## Backup automatizado no host Compose

`tools/scheduled_backup.py` executa sempre o ensaio completo de `backup.py --restore-check`: restaura em base temporária, verifica históricos e integridade dos anexos e só então aplica retenção. É destinado ao ambiente Compose com serviço `db`; o perfil institucional com PostgreSQL externo exige agendamento/credenciais próprios da infraestrutura.

```sh
python3 tools/scheduled_backup.py --directory /caminho/privado/agenda-backups
```

Padrões: 30 dias de retenção, preservando no mínimo as sete cópias verificadas mais recentes, mesmo que antigas. Apenas pares `agenda-DATA-UUID.dump/.json` com restauração e integridade de evidências confirmadas, tamanho e SHA-256 corretos são elegíveis à limpeza. Arquivos manuais, incompletos, inválidos e links simbólicos ficam preservados para revisão. A retenção só roda após verificar a cópia recém-criada. O lock impede sobreposição **no mesmo diretório**; todos os agendamentos devem usar esse destino. Não mover/substituir arquivos durante a execução. O diretório deve pertencer ao operador e não ser compartilhado para escrita.

`last-run.json` registra sucesso/falha, início/fim UTC, nome da cópia e quantidade removida, sem dados do banco nem saída bruta do subprocesso. Diretório 0700 e arquivos 0600. Falha retorna código 1; execução simultânea é ignorada com código 0, preservando o resultado anterior. Monitorar o código de saída **e a idade do último sucesso**: agendamento desligado não produz uma nova falha. O timeout padrão é uma hora; se interrompido, revisar possíveis bases `phase8_restore_*` e dumps sem manifesto antes do próximo ensaio. Nunca remover a base de origem.

### Linux com systemd

Modelos em `deploy/systemd/agenda-backup.service` e `agenda-backup.timer`: execução diária às 03h no fuso do host, com atraso aleatório de até 15 minutos e recuperação da execução perdida após reinício. Ajustar caminhos, usuário, retenção e fuso antes de instalar. O usuário precisa ler o projeto/configuração e operar o Docker; acesso ao socket Docker equivale a privilégio administrativo no host. Usar a conta operacional já autorizada, sem conceder isso ao usuário web. Preparar o destino privado com proprietário correto.

Após adaptar e instalar os dois arquivos em `/etc/systemd/system`, o operador pode ativar:

```sh
sudo systemctl daemon-reload
sudo systemctl enable --now agenda-backup.timer
sudo systemctl start agenda-backup.service
systemctl list-timers agenda-backup.timer
journalctl -u agenda-backup.service
```

Os modelos não são instalados/ativados automaticamente. Falhas precisam ser integradas ao monitoramento institucional; nenhum e-mail é enviado pelo script.

### macOS / cron

Com Docker Desktop iniciado, usar caminhos absolutos e um PATH que encontre o Docker e seu plugin Compose. Exemplo de entrada no `crontab` do operador (adaptar diretório e Python):

```cron
0 3 * * * PATH=/Applications/Docker.app/Contents/Resources/bin:/Users/SEU_USUARIO/.docker/bin:/usr/local/bin:/usr/bin:/bin /usr/bin/python3 /CAMINHO/agenda-regulatoria/tools/scheduled_backup.py >> /CAMINHO/PRIVADO/backup.log 2>&1
```

Preparar o log com modo 0600 e rotação, e testar o comando no mesmo ambiente do cron. O Mac deve estar ligado/acordado e Docker ativo; cron não recupera horários perdidos. Nenhum agendamento local é instalado implicitamente.

O backup local inclui os anexos armazenados no PostgreSQL. Não oferece cópia fora do host, cifra, PITR/WAL nem proteção contra perda do disco. Encaminhar cópias verificadas para armazenamento corporativo protegido, definir retenção aprovada e homologar RPO/RTO antes de uso institucional.
