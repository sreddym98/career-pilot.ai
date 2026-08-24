/* CareerPilot AI — Copyright (c) 2026 Santosh Reddy Mamindla.
   Proprietary and confidential. See LICENSE. */
/* Service worker. Talks to the CareerPilot API and holds the session token.
   Never stores your password — only the JWT the site already issued. */

const PROD_API = "https://api.careerpilot.ai";
const DEV_API = "http://localhost:8000";

async function apiBase() {
  const { apiBase, tokenOrigin } = await chrome.storage.local.get(["apiBase", "tokenOrigin"]);
  if (apiBase) return apiBase;                        // explicit setting wins
  // Otherwise infer it from wherever the session came from, so running the
  // whole stack locally needs no configuration at all.
  if (tokenOrigin && tokenOrigin.startsWith("http://localhost")) return DEV_API;
  return PROD_API;
}

async function token() {
  const { token } = await chrome.storage.local.get("token");
  return token || null;
}

const NOT_SIGNED_IN = "Not signed in — open CareerPilot and sign in first.";

async function api(path) {
  const base = await apiBase(), t = await token();
  if (!t) throw new Error(NOT_SIGNED_IN);

  let r;
  try {
    r = await fetch(`${base}${path}`, { headers: { Authorization: `Bearer ${t}` } });
  } catch (_) {
    throw new Error(`Can't reach CareerPilot at ${base}.`);
  }

  if (r.status === 401) throw new Error("Your session expired — sign in again on CareerPilot.");
  if (r.status === 403) {
    // Seeker and recruiter are separate accounts, and autofill belongs to the
    // seeker side. Say which it is rather than showing a bare 403.
    throw new Error("This is a job-seeker feature, and you're signed in as a recruiter.");
  }
  if (!r.ok) throw new Error(`CareerPilot returned ${r.status}`);
  return r.json();
}

async function getSession() {
  const { user } = await api("/api/auth/session");
  return user;
}

async function getProfile() {
  const p = await api("/api/profile");

  const [first, ...rest] = (p.name || "").split(" ");
  return {
    first_name: first || "",
    last_name: rest.join(" "),
    full_name: p.name || "",
    email: p.email || "",
    phone: p.phone || "",
    location: p.location || "",
    linkedin: p.linkedin || "",
    website: p.slug ? `https://careerpilot.ai/u/${p.slug}` : "",
    _meta: {
      total: p.total_label,
      positions: (p.positions || []).length,
      email: p.email || "",
    },
  };
}

chrome.runtime.onMessage.addListener((msg, sender, reply) => {
  if (msg.type === "ats_detected") {
    chrome.action.setBadgeText({ text: "●", tabId: sender.tab.id });
    chrome.action.setBadgeBackgroundColor({ color: "#4C6B4F", tabId: sender.tab.id });
    return;
  }

  if (msg.type === "session_token") {
    // Sent by content/session.js from CareerPilot's own pages only. An empty
    // token means signed out there, which should sign the extension out too
    // rather than leaving a stale session behind.
    chrome.storage.local.set({ token: msg.token || "", tokenOrigin: msg.origin || "" });
    return;
  }

  if (msg.type === "get_profile") {
    getProfile().then((p) => reply({ ok: true, profile: p }))
                .catch((e) => reply({ ok: false, error: e.message }));
    return true;
  }

  if (msg.type === "get_session") {
    getSession().then((u) => reply({ ok: true, user: u }))
                .catch((e) => reply({ ok: false, error: e.message }));
    return true;
  }
});
