<p align="center">
  <img src="https://img.shields.io/badge/Next.js-14-black?logo=next.js" alt="Next.js 14" />
  <img src="https://img.shields.io/badge/FastAPI-0.115-009688?logo=fastapi" alt="FastAPI" />
  <img src="https://img.shields.io/badge/PostgreSQL-16-336791?logo=postgresql&logoColor=white" alt="PostgreSQL" />
  <img src="https://img.shields.io/badge/TypeScript-5.6-3178C6?logo=typescript&logoColor=white" alt="TypeScript" />
  <img src="https://img.shields.io/badge/Python-3.12-3776AB?logo=python&logoColor=white" alt="Python" />
  <img src="https://img.shields.io/badge/License-Apache_2.0-blue" alt="License" />
</p>

# aiRA Pulse — Context Gen Tool

All-in-one context management platform for the **aiRA AI system**. Extract structured context from Databricks, Confluence, and Config APIs, then refactor it into LLM-optimized documents using a proven 7-phase methodology.

---

## Features

- **Context Management** — Create, edit, organize, and version context documents with a dual-tab system (saved vs. AI-generated)
- **AI Chat** — Conversational interface with tool-calling, real-time streaming, and multi-round orchestration (Anthropic Claude / OpenAI)
- **Databricks Source** — Automated pipeline: notebook discovery, SQL extraction, frequency analysis, and document generation with live WebSocket progress
- **Confluence Source** — Browse spaces, select pages, and extract structured context from Confluence Cloud
- **Config APIs Source** — Fetch and transform API configurations into context documents
- **Smart Refactoring** — Restructure messy context into a clean 5-document architecture using a 790-line production blueprint
- **Admin Panel** — Role-based access control, user management, permission grants, and full audit logging
- **Auth** — Capillary Intouch SSO with local JWT sessions and granular RBAC

---

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Frontend | Next.js 14 (App Router), React 18, TypeScript, Tailwind CSS, shadcn/ui |
| State | Zustand, TanStack Query |
| Backend | FastAPI, Uvicorn, SQLAlchemy 2.0 (async), Alembic |
| Database | PostgreSQL 16 |
| Real-time | WebSocket (native FastAPI) |
| LLM | Anthropic Claude, OpenAI (server-side keys) |
| Auth | Capillary Intouch proxy, JWT (HS256), RBAC |
| DevOps | Docker, Turbo monorepo, GitHub Actions CI |
| Deployment | Vercel (frontend), Railway (backend + DB) |

---

## Project Structure

```
context_gen_tool/
├── apps/
│   ├── api/                          # FastAPI backend
│   │   ├── alembic/                  #   Database migrations
│   │   ├── app/
│   │   │   ├── core/                 #   Auth, RBAC, WebSocket manager
│   │   │   ├── models/               #   SQLAlchemy ORM models
│   │   │   ├── routers/              #   API route handlers
│   │   │   ├── schemas/              #   Pydantic request/response schemas
│   │   │   ├── services/
│   │   │   │   ├── databricks/       #   Databricks pipeline (12 modules)
│   │   │   │   ├── sources/          #   Source connectors (Confluence)
│   │   │   │   └── tools/            #   Chat tool implementations
│   │   │   ├── resources/            #   Blueprint & static assets
│   │   │   ├── main.py               #   FastAPI app entry point
│   │   │   ├── config.py             #   Settings & cluster mappings
│   │   │   └── database.py           #   Async engine & session
│   │   ├── seed_data.py              #   Roles, permissions, admin user seed
│   │   ├── Dockerfile
│   │   └── railway.json
│   │
│   └── web/                          # Next.js 14 frontend
│       └── src/
│           ├── app/                   #   Pages (App Router)
│           │   ├── login/             #     Login page
│           │   ├── org-picker/        #     Organization selection
│           │   └── dashboard/
│           │       ├── contexts/      #     Context management
│           │       ├── chat/          #     AI chat interface
│           │       ├── admin/         #     Admin panel
│           │       └── sources/       #     Databricks, Confluence, Config APIs
│           ├── components/            #   React components
│           ├── hooks/                 #   Custom hooks (WebSocket, etc.)
│           ├── stores/                #   Zustand state stores
│           └── types/                 #   TypeScript definitions
│
├── docker-compose.yml                # Development environment
├── docker-compose.prod.yml           # Production environment
├── turbo.json                        # Monorepo task config
└── package.json                      # Root workspace config
```

---

## Getting Started

### Prerequisites

- **Node.js** 20+ (via [nvm](https://github.com/nvm-sh/nvm))
- **Python** 3.12+
- **PostgreSQL** 16 (or use Docker)
- **npm** 10+

### Option A: Docker (Recommended)

Spin up the entire stack with one command:

```bash
docker compose up --build
```

This starts PostgreSQL, the API server (with auto-migrations), and the frontend:

| Service | URL |
|---------|-----|
| Frontend | http://localhost:3000 |
| API | http://localhost:8000 |
| API Docs | http://localhost:8000/docs |
| PostgreSQL | localhost:5432 |

### Option B: Manual Setup

#### 1. Clone & install

```bash
git clone https://github.com/akhil-kumar-capillary/context_gen_tool.git
cd context_gen_tool
npm install
```

#### 2. Set up the backend

```bash
cd apps/api

# Create virtual environment
python3 -m venv .venv
source .venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Configure environment
cp .env.example .env
# Edit .env with your values (see Environment Variables below)
```

#### 3. Set up the database

Make sure PostgreSQL is running, then:

```bash
# Run migrations
alembic upgrade head

# Seed roles, permissions, and admin user
python seed_data.py
```

#### 4. Set up the frontend

```bash
cd apps/web
cp .env.local.example .env.local
# Edit .env.local with your API URL
```

#### 5. Run in development

From the project root:

```bash
# Run both frontend and backend with hot reload
npm run dev

# Or run them separately:
npm run dev:web   # Frontend only (port 3000)
npm run dev:api   # Backend only (port 8000)
```

---

## Environment Variables

### Backend (`apps/api/.env`)

| Variable | Required | Description |
|----------|----------|-------------|
| `DATABASE_URL` | Yes | Async PostgreSQL URL (`postgresql+asyncpg://...`) |
| `DATABASE_URL_SYNC` | Yes | Sync PostgreSQL URL (`postgresql+psycopg://...`) |
| `SESSION_SECRET` | Yes | JWT signing key. Generate: `openssl rand -hex 32` |
| `PRIMARY_ADMIN_EMAIL` | Yes | Super-admin email (cannot be demoted) |
| `CORS_ORIGINS` | Yes | Allowed frontend origins as JSON array |
| `ANTHROPIC_API_KEY` | Yes* | Anthropic API key for Claude |
| `OPENAI_API_KEY` | No | OpenAI API key (optional fallback) |
| `DATABRICKS_<CLUSTER>_TOKEN` | No | Per-cluster Databricks PATs (APAC2, APAC, EU, US, TATA, USHC, SEA) |
| `CONFLUENCE_URL` | No | Confluence instance URL |
| `CONFLUENCE_EMAIL` | No | Confluence user email |
| `CONFLUENCE_API_TOKEN` | No | Confluence API token |
| `DEBUG` | No | Enable debug logging (`false` by default) |

> *At least one LLM key (Anthropic or OpenAI) is required for AI features.

### Frontend (`apps/web/.env.local`)

| Variable | Required | Description |
|----------|----------|-------------|
| `NEXT_PUBLIC_API_URL` | Yes | Backend API URL (e.g., `http://localhost:8000`) |
| `NEXT_PUBLIC_WS_URL` | Yes | Backend WebSocket URL (e.g., `ws://localhost:8000`) |

---

## API Endpoints

| Prefix | Description |
|--------|-------------|
| `GET /health` | Health check |
| `/api/auth` | Login, session management |
| `/api/contexts` | Context CRUD operations |
| `/api/sources/databricks` | Databricks pipeline & extraction |
| `/api/sources/confluence` | Confluence space browsing & extraction |
| `/api/sources/config-apis` | Config API fetching |
| `/api/llm` | LLM operations (refactoring, sanitization) |
| `/api/chat` | Chat endpoints + WebSocket streaming |
| `/api/admin` | User/role/permission management, audit logs |
| `/api/ws` | WebSocket for pipeline progress |

Full interactive docs available at [`/docs`](http://localhost:8000/docs) (Swagger UI).

---

## RBAC & Roles

Three pre-defined roles with 18 permissions across 5 modules:

| Role | Access |
|------|--------|
| **Admin** | Full access to all modules + user management |
| **Operator** | All source modules + context management (no secrets management) |
| **Viewer** | Read-only access across all modules |

Permissions follow a `module.operation` pattern (e.g., `databricks.extract`, `context_management.refactor`).

---

## Deployment

### Production with Railway + Vercel

**Backend (Railway):**

1. Create a Railway project with PostgreSQL
2. Add a service from your GitHub repo with root directory `apps/api`
3. Set environment variables (see table above)
4. Railway auto-detects `Dockerfile` and `railway.json`
5. Start command runs migrations, seeds data, and starts uvicorn

**Frontend (Vercel):**

1. Import your repo on Vercel with root directory `apps/web`
2. Set `NEXT_PUBLIC_API_URL` and `NEXT_PUBLIC_WS_URL` to your Railway URL
3. Deploy

**Or use Docker Compose for self-hosted:**

```bash
# Copy and configure production env
cp .env.example .env
# Edit .env with production values

docker compose -f docker-compose.prod.yml up -d
```

---

## Available Scripts

| Command | Description |
|---------|-------------|
| `npm run dev` | Start both frontend and backend with hot reload |
| `npm run build` | Build both applications |
| `npm run lint` | Lint both applications |
| `npm run dev:web` | Start frontend only |
| `npm run dev:api` | Start backend only |
| `npm run db:migrate` | Run pending database migrations |
| `npm run db:revision` | Generate a new migration from model changes |

---

## License

[Apache License 2.0](LICENSE)
