# Fase 6 — Campos dinâmicos

Implementa catálogo de campos administrável sem alterações de código ou migrations por campo, formulários publicados por categoria, renderização reativa no cadastro/edição e valores JSONB vinculados à versão usada. Campos essenciais, autorização, datas de vencimento e workflow continuam relacionais.

## Uso

1. Entre como administrador e abra **Campos personalizados**.
2. Cadastre nome, identificador técnico, tipo, descrição, obrigatoriedade, padrão, regras, opções, ordem e estado ativo. Toda gravação exige justificativa.
3. Selecione uma categoria e os campos; publique uma versão do formulário. A ordem vem do catálogo, com identificador como desempate.
4. O demandante seleciona a categoria ao criar um compromisso. O formulário vigente aparece com os valores padrão; campos obrigatórios precisam ser preenchidos.
5. Detalhes e edição usam a versão original da ocorrência. A alteração exige justificativa e revisão, produz snapshot/auditoria e notificação de alteração relevante.

Editar um campo modifica o catálogo e incrementa sua revisão. **Publique outra versão** para aplicar a alteração a novos compromissos. Desativar um campo impede sua inclusão em novas publicações; formulários já publicados permanecem válidos. Para retirar um campo de novos compromissos, publique sem ele. Publicar uma versão sem campos esvazia o formulário para novos cadastros.

Não há migração automática de valores antigos, troca de tipo ou adoção retroativa de um formulário. Compromissos existentes sem formulário permanecem sem campos adicionais. Reabrir uma conclusão mantém sua versão original; regras existentes de autorização e workflow continuam aplicáveis. Um novo tipo ou identificador exige outro campo.

## Tipos e contrato de valores

| Tipo | JSON | Validação |
|---|---|---|
| Texto curto | string | Até 500 caracteres; min_length/max_length |
| Texto longo | string | Até 20.000 caracteres; min_length/max_length |
| Inteiro | integer | Sem booleanos/frações; até ±9.007.199.254.740.991; min/max |
| Decimal | string, como `"123.45"` | Até 28 algarismos, 8 casas ou decimal_places menor; min/max como strings; sem expoente/NaN/Infinity |
| Data | `"2028-02-29"` | ISO, data existente, min/max |
| Data e hora | `"2026-10-11T14:30:00-03:00"` | ISO com fuso; min/max com fuso comparados como instantes |
| Seleção única | string | value publicado nas opções |
| Seleção múltipla | array de strings | Opções publicadas, sem duplicatas |
| Booleano | true/false | Não aceita texto ou números; false satisfaz obrigatoriedade |
| URL | string | HTTP/HTTPS; até 2.048 caracteres; não é link executável no detalhamento |
| E-mail | string | Formato validado; até 254 caracteres |
| Referência a usuário | UUID string | Usuário ativo associado à unidade responsável |
| Referência a unidade | UUID string | A própria unidade responsável ativa |

Referências não ampliam acesso nem atribuem papéis/responsabilidades. Não permitem padrão fixo global. Uma referência histórica inativa pode ser mantida sem substituição em edição; uma nova referência exige validação atual. Identificadores UUID são preservados no detalhamento de referências a usuário.

Campo vazio é armazenado como null; false e zero são valores preenchidos. No cadastro, uma chave omitida recebe o padrão; null explícito não recebe padrão. Na edição, custom_values substitui o objeto completo, validado contra o formulário original; omitir custom_values preserva os valores atuais. Não se reaplicam padrões na edição. Campos desconhecidos são rejeitados. Até 50 campos por formulário e 100 opções por seleção.

A UI de administração aceita regras/padrões em JSON, com ajuda e exemplos. Opções usam uma linha por `value | label`. Regras não suportam código, expressões ou regex arbitrárias. Tipos e limites são checados no servidor, independentemente da UI. A UI usa horário local do navegador no controle de data/hora e envia ISO com fuso; esse campo adicional não altera a data do calendário. Uma edição que não muda o instante preserva a string original, incluindo offset e frações de segundo, sem truncamento silencioso.

## Versionamento, recorrência e segurança

CustomFieldDefinition é catálogo relacional, com revisão e auditoria dos metadados. FormVersion contém cópia completa dos metadados, referências relacionais à categoria/autor e revisão única por categoria. Triggers PostgreSQL/SQLite impedem atualização e exclusão das versões publicadas. Não há DELETE de campos pela API.

Definição e ocorrência referenciam FormVersion por FK PROTECT e possuem custom_values JSONB no PostgreSQL. Snapshots de ocorrência registram versão e valores. Publicação e criação bloqueiam a mesma categoria; a criação exige o UUID da versão vigente quando existir formulário, evitando salvar um formulário desatualizado. Metadados administrativos são globais e legíveis por usuários autenticados; catálogo de campos e mutações administrativas exigem superusuário ativo. Valores permanecem acessíveis somente pelo escopo das ocorrências.

A recorrência copia formulário e valores no template versionado e em cada ocorrência. Alterar uma ocorrência não muda as demais. Publicar um novo formulário não muda séries existentes nem suas gerações futuras; preserva o template original. O editor de séries mantém os campos adicionais atuais e não oferece migração de formulário.

Valores adicionais não são incluídos nos e-mails, logs operacionais ou listagens de calendário. Texto é interpolado/escapado, sem HTML ativo. Alterações de metadados, publicações e valores participam da transação da auditoria; falha de auditoria desfaz a mutação.

## API

- GET/POST `/api/v1/custom-fields/`: catálogo administrativo. POST exige revision=0 e reason.
- GET/PUT `/api/v1/custom-fields/{id}/`: edição completa com revisão vigente; key/kind estáveis.
- GET/POST `/api/v1/form-versions/`: histórico/publicação. Filtros category e latest=true; publicação exige revisão anterior (zero inicialmente), reason e lista UUID fields.
- GET `/api/v1/form-versions/{id}/`: versão imutável.
- GET `/api/v1/custom-field-users/?unit={uuid}`: referências ativas autorizadas, paginadas, somente demandante da unidade/admin.
- POST `/api/v1/definitions/`: adiciona form_version e custom_values.
- PATCH `/api/v1/occurrences/{id}/edit/`: custom_values completo opcional; não permite trocar form_version.
- GET `/api/v1/occurrences/{id}/`: inclui form_version, form_schema e custom_values. Listas permanecem compactas.

Exemplo de catálogo decimal: kind=decimal, default=`"0.00"`, rules=`{"min":"0.00","max":"999999.99","decimal_places":2}`, options=[], required=true. O cadastro de ocorrência envia custom_values como `{"valor":"123.45"}`, não como float.

## Implantação e verificação

As migrations são aplicadas pelo backend no Compose. Não é necessário mudar .env nem reinstalar PostgreSQL.

```sh
docker compose up -d --build backend frontend worker scheduler
docker compose exec -T backend python manage.py test --noinput
```

Resultados de verificação e capturas em TESTING.md e VERIFICATION.md. Pesquisa/exportação dos valores adicionais e migração explícita entre formulários são extensões futuras; não fazem parte deste editor.
