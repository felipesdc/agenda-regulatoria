# ADR 0005 — Calendário por período e contagens anuais
Aceita. Evitar carregar todas as ocorrências na SPA. Endpoint agregado por due_date/status, com limite de 366 dias em summary e 62 dias detalhados. Amostrar três registros/dia via window function, deduplicando antes da janela. Paginar os demais no endpoint de ocorrências. Segurança usa o mesmo escopo anterior a agregações, sem autorização só na interface.

Usar due_date como evento de dia inteiro enquanto o domínio não define horários. Ano preserva foco e usa somente contagens; minicalendário navega ao mês. Dialog nativo reutiliza detalhe/workflow existente. JSON de favoritos armazena preferências de filtro validadas, com owner relacional e unicidade de nome por usuário.
