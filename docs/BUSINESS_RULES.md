# Regras de negócio
Identidade e escopos: usuário ativo, unidade ativa, papéis explícitos e acumuláveis por unidade. Administrador global é superusuário ativo. Não há herança de autorização pela árvore. Usuário comum não lista usuários globais; listagem de demandados para atribuição exige demandante na unidade.

Compromissos, workflow e integridade: regras implementadas e exemplos estão em [PHASE2.md](PHASE2.md). Aprovação da própria execução é bloqueada inclusive para administradores. Rejeição, cancelamento, reabertura e edição exigem motivo. Após rejeição, nova providência obrigatória antes de ressubmeter. Occorrências independentes, atraso derivado e definição original preservada. Revisão de concorrência enviada nas transições/edições. Transação abrange mudança e auditoria.

Login inválido usa mensagem uniforme e bloqueio persistente por IP após cinco falhas por uma hora; sessão inativa expira em 30 minutos. Recorrência, calendários úteis, versões de formulários e eventos outbox permanecem nas próximas fases; nenhuma regra legal real foi inventada no seed.

## Recorrência
Regras determinísticas e limites em [PHASE4.md](PHASE4.md). Geração não replica workflow nem ações. Alterações coletivas limitadas a pendentes sem execução; reprogramação de datas materializadas permanece individual e auditada.

## Notificações
Eventos e destinatários persistem junto com a mutação. Atribuição, alteração relevante e workflow emitem avisos; providências não são reproduzidas em e-mail. Alertas são configurados por definição, depois categoria, depois padrão. Envio não modifica workflow. Aceito pelo SMTP não é entrega; falhas incertas exigem revisão explícita. Regras completas e intervalos em [PHASE5.md](PHASE5.md).

## Fase 6 — Campos adicionais
Novos compromissos usam a versão vigente do formulário da categoria, confirmada pelo cliente. Edição usa a versão original e exige autorização, revisão e justificativa; estados bloqueados continuam bloqueados. Padrões se aplicam apenas a chaves omitidas na criação. false/zero satisfazem obrigatoriedade. Referências devem pertencer à unidade responsável, não atribuem acesso e não permitem padrão fixo. Publicação e desativação não alteram registros/séries existentes. Decimal é texto, datetime inclui fuso. Ver PHASE6.md para os limites.

## Fase 7
Relatórios usam vencimento e filtros autorizados; total é por ocorrência. Grupos por demandado usam atribuições atuais e não são somáveis. Percentual no prazo usa aprovação final em data local sobre concluídas com data conhecida; médias indicam amostra e usam criação→aprovação e última submissão→aprovação. Sem amostra retorna null. Painel conta conclusões do mês por timestamp separadamente. Exportações seguem última consulta aplicada e rejeitam excesso. Ver PHASE7.md para definições completas.
