# Seattle Creates — Impact Dashboard

A static HTML dashboard fed by a Python agent that pulls program data from a
SharePoint-hosted Excel workbook via the Microsoft Graph API.

```
sails-dashboard/
├── agent/
│   ├── agent.py          # Graph API fetcher + metrics computation
│   ├── .env.example      # Template — copy to .env and fill in credentials
│   └── requirements.txt
├── dashboard/
│   ├── index.html        # Static dashboard (open in browser or deploy to Netlify)
│   └── data.json         # Output from agent (committed after each run)
├── .gitignore
└── README.md
```

---

## Part 1 — Azure App Registration (one-time setup)

You need to register an app in Azure so the Python agent can authenticate as
the app itself (no user login required). This is called the **client
credentials flow**.

### Step-by-step

1. **Sign in to the Azure Portal**
   Go to [portal.azure.com](https://portal.azure.com) and sign in with your
   organization's Microsoft 365 admin account.

2. **Open App registrations**
   Search "App registrations" in the top bar → click **New registration**.

3. **Name and register the app**
   - Name: `Seattle Creates Dashboard Agent` (or anything you like)
   - Supported account types: **Accounts in this organizational directory only**
   - Redirect URI: leave blank
   - Click **Register**

4. **Copy your IDs**
   On the app's overview page, copy:
   - **Application (client) ID** → `CLIENT_ID` in your `.env`
   - **Directory (tenant) ID** → `TENANT_ID` in your `.env`

5. **Create a client secret**
   Left sidebar → **Certificates & secrets** → **New client secret**
   - Description: `dashboard-agent`
   - Expiry: 24 months (or whatever your org policy allows)
   - Click **Add**, then immediately copy the **Value** → `CLIENT_SECRET` in
     your `.env`. You cannot see it again after leaving this page.

6. **Grant API permissions**
   Left sidebar → **API permissions** → **Add a permission** →
   **Microsoft Graph** → **Application permissions** → search for and add:
   - `Sites.Read.All` — read SharePoint site data
   - `Files.Read.All` — read files in OneDrive/SharePoint

   Then click **Grant admin consent for [your org]** (requires admin role).
   The status column should show a green checkmark.

---

## Part 2 — Find your SharePoint / Drive IDs

You need three IDs from your SharePoint environment. The easiest way is via
Microsoft Graph Explorer ([graph.microsoft.com/graph-explorer](https://developer.microsoft.com/graph/graph-explorer)).

Sign in with your org account, then run these queries:

### Find SHAREPOINT_SITE_ID
```
GET https://graph.microsoft.com/v1.0/sites?search=<your-sharepoint-domain>
```
Or if you know the site URL:
```
GET https://graph.microsoft.com/v1.0/sites/<hostname>:/sites/<site-name>
```
Copy the `id` field from the response.

### Find DRIVE_ID
```
GET https://graph.microsoft.com/v1.0/sites/<SITE_ID>/drives
```
Look for the drive named "Documents" (or your document library name).
Copy its `id`.

### Find FILE_ID
```
GET https://graph.microsoft.com/v1.0/drives/<DRIVE_ID>/root/children
```
Find your Excel file in the list and copy its `id`. If the file is in a
subfolder, navigate: `.../root:/FolderName:/children`

---

## Part 3 — Local Setup

### Install Python dependencies
```bash
cd agent
pip install -r requirements.txt
```

### Configure credentials
```bash
cp agent/.env.example agent/.env
```

Open `agent/.env` and fill in all six values:
```
TENANT_ID=...
CLIENT_ID=...
CLIENT_SECRET=...
SHAREPOINT_SITE_ID=...
DRIVE_ID=...
FILE_ID=...
SHEET_NAME=Sheet1    # change if your tab is named differently
```

### Customize column names (important!)
Open `agent/agent.py` and scroll to the **COLUMN NAME MAPPING** section
(around line 130). Change the right-hand side of each constant to match your
actual Excel column headers exactly.

Example — if your form uses "Full Name" instead of "Name":
```python
PART_NAME = "Full Name"   # was: "Name"
```

---

## Part 4 — Running the Agent

```bash
cd agent
python agent.py
```

Expected output:
```
=== Seattle Creates — Data Agent ===

✓  Authenticated with Microsoft Graph API
✓  Fetched 247 rows with 28 columns
✓  Categorized: 190 participants, 18 artists/mentors, ...

✓  data.json written → .../dashboard/data.json
    Participants : 156
    Events       : 12
    Placements   : 8
```

### Verify data.json looks right

Open `dashboard/data.json` and check:
- `metrics.totals.participants` is in the right ballpark
- `metrics.breakdowns.participants_by_discipline` has your actual disciplines
- `metrics.stories` has text from your "Notable Outcomes" column
- `raw` arrays have the expected number of records

If participant counts seem off, check the `categorize_records()` function —
it detects record type by which fields are populated. If your form has a
dedicated "Record Type" column, switch the detection logic to use that.

---

## Part 5 — Previewing the Dashboard Locally

Because the dashboard fetches `data.json` via `fetch()`, you need a local HTTP
server (opening the HTML file directly will fail with a CORS error).

**Option A — Python (simplest)**
```bash
cd dashboard
python -m http.server 8080
```
Then open [http://localhost:8080](http://localhost:8080)

**Option B — VS Code**
Install the "Live Server" extension, right-click `index.html` → Open with
Live Server.

---

## Part 6 — Deployment Checklist

### Before deploying
- [ ] Run `python agent/agent.py` and confirm `dashboard/data.json` is updated
- [ ] Open `dashboard/index.html` locally and verify all 5 stat cards show
      real numbers
- [ ] Check that all 3 charts render (discipline donut, headcount bar, new/returning line)
- [ ] Scroll through stories feed — confirm stories appear
- [ ] Verify the footer timestamp matches when you ran the agent
- [ ] Confirm `agent/.env` is NOT in your git staging area (`git status`)

### Deploy to Netlify (recommended — free, instant)

1. Push your repo to GitHub (without `.env` — it's in `.gitignore`)
2. Go to [netlify.com](https://netlify.com) → **Add new site** →
   **Import an existing project**
3. Connect your GitHub repo
4. Build settings:
   - **Base directory**: `dashboard`
   - **Publish directory**: `dashboard`
   - **Build command**: leave blank (static site, no build step)
5. Click **Deploy site**

Your dashboard will be live at `https://<random-name>.netlify.app`.

To update after a new data run:
```bash
python agent/agent.py          # regenerate data.json
git add dashboard/data.json
git commit -m "Update impact data"
git push
```
Netlify redeploys automatically on push.

### Deploy to GitHub Pages (alternative)

1. In your GitHub repo → **Settings** → **Pages**
2. Source: **Deploy from a branch**, branch: `main`, folder: `/dashboard`
3. Your dashboard will be at `https://<username>.github.io/<repo-name>/`

> **Note on PII:** `data.json` in its current form contains aggregated metrics
> and story text (no individual names). If you add raw participant records to
> the dashboard in the future, reconsider what you commit to a public repo.

---

## Troubleshooting

| Error | Likely cause | Fix |
|---|---|---|
| `401 Unauthorized` | Wrong CLIENT_ID / CLIENT_SECRET | Double-check .env values |
| `403 Forbidden` | Missing API permissions or admin consent not granted | Re-check Azure Portal permissions step |
| `404 Not Found` on sheet | Wrong SHEET_NAME | Check the tab name in Excel |
| Empty `data.json` | Column names don't match | Update constants in COLUMN NAME MAPPING |
| `fetch` error in browser | Opened HTML as file:// | Use `python -m http.server 8080` |
