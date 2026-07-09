-- ============================================================
-- Seattle Creates — Supabase Database Setup
-- Run this entire file in the Supabase SQL Editor (one paste).
-- supabase.com → your project → SQL Editor → New query → paste → Run
-- ============================================================


-- ------------------------------------------------------------
-- 1. RESPONSES TABLE
-- Stores one row per Microsoft Form submission.
-- Power Automate inserts rows here via the /api/webhook route.
-- ------------------------------------------------------------

CREATE TABLE IF NOT EXISTS responses (
  id                       bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  submitted_at             timestamptz DEFAULT now(),          -- when the row was inserted
  name                     text,                               -- respondent's full name
  role                     text,                               -- comma-separated roles, e.g. "Participant, Volunteer"
  is_alumni                text,                               -- "Yes" or "No"
  wants_mentorship         text,                               -- "Yes", "No", or "Maybe"
  industry                 text,                               -- free-text, e.g. "Music", "Film"
  skills_seeking           text,                               -- free-text, may be multi-line
  has_returned             text,                               -- "Yes" or "No"
  became_teaching_artist   text,                               -- "Yes" or "No"
  got_job_or_opportunity   text,                               -- "Yes" or "No"
  launched_business        text                                -- "Yes" or "No"
);


-- ------------------------------------------------------------
-- 2. ROW LEVEL SECURITY (RLS)
-- RLS controls who can read or write rows.
-- With RLS ON and no policy, NOBODY can access the table by default.
-- The service_role key (used by the webhook) bypasses RLS entirely.
-- The anon key (used by the dashboard) must be explicitly allowed.
-- ------------------------------------------------------------

ALTER TABLE responses ENABLE ROW LEVEL SECURITY;

-- Allow anyone with the anon key to READ rows (dashboard needs this)
CREATE POLICY "Public read"
  ON responses
  FOR SELECT
  USING (true);

-- Block anonymous INSERT — only the service_role key (via webhook) can insert.
-- (service_role bypasses RLS, so no INSERT policy is needed for it.)
-- This policy makes the restriction explicit and self-documenting.
CREATE POLICY "Block anon insert"
  ON responses
  FOR INSERT
  WITH CHECK (false);


-- ------------------------------------------------------------
-- 3. DASHBOARD METRICS VIEW
-- Pre-computes the aggregate numbers the dashboard hero cards show.
-- The dashboard can either query this view OR compute from raw rows.
-- Having it server-side is faster for large datasets.
-- ------------------------------------------------------------

CREATE OR REPLACE VIEW dashboard_metrics AS
SELECT
  COUNT(*)                                                          AS total_responses,
  COUNT(DISTINCT LOWER(TRIM(name))) FILTER (WHERE name IS NOT NULL) AS unique_respondents,
  COUNT(*) FILTER (WHERE role ILIKE '%Teaching Artist%')            AS teaching_artists,
  COUNT(*) FILTER (WHERE got_job_or_opportunity ILIKE 'Yes')        AS got_job,
  COUNT(*) FILTER (WHERE launched_business ILIKE 'Yes')             AS launched_business,
  COUNT(*) FILTER (WHERE has_returned ILIKE 'Yes')                  AS returning_participants,
  COUNT(*) FILTER (WHERE is_alumni ILIKE 'Yes')                     AS alumni,
  COUNT(*) FILTER (WHERE became_teaching_artist ILIKE 'Yes')        AS became_ta,
  COUNT(*) FILTER (WHERE wants_mentorship ILIKE 'Yes')              AS wants_mentorship_yes,
  COUNT(*) FILTER (WHERE wants_mentorship ILIKE 'No')               AS wants_mentorship_no,
  COUNT(*) FILTER (WHERE wants_mentorship ILIKE 'Maybe')            AS wants_mentorship_maybe
FROM responses;
