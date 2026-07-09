# Seattle Creates — Impact Dashboard

A live impact dashboard for Seattle Creates. Data flows automatically from a Microsoft Form into a Supabase database and appears on the dashboard in real time — no manual exports, no Python scripts.

## Architecture

```
Microsoft Form
     │
     │  (new response submitted)
     ▼
Power Automate
     │
     │  POST /api/webhook  (with x-webhook-secret header)
     ▼
Vercel Serverless Function  (api/webhook.js)
     │
     │  INSERT into responses table
     ▼
Supabase (Postgres)
     │
     │  SELECT * FROM responses  (anon key, RLS = read-only)
     ▼
Dashboard (dashboard/index.html)
     │
     │  computes metrics client-side, renders charts
     ▼
Vercel (static hosting)  →  https://sails-dashboard.vercel.app
```

## Repo Structure

```
sails-dashboard/
├── api/
│   └── webhook.js        Vercel serverless function — receives Power Automate POSTs
├── dashboard/
│   └── index.html        Static dashboard — reads live from Supabase
├── sql/
│   └── setup.sql         Run once in Supabase SQL Editor to create table + RLS
├── .gitignore
├── package.json          @supabase/supabase-js dependency for the API route
├── vercel.json           Tells Vercel to serve dashboard/ as the static root
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
- The `responses` table with all the form columns
- Row Level Security (RLS) so only the dashboard can read and only the webhook can write
- A `dashboard_metrics` view for fast aggregate queries

### Step 3 — Collect your Supabase credentials

In your Supabase project: **Project Settings → API**

Copy these three values — you'll need them in the next steps:

| Value | Where to use it |
|---|---|
| **Project URL** (e.g. `https://abc.supabase.co`) | Vercel env var + `index.html` |
| **Anon / public key** | `index.html` only (safe to expose) |
| **Service role key** | Vercel env var only (keep secret) |

### Step 4 — Add environment variables in Vercel

In your Vercel project: **Settings → Environment Variables**

Add these three variables (never put them in your code):

| Name | Value |
|---|---|
| `SUPABASE_URL` | Your project URL from step 3 |
| `SUPABASE_SERVICE_ROLE_KEY` | Your service role key from step 3 |
| `WEBHOOK_SECRET` | Any random string you invent, e.g. `sc-2026-secret-xyz` — you'll use this same string in Power Automate |

After adding them, redeploy: **Deployments → three dots → Redeploy**.

### Step 5 — Add your Supabase keys to the dashboard

Open `dashboard/index.html` and find these two lines near the top of the `<script>` section:

```javascript
const SUPABASE_URL      = "https://YOUR_PROJECT_ID.supabase.co";  // ← REPLACE
const SUPABASE_ANON_KEY = "YOUR_ANON_KEY_HERE";                   // ← REPLACE
```

Replace both values with the ones from Step 3, then save the file.

**The anon key is safe to put here.** Row Level Security means the browser can only read data — it cannot insert, update, or delete anything.

### Step 6 — Push and deploy

```bash
git add dashboard/index.html
git commit -m "Add Supabase credentials"
git push
```

Vercel picks up the push and redeploys automatically (~30 seconds).

---

## Power Automate Setup

Power Automate runs inside your Accenture Microsoft 365 account and triggers on every new form submission.

### Create the flow

1. Go to [flow.microsoft.com](https://flow.microsoft.com) — sign in with your Accenture account
2. Click **Create → Automated cloud flow**
3. Name it `Seattle Creates → Dashboard`
4. Search for trigger: **"When a new response is submitted"** (Microsoft Forms connector)
5. Select form: **Human Capital Impact Survey**
6. Click **Create**

### Add "Get response details"

1. Click **+ New step**
2. Search: **"Get response details"** (Microsoft Forms)
3. Form ID: select **Human Capital Impact Survey**
4. Response ID: select **List of response notifications Response Id** from the dynamic content panel

### Add the HTTP action

1. Click **+ New step**
2. Search: **"HTTP"** — select the built-in HTTP action
3. Fill in:

   **Method:** `POST`

   **URI:** `https://sails-dashboard.vercel.app/api/webhook`

   **Headers:**
   ```
   Content-Type   application/json
   x-webhook-secret   <paste your WEBHOOK_SECRET from Vercel>
   ```

   **Body** — paste this JSON and map each `<...>` to the matching form field from the dynamic content panel:
   ```json
   {
     "name":                   "@{outputs('Get_response_details')?['body/r5c6b7']?['value']}",
     "role":                   "@{outputs('Get_response_details')?['body/r1234']?['value']}",
     "is_alumni":              "@{outputs('Get_response_details')?['body/r5678']?['value']}",
     "wants_mentorship":       "@{outputs('Get_response_details')?['body/r9012']?['value']}",
     "industry":               "@{outputs('Get_response_details')?['body/r3456']?['value']}",
     "skills_seeking":         "@{outputs('Get_response_details')?['body/r7890']?['value']}",
     "has_returned":           "@{outputs('Get_response_details')?['body/r1111']?['value']}",
     "became_teaching_artist": "@{outputs('Get_response_details')?['body/r2222']?['value']}",
     "got_job_or_opportunity": "@{outputs('Get_response_details')?['body/r3333']?['value']}",
     "launched_business":      "@{outputs('Get_response_details')?['body/r4444']?['value']}",
     "name1":                  "@{outputs('Get_response_details')?['body/responderEmail']}"
   }
   ```

   > **Note on field IDs:** The `r5c6b7`-style codes are internal Microsoft Forms identifiers. When you click inside the Body field and open the dynamic content panel, Power Automate shows each form question by its label — just click the matching question to insert the correct expression automatically. You don't need to know the codes.

4. Click **Save**, then **Test** the flow by submitting a test response to the form.

### Verify a row arrived

In Supabase: **Table Editor → responses** — you should see the test row appear within a few seconds.

---

## Testing the Webhook Manually

Use this `curl` command to send a test row without going through Power Automate.
Replace `YOUR_SECRET` with your actual `WEBHOOK_SECRET`.

```bash
curl -X POST https://sails-dashboard.vercel.app/api/webhook \
  -H "Content-Type: application/json" \
  -H "x-webhook-secret: YOUR_SECRET" \
  -d '{
    "name": "Test Person",
    "role": "Participant, Volunteer",
    "is_alumni": "No",
    "wants_mentorship": "Yes",
    "industry": "Music",
    "skills_seeking": "Music production\nGrant writing",
    "has_returned": "No",
    "became_teaching_artist": "No",
    "got_job_or_opportunity": "Yes",
    "launched_business": "No"
  }'
```

Expected response: `{"success":true}`

If you get `401`, the secret doesn't match your Vercel env var.
If you get `500`, check the Supabase table exists and RLS is configured.

---

## Updating the Dashboard After Setup

Once everything is wired up, the dashboard updates automatically — no manual steps needed. Every new form submission triggers Power Automate, which calls the webhook, which inserts a row into Supabase. The dashboard reads live from Supabase on every page load.

To refresh data while looking at the dashboard: just reload the page.

---

## Security Notes

| Key | Where it lives | Who can see it |
|---|---|---|
| Supabase URL | `index.html` + Vercel env | Public (not sensitive) |
| Supabase anon key | `index.html` | Public (RLS blocks writes) |
| Supabase service role key | Vercel env only | Never in code or git |
| Webhook secret | Vercel env + Power Automate | Never in code or git |

The `.gitignore` excludes `.env` files. Never commit secrets to git.
