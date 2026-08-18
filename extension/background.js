/* CareerPilot AI — Copyright (c) 2026 Santosh Reddy Mamindla.
   Proprietary and confidential. See LICENSE. */
/* Service worker. Talks to the CareerPilot API and holds the session token.
   Never stores your password — only the JWT the site already issued. */

const DEFAULT_API = "https://api.careerpilot.ai";

async function apiBase() {
  const { apiBase } = await chrome.storage.local.get("apiBase");
  return apiBase || DEFAULT_API;
}

async function token() {
  const { token } = await chrome.storage.local.get("token");
  return token || null;
}

async function getProfile() {
  const base = await apiBase(), t = await token();
  const r = await fetch(`${base}/api/profile`, {
    headers: t ? { Authorization: `Bearer ${t}` } : {},
  });
  if (r.status === 401) throw new Error("Not signed in — open CareerPilot and sign in first.");
  if (!r.ok) throw new Error(`API returned ${r.status}`);
  const p = await r.json();

  const [first, ...rest] = (p.name || "").split(" ");
  return {
    first_name: first || "",
    last_name: rest.join(" "),
    full_name: p.name || "",
    email: p.email || "",
    phone: p.phone || "",
    location: p.location || "",
    linkedin: p.linkedin || "",
    github: p.github || "",
    website: p.slug ? `https://careerpilot.ai/u/${p.slug}` : "",
    cover_letter: p.cover_letter || "",
    _meta: { total: p.total_label, positions: (p.positions || []).length },
  };
}

chrome.runtime.onMessage.addListener((msg, sender, reply) => {
  if (msg.type === "ats_detected") {
    chrome.action.setBadgeText({ text: "●", tabId: sender.tab.id });
    chrome.action.setBadgeBackgroundColor({ color: "#4F46E5", tabId: sender.tab.id });
    return;
  }
  if (msg.type === "get_profile") {
    getProfile().then((p) => reply({ ok: true, profile: p }))
                .catch((e) => reply({ ok: false, error: e.message }));
    return true;
  }
});
