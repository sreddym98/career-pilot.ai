/* CareerPilot AI — Copyright (c) 2026 Santosh Reddy Mamindla.
   Proprietary and confidential. See LICENSE. */
/* Runs only on CareerPilot's own pages.

   Before this, using the extension meant copying a JWT out of the web app by
   hand and pasting it into a settings box — which is both miserable and a good
   way to teach people that pasting credentials into things is normal. Signing
   in on the site is now enough: this reads the session the site already holds
   and hands it to the extension.

   It only ever reads. It never sends the token anywhere except to this
   extension's own service worker, and it runs on no other origin. */
(() => {
  const KEY = "cp_token";

  function readToken() {
    let raw;
    try {
      raw = localStorage.getItem(KEY);
    } catch (_) {
      return null;                      // storage blocked; nothing to report
    }
    if (!raw) return null;
    // The app writes through a wrapper that JSON-encodes, so what is actually
    // on disk is a quoted string: "eyJhbGci...". Sending that verbatim
    // produces `Authorization: Bearer "eyJ..."` and every request 401s.
    try {
      const parsed = JSON.parse(raw);
      return typeof parsed === "string" ? parsed : null;
    } catch (_) {
      return raw;                       // written raw by some older build
    }
  }

  let lastSent;

  function report() {
    const token = readToken();
    const payload = token || "";
    if (payload === lastSent) return;   // don't wake the worker for no change
    lastSent = payload;
    try {
      chrome.runtime.sendMessage({
        type: "session_token",
        token: payload,
        origin: location.origin,
      });
    } catch (_) {
      // Extension reloaded or updated out from under this page. The next
      // report picks it up; nothing here is worth surfacing to the user.
      lastSent = undefined;
    }
  }

  report();

  // `storage` only fires for *other* tabs, so signing in on this one has to be
  // noticed another way. Both of these are cheap and cover the real cases:
  // switching back to the tab after signing in, and signing out elsewhere.
  window.addEventListener("storage", (e) => { if (!e.key || e.key === KEY) report(); });
  document.addEventListener("visibilitychange", () => { if (!document.hidden) report(); });
  window.addEventListener("focus", report);
  setInterval(report, 10000);
})();
