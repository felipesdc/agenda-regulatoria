# Anexos comprobatórios

## Uso

Abra um compromisso como responsável atribuído, inicie a execução e registre uma providência. Em **Anexos comprobatórios**, selecione os arquivos opcionais antes de registrar. Texto e anexos são gravados juntos; se algum arquivo for recusado, a providência não é criada e o texto permanece no formulário para correção. **Limpar anexos** permite continuar sem arquivos. Sair com texto/arquivos ainda não enviados pede confirmação.

No histórico da providência, cada anexo mostra nome, tamanho, data, verificação realizada e SHA-256. **Baixar** consulta a API com a sessão atual; o arquivo é entregue como download, sem visualização HTML/PDF embutida. A aplicação verifica tamanho e hash antes de entregar e registra a autorização de download em auditoria; isso não comprova que o usuário salvou o arquivo em seu dispositivo.

A retirada é lógica, com justificativa obrigatória e identificação de autor/data. O original permanece no armazenamento e nos backups, mas o download normal passa a responder 410, inclusive para administrador. Pode retirar o autor ainda autorizado a executar ou o demandante responsável/administrador, apenas em estados pendente, em andamento ou rejeitado. Aguardando validação, concluído e cancelado bloqueiam a retirada. Não há alteração/substituição nem exclusão física pela API; corrija com nova providência e, quando permitido, retire o anexo anterior.

## Formatos e limites

PDF, PNG, JPEG, TXT UTF-8, DOCX e XLSX. A validação usa conteúdo e estrutura, sem confiar no MIME informado pelo navegador. Imagens são verificadas/decodificadas e limitadas a 20 milhões de pixels, sem animação. PDFs têm estrutura validada, limite de 500 páginas e bloqueio de criptografia, JavaScript, ações automáticas, anexos embutidos e outras ações ativas comuns. Os bytes originais não são regravados; não há verificação de assinatura digital/PAdES.

DOCX/XLSX exigem um contêiner OOXML consistente, XML UTF-8, no máximo 200 entradas e 8 MiB descompactados (até 2 MiB por entrada). São recusados macros, objetos embutidos, ActiveX, conexões/links externos, campos ativos comuns, XML com DTD/entidades, arquivos cifrados, entradas perigosas e compressão diferente de stored/deflate. Documentos com hyperlinks externos ou fontes/recursos embutidos fora da lista permitida podem ser recusados. ZIP genérico, SVG, executáveis, DOC/XLS antigos e documentos protegidos por senha não são aceitos. Essas verificações não equivalem a desarmamento completo de conteúdo nem garantem ausência de ameaças desconhecidas.

| Configuração | Padrão |
| --- | --- |
| `EVIDENCE_MAX_FILE_BYTES` | 2 MiB por arquivo (configurável até 10 MiB) |
| `EVIDENCE_MAX_FILES` | 3 por providência (até 5) |
| Total por envio | 10 MiB de arquivos |
| `EVIDENCE_MAX_OCCURRENCE_BYTES` | 50 MiB por ocorrência |
| `EVIDENCE_MAX_OCCURRENCE_FILES` | 30 por ocorrência |
| Nginx / corpo multipart | 12 MiB |

Um upload handler interrompe a recepção de arquivos grandes/excedentes e marca a requisição para rejeição integral, impedindo que uma lista parcial seja aceita. Arquivos maiores que 256 KiB usam temporários privados do Django; o conteúdo definitivo é gravado apenas depois da validação. Retiradas lógicas continuam contando nas quotas de retenção. Os limites por envio são expostos pela API de política para a interface; as quotas por ocorrência são revalidadas sob bloqueio da ocorrência.

## Antivírus

`EVIDENCE_SCANNER_HOST` e `EVIDENCE_SCANNER_PORT` configuram um serviço clamd privado. O cliente envia os bytes pelo protocolo INSTREAM, com timeout e resposta limitada; só aceita a resposta exata `stream: OK`. Detecção, indisponibilidade, timeout ou resposta inesperada recusam o envio inteiro. Quando um scanner foi configurado, não existe fallback sem inspeção.

Fora de DEBUG, anexos exigem scanner configurado e veredito registrado. Sem scanner, providências somente com texto continuam funcionando. Arquivos criados em desenvolvimento sem antivírus também ficam bloqueados para download fora de DEBUG; não se deve promover a base de demonstração como base institucional.

No ambiente local com DEBUG e sem scanner, apenas a validação estrutural é realizada. O registro armazena `development:structural_only` e a interface informa explicitamente **sem inspeção antivírus**. Não foi instalado ou homologado um antivírus corporativo nesta implementação. Os testes de integração verificam o protocolo por um servidor TCP de teste; não representam uma verificação real com base de assinaturas ClamAV.

A instituição deve fornecer o serviço privado, monitorar disponibilidade e atualização das assinaturas e homologar o fluxo. Não exponha clamd diretamente na rede pública. Referências: [protocolo clamd](https://docs.clamav.net/manual/Usage/ClamdProtocol.html), [implantação oficial em Docker](https://docs.clamav.net/manual/Installing/Docker.html).

## Armazenamento e recuperação

O backend padrão, `DatabaseEvidenceStorage`, implementa a interface Django Storage e mantém os bytes em uma tabela privada (`EvidenceBlob`) do PostgreSQL, separados dos metadados. Uma chave UUID opaca é gerada pelo servidor; nomes fornecidos pelo usuário nunca viram caminhos de armazenamento. Não há `MEDIA_URL`, bucket público ou compartilhamento estático. Upload, metadados e auditoria pertencem à mesma transação no backend padrão. Triggers impedem UPDATE/DELETE em bytes, metadados e retiradas, assim como no restante do histórico.

O dump PostgreSQL contém também os arquivos e não depende de um volume de mídia separado. `tools/backup.py --restore-check` inclui as três novas tabelas nos fingerprints, conferindo bytes e metadados na cópia restaurada. Os backups contêm dados sensíveis e mantêm as proteções de diretório/arquivo já descritas em RECOVERY.md.

`EVIDENCE_STORAGE_BACKEND` seleciona uma classe Django Storage privada; cada evidência registra a classe e a chave utilizadas. O contrato permite preparar adaptadores para filesystem protegido ou objetos corporativos, mas apenas o backend de banco está implementado/testado. Um novo provedor deve impedir URLs públicas, preservar objetos, tratar objetos órfãos em rollback e ter procedimento próprio de backup/restauração antes de ativação. Não basta trocar para um bucket ou diretório público.

## API e autorização

- `GET /api/v1/evidence-policy/`: regras globais para usuários autenticados.
- `POST /api/v1/occurrences/{id}/actions/`: JSON com `text` permanece compatível; anexos usam multipart com `text` e um ou mais campos `files`.
- `GET /api/v1/evidence/{id}/download/`: autenticação e escopo reavaliados, integridade verificada, `attachment`, `application/octet-stream`, `nosniff`, `no-store, private`.
- `POST /api/v1/evidence/{id}/withdraw/`: `{ "reason": "..." }`, autorizado, justificado e auditado.

Consultores de uma ocorrência podem baixar anexos ativos. O upload segue a mesma permissão de registrar providências: responsável atribuído em unidade ativa, em execução/rejeitado. Consultar uma unidade não autoriza enviar anexos em nome de outro responsável. Revogação de papel e unidade inativa bloqueiam acesso. Identificadores desconhecidos ou de fora do escopo respondem 404; sem sessão, 403. Nenhum endpoint expõe chaves internas ou bytes em respostas de metadados, relatórios, filtros na URL ou e-mails.

## Verificação local

Os testes de backend verificam arquivos válidos e falsificados, PDF com JavaScript recusado, quotas incluindo retirados, autorização/revogação/unidade inativa, rollback de arquivo/providência/auditoria, integridade e imutabilidade. Um servidor TCP de teste verifica o enquadramento INSTREAM e as respostas limpa/detectada/erro; ele não é um antivírus real. A interface cobre upload real, rejeição, download com comparação dos bytes/SHA-256, retirada justificada, sessão ausente e outra unidade, com axe em desktop/celular.

O ensaio de restauração em base temporária comparou as três tabelas de anexos estáveis, verificou os SHA-256 dos seis arquivos recuperados (incluindo retirados) e confirmou onze triggers de proteção do histórico. A base original foi preservada. Os arquivos fictícios e seus históricos permanecem no ambiente local; dumps privados ficam em `.backups`, fora do Git.

Para ativação institucional, aplique a migração `0010_evidence` pelo papel de migrações e conceda ao papel de runtime SELECT/INSERT nas três novas tabelas, sem DDL. Mantenha os triggers e o limite do gateway alinhado a 12 MiB. O texto de providência e a justificativa de retirada ficam temporariamente somente para leitura durante a requisição, para evitar perder alterações digitadas depois do início do envio.
