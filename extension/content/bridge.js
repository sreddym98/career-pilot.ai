/* CareerPilot AI — Copyright (c) 2026 Santosh Reddy Mamindla.
   Proprietary and confidential. See LICENSE. */
/* Runs only on CareerPilot's own site. Lets the web app (a) see that the
   extension is installed, (b) hand it the scoped extension key ("Connect
   extension"), and (c) hand off an application the user is about to open on
   the employer's site. Messages from any other window or origin are ignored. */
(() => {
  const VERSION = chrome.runtime.getManifest().version;
  const say = (type, extra = {}) =>
    window.postMessage({ source: "careerpilot-ext", type, version: VERSION, ...extra }, location.origin);
  const ask = (msg) => new Promise((res) => {
    try { chrome.runtime.sendMessage(msg, (r) => res(r || { ok: false, error: chrome.runtime.lastError?.message })); }
    catch (e) { res({ ok: false, error: e.message }); }
  });

  window.addEventListener("message", async (e) => {
    if (e.source !== window || e.origin !== location.origin) return;
    const m = e.data;
    if (!m || m.source !== "careerpilot-web" || typeof m.type !== "string") return;
    if (m.type === "cp_ping") {
      const st = await ask({ type: "status" });
      say("cp_pong", { connected: !!st.connected, id: m.id });
    } else if (m.type === "cp_connect") {
      const r = await ask({ type: "connect", token: m.token, apiBase: m.apiBase });
      say("cp_connected", { ok: !!r.ok, error: r.error || null, id: m.id });
    } else if (m.type === "cp_handoff") {
      const r = await ask({ type: "handoff", applicationId: m.applicationId, applyUrl: m.applyUrl });
      say("cp_handoff_ok", { ok: !!r.ok, error: r.error || null, id: m.id });
    } else if (m.type === "cp_disconnect") {
      const r = await ask({ type: "disconnect" });
      say("cp_disconnected", { ok: !!r.ok, id: m.id });
    }
  });
  document.documentElement.setAttribute("data-careerpilot-ext", VERSION);
  say("cp_hello");
})();
