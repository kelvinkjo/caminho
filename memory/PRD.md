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

## Implementado (2026-06 — iteração 8) 🔴 Central de Transmissão ao Vivo (LiveKit WebRTC) — FASE 1
- **Integração LiveKit** (WebRTC SFU): captura via APIs oficiais do navegador (`getUserMedia`); tokens JWT curtos (15 min) gerados **só no backend**, papel (broadcaster/viewer) derivado no servidor. Segredos só em `backend/.env` (`LIVEKIT_URL/API_KEY/API_SECRET`). ⚠️ **Credenciais ainda não fornecidas** pelo usuário → `/api/livekit/status` = `configured:false` e `/broadcasts/{id}/token` responde **503 controlado**; app continua funcionando (câmera/preview/checklist/chat operam).
- **Permissões novas** (só Mestre concede): MANAGE_LIVE, MANAGE_CAMERA, MANAGE_MICROPHONE, MANAGE_SCENES, MANAGE_SOURCES, VIEW_LIVE_ANALYTICS, TAKE_OVER_LIVE (+ CREATE/EDIT/START/END/MODERATE_LIVE já existentes).
- **Endpoints** (`db.broadcasts`): CRUD `/api/broadcasts`, `/start` (muda status→live **+ aviso automático** aos membros da etapa), `/end` (duration_min), `/takeover` (só TAKE_OVER_LIVE/Mestre → "Transmissão assumida"), `/token` (LiveKit), `/heartbeat` + `/stats` (espectadores/pico), chat `/chat` (GET/POST/DELETE/highlight) + `/moderate` (mute/block/toggle_chat, exige MODERATE_LIVE), `/report` (VIEW_LIVE_ANALYTICS), `/livekit/status`.
- **Acesso por ETAPA OFICIAL** (`broadcast_accessible`, nunca por progresso). Invariante verificado: nenhum endpoint de transmissão altera `current_stage_order`.
- **UI**: `/app/transmissoes` (Central — criar/listar), `/app/estudio/:id` (estúdio broadcaster: permissão câmera/mic, seleção de dispositivos, medidor de áudio + clipping, preview, checklist, modo Simples/Profissional, iniciar/encerrar com confirmação, takeover, stats ao vivo, chat+moderação), `/app/ao-vivo/:id` (espectador: player + chat + contagem + fullscreen). Link no Perfil. `data-testid` em todos os elementos.
- **Faseamento**: Fase 2 (cenas/fontes/layouts/lower-third/banner/temas/screen-share/presets/agenda) e Fase 3 (multiapresentador/convidados/sala de espera) — PENDENTES.
- Testado: 14/14 novos testes backend + 16/16 checkpoints UI (100%). LiveKit intencionalmente não configurado nesta fase (token=503 correto). Streaming de vídeo real depende das credenciais do LiveKit.

## Implementado (2026-06 — iteração 7) ✅ Central de Mídia Externa (embed oficial)
- **Modo embed-only** (opção escolhida pelo usuário): armazena **apenas** URL/provider/external_id/metadados. NUNCA baixa, copia ou faz scraping de vídeo.
- **Adaptadores** (`MediaProvider` base + `YouTubeProvider` + `VimeoProvider`) — arquitetura pronta para novos provedores/APIs oficiais no futuro. Detecção/normalização de URL: YouTube `watch?v=`, `youtu.be/`, `live/`, `embed/`, `shorts/`; Vimeo `vimeo.com/ID` e `player.vimeo.com/video/ID`.
- **Endpoints**: `POST /api/media/parse` (valida/normaliza; 400 para URL inválida e provedor não suportado; requer `MANAGE_EXTERNAL_MEDIA`), `POST/GET/PATCH/DELETE /api/external-media`, `GET /api/external-media/{id}` (bloqueio por etapa oficial no backend + registro de histórico "acessado"), `/favorite` (toggle), `/favorites`, `/history`, `/{id}/live-status`, `GET /api/media/providers`, `PUT /api/master/media/providers` (config do Mestre).
- **Acesso por ETAPA OFICIAL** (`media_accessible`, nunca por progresso). Status de live externa: draft/scheduled/waiting/live/ended/unavailable; ao virar `live` notifica membros. Player oficial via iframe + fallback "Abrir na plataforma". Auditoria nas ações.
- **UI**: `/app/midia` (Central de Mídia — tabs Todos/Vídeos/Lives/Favoritos/Histórico + busca), `/app/midia/:id` (assistir com iframe/fallback/favorito), `/app/midia/gerenciar` (formador/mestre: cadastro, etapas, status de live; Mestre configura provedores). Link no Perfil.
- **Permissão**: nova `MANAGE_EXTERNAL_MEDIA` (só Mestre concede). Formador demo recebeu a permissão.
- **Melhorias**: `/api/notifications` agora aceita `since`/`limit`; des-favoritar permitido mesmo sem acesso atual.
- Testado: 11/11 novos testes backend + 16/16 checkpoints UI (100%). Invariante "etapa ≠ progresso" preservado.

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

## Implementado (2026-06 — iteração 6) ✅
- **Permissões granulares** (26 tipos: cursos/módulos/aulas/mídias/avisos/lives/analytics) concedidas **apenas pelo Login Mestre** (`/api/master/formadores-permissions`, PUT permissions). Helpers `has_perm/require_perm/can_edit`; `mestre` sempre autorizado. Formador nunca altera etapa (mantido).
- **Autoria de conteúdo**: `/api/courses`, `/api/modules`, `/api/lessons` (+PATCH com verificação de propriedade / EDIT_ALL_CONTENT), `/api/announcements` (criar/listar/excluir) — tudo com `owner_id` e auditoria (`audit_logs`).
- **Lives (ciclo de vida)**: `/api/lives` criar, PATCH editar, `/start` (START_LIVE), `/end` (END_LIVE); estados scheduled→live→ended; acesso por etapas (lista) validado no backend; notifica membros autorizados ao iniciar. Streaming real fica preparado (status + stream_url).
- **UI**: Central do Formador (avisos + lives + iniciar/encerrar, menu dinâmico por permissão), Permissões (Mestre), Comunicados no dashboard do membro.
- **Salvaguarda**: seed garante que o Login Mestre nunca fique bloqueado após reinício.
- Testado: TESTES 1–10 + gestão de permissões/avisos — 64/64 backend + 15/15 UI (100%).


## Implementado (2026-06 — iteração 5) ✅
- **Requisitos configuráveis por etapa** (Mestre): `/api/master/stage-requirements` (GET/PUT) — define se "formação concluída" exige 100% das aulas e/ou lives obrigatórias. `formation_status` respeita a config. Tela em Controle Mestre → Requisitos por Etapa (toggles).
- **Passaporte da Jornada**: `/api/passport` com 8 marcos e selos; auto-conquista (primeiro encontro no onboarding, primeira formação ao concluir aula, primeira missão, primeiro acompanhamento ao vincular formador, compromisso/consagração por etapa). Master pode conceder marco. Tela com grade de selos.
- **Relatório Pastoral** (Mestre): `/api/master/pastoral-report` — panorama de conclusão por etapa + lista de quem aguarda decisão, com formador. Tela dedicada.
- **Central de Notificações**: `/api/notifications` (histórico completo) + marcar lidas. Tela dedicada + sino no header do dashboard.


## Implementado (2026-06 — iteração 3) ✅
- **Lives (Fase 3)**: `/api/lives` (buckets ao vivo/próximas/gravadas com acesso por etapa validado no backend), `/api/lives/{id}/presence` (presença mínima 75%, confirmada/parcial). **Lives obrigatórias como requisito de etapa**: `request-approval` bloqueia (400) até a presença nas lives obrigatórias ser confirmada. Página Lives com abas e confirmação de presença.
- **Recomendações da IA** (`/api/recommendations`): próxima aula + missão pendente (regra) + dica curta gerada por IA (texto simples). Card "Para você hoje" no dashboard + ícone de busca no header.
- **Defesa da Fé / Apologética** (`/api/apologetics`): trilha com pergunta, resposta curta, explicação, Bíblia, Tradição, Catecismo, Magistério, material complementar. 6 entradas seed, filtro por categoria. Página no Perfil.
- **Busca Inteligente** (`/api/search`): busca por tema nas aulas (com escopo por etapa) + apologética + resposta doutrinal gerada por IA. Página no Perfil e no header.
- Testado: 42/42 backend + fluxos frontend (100%).


## Próximas tarefas sugeridas