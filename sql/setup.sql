-- ============================================================
-- Seattle Creates — Supabase Database Setup
-- Run this entire file in the Supabase SQL Editor (one paste).
-- supabase.com → your project → SQL Editor → New query → paste → Run
--
-- NOTE: This script drops and recreates the responses table so that
-- the 'role' column changes from text to text[] (Postgres array).
-- Any existing test rows will be removed.
-- ============================================================


-- ------------------------------------------------------------
-- 1. DROP EXISTING TABLE AND POLICIES
-- ------------------------------------------------------------

DROP TABLE IF EXISTS responses;
DROP VIEW  IF EXISTS dashboard_metrics;


-- ------------------------------------------------------------
-- 2. RESPONSES TABLE
-- Stores one row per survey submission from /survey.
-- role is now a Postgres text array for multi-select checkboxes.
-- ------------------------------------------------------------

CREATE TABLE responses (
  id                       bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  submitted_at             timestamptz DEFAULT now(),
  name                     text NOT NULL,
  role                     text[],                           -- e.g. {"Participant","Volunteer"}
  is_alumni                text,                             -- "Yes" or "No"
  wants_mentorship         text,                             -- "Yes", "No", or "Maybe"
  industry                 text,
  skills_seeking           text,
  has_returned             text,                             -- "Yes" or "No"
  became_teaching_artist   text,                             -- "Yes" or "No"
  got_job_or_opportunity   text,                             -- "Yes" or "No"
  launched_business        text                              -- "Yes" or "No"
);


-- ------------------------------------------------------------
-- 3. ROW LEVEL SECURITY
-- Anonymous SELECT  → dashboard can read
-- Anonymous INSERT  → survey form can write (via /api/submit)
-- The service_role key bypasses RLS entirely (used in API route).
-- ------------------------------------------------------------

ALTER TABLE responses ENABLE ROW LEVEL SECURITY;

CREATE POLICY "Public read"
  ON responses FOR SELECT USING (true);

CREATE POLICY "Public insert"
  ON responses FOR INSERT WITH CHECK (true);


-- ------------------------------------------------------------
-- 4. DASHBOARD METRICS VIEW
-- Pre-computes aggregate numbers for fast dashboard queries.
-- ------------------------------------------------------------

CREATE OR REPLACE VIEW dashboard_metrics AS
SELECT
  COUNT(*)                                                          AS total_responses,
  COUNT(DISTINCT LOWER(TRIM(name))) FILTER (WHERE name IS NOT NULL) AS unique_respondents,
  COUNT(*) FILTER (WHERE 'Teaching Artist' = ANY(role))             AS teaching_artists,
  COUNT(*) FILTER (WHERE got_job_or_opportunity ILIKE 'Yes')        AS got_job,
  COUNT(*) FILTER (WHERE launched_business ILIKE 'Yes')             AS launched_business,
  COUNT(*) FILTER (WHERE has_returned ILIKE 'Yes')                  AS returning_participants,
  COUNT(*) FILTER (WHERE is_alumni ILIKE 'Yes')                     AS alumni,
  COUNT(*) FILTER (WHERE became_teaching_artist ILIKE 'Yes')        AS became_ta,
  COUNT(*) FILTER (WHERE wants_mentorship ILIKE 'Yes')              AS wants_mentorship_yes,
  COUNT(*) FILTER (WHERE wants_mentorship ILIKE 'No')               AS wants_mentorship_no,
  COUNT(*) FILTER (WHERE wants_mentorship ILIKE 'Maybe')            AS wants_mentorship_maybe
FROM responses;
