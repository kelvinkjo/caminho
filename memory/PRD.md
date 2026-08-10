# CAMINHO — PRD

## Problema
App web (PT-BR) para comunidade católica jovem, carismática, missionária e vocacional. Une Formação + Oração + Comunidade + Missão + Vocação + Acompanhamento + Lives, transmitindo a sensação de uma **jornada de vida vocacional** — não apenas uma plataforma de cursos.

Prioridades absolutas do projeto: **1) segurança das etapas, 2) acompanhamento humano, 3) experiência da jornada.**

## Arquitetura
- Frontend: React 19 (CRA/craco), Tailwind, framer-motion, lucide-react, recharts, sonner. Mobile-first.
- Backend: FastAPI + MongoDB (motor). Todas as rotas sob `/api`.
- Auth: JWT (bcrypt), token Bearer em localStorage (`caminho_token`). Toda autorização validada no backend.
- Design: dark stone (#0C0A09) + laranja fogo (#EA580C); fontes Outfit / Plus Jakarta Sans / Cormorant Garamond.

## Personas / Papéis
- ADMINISTRADOR (acesso completo), FORMADOR (acompanha/aprova), MODERADOR (comunidade), MEMBRO (comum).

## Etapas (enum, ordem 1→6)
PRE_VOCACIONADO → VOCACIONADO → DISCIPULO_ANO_1 → DISCIPULO_ANO_2 → COMPROMISSADO → CONSAGRADO. Cada uma com tema, pergunta, ícone, descrição.

## Implementado (2026-06 — iteração 1) ✅
- **Autenticação**: registro, login, logout, /me, recuperar senha (stub), onboarding de 1º acesso (4 telas). Rotas protegidas por sessão e por papel.
- **Segurança das etapas (backend)**: usuário acessa apenas etapas com ordem ≤ sua etapa atual; etapas superiores retornam 403. Aulas e progresso também validados. `require_roles` protege endpoints de formador/admin. (Validado: 403/401 corretos.)
- **Jornada**: mapa vertical das 6 etapas com estados (bloqueada, atual, concluída, aguardando avaliação).
- **Formação**: Etapa → Módulo → Aula, player de aula, marcar aula como concluída, barra de progresso da etapa. Conteúdo católico de exemplo populado (etapas 1–3).
- **Progressão + aprovação**: só solicita avaliação com 100% das aulas; formador aprova (avança etapa) ou solicita acompanhamento. Nunca libera automaticamente.
- **Acompanhamento humano**: "Minhas Pessoas" + Radar Pastoral (verde/amarelo/vermelho por dias sem acessar).
- **Dashboard**: saudação, Palavra do dia, card da jornada, continue de onde parou, próxima live, missão da semana, agenda.
- **Missões da semana** (marcar concluída, sem pontuação/competição).
- **Admin**: stats + gráfico de membros por etapa, gestão de usuários (papel, etapa, formador, bloquear) com audit_logs.
- **Navegação inferior mobile**: Início, Jornada, Formação, Lives, Perfil.
- Testado: 17/17 backend + fluxos frontend (100%).

## Backlog priorizado
- P0: Lives (transmissão, chat, presença, obrigatórias), requisitos de etapa configuráveis pelo admin (atividades/avaliações/lives/presença), atividades e avaliações.
- P1: Passaporte da jornada (marcos/selos), Regra de Vida, Diário espiritual (privado/compartilhar com formador), Eventos + confirmar presença + QR Code, Pedidos de oração, Feed da comunidade com moderação, Notificações.
- P2: Liturgia "Hoje na Igreja", Biblioteca católica, Louvor, Modo Missão, Assistente de Formação com IA, Defesa da Fé, Certificados, Área Consagrados, Relatórios/exportação, privacidade/LGPD, login Google/Apple/telefone.

## Próximas tarefas sugeridas
- Área de Lives com presença e lives obrigatórias como requisito.
- Requisitos de etapa configuráveis no admin.
- Diário espiritual e Regra de Vida (uso diário).
