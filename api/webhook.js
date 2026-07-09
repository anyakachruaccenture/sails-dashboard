// ============================================================
// /api/webhook.js — Vercel Serverless Function
// ============================================================
// This endpoint receives POST requests from Power Automate
// whenever someone submits the Microsoft Form.
//
// Flow:
//   Power Automate → POST /api/webhook → validate secret → insert into Supabase
//
// Environment variables (set in Vercel dashboard, never in code):
//   SUPABASE_URL             — your project URL, e.g. https://abc.supabase.co
//   SUPABASE_SERVICE_ROLE_KEY — the secret key that bypasses RLS (server-side only)
//   WEBHOOK_SECRET           — a random string you choose; Power Automate sends it
//                              as the x-webhook-secret header to prove it's legit
// ============================================================

const { createClient } = require("@supabase/supabase-js");

// Initialize the Supabase client using the service_role key.
// This key bypasses Row Level Security so we can insert rows.
// NEVER put this key in client-side (browser) code.
const supabase = createClient(
  process.env.SUPABASE_URL,
  process.env.SUPABASE_SERVICE_ROLE_KEY
);

module.exports = async function handler(req, res) {
  // ── Only allow POST ──────────────────────────────────────
  if (req.method !== "POST") {
    return res.status(405).json({ error: "Method not allowed" });
  }

  // ── Validate the shared secret ───────────────────────────
  // Power Automate sends this header. If it's missing or wrong,
  // we reject the request so random internet traffic can't insert rows.
  const incomingSecret = req.headers["x-webhook-secret"];
  if (!incomingSecret || incomingSecret !== process.env.WEBHOOK_SECRET) {
    console.warn("Webhook: bad or missing secret");
    return res.status(401).json({ error: "Unauthorized" });
  }

  // ── Map incoming JSON fields to table columns ─────────────
  // Power Automate sends the form fields as JSON.
  // The keys here must match what you set in the Power Automate HTTP body.
  // See README.md for the exact JSON template to paste into Power Automate.
  const body = req.body || {};

  const row = {
    name:                    (body.name                    || "").trim() || null,
    role:                    (body.role                    || "").trim() || null,
    is_alumni:               (body.is_alumni               || "").trim() || null,
    wants_mentorship:        (body.wants_mentorship        || "").trim() || null,
    industry:                (body.industry                || "").trim() || null,
    skills_seeking:          (body.skills_seeking          || "").trim() || null,
    has_returned:            (body.has_returned            || "").trim() || null,
    became_teaching_artist:  (body.became_teaching_artist  || "").trim() || null,
    got_job_or_opportunity:  (body.got_job_or_opportunity  || "").trim() || null,
    launched_business:       (body.launched_business       || "").trim() || null,
  };

  // ── Insert the row ────────────────────────────────────────
  const { error } = await supabase.from("responses").insert([row]);

  if (error) {
    console.error("Supabase insert error:", error.message);
    return res.status(500).json({ error: error.message });
  }

  // ── Success ───────────────────────────────────────────────
  console.log("Webhook: inserted row for", row.name || "(no name)");
  return res.status(200).json({ success: true });
};
