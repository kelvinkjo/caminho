# Caminho

Plataforma de formação católica para acompanhar jornadas, etapas formativas, aulas, missões, mídia, transmissões ao vivo e a atuação de formadores. O projeto prioriza uma experiência em português do Brasil, mobile-first e regras claras de acesso por função e etapa.

## Visão geral

O Caminho reúne duas aplicações:

| Camada | Tecnologia | Responsabilidade |
| --- | --- | --- |
| Frontend | React 19, Create React App, CRACO, Tailwind CSS e Radix UI | Interface, navegação, autenticação no cliente e fluxos da jornada |
| Backend | Python, FastAPI e MongoDB (Motor) | API, autenticação, regras de permissão, progresso e dados da plataforma |

Funcionalidades principais incluem:

- cadastro, login, onboarding e perfil;
- jornada e formação por etapas, módulos e aulas;
- controle de acesso por função e etapa;
- missões, notificações e acompanhamento;
- biblioteca de mídia e transmissões ao vivo;
- telas de gestão para formadores, administradores e autoridades institucionais.

## Regras de segurança e produto

As regras a seguir são parte essencial do projeto:

- o backend é a fonte de verdade para autorização; a interface não deve conceder acesso sozinha;
- participantes não podem avançar para etapas não liberadas;
- mudanças de função, permissões e etapas devem respeitar as regras de autoridade;
- tokens, senhas, arquivos `.env` e credenciais nunca devem ser enviados ao Git;
- testes de integração podem alterar dados de usuários e progresso: execute-os apenas em um ambiente de testes.

## Pré-requisitos

- Git;
- Node.js LTS (recomendado: versão 20 ou superior) e Yarn 1.22;
- Python 3.10 ou superior;
- uma instância acessível de MongoDB;
- Visual Studio Code (recomendado).

> O frontend usa Yarn. Não misture `npm install` e Yarn no mesmo projeto. O arquivo `package-lock.json` não deve ser criado ou versionado enquanto o `yarn.lock` for o lockfile oficial.

## Configuração inicial

### 1. Obter o projeto

```powershell
git clone https://github.com/kelvinkjo/caminho.git
cd caminho
```

Se a pasta já existe, não clone novamente. Entre nela e verifique o estado:

```powershell
git status
git remote -v
```

### 2. Configurar o backend

No PowerShell, na raiz do projeto:

```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements-minimal.txt
```

Crie o arquivo `backend/.env` a partir deste modelo (use valores locais e secretos):

```dotenv
MONGO_URL=mongodb://localhost:27017
DB_NAME=caminho
JWT_SECRET=gere-uma-chave-longa-e-privada
CORS_ORIGINS=http://localhost:3000
```

Variáveis utilizadas pelo backend:

| Variável | Obrigatória | Descrição |
| --- | --- | --- |
| `MONGO_URL` | Sim | URL de conexão do MongoDB |
| `DB_NAME` | Sim | Nome do banco de dados |
| `JWT_SECRET` | Sim | Chave privada para tokens de sessão |
| `CORS_ORIGINS` | Recomendado | Origens separadas por vírgula autorizadas a chamar a API |

Inicie a API:

```powershell
uvicorn server:app --reload --host 0.0.0.0 --port 8000
```

### 3. Configurar o frontend

Abra outro terminal e execute:

```powershell
cd frontend
yarn install
```

Crie `frontend/.env`:

```dotenv
REACT_APP_BACKEND_URL=http://localhost:8000
```

Inicie a aplicação web:

```powershell
yarn start
```

Por padrão, ela fica disponível em `http://localhost:3000`.

## Comandos do dia a dia

### Frontend

Execute dentro de `frontend/`:

```powershell
yarn start
yarn build
yarn test
```

| Comando | Resultado |
| --- | --- |
| `yarn start` | Inicia o servidor local do React/CRACO |
| `yarn build` | Gera a versão otimizada em `frontend/build/` |
| `yarn test` | Inicia os testes do frontend |

### Backend e testes de integração

Com o ambiente virtual ativo, execute dentro de `backend/`:

```powershell
python -m pytest tests
```

Os testes usam `pytest-xdist` e fazem chamadas HTTP para a API configurada. Use um banco de testes e dados de teste próprios; não rode esse conjunto contra produção.

## Estrutura do repositório

```text
caminho/
├── backend/
│   ├── server.py                 # API FastAPI, regras de domínio e acesso
│   ├── requirements*.txt         # Dependências Python
│   ├── tests/                    # Testes de integração e RBAC
│   └── .env                      # Segredos locais (não versionado)
├── frontend/
│   ├── src/
│   │   ├── components/           # Componentes reutilizáveis
│   │   ├── context/              # Contextos de estado e autenticação
│   │   ├── lib/api.js            # Cliente HTTP e URL da API
│   │   └── pages/                # Páginas e fluxos do produto
│   ├── public/                   # Arquivos públicos
│   ├── package.json              # Scripts e dependências JavaScript
│   ├── yarn.lock                 # Lockfile oficial do frontend
│   └── .env                      # Configuração local (não versionada)
├── .github/agents/               # Contexto especializado para agentes de código
├── .gitignore                    # Arquivos locais e secretos ignorados
└── README.md
```

## Trabalhando com Git e GitHub

Antes de começar uma mudança:

```powershell
git status
git switch main
git pull --ff-only
git switch -c tipo/descricao-curta
```

Use nomes de ramificação claros, por exemplo:

- `feat/central-de-midia`
- `fix/permissao-de-etapa`
- `docs/atualiza-readme`

Antes de commitar:

```powershell
git diff --check
git status
git add <arquivos-revisados>
git diff --cached --stat
git commit -m "tipo: descrição curta"
```

Evite comandos destrutivos, como `git reset --hard`, `git clean -fd` e `git checkout --`, quando houver alterações não verificadas. Nunca envie `.env`, credenciais, logs ou `node_modules`.

## VS Code

Abra a raiz do projeto, não apenas `frontend/` ou `backend/`:

```powershell
code C:\Projetos\caminho
```

Extensões úteis:

- Python;
- ESLint;
- Tailwind CSS IntelliSense;
- GitLens (opcional).

Use o painel **Source Control** para revisar arquivos individualmente antes de preparar um commit. O terminal integrado pode executar os mesmos comandos do PowerShell.

## Codex no projeto

Ao trabalhar com o Codex, abra a pasta raiz `C:\Projetos\caminho` como projeto. A pasta `.github/agents/` descreve o contexto do Caminho, incluindo suas regras de segurança, permissões, etapas e integração entre frontend e backend.

Um bom pedido ao Codex informa:

1. o fluxo ou problema exato;
2. as telas, rotas ou arquivos envolvidos;
3. a regra de acesso ou de formação que não pode ser quebrada;
4. como validar o resultado.

Exemplo:

> Corrija o acesso à página de mídia para formadores, preservando a autorização no backend. Revise o contrato da API, faça a menor alteração necessária e rode a verificação relevante.

## Solução de problemas

| Sintoma | Verificação inicial |
| --- | --- |
| A página não conecta à API | Confira `REACT_APP_BACKEND_URL`, a API na porta 8000 e `CORS_ORIGINS` |
| Porta 3000 ocupada | Encerre o processo anterior ou aceite outra porta indicada pelo CRACO |
| Erro de conexão com MongoDB | Revise `MONGO_URL`, `DB_NAME` e a disponibilidade do MongoDB |
| Dependência Python não instala | Use `requirements-minimal.txt` no ambiente local e investigue a dependência específica |
| Mudanças inesperadas no lockfile | Use somente Yarn e revise `yarn.lock` antes do commit |
| Git não identifica o autor | Configure `user.name` e `user.email` no repositório ou globalmente |

## Licença

Não há uma licença declarada neste repositório. Antes de distribuição, reutilização ou contribuição externa, defina uma licença e a política de contribuição aplicável.
