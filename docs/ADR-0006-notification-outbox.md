# ADR 0006 — Outbox de notificações e resultados SMTP
Status: aceita na Fase 5.

Evento e destinatários ficam no mesmo PostgreSQL e transação do compromisso. Beat consulta a outbox e publica IDs via Redis; o worker usa claim/lease com lock e registra tentativas/resultados. Polling recupera a lacuna banco/broker sem fazer a disponibilidade do Redis determinar o sucesso da mutação de negócio. Um wake-up após reprocessamento manual acelera a rodada, mas não é a fonte de durabilidade.

Unicidade de evento/destinatário e claim impedem duplicação interna por reexecução/concorrência. SMTP não participa da transação de banco; portanto, não se promete exatamente uma entrega externa. Aceitação, falha e incerteza são estados distintos; resultado incerto exige revisão e reconhecimento explícito do risco para resend. Destino e contador das tentativas são preservados; backoff e agenda persistem no banco. Message-ID estável ajuda correlação, sem impor deduplicação ao destinatário.

Política de definição prevalece sobre categoria e padrão; intervalos corridos/úteis usam feriados configurados. Um scheduler Beat, despachante a cada 30 s (100 IDs), scanner a cada 5 min com catch-up de 7 dias. Esses limites tornam a operação explícita; carga institucional e SMTP corporativo serão validados antes de produção. Monitor e logs mostram o estado conhecido, sem expor respostas SMTP brutas ou credenciais.
