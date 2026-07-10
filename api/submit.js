// ============================================================
// /api/submit.js — Vercel Serverless Function
// ============================================================
// Receives POST requests from the /survey form, validates and
// sanitizes the data, checks for duplicate submissions within
// the past hour, then inserts a row into Supabase.
//
// Environment variables (set in Vercel dashboard, never in code):
//   SUPABASE_URL              — your project URL
//   SUPABASE_SERVICE_ROLE_KEY — bypasses RLS (server-side only)
// ============================================================

const { createClient } = require("@supabase/supabase-js");

const supabase = createClient(
  process.env.SUPABASE_URL,
  process.env.SUPABASE_SERVICE_ROLE_KEY
);

const ALLOWED_ROLES = [
  "Participant", "Teaching Artist", "Industry Mentor",
  "Speaker", "Volunteer", "Alumni", "Intern", "Apprentice",
];
const YES_NO       = ["Yes", "No"];
const YES_NO_MAYBE = ["Yes", "No", "Maybe"];

module.exports = async function handler(req, res) {
  res.setHeader("Access-Control-Allow-Origin", "*");
  res.setHeader("Access-Control-Allow-Methods", "POST, OPTIONS");
  res.setHeader("Access-Control-Allow-Headers", "Content-Type");

  if (req.method === "OPTIONS") return res.status(200).end();
  if (req.method !== "POST")
    return res.status(405).json({ error: "Method not allowed" });

  const b = req.body || {};
  const errors = [];

  // ── Validate name ───────────────────────────────────────────
  const name = (b.name || "").trim().slice(0, 200);
  if (!name) errors.push("Name is required.");

  // ── Validate roles (must be non-empty array of allowed values) ─
  const role = Array.isArray(b.role) ? b.role : [];
  if (!role.length) errors.push("Please select at least one role.");
  const badRoles = role.filter(r => !ALLOWED_ROLES.includes(r));
  if (badRoles.length) errors.push(`Unrecognised role(s): ${badRoles.join(", ")}`);

  // ── Validate yes/no fields ──────────────────────────────────
  const yesNoFields = [
    ["is_alumni",              YES_NO,       "Alumni status"],
    ["has_returned",           YES_NO,       "Return status"],
    ["became_teaching_artist", YES_NO,       "Teaching artist status"],
    ["got_job_or_opportunity", YES_NO,       "Job/opportunity"],
    ["launched_business",      YES_NO,       "Business launch"],
    ["wants_mentorship",       YES_NO_MAYBE, "Mentorship preference"],
  ];
  const cleaned = {};
  for (const [field, allowed, label] of yesNoFields) {
    const val = (b[field] || "").trim();
    if (!val) { errors.push(`${label} is required.`); continue; }
    if (!allowed.includes(val)) {
      errors.push(`${label} must be one of: ${allowed.join(", ")}.`);
      continue;
    }
    cleaned[field] = val;
  }

  // ── Validate free-text fields ───────────────────────────────
  const industry      = (b.industry      || "").trim().slice(0, 200);
  const skillsSeeking = (b.skills_seeking || "").trim().slice(0, 2000);
  if (!industry)      errors.push("Industry / creative field is required.");
  if (!skillsSeeking) errors.push("Skills you're seeking is required.");

  if (errors.length)
    return res.status(400).json({ error: errors.join(" ") });

  // ── Rate limit: same name cannot submit more than once per hour ─
  const oneHourAgo = new Date(Date.now() - 60 * 60 * 1000).toISOString();
  const { data: existing } = await supabase
    .from("responses")
    .select("id")
    .ilike("name", name)
    .gte("submitted_at", oneHourAgo)
    .limit(1);

  if (existing && existing.length > 0) {
    return res.status(429).json({
      error: "It looks like you've already submitted recently. Please wait an hour before submitting again.",
    });
  }

  // ── Insert ──────────────────────────────────────────────────
  const { error } = await supabase.from("responses").insert([{
    name,
    role,
    industry,
    skills_seeking: skillsSeeking,
    ...cleaned,
  }]);

  if (error) {
    console.error("Supabase insert error:", error.message);
    return res.status(500).json({ error: "Something went wrong. Please try again." });
  }

  console.log("submit: inserted row for", name);
  return res.status(200).json({ success: true });
};
