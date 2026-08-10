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

## Implementado (2026-06 — iteração 2) ✅
- **FASE 8 — Assistente de Formação com IA** (`/api/assistant/ask`, Claude Sonnet 4.6 via Emergent LLM key): responde sobre Bíblia, Catecismo, doutrina, santos, liturgia, apologética; cita fontes (CIC, passagens), diferencia doutrina de opinião, não inventa e encaminha a sacerdote/formador em questões pastorais. Histórico persistido em `assistant_messages`. Página de chat no Perfil.
- **Dados de teste (item 59)**: 8 usuários — um por etapa (1–6) + formador + admin, todos senha ***REMOVED***.
- **Segurança reforçada**: acesso a etapa/aula bloqueada retorna 403 no backend mesmo via URL direta; frontend redireciona para a Jornada com aviso. Rota /app/admin restrita a admin (formador não acessa nem via URL). Usuário não altera o próprio nível (apenas admin via PATCH) e só acessa os próprios dados.

## Implementado (2026-06 — iteração 3) ✅
- **Lives (Fase 3)**: `/api/lives` (buckets ao vivo/próximas/gravadas com acesso por etapa validado no backend), `/api/lives/{id}/presence` (presença mínima 75%, confirmada/parcial). **Lives obrigatórias como requisito de etapa**: `request-approval` bloqueia (400) até a presença nas lives obrigatórias ser confirmada. Página Lives com abas e confirmação de presença.
- **Recomendações da IA** (`/api/recommendations`): próxima aula + missão pendente (regra) + dica curta gerada por IA (texto simples). Card "Para você hoje" no dashboard + ícone de busca no header.
- **Defesa da Fé / Apologética** (`/api/apologetics`): trilha com pergunta, resposta curta, explicação, Bíblia, Tradição, Catecismo, Magistério, material complementar. 6 entradas seed, filtro por categoria. Página no Perfil.
- **Busca Inteligente** (`/api/search`): busca por tema nas aulas (com escopo por etapa) + apologética + resposta doutrinal gerada por IA. Página no Perfil e no header.
- Testado: 42/42 backend + fluxos frontend (100%).


## Próximas tarefas sugeridas
