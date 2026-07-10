# Seattle Creates — Impact Dashboard

A live impact dashboard for Seattle Creates. Community members fill out a survey at `/survey`, their responses are written directly to Supabase, and the dashboard at `/` reads live data in real time.

## Architecture

```
/survey (survey/index.html)
     │
     │  POST /api/submit  (JSON body)
     ▼
Vercel Serverless Function  (api/submit.js)
     │  validates fields, rate-limits by name (1 hr), inserts row
     ▼
Supabase (Postgres)
     │
     │  SELECT * FROM responses  (anon key, RLS = read + insert)
     ▼
Dashboard (dashboard/index.html)
     │  computes metrics client-side, renders charts
     ▼
Vercel (static hosting)  →  https://sails-dashboard.vercel.app
```

## Repo Structure

```
sails-dashboard/
├── api/
│   └── submit.js         Vercel serverless function — receives survey POSTs
├── dashboard/
│   └── index.html        Static dashboard — reads live from Supabase
├── survey/
│   └── index.html        4-step survey form — posts to /api/submit
├── sql/
│   └── setup.sql         Run once in Supabase SQL Editor to create table + RLS
├── .gitignore
├── package.json          @supabase/supabase-js for the API route
├── vercel.json           URL rewrites: / → dashboard, /survey → survey form
└── README.md
```

---

## Setup Guide

### Step 1 — Create a free Supabase project

1. Go to [supabase.com](https://supabase.com) and sign up / sign in
2. Click **New Project** — choose a name (e.g. `seattle-creates`) and a strong password
3. Wait ~2 minutes for the project to spin up

### Step 2 — Run the database migration

1. In your Supabase project, click **SQL Editor** in the left sidebar
2. Click **New query**
3. Paste the entire contents of `sql/setup.sql` into the editor
4. Click **Run** (the green button)

This creates:
- The `responses` table (with `role` as a Postgres `text[]` array for multi-select)
- Row Level Security allowing anonymous SELECT and INSERT
- A `dashboard_metrics` view for aggregate queries

> **Note:** Running `setup.sql` drops and recreates the table — any existing test rows will be removed. Run it once on a fresh project.

### Step 3 — Collect your Supabase credentials

In your Supabase project: **Project Settings → API**

| Value | Where to use it |
|---|---|
| **Project URL** | Vercel env var + `dashboard/index.html` |
| **Anon / public key** | `dashboard/index.html` only (safe to expose) |
| **Service role key** | Vercel env var only — keep this secret |

### Step 4 — Add environment variables in Vercel

In your Vercel project: **Settings → Environment Variables**

| Name | Value |
|---|---|
| `SUPABASE_URL` | Your project URL |
| `SUPABASE_SERVICE_ROLE_KEY` | Your service role key |

After adding them: **Deployments → three dots → Redeploy**.

### Step 5 — Credentials already in the dashboard

`dashboard/index.html` already has the Supabase URL and anon key hardcoded.
The anon key is safe in client-side code — RLS allows only SELECT and INSERT.

### Step 6 — Push and deploy

```bash
git add .
git commit -m "Initial deploy"
git push
```

Vercel picks up the push and redeploys automatically (~30 seconds).

---

## Testing the Survey Endpoint Manually

Use `curl` to send a test submission without opening the form:

```bash
curl -X POST https://sails-dashboard.vercel.app/api/submit \
  -H "Content-Type: application/json" \
  -d '{
    "name":                   "Test Person",
    "role":                   ["Participant", "Volunteer"],
    "is_alumni":              "No",
    "has_returned":           "No",
    "became_teaching_artist": "No",
    "got_job_or_opportunity": "Yes",
    "launched_business":      "No",
    "wants_mentorship":       "Yes",
    "industry":               "Music",
    "skills_seeking":         "Music production, grant writing"
  }'
```

Expected response: `{"success":true}`

- `400` → validation error (check the `error` field for details)
- `429` → same name submitted within the last hour
- `500` → Supabase issue (check env vars and table exists)

---

## Security Notes

| Key | Where it lives | Who can see it |
|---|---|---|
| Supabase URL | `dashboard/index.html` + Vercel env | Public (not sensitive) |
| Supabase anon key | `dashboard/index.html` | Public (RLS limits to SELECT + INSERT) |
| Supabase service role key | Vercel env only | Never in code or git |

The `.gitignore` excludes `.env` files. Never commit secrets to git.

---

## How data flows

1. Someone visits `https://sails-dashboard.vercel.app/survey`
2. They fill out the 4-step form and click **Submit**
3. The form POSTs JSON to `/api/submit`
4. `api/submit.js` validates fields, checks the rate limit, and inserts a row into Supabase
5. The dashboard at `/` fetches all rows on page load and renders charts + metrics

Microsoft Forms is still used for Accenture compliance records — but it is no longer the data source for the dashboard.
