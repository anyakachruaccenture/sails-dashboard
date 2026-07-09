"""
Seattle Creates — Impact Dashboard Data Agent
=============================================
Authenticates with Microsoft Graph API (app-only / client credentials flow),
pulls all rows from a SharePoint-hosted Excel workbook, computes metrics, and
writes a single data.json file that the static dashboard reads.

Run:
    python agent.py

Requirements:
    pip install -r requirements.txt
    Copy .env.example to .env and fill in your credentials.
"""

import json
import os
import sys
from collections import defaultdict
from datetime import datetime, timedelta, timezone

import requests
from dotenv import load_dotenv

# ---------------------------------------------------------------------------
# 0. LOAD ENVIRONMENT VARIABLES
# ---------------------------------------------------------------------------
load_dotenv()

TENANT_ID     = os.getenv("TENANT_ID")
CLIENT_ID     = os.getenv("CLIENT_ID")
CLIENT_SECRET = os.getenv("CLIENT_SECRET")
SITE_ID       = os.getenv("SHAREPOINT_SITE_ID")
DRIVE_ID      = os.getenv("DRIVE_ID")
FILE_ID       = os.getenv("FILE_ID")
SHEET_NAME    = os.getenv("SHEET_NAME", "Sheet1")

OUTPUT_PATH    = os.path.join(os.path.dirname(__file__), "..", "dashboard", "data.json")
OUTPUT_JS_PATH = os.path.join(os.path.dirname(__file__), "..", "dashboard", "data.js")


# ---------------------------------------------------------------------------
# 1. AUTHENTICATION — Microsoft Graph API (client credentials / app-only)
# ---------------------------------------------------------------------------

def get_access_token() -> str:
    """
    Exchange app credentials for a Bearer token valid for ~1 hour.
    Uses the client credentials (app-only) flow — no user login needed.
    """
    url = f"https://login.microsoftonline.com/{TENANT_ID}/oauth2/v2.0/token"
    payload = {
        "grant_type":    "client_credentials",
        "client_id":     CLIENT_ID,
        "client_secret": CLIENT_SECRET,
        "scope":         "https://graph.microsoft.com/.default",
    }
    resp = requests.post(url, data=payload, timeout=30)
    resp.raise_for_status()
    token = resp.json().get("access_token")
    if not token:
        raise ValueError("No access_token in response — check your credentials.")
    print("✓  Authenticated with Microsoft Graph API")
    return token


# ---------------------------------------------------------------------------
# 2. DATA FETCHING — pull all used rows from the Excel worksheet
# ---------------------------------------------------------------------------

def fetch_sheet_data(token: str) -> tuple[list[str], list[list]]:
    """
    Call the Graph API usedRange endpoint to get every populated cell.
    Returns (headers, data_rows) where each is a list.
    """
    url = (
        f"https://graph.microsoft.com/v1.0"
        f"/drives/{DRIVE_ID}/items/{FILE_ID}"
        f"/workbook/worksheets/{SHEET_NAME}/usedRange"
    )
    resp = requests.get(url, headers={"Authorization": f"Bearer {token}"}, timeout=60)

    if resp.status_code == 404:
        print(f"ERROR: Sheet '{SHEET_NAME}' not found. Check SHEET_NAME in .env.")
        sys.exit(1)

    resp.raise_for_status()
    all_rows = resp.json().get("values", [])

    if len(all_rows) < 2:
        print("WARNING: Sheet appears empty or has no data rows.")
        return [], []

    column_headers = [str(h).strip() for h in all_rows[0]]
    data_rows      = all_rows[1:]
    print(f"✓  Fetched {len(data_rows)} rows × {len(column_headers)} columns")
    return column_headers, data_rows


def rows_to_dicts(headers: list[str], rows: list[list]) -> list[dict]:
    """Convert the 2-D array the API returns into a list of {column: value} dicts."""
    result = []
    for row in rows:
        padded = row + [""] * (len(headers) - len(row))
        result.append({h: v for h, v in zip(headers, padded)})
    return result


# ---------------------------------------------------------------------------
# 3. COLUMN NAME MAPPING
# ---------------------------------------------------------------------------
# These match the exact headers exported by your Microsoft Form to Excel.
# If you rename a question in the form, update the matching constant here.
# ---------------------------------------------------------------------------

# Microsoft Forms metadata columns (present in every export)
COL_ID          = "Id"
COL_START       = "Start time"
COL_COMPLETE    = "Completion time"   # ← used as the submission date for trends
COL_EMAIL       = "Email"
COL_NAME_AUTO   = "Name"             # M365 account display name (auto-captured)
COL_NAME_FORM   = "Name1"            # "Your name" question inside the form

# Core form questions
COL_ROLES       = "Please select your role(s) in our ecosystem."
COL_ALUM        = "Are you an alumnus/alumna of our programs?"
COL_MENTORSHIP  = "Would you like to receive mentorship?"
COL_INDUSTRY    = "Which industry are you currently working or interested in?"
COL_SKILLS      = "What skills are you seeking to develop?"
COL_RETURNING   = "Have you returned to participate in our programs or events after your initial involvement?"
COL_BECAME_TA   = "Have you become a Teaching Artist with us?"
COL_GOT_JOB     = "Did you get a job, gig, or new opportunity through our ecosystem?"
COL_LAUNCHED_BIZ= "Did you launch a business or new venture as a result of your involvement?"

# CUSTOMIZE: add any additional columns your form has below.
# Common additions to ask about adding to your form:
#   - "Zip Code / Neighborhood"  → for geographic breakdown
#   - "Creative Discipline"       → for discipline donut chart
#   - "Volunteer Hours"           → for volunteer hours totals
#   - "Event Attended"            → for event-level headcounts
#   - "Your Story / Outcome"      → free-text for the stories feed
COL_ZIP         = "Zip Code / Neighborhood"    # not yet in form — add when ready
COL_DISCIPLINE  = "Creative Discipline"        # not yet in form — add when ready
COL_VOL_HOURS   = "Volunteer Hours"            # not yet in form — add when ready
COL_EVENT       = "Event Attended"             # not yet in form — add when ready
COL_STORY       = "Your Story / Outcome"       # not yet in form — add when ready

# Role values — what the multi-select checkboxes produce.
# Microsoft Forms exports multi-select answers as semicolon-separated strings.
# CUSTOMIZE: adjust these strings if your checkbox labels differ.
ROLE_PARTICIPANT = "Participant"
ROLE_TA          = "Teaching Artist"
ROLE_MENTOR      = "Mentor"
ROLE_VOLUNTEER   = "Volunteer"


# ---------------------------------------------------------------------------
# 4. HELPERS
# ---------------------------------------------------------------------------

def has_role(record: dict, role_label: str) -> bool:
    """Return True if this record's role field contains the given label."""
    raw = str(record.get(COL_ROLES, "")).strip()
    # Multi-select answers are semicolon-separated; do a case-insensitive substring check
    return role_label.lower() in raw.lower()


def is_yes(record: dict, col: str) -> bool:
    """Return True if a Yes/No column contains an affirmative answer."""
    v = str(record.get(col, "")).strip().lower()
    return v in ("yes", "y", "true", "1")


def respondent_name(record: dict) -> str:
    """Prefer the form's own name question; fall back to the M365 display name."""
    return (
        str(record.get(COL_NAME_FORM, "")).strip()
        or str(record.get(COL_NAME_AUTO, "")).strip()
    )


def safe_float(value, default=0.0) -> float:
    try:
        return float(str(value).replace("$", "").replace(",", "").strip())
    except (ValueError, TypeError):
        return default


def safe_int(value, default=0) -> int:
    return int(safe_float(value, default))


def parse_date(value) -> datetime | None:
    """
    Parse the date string that Microsoft Forms puts in 'Completion time'.
    Typical format: "4/5/2026 2:34:00 PM"
    Falls back through several formats and Excel serial numbers.
    """
    if not value:
        return None
    s = str(value).strip()
    for fmt in (
        "%m/%d/%Y %I:%M:%S %p",   # Microsoft Forms default
        "%m/%d/%Y %H:%M:%S",
        "%Y-%m-%dT%H:%M:%S",
        "%Y-%m-%d",
        "%m/%d/%Y",
    ):
        try:
            return datetime.strptime(s, fmt)
        except ValueError:
            continue
    # Excel serial date number fallback
    try:
        return datetime(1899, 12, 30) + timedelta(days=int(s))
    except ValueError:
        pass
    return None


def month_key(dt: datetime | None) -> str:
    return dt.strftime("%Y-%m") if dt else "Unknown"


def quarter_key(dt: datetime | None) -> str:
    if not dt:
        return "Unknown"
    q = (dt.month - 1) // 3 + 1
    return f"{dt.year}-Q{q}"


# ---------------------------------------------------------------------------
# 5. CATEGORISATION
# ---------------------------------------------------------------------------
# Everyone fills out the same unified form. The role(s) column drives which
# category (or categories) a respondent falls into. One person can appear in
# multiple categories if they selected multiple roles.
# ---------------------------------------------------------------------------

def categorize_records(records: list[dict]) -> dict:
    """
    Split records into logical groups using the role column.
    A single respondent may appear in more than one group.
    """
    participants = []
    artists      = []
    mentors      = []
    volunteers   = []
    career       = []   # anyone who got a gig or launched a business

    for r in records:
        # Skip blank rows
        if not any(str(v).strip() for v in r.values()):
            continue

        roles_raw = str(r.get(COL_ROLES, "")).strip()

        # Participants: explicitly selected Participant OR no role filled in yet
        if has_role(r, ROLE_PARTICIPANT) or not roles_raw:
            participants.append(r)

        if has_role(r, ROLE_TA):
            artists.append(r)

        if has_role(r, ROLE_MENTOR):
            mentors.append(r)

        if has_role(r, ROLE_VOLUNTEER):
            volunteers.append(r)

        # Career outcomes apply to anyone who answered yes to either question
        if is_yes(r, COL_GOT_JOB) or is_yes(r, COL_LAUNCHED_BIZ):
            career.append(r)

    print(
        f"✓  Categorized: {len(participants)} participants, "
        f"{len(artists)} teaching artists, {len(mentors)} mentors, "
        f"{len(volunteers)} volunteers, {len(career)} career outcomes"
    )
    return {
        "participants": participants,
        "artists":      artists,
        "mentors":      mentors,
        "volunteers":   volunteers,
        "career":       career,
        "all":          [r for r in records if any(str(v).strip() for v in r.values())],
    }


def dedup_by_email(records: list[dict]) -> list[dict]:
    """
    Deduplicate records by email address.
    If email is blank, fall back to respondent name as the key.
    """
    seen    = set()
    unique  = []
    for r in records:
        email = str(r.get(COL_EMAIL, "")).strip().lower()
        name  = respondent_name(r).lower()
        key   = email if email else name
        if key and key not in seen:
            seen.add(key)
            unique.append(r)
    return unique


# ---------------------------------------------------------------------------
# 6. METRICS COMPUTATION
# ---------------------------------------------------------------------------

def compute_metrics(cats: dict) -> dict:
    all_records  = cats["all"]
    participants = cats["participants"]
    artists      = cats["artists"]
    mentors      = cats["mentors"]
    volunteers   = cats["volunteers"]
    career       = cats["career"]

    unique_all   = dedup_by_email(all_records)

    # -----------------------------------------------------------------------
    # TOTALS
    # -----------------------------------------------------------------------
    total_got_job  = sum(1 for r in unique_all if is_yes(r, COL_GOT_JOB))
    total_biz      = sum(1 for r in unique_all if is_yes(r, COL_LAUNCHED_BIZ))
    total_alum     = sum(1 for r in unique_all if is_yes(r, COL_ALUM))
    total_want_mentorship = sum(1 for r in unique_all if is_yes(r, COL_MENTORSHIP))
    total_became_ta = sum(1 for r in unique_all if is_yes(r, COL_BECAME_TA))
    total_vol_hours = sum(safe_float(r.get(COL_VOL_HOURS)) for r in volunteers)

    totals = {
        "total_respondents":     len(unique_all),
        "participants":          len(dedup_by_email(participants)),
        "teaching_artists":      len(dedup_by_email(artists)),
        "mentors":               len(dedup_by_email(mentors)),
        "artists_and_mentors":   len(dedup_by_email(artists + mentors)),
        "volunteers":            len(dedup_by_email(volunteers)),
        # Career outcomes
        "got_job_or_gig":        total_got_job,
        "launched_business":     total_biz,
        "career_placements":     total_got_job + total_biz,
        # Background
        "alumni":                total_alum,
        "seeking_mentorship":    total_want_mentorship,
        "became_teaching_artist":total_became_ta,
        "volunteer_hours":       round(total_vol_hours, 1),
        # events — populated from COL_EVENT if available; shown as 0 until that
        # column is added to the form
        "events":                len(set(
            str(r.get(COL_EVENT, "")).strip()
            for r in all_records
            if str(r.get(COL_EVENT, "")).strip()
        )),
    }

    # -----------------------------------------------------------------------
    # BREAKDOWNS
    # -----------------------------------------------------------------------

    # By industry / discipline (using COL_INDUSTRY; swap to COL_DISCIPLINE when added)
    industry_counts: dict[str, int] = defaultdict(int)
    for r in unique_all:
        ind = str(r.get(COL_INDUSTRY, "")).strip() or str(r.get(COL_DISCIPLINE, "")).strip() or "Other"
        # Industry answers can be long; truncate gracefully for display
        industry_counts[ind[:60]] += 1

    # By zip / neighborhood (blank until COL_ZIP column is added to the form)
    zip_counts: dict[str, int] = defaultdict(int)
    for r in unique_all:
        z = str(r.get(COL_ZIP, "")).strip() or "Not collected yet"
        zip_counts[z] += 1

    # Alumni breakdown
    alum_counts = {
        "Alumni": total_alum,
        "Non-Alumni": len(unique_all) - total_alum,
    }

    # Returning vs. first-time (based on the returning question)
    returning_counts = {
        "Returning": sum(1 for r in unique_all if is_yes(r, COL_RETURNING)),
        "First-time": sum(1 for r in unique_all if not is_yes(r, COL_RETURNING)),
    }

    # Skills being sought
    skills_counts: dict[str, int] = defaultdict(int)
    for r in unique_all:
        raw = str(r.get(COL_SKILLS, "")).strip()
        if raw:
            # Skills may be a multi-select (semicolons) or free text
            for skill in raw.split(";"):
                s = skill.strip()
                if s:
                    skills_counts[s[:50]] += 1

    breakdowns = {
        "by_industry":          dict(sorted(industry_counts.items(), key=lambda x: -x[1])),
        "by_zip":               dict(sorted(zip_counts.items(),      key=lambda x: -x[1])),
        "alumni_vs_non":        alum_counts,
        "returning_vs_new":     returning_counts,
        "skills_sought":        dict(sorted(skills_counts.items(),   key=lambda x: -x[1])[:15]),
    }

    # -----------------------------------------------------------------------
    # TRENDS  (keyed by Completion time)
    # -----------------------------------------------------------------------

    # New vs. returning respondents per month
    new_ret_by_month: dict[str, dict] = defaultdict(lambda: {"new": 0, "returning": 0})
    for r in all_records:
        dt = parse_date(r.get(COL_COMPLETE))
        mk = month_key(dt)
        if is_yes(r, COL_RETURNING):
            new_ret_by_month[mk]["returning"] += 1
        else:
            new_ret_by_month[mk]["new"] += 1

    # Submissions per month (overall engagement trend)
    submissions_by_month: dict[str, int] = defaultdict(int)
    for r in all_records:
        dt = parse_date(r.get(COL_COMPLETE))
        submissions_by_month[month_key(dt)] += 1

    # Career outcomes over time
    outcomes_by_month: dict[str, dict] = defaultdict(lambda: {"job_gig": 0, "business": 0})
    for r in all_records:
        dt = parse_date(r.get(COL_COMPLETE))
        mk = month_key(dt)
        if is_yes(r, COL_GOT_JOB):
            outcomes_by_month[mk]["job_gig"] += 1
        if is_yes(r, COL_LAUNCHED_BIZ):
            outcomes_by_month[mk]["business"] += 1

    # Teaching artist conversions over time
    ta_by_month: dict[str, int] = defaultdict(int)
    for r in all_records:
        if is_yes(r, COL_BECAME_TA):
            dt = parse_date(r.get(COL_COMPLETE))
            ta_by_month[month_key(dt)] += 1

    # Volunteer hours by quarter (requires COL_VOL_HOURS on form)
    hours_by_quarter: dict[str, float] = defaultdict(float)
    for r in volunteers:
        dt = parse_date(r.get(COL_COMPLETE))
        hours_by_quarter[quarter_key(dt)] += safe_float(r.get(COL_VOL_HOURS))

    # Event headcounts (requires COL_EVENT on form)
    event_headcounts = []
    event_counter: dict[str, dict] = defaultdict(lambda: {"count": 0, "date": None})
    for r in all_records:
        evt = str(r.get(COL_EVENT, "")).strip()
        if evt:
            dt = parse_date(r.get(COL_COMPLETE))
            event_counter[evt]["count"] += 1
            if event_counter[evt]["date"] is None and dt:
                event_counter[evt]["date"] = dt.strftime("%Y-%m-%d")
    for name, info in sorted(event_counter.items(), key=lambda x: x[1]["date"] or ""):
        event_headcounts.append({"event": name, "date": info["date"], "headcount": info["count"]})

    trends = {
        "new_vs_returning_by_month":  dict(sorted(new_ret_by_month.items())),
        "submissions_by_month":       dict(sorted(submissions_by_month.items())),
        "outcomes_by_month":          dict(sorted(outcomes_by_month.items())),
        "ta_conversions_by_month":    dict(sorted(ta_by_month.items())),
        "volunteer_hours_by_quarter": dict(sorted(hours_by_quarter.items())),
        "headcount_per_event":        event_headcounts,
    }

    # -----------------------------------------------------------------------
    # STORIES
    # -----------------------------------------------------------------------
    # Primary: pull from the free-text story field (add COL_STORY to your form).
    # Fallback: auto-generate brief outcome statements from Yes/No answers.
    # -----------------------------------------------------------------------
    stories = []

    for r in unique_all:
        name  = respondent_name(r)
        dt    = parse_date(r.get(COL_COMPLETE))
        label = dt.strftime("%B %Y") if dt else None
        event = str(r.get(COL_EVENT, "")).strip() or "Program Participant"

        # Prefer explicit story text
        story_text = str(r.get(COL_STORY, "")).strip()
        if story_text and name:
            stories.append({"event": event, "date": label, "story": story_text})
            continue

        # Auto-generate from outcome flags (only if we have a name and at least one win)
        wins = []
        if is_yes(r, COL_GOT_JOB):
            wins.append("landed a job, gig, or new opportunity")
        if is_yes(r, COL_LAUNCHED_BIZ):
            wins.append("launched a new business or venture")
        if is_yes(r, COL_BECAME_TA):
            wins.append("became a Teaching Artist")

        if wins and name:
            stories.append({
                "event": event,
                "date":  label,
                "story": f"{name} {' and '.join(wins)} through their involvement with Seattle Creates.",
            })

    return {
        "totals":     totals,
        "breakdowns": breakdowns,
        "trends":     trends,
        "stories":    stories[:20],  # cap at 20 for dashboard display
    }


# ---------------------------------------------------------------------------
# 7. SHAPE RAW ROWS FOR JSON OUTPUT
# ---------------------------------------------------------------------------

def shape_raw(cats: dict) -> dict:
    def clean(records):
        return [
            {k: str(v).strip() for k, v in r.items() if str(v).strip()}
            for r in records
        ]
    return {
        "participants": clean(cats["participants"]),
        "artists":      clean(cats["artists"]),
        "mentors":      clean(cats["mentors"]),
        "volunteers":   clean(cats["volunteers"]),
        "career":       clean(cats["career"]),
    }


# ---------------------------------------------------------------------------
# 8. MAIN ENTRY POINT
# ---------------------------------------------------------------------------

def main():
    print("\n=== Seattle Creates — Data Agent ===\n")

    missing = [k for k, v in {
        "TENANT_ID":          TENANT_ID,
        "CLIENT_ID":          CLIENT_ID,
        "CLIENT_SECRET":      CLIENT_SECRET,
        "SHAREPOINT_SITE_ID": SITE_ID,
        "DRIVE_ID":           DRIVE_ID,
        "FILE_ID":            FILE_ID,
    }.items() if not v]

    if missing:
        print(f"ERROR: Missing env vars: {', '.join(missing)}")
        print("Copy .env.example to .env and fill in your credentials.")
        sys.exit(1)

    token                      = get_access_token()
    column_headers, raw_rows   = fetch_sheet_data(token)
    records                    = rows_to_dicts(column_headers, raw_rows)
    cats                       = categorize_records(records)
    metrics                    = compute_metrics(cats)

    output = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source":       f"SharePoint file {FILE_ID} / sheet '{SHEET_NAME}'",
        "metrics":      metrics,
        "raw":          shape_raw(cats),
    }

    os.makedirs(os.path.dirname(OUTPUT_PATH), exist_ok=True)

    # Write data.json (used when served via HTTP / Netlify / GitHub Pages)
    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        json.dump(output, f, indent=2, ensure_ascii=False)

    # Write data.js (used when opening index.html directly as a file://)
    # The dashboard loads whichever one works; this one always works.
    with open(OUTPUT_JS_PATH, "w", encoding="utf-8") as f:
        f.write("window.DASHBOARD_DATA = ")
        json.dump(output, f, ensure_ascii=False)
        f.write(";\n")

    t = metrics["totals"]
    print(f"\n✓  data.json + data.js written → {os.path.abspath(OUTPUT_PATH)}")
    print(f"    Total respondents  : {t['total_respondents']}")
    print(f"    Teaching artists   : {t['teaching_artists']}")
    print(f"    Career placements  : {t['career_placements']}")
    print(f"    Business launches  : {t['launched_business']}")
    print("\nDone.\n")


if __name__ == "__main__":
    main()
