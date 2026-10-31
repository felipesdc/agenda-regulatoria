# Continuidade das consultas — 29/10/2026

Compromissos, Minhas atribuições, Validações pendentes e Auditoria lembram a última consulta aplicada e sua página ao trocar de seção e retornar. Abrir/fechar detalhes mantém a consulta existente.

- Cada usuário/lista tem estado separado, em memória da aba. Não se armazenam resultados, credenciais ou consultas em localStorage/sessionStorage.
- Texto/estado alterados no formulário só passam a definir a consulta após Filtrar; a paginação usa os filtros aplicados, sem aplicar um rascunho implicitamente.
- Consulta com erro preserva os últimos filtros aplicados/página; se uma página salva retornar 404 por deixar de existir, a aplicação busca a primeira página e mantém os filtros.
- Retornar à lista sempre consulta o backend e reaplica autorização atual. Não há cache de registros.
- Logout bem-sucedido limpa o estado. Recarregar/fechar a aba também o descarta. Relatórios/calendário continuam com seus fluxos/favoritos próprios; não foram alterados nesta melhoria.

Implementação: CommitmentQueryStore fornecido na raiz da aplicação, com cópia de estados por usuário/modo; consultas aplicadas separadas dos controles de formulário em Commitments e limpeza no logout.

Verificação Playwright desktop/mobile: cria série fictícia de 51 ocorrências pelo backend real; filtra, altera rascunho, pagina, troca de seção e retorna à página 2; abre/fecha detalhe; testa página salva inválida com resposta HTTP 404 simulada; confirma isolamento entre listas e limpeza após logout/login. A simulação 404 existe apenas no teste; os demais dados/consultas usam API e PostgreSQL locais. Resultados da regressão em TESTING.md.

Durante a regressão foi corrigido também um bloqueio indevido no scanner de vencimentos: a consulta usava FOR UPDATE nas tabelas relacionadas (unidade/demandante) junto com a ocorrência. Agora bloqueia somente a ocorrência (`of=("self",)`), evitando o ciclo de locks com gravações concorrentes de auditoria. Um teste PostgreSQL pausa o scanner dentro da transação e confirma que unidade/demandante continuam disponíveis para lock independente.

O teste de calendário foi ajustado para navegar além dos dias adjacentes da grade de 42 dias; a aplicação continua mostrando os dias de meses vizinhos normalmente.

## Criação e edição pelo calendário — 29/10/2026

Na visão mensal ou semanal, selecione o número ou cabeçalho do dia e use **Criar compromisso nesta data**. A ação aparece para administradores e demandantes; o vencimento recebe a data selecionada, enquanto a referência começa na data atual e pode ser alterada. A criação usa o mesmo formulário, permissões, campos personalizados e regras de repetição da lista de compromissos. Salvar e editar atualizam a agenda com os filtros atuais; um compromisso que não atende aos filtros pode não aparecer na grade.

O formulário agrupa identificação, unidade/responsáveis e classificação/prazos. Se houver somente uma unidade permitida para criação, ela é preenchida e seus responsáveis são carregados. O título recebe foco ao abrir a criação ou edição. As orientações explicam os dados necessários para habilitar o salvamento. A edição informa que altera somente a ocorrência e mantém a justificativa obrigatória e o histórico de versões.

O teste `frontend/creation.spec.ts` cria e edita um registro fictício pela interface em desktop e celular, verifica o vencimento preenchido, o foco, os bloqueios de salvamento, a atualização da agenda e executa axe no formulário aberto. Os registros fictícios permanecem no ambiente local para preservar a trilha de auditoria.

Ao abrir um compromisso pela lista de gestão, a página rola até o início do painel de detalhes e transfere o foco para ele. Isso também funciona nas listas de atribuições e validações, mantendo filtros e paginação. Os detalhes abertos em diálogos do calendário e dos relatórios mantêm sua navegação própria.

## URLs e proteção de rotas — 29/10/2026

A navegação usa Angular Router e links nativos: é possível copiar endereços, abrir seções em outra aba, atualizar a página e usar voltar/avançar. O menu identifica a página atual; o título da aba acompanha a seção. O Nginx já encaminha as URLs da interface para `index.html`, preservando as rotas de API e administração.

| URL | Seção | Acesso |
| --- | --- | --- |
| `/entrar` | Autenticação | Público |
| `/painel` | Painel inicial | Autenticado |
| `/calendario` | Calendário | Autenticado, dados no escopo |
| `/compromissos` | Gestão de compromissos | Autenticado, dados no escopo |
| `/compromissos/:id` | Ocorrência por UUID | Autenticado, autorização na API |
| `/minhas-atribuicoes` | Minhas atribuições | Autenticado, dados no escopo |
| `/validacoes` | Validações pendentes | Autenticado, dados no escopo |
| `/relatorios` | Relatórios | Autenticado, dados no escopo |
| `/notificacoes` | Notificações | Autenticado, dados no escopo |
| `/perfil` | Meu perfil | Autenticado |
| `/unidades` | Minhas unidades | Autenticado, dados no escopo |
| `/auditoria` | Auditoria | Administrador |
| `/campos-personalizados` | Administração dos campos | Administrador |

Os guards consultam a sessão e as unidades no servidor antes de ativar uma seção. Um endereço protegido sem sessão leva a `/entrar`, guardando somente um destino interno conhecido no parâmetro `returnTo`. Após autenticar, a navegação retoma esse destino e verifica novamente as permissões. URLs externas e destinos inválidos são substituídos por `/painel`; não há redirecionamento livre. Endereços desconhecidos levam à página de não encontrado, e áreas administrativas sem permissão levam a acesso não autorizado.

Uma resposta 401/403 de operação da interface dispara uma verificação da sessão: se ela expirou, os dados em memória são limpos e a interface volta ao login. Uma recusa de permissão com sessão válida permanece como erro da operação. O logout limpa o perfil, as unidades e as consultas memorizadas; voltar no navegador exige uma nova verificação da sessão. Credenciais e tokens não são armazenados nas URLs ou em armazenamento local. A autorização de dados continua obrigatória na API; guards não substituem essas verificações.

Links anteriores de e-mail no formato `/?occurrence=UUID` são encaminhados para `/compromissos/UUID`, inclusive quando é necessário autenticar antes. Filtros e paginação das listas continuam em memória, conforme descrito acima.

### Central de pendências — 30/10/2026

A rota protegida `/pendencias` está disponível no menu e no Painel inicial, inclusive como destino seguro após login. Os detalhes abrem em diálogo; fechar atualiza os indicadores e a lista mantendo o grupo e a página quando possível. Regras em [PENDING_CENTER.md](PENDING_CENTER.md).

### Formulários com alterações não salvas — 30/10/2026

Sair de uma rota, fechar um painel de criação/edição ou fazer logout pede confirmação quando há alterações de compromisso ainda não salvas. Cancelar mantém os dados. A sessão expirada continua voltando ao login. Ao fechar/recarregar a aba, o navegador pode mostrar seu aviso nativo. Consulte [FORMS.md](FORMS.md) para alcance e limites.

### Filtros na URL — 30/10/2026

As consultas aplicadas agora usam parâmetros na URL em compromissos/atribuições/validações, auditoria, calendário, relatórios, notificações e pendências. A URL explícita tem prioridade sobre a memória da sessão; links de listas sem parâmetros ainda podem recuperar a consulta anterior. Filtros, páginas e períodos são restaurados ao recarregar e pelo histórico, inclusive após login. Alterações em formulários não entram no endereço. Regras, exemplos e limites em [URL_FILTERS.md](URL_FILTERS.md).
