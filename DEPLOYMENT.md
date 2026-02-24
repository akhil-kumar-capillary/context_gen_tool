# Deployment Guide — aiRA Context Gen Tool

> A step-by-step guide for deploying the full application. No prior experience required.

---

## What Are We Deploying?

This application has 3 parts that need to be deployed separately:

| Part | What It Does | Where We Deploy It |
|------|-------------|-------------------|
| **Database** (PostgreSQL) | Stores all app data — users, contexts, chat history | Railway |
| **Backend API** (Python/FastAPI) | Handles business logic, AI features, authentication | Railway |
| **Frontend Website** (Next.js/React) | The user interface people interact with in their browser | Vercel |

**Railway** (railway.app) and **Vercel** (vercel.com) are cloud platforms — they run your code on the internet so anyone can access it. Both have free tiers.

---

## Pre-requisites (Things You Need Before Starting)

Gather these before you begin:

1. **A GitHub account** — the code is already on GitHub at:
   `https://github.com/akhil-kumar-capillary/context_gen_tool`

2. **An Anthropic API key** — powers the AI chat (Claude)
   - Go to https://console.anthropic.com
   - Sign up or log in
   - Go to **"API Keys"** in the left sidebar
   - Click **"Create Key"**
   - Copy the key — it starts with `sk-ant-...`
   - **Save it somewhere safe** — you can't see it again after closing the page

3. **Databricks access tokens** _(optional)_ — only if you want the Databricks source feature

4. **Confluence credentials** _(optional)_ — only if you want the Confluence source feature

---

## STAGE 1: Set Up Railway (Database + Backend)

### Step 1.1 — Create a Railway Account

1. Open your browser and go to **https://railway.app**
2. Click **"Login"** in the top-right corner
3. Choose **"Login with GitHub"**
4. GitHub will ask you to authorize Railway — click **"Authorize Railway"**
5. You're now on the Railway dashboard — it shows your projects (empty for now)

### Step 1.2 — Create a New Project

1. Click the **"+ New Project"** button (top-right of the dashboard)
2. Select **"Empty Project"** from the dropdown menu
3. You'll see a blank canvas — think of this as a workspace where your services will live side by side

### Step 1.3 — Add a PostgreSQL Database

The database stores all your application data.

1. On the project canvas, click **"+ New"** (top-right)
2. Select **"Database"**
3. Select **"Add PostgreSQL"**
4. Railway creates a PostgreSQL database in about 10 seconds
5. A new **PostgreSQL card** appears on the canvas

**Now get the database connection URL:**

6. Click on the **PostgreSQL card** to open its details panel
7. Go to the **"Variables"** tab (you might also find it under "Data" → "Connect")
8. Look for the variable called **`DATABASE_URL`** — it looks like this:
   ```
   postgresql://postgres:AbCdEfGhIjKlMnOp@roundhouse.proxy.rlwy.net:12345/railway
   ```
9. **Copy this entire URL** and paste it into a text file on your computer — you'll need it in the next step

### Step 1.4 — Prepare Your Environment Variables

The backend needs two slightly different versions of the database URL. Here's how to create them:

**Original URL from Railway:**
```
postgresql://postgres:AbCdEfGhIjKlMnOp@roundhouse.proxy.rlwy.net:12345/railway
```

**Version 1 — for the running app (async driver):**
Take the original and replace `postgresql://` at the beginning with `postgresql+asyncpg://`:
```
postgresql+asyncpg://postgres:AbCdEfGhIjKlMnOp@roundhouse.proxy.rlwy.net:12345/railway
```
Save this as your `DATABASE_URL`.

**Version 2 — for database setup/migrations (sync driver):**
Take the original and replace `postgresql://` at the beginning with `postgresql+psycopg://`:
```
postgresql+psycopg://postgres:AbCdEfGhIjKlMnOp@roundhouse.proxy.rlwy.net:12345/railway
```
Save this as your `DATABASE_URL_SYNC`.

> **Tip:** Everything after the `://` stays exactly the same. You're only changing the prefix.

**Generate a secret key:**

This is a random password the app uses internally to sign login sessions.

- **On Mac:** Open Terminal (search "Terminal" in Spotlight) and run:
  ```
  openssl rand -hex 32
  ```
- **On Windows:** Open PowerShell and run:
  ```
  -join ((1..32) | ForEach-Object { '{0:x2}' -f (Get-Random -Maximum 256) })
  ```
- You'll get a random string like: `e9a4d84018d67c27d0c4f3bdf0db48ac441d3a74940415d9e22f9a82084c7415`
- **Copy this** and save it — this is your `SESSION_SECRET`

### Step 1.5 — Deploy the Backend API

1. Go back to your Railway project canvas
2. Click **"+ New"** (top-right) again
3. This time select **"GitHub Repo"**
4. If prompted, authorize Railway to access your GitHub repositories — click **"Authorize"**
5. You'll see a list of your GitHub repos — find and select **`context_gen_tool`**
6. Railway creates a new service card on the canvas

**Now configure it:**

7. Click on the new service card to open its details
8. Go to the **"Settings"** tab
9. Find **"Root Directory"** — click the edit/pencil icon next to it
10. Type: **`apps/api`** and press Enter
    > This tells Railway: "The backend code is inside the `apps/api` folder, not at the root."
11. Find **"Builder"** — it should already say **"Dockerfile"** (Railway auto-detects this from the code). If it doesn't, select "Dockerfile".
12. Check the **"Start Command"** — it should auto-populate from the `railway.json` file in the code. If it's empty, paste this:
    ```
    alembic upgrade head && python seed_data.py && uvicorn app.main:app --host 0.0.0.0 --port $PORT --workers 2
    ```

> **What does that command do?**
> - `alembic upgrade head` — Creates all the database tables (users, contexts, chats, etc.)
> - `python seed_data.py` — Creates the default admin roles, permissions, and your admin user account
> - `uvicorn app.main:app ...` — Starts the API server so it can accept requests

### Step 1.6 — Set Environment Variables on Railway

Environment variables are configuration values the app reads at startup. Think of them as settings.

1. Still in the API service, go to the **"Variables"** tab
2. For each row in the table below, click **"+ New Variable"**, type the **Name** on the left and the **Value** on the right, then press Enter:

| Name | Value | Notes |
|------|-------|-------|
| `DATABASE_URL` | Your **async** URL from Step 1.4 | Starts with `postgresql+asyncpg://` |
| `DATABASE_URL_SYNC` | Your **sync** URL from Step 1.4 | Starts with `postgresql+psycopg://` |
| `SESSION_SECRET` | The random string from Step 1.4 | The long hex string you generated |
| `PRIMARY_ADMIN_EMAIL` | `akhil.kumar@capillarytech.com` | This person gets full admin access |
| `CORS_ORIGINS` | `["http://localhost:3000"]` | Temporary — we'll update this in Stage 3 |
| `ANTHROPIC_API_KEY` | Your Anthropic key | Starts with `sk-ant-...` |
| `OPENAI_API_KEY` | Your OpenAI key _(or leave empty)_ | Optional, starts with `sk-...` |
| `DEBUG` | `false` | Keep this off in production |

**Optional — Add these only if you're using Databricks:**

| Name | Value |
|------|-------|
| `DATABRICKS_APAC2_TOKEN` | Databricks access token for the APAC2 cluster |
| `DATABRICKS_APAC_TOKEN` | Databricks access token for the APAC cluster |
| `DATABRICKS_EU_TOKEN` | Databricks access token for the EU cluster |
| `DATABRICKS_US_TOKEN` | Databricks access token for the US cluster |
| `DATABRICKS_TATA_TOKEN` | Databricks access token for the TATA cluster |
| `DATABRICKS_USHC_TOKEN` | Databricks access token for the USHC cluster |
| `DATABRICKS_SEA_TOKEN` | Databricks access token for the SEA cluster |

> **How to get a Databricks token:** Log into the Databricks workspace → Click your profile icon (top-right) → User Settings → Developer → Access tokens → Generate new token

**Optional — Add these only if you're using Confluence:**

| Name | Value |
|------|-------|
| `CONFLUENCE_URL` | e.g. `https://capillary.atlassian.net` |
| `CONFLUENCE_EMAIL` | Your Confluence login email |
| `CONFLUENCE_API_TOKEN` | Your Confluence API token |

### Step 1.7 — Generate a Public URL for the Backend

Your API needs a public URL so the frontend (and you) can reach it.

1. In the API service, go to the **"Networking"** tab
   > If you don't see "Networking", try **"Settings"** → scroll down to **"Networking"**
2. Click **"Generate Domain"**
3. Railway creates a URL like:
   ```
   context-gen-tool-api-production-xxxx.up.railway.app
   ```
4. **Copy this URL** — you'll need it for the frontend setup in Stage 2

**Test it right now:**

5. Open a new browser tab and go to:
   ```
   https://context-gen-tool-api-production-xxxx.up.railway.app/health
   ```
   _(replace with your actual URL)_

6. If everything is working, you'll see this in the browser:
   ```json
   {"status":"ok","service":"aira-context-gen"}
   ```

   If you see this — congratulations! Your backend is live.

### Step 1.8 — Watch the Deployment Logs (If Something Goes Wrong)

1. In the API service, go to the **"Deployments"** tab
2. Click on the latest deployment to see its log output
3. **A successful deployment** shows something like:
   ```
   INFO  [alembic.runtime.migration] Running upgrade  -> 5c6c874465c9, initial schema all models
   Seeding permissions... 18 permissions created
   Seeding roles... 3 roles created
   Creating primary admin user... done
   INFO:     Uvicorn running on http://0.0.0.0:PORT
   ```
4. **If you see errors**, the most common causes are:
   - **Wrong `DATABASE_URL`** — double-check you replaced the prefix correctly
   - **Missing variable** — make sure all required variables are set
   - **Wrong root directory** — must be `apps/api` (not `apps/api/` with trailing slash)

---

## STAGE 2: Set Up Vercel (Frontend Website)

### Step 2.1 — Create a Vercel Account

1. Open your browser and go to **https://vercel.com**
2. Click **"Sign Up"** in the top-right corner
3. Choose **"Continue with GitHub"**
4. Authorize Vercel to access your GitHub account
5. You're now on the Vercel dashboard

### Step 2.2 — Import the Project

1. Click **"Add New..."** (top of dashboard) → **"Project"**
2. You'll see a list of your GitHub repos
3. Find **`context_gen_tool`** and click **"Import"**
4. Vercel shows a configuration screen. Set these values:

| Setting | What To Do |
|---------|-----------|
| **Framework Preset** | Should auto-detect as "Next.js" — if not, select it from the dropdown |
| **Root Directory** | Click the **"Edit"** button → type `apps/web` → click outside or press Enter |
| **Build Command** | Leave as `npm run build` (the default) |
| **Install Command** | Leave as `npm install` (the default) |

> **Why set Root Directory?** The code has both frontend and backend. Setting `apps/web` tells Vercel to only look at the frontend folder.

### Step 2.3 — Set Environment Variables on Vercel

**Before clicking Deploy**, scroll down and expand the **"Environment Variables"** section.

Add these two variables (click "Add" after each one):

| Name | Value |
|------|-------|
| `NEXT_PUBLIC_API_URL` | `https://context-gen-tool-api-production-xxxx.up.railway.app` |
| `NEXT_PUBLIC_WS_URL` | `wss://context-gen-tool-api-production-xxxx.up.railway.app` |

> **Replace** `context-gen-tool-api-production-xxxx.up.railway.app` with your **actual Railway URL** from Step 1.7.

**Important — notice the different prefixes:**
- `NEXT_PUBLIC_API_URL` starts with **`https://`** — this is for regular web requests
- `NEXT_PUBLIC_WS_URL` starts with **`wss://`** — this is for WebSocket (real-time chat streaming). The "wss" means "WebSocket Secure"
- Both use the **same domain**, just different protocols

### Step 2.4 — Deploy

1. Click the **"Deploy"** button
2. Vercel starts building your frontend — you'll see a log with messages like:
   - "Cloning repository..."
   - "Installing dependencies..."
   - "Building Next.js application..."
3. This takes about **2-3 minutes**
4. When it finishes, you'll see a **"Congratulations!"** screen with a screenshot preview of your site
5. Your app is now live! The URL looks like:
   ```
   https://context-gen-tool-xxxx.vercel.app
   ```
6. **Copy this URL** — you need it for the final connection step

---

## STAGE 3: Connect Frontend to Backend (Update CORS)

Right now the backend doesn't recognize the frontend's URL, so it blocks all requests from it. This is a security feature called **CORS** (Cross-Origin Resource Sharing). We need to tell the backend: "trust requests from this frontend URL."

### Step 3.1 — Update CORS on Railway

1. Go back to **https://railway.app** → open your project → click on the **API service**
2. Go to the **"Variables"** tab
3. Find the variable called **`CORS_ORIGINS`**
4. Click on its value to edit it
5. Replace the old value with your Vercel URL:
   ```
   ["https://context-gen-tool-xxxx.vercel.app"]
   ```
   > Replace with your **actual** Vercel URL. Make sure to:
   > - Keep the square brackets `[` and `]`
   > - Keep the double quotes around the URL
   > - Use `https://` (not `http://`)
   > - **No trailing slash** at the end
6. Press Enter or click away to save
7. Railway will **automatically redeploy** with the new setting — this takes about 1-2 minutes

---

## STAGE 4: Verify Everything Works

### Step 4.1 — Check the Backend Health

Open your browser and go to:
```
https://YOUR-RAILWAY-URL.up.railway.app/health
```

You should see:
```json
{"status":"ok","service":"aira-context-gen"}
```

**If yes** — the backend is alive and connected to the database.

### Step 4.2 — Open the Frontend

Open your browser and go to:
```
https://YOUR-VERCEL-URL.vercel.app
```

You should see the **login page** of the application.

**If you see a blank page or errors**, open the browser console (press F12 → Console tab) and look for:
- **CORS errors** → Go back to Stage 3 and verify the `CORS_ORIGINS` value
- **Network errors** → Check that `NEXT_PUBLIC_API_URL` on Vercel is correct

### Step 4.3 — Test the Login Flow

1. On the login page, enter your **Capillary Intouch credentials** (email and password)
2. After login, you should see the **organization picker** — a list of your Capillary orgs
3. Select an organization
4. You land on the **main dashboard**

### Step 4.4 — Test Key Features

Go through each feature to make sure everything works:

| Feature | How to Test | What You Should See |
|---------|-------------|-------------------|
| **Contexts** | Click the "Contexts" tab in the sidebar | An empty context list (or your existing contexts) |
| **Chat** | Click the "Chat" tab → type "Hello" → press Enter | The AI responds with streaming text appearing word by word |
| **Admin Panel** | Click the "Admin" tab (visible only to the primary admin) | Four tabs: Users, Roles, Permissions, Audit Logs |
| **Databricks** | Click Sources → Databricks _(only if tokens were configured)_ | A list of available Databricks clusters |
| **Confluence** | Click Sources → Confluence _(only if credentials were configured)_ | Confluence space browser |

---

## STAGE 5: Custom Domain (Optional)

If you want your app on a nice URL like `aira.capillarytech.com` instead of the auto-generated one:

### For the Frontend (Vercel)

1. Go to **Vercel** → your project → **"Settings"** → **"Domains"**
2. Type your domain (e.g., `aira-context.capillarytech.com`) and click **"Add"**
3. Vercel shows a DNS record you need to add — usually:
   - **Type:** CNAME
   - **Name:** `aira-context` (or whatever subdomain)
   - **Value:** `cname.vercel-dns.com`
4. Go to your DNS provider (e.g., Cloudflare, AWS Route 53, GoDaddy) and add that record
5. Wait 5-60 minutes for DNS to propagate
6. Vercel will show a green checkmark when the domain is verified

### For the Backend (Railway)

1. Go to **Railway** → your API service → **"Settings"** → scroll to **"Custom Domain"**
2. Type your domain (e.g., `aira-api.capillarytech.com`) and click **"Add"**
3. Railway shows a CNAME record to add
4. Add it at your DNS provider and wait for propagation

### After Adding Custom Domains — Update 3 Values

| Where | Variable | New Value |
|-------|----------|-----------|
| **Railway** (API Variables) | `CORS_ORIGINS` | `["https://aira-context.capillarytech.com"]` |
| **Vercel** (Environment Variables) | `NEXT_PUBLIC_API_URL` | `https://aira-api.capillarytech.com` |
| **Vercel** (Environment Variables) | `NEXT_PUBLIC_WS_URL` | `wss://aira-api.capillarytech.com` |

> After changing Vercel env vars, you need to **redeploy**: Go to Deployments tab → click the three dots on the latest deployment → "Redeploy".
> Railway redeploys automatically when you change variables.

---

## Troubleshooting

| Problem | Most Likely Cause | How to Fix |
|---------|------------------|-----------|
| Health check (`/health`) doesn't work | Database URL is wrong | Check `DATABASE_URL` and `DATABASE_URL_SYNC` — make sure you changed the prefix correctly (`+asyncpg` and `+psycopg`) |
| Frontend is blank / shows error | Backend URL not set | Check `NEXT_PUBLIC_API_URL` in Vercel env vars — must start with `https://` |
| Browser console shows "CORS error" | Backend doesn't trust the frontend URL | Update `CORS_ORIGINS` in Railway to match your exact Vercel URL (no trailing slash) |
| Chat doesn't work / no streaming | WebSocket URL wrong | Check `NEXT_PUBLIC_WS_URL` in Vercel — must start with `wss://` not `ws://` |
| Login button does nothing | Backend can't be reached | First check if `/health` works. If it does, it's likely a CORS issue |
| "No Databricks clusters" | Tokens not configured | Add `DATABRICKS_<CLUSTER>_TOKEN` variables in Railway |
| Railway build fails | Wrong root directory | Must be `apps/api` — check Settings tab |
| Vercel build fails | Wrong root directory | Must be `apps/web` — check Settings → General |
| Login works but dashboard is empty | Normal for first use | Contexts will appear once you create them via Chat or manual creation |

---

## Quick Reference Card

| What | Where | URL |
|------|-------|-----|
| Railway Dashboard | Manage backend + database | https://railway.app/dashboard |
| Vercel Dashboard | Manage frontend | https://vercel.com/dashboard |
| Backend Health Check | Verify API is running | `https://YOUR-RAILWAY-URL/health` |
| Backend API Docs | Swagger UI (interactive) | `https://YOUR-RAILWAY-URL/docs` |
| Frontend App | The application itself | `https://YOUR-VERCEL-URL` |
| GitHub Repo | Source code | https://github.com/akhil-kumar-capillary/context_gen_tool |

---

## Final Verification Checklist

Use this to confirm everything is working:

- [ ] Railway PostgreSQL service shows **green** status
- [ ] Railway API service deployed successfully (Deployments → latest shows **green**)
- [ ] `https://YOUR-RAILWAY-URL/health` returns `{"status":"ok"}` in the browser
- [ ] Vercel deployment is **green** (Deployments tab)
- [ ] `CORS_ORIGINS` on Railway contains the Vercel frontend URL
- [ ] Login page loads when you visit the Vercel URL
- [ ] Login with Capillary Intouch credentials works
- [ ] Organization picker shows your orgs
- [ ] Dashboard loads after selecting an org
- [ ] Chat tab works — AI responds with streaming text
- [ ] Admin panel shows Users, Roles, Permissions tabs (for the primary admin)
