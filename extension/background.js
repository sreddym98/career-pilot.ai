/* CareerPilot AI — Copyright (c) 2026 Santosh Reddy Mamindla.
   Proprietary and confidential. See LICENSE. */
/* Service worker. Talks to the CareerPilot API and holds the session token.
   Never stores your password — only the JWT the site already issued. */

// PLACEHOLDER: production API origin. Replace with the real deployed API before
// publishing, and keep it in sync with host_permissions in manifest.json.
// Users/devs can override at runtime via popup Settings (chrome.storage.local "apiBase").
const DEFAULT_API_BASE_PLACEHOLDER = "https://api.careerpilot.ai";
// Public site origin, used only to build the user's public profile link.
const SITE_ORIGIN = "https://careerpilot.ai";

async function apiBase() {
  const { apiBase } = await chrome.storage.local.get("apiBase");
  return (apiBase || DEFAULT_API_BASE_PLACEHOLDER).replace(/\/+$/, "");
}

async function token() {
  const { token } = await chrome.storage.local.get("token");
  return token || null;
}

async function getProfile() {
  const base = await apiBase(), t = await token();
  let r;
  try {
    r = await fetch(`${base}/api/profile`, {
      headers: t ? { Authorization: `Bearer ${t}` } : {},
    });
  } catch (e) {
    throw new Error(`Could not reach ${base}. Check the API address in Settings and that you granted access to it.`);
  }
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
    website: p.slug ? `${SITE_ORIGIN}/u/${p.slug}` : "",
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
