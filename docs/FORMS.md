# Formulários de compromissos

## Seleção de responsáveis

Criação e edição usam busca por nome/usuário e caixas de seleção, sem necessidade de Ctrl/⌘. A busca mantém as seleções; a lista de selecionados permite remover uma pessoa sem procurar novamente. Trocar a unidade limpa a seleção anterior e carrega os responsáveis autorizados da nova unidade. Um responsável anteriormente atribuído que deixou de estar disponível permanece identificado como indisponível até ser removido explicitamente; o backend mantém a validação de quem pode ser atribuído.

## Validação

Campos obrigatórios exibem mensagens junto ao controle depois de perder o foco, com `aria-invalid` e associação à mensagem. Título limitado a 200 caracteres na criação e edição. Justificativa continua obrigatória na edição, e os campos personalizados mantêm seus validadores e interpretações existentes. Erros devolvidos pelo backend continuam visíveis; o botão de salvar respeita a validade do formulário e as regras de campos personalizados/recorrência.

## Alterações não salvas

Os formulários de criação e edição de ocorrências registram alterações de campos, responsáveis, campos personalizados e recorrência. Fechar, desistir da edição, abrir outro registro, começar outro cadastro, trocar de rota ou sair da sessão pede confirmação antes de descartar. Cancelar a saída preserva o formulário. Apenas pesquisar responsáveis não cria um rascunho de negócio.

Ao recarregar ou fechar a aba, o aviso nativo do navegador é solicitado quando há alterações. O texto e a apresentação desse aviso são controlados pelo navegador. Uma expiração de sessão detectada continua removendo a interface protegida, sem impedir o retorno ao login.

Rascunhos e seleções não são armazenados em localStorage, sessionStorage ou enviados ao servidor antes de salvar. A proteção se aplica à criação/edição de ocorrências e, após a implementação dos anexos, também ao registro de providências com texto/arquivos ainda não enviados. Os demais formulários administrativos e a edição de séries mantêm seu comportamento anterior.

A busca de responsáveis não submete o formulário ao pressionar Enter. Reiniciar um cadastro, após confirmar o descarte, limpa o formulário e o acompanhamento do rascunho anterior. Se uma saída aprovada não se concretiza, a proteção das alterações permanece ativa.

## Verificação de interface

`frontend/forms.spec.ts` cobre erro após sair do título, correção do erro, busca que preserva seleção, remoção de responsável, recusa de descarte ao fechar/trocar de rota, tentativa real de fechar a aba com `beforeunload`, descarte aprovado, reinício limpo, busca sem rascunho e Enter sem submissão. Executa axe e verifica largura em desktop e celular. O teste de criação pelo calendário também tenta desistir da edição e fechar o painel, recusando ambos para confirmar a preservação dos valores antes de salvar.
