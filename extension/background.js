/* CareerPilot AI — Copyright (c) 2026 Santosh Reddy Mamindla.
   Proprietary and confidential. See LICENSE. */
/* Service worker. Talks to the CareerPilot API with the scoped extension key
   the web app hands over ("Connect extension"). That key can only read the
   apply packet, download your tailored resume and report fill status — it is
   not your session and can be disconnected at any time.

   This extension NEVER submits an application. It fills fields and attaches
   files; you click the employer's Submit button yourself. */

// Production API. Override in popup Settings (chrome.storage.local "apiBase");
// keep in sync with host_permissions in manifest.json.
const DEFAULT_API_BASE = "https://careerpilot-api-rri9.onrender.com";
const PENDING_MAX_AGE_MS = 30 * 60 * 1000;

async function apiBase() {
  const { apiBase } = await chrome.storage.local.get("apiBase");
  return (apiBase || DEFAULT_API_BASE).replace(/\/+$/, "");
}

async function authToken() {
  const { extToken, token } = await chrome.storage.local.get(["extToken", "token"]);
  return extToken || token || null;
}

function okBase(raw) {
  try {
    const u = new URL(raw);
    const local = u.hostname === "localhost" || u.hostname === "127.0.0.1";
    if (u.protocol === "https:" || (u.protocol === "http:" && local)) return u.origin;
  } catch (_) {}
  return null;
}

async function api(path, opts = {}) {
  const base = await apiBase(), t = await authToken();
  let r;
  try {
    r = await fetch(base + path, { ...opts, headers: { ...(t ? { Authorization: `Bearer ${t}` } : {}),
                                                       ...(opts.headers || {}) } });
  } catch (e) {
    throw new Error(`Could not reach ${base}. Check the API address in Settings.`);
  }
  if (r.status === 401) throw new Error("Not connected. Open CareerPilot and press Connect extension.");
  if (!r.ok) throw new Error(`API returned ${r.status}`);
  return r;
}

// Only CareerPilot's own pages may connect the extension or hand off an application.
const SITE_ORIGINS = ["https://career-pilot-ai.mamindlasreddy.workers.dev"];
function fromSite(sender) {
  try {
    const o = new URL(sender.url || sender.origin || "").origin;
    const h = new URL(o).hostname;
    return SITE_ORIGINS.includes(o) || h === "localhost" || h === "127.0.0.1";
  } catch (_) { return false; }
}

function b64(buf) {
  const bytes = new Uint8Array(buf); let s = "";
  for (let i = 0; i < bytes.length; i += 0x8000) s += String.fromCharCode.apply(null, bytes.subarray(i, i + 0x8000));
  return btoa(s);
}

async function getProfile() {
  const p = (await (await api("/api/apply-packet")).json()).profile || {};
  return { ...p, cover_letter: "", _meta: {} };
}

/* Does this page belong to the application the user just sent from the web app? */
function samePosting(applyUrl, pageUrl) {
  try {
    const a = new URL(applyUrl), b = new URL(pageUrl);
    const ids = (a.pathname + a.search).match(/[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}|\d{5,}/gi) || [];
    if (ids.length) return ids.some((id) => (b.pathname + b.search).toLowerCase().includes(id.toLowerCase()));
    return a.hostname === b.hostname && b.pathname.startsWith(a.pathname.replace(/\/apply\/?$/, ""));
  } catch (_) { return false; }
}

async function claimPending(pageUrl) {
  const { pending } = await chrome.storage.local.get("pending");
  if (!pending || Date.now() - pending.at > PENDING_MAX_AGE_MS) return { ok: true, packet: null };
  if (!samePosting(pending.applyUrl, pageUrl)) return { ok: true, packet: null };
  const packet = await (await api(`/api/apply-packet?application_id=${encodeURIComponent(pending.applicationId)}`)).json();
  let resume = null;
  if (packet.files && packet.files.resume_pdf) {
    try {
      const r = await api(packet.files.resume_pdf);
      const cd = r.headers.get("content-disposition") || "";
      const name = (cd.match(/filename="?([^";]+)"?/) || [])[1] || "Resume.pdf";
      resume = { name, type: "application/pdf", b64: b64(await r.arrayBuffer()) };
    } catch (e) { resume = { error: e.message }; }
  }
  return { ok: true, packet, resume };
}

chrome.runtime.onMessage.addListener((msg, sender, reply) => {
  const run = (p) => { p.then((v) => reply(v)).catch((e) => reply({ ok: false, error: e.message })); return true; };

  if (msg.type === "ats_detected") {
    if (sender.tab) {
      chrome.action.setBadgeText({ text: "●", tabId: sender.tab.id });
      chrome.action.setBadgeBackgroundColor({ color: "#4F46E5", tabId: sender.tab.id });
    }
    return;
  }
  if (msg.type === "get_profile") return run(getProfile().then((p) => ({ ok: true, profile: p })));

  // From the web app (content/bridge.js, only on CareerPilot's own origins).
  if (msg.type === "connect") return run(!fromSite(sender) && sender.tab ? Promise.resolve({ ok: false, error: "not allowed here" }) : (async () => {
    if (typeof msg.token !== "string" || msg.token.split(".").length !== 3) return { ok: false, error: "bad key" };
    const set = { extToken: msg.token };
    const base = msg.apiBase && okBase(msg.apiBase);
    if (base) set.apiBase = base;
    await chrome.storage.local.set(set);
    return { ok: true };
  })());
  if (msg.type === "status") return run(!fromSite(sender) && sender.tab ? Promise.resolve({ ok: false, error: "not allowed here" }) : (async () => {
    const { extToken } = await chrome.storage.local.get("extToken");
    return { ok: true, connected: !!extToken, apiBase: await apiBase() };
  })());
  if (msg.type === "handoff") return run(!fromSite(sender) && sender.tab ? Promise.resolve({ ok: false, error: "not allowed here" }) : (async () => {
    if (!msg.applicationId || !/^https?:\/\//i.test(msg.applyUrl || "")) return { ok: false, error: "bad handoff" };
    await chrome.storage.local.set({ pending: { applicationId: String(msg.applicationId), applyUrl: msg.applyUrl, at: Date.now() } });
    return { ok: true };
  })());
  if (msg.type === "disconnect") return run(!fromSite(sender) && sender.tab ? Promise.resolve({ ok: false, error: "not allowed here" }) : chrome.storage.local.remove(["extToken", "pending"]).then(() => ({ ok: true })));

  // From the employer's page (content/fill.js).
  if (msg.type === "claim_pending") return run(claimPending(msg.url || (sender.tab && sender.tab.url) || ""));
  if (msg.type === "report") return run((async () => {
    if (!["filled", "applied"].includes(msg.status)) return { ok: false, error: "bad status" };
    await api(`/api/apply/${encodeURIComponent(msg.applicationId)}/report`, {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ status: msg.status, filled: msg.filled ?? null, needs_you: msg.needsYou ?? null }) });
    if (msg.status === "applied") await chrome.storage.local.remove("pending");
    return { ok: true };
  })());
});
