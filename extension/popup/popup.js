/* CareerPilot AI — Copyright (c) 2026 Santosh Reddy Mamindla.
   Proprietary and confidential. See LICENSE. */
const $ = (id) => document.getElementById(id);
const ATS_NAME = { workday:"Workday", greenhouse:"Greenhouse", lever:"Lever",
                   ashby:"Ashby", icims:"iCIMS", smartrecruiters:"SmartRecruiters" };
let PROFILE = null;

async function activeTab() {
  const [t] = await chrome.tabs.query({ active: true, currentWindow: true });
  return t;
}

async function init() {
  const { apiBase, token } = await chrome.storage.local.get(["apiBase","token"]);
  $("apiBase").value = apiBase || "";
  $("token").value = token || "";

  const tab = await activeTab();
  let probe = null;
  try { probe = await chrome.tabs.sendMessage(tab.id, { type: "probe" }); } catch (_) {}

  if (!probe || !probe.ats) {
    $("ats").textContent = "no application form here";
    $("state").innerHTML = `<span class="pill warn">IDLE</span>Open a job application on Workday, Greenhouse, Lever, Ashby, iCIMS, or SmartRecruiters.`;
    return;
  }

  $("ats").textContent = ATS_NAME[probe.ats] + " detected";

  const res = await chrome.runtime.sendMessage({ type: "get_profile" });
  if (!res.ok) {
    $("state").innerHTML = `<span class="pill bad">NOT SIGNED IN</span>${res.error}`;
    return;
  }
  PROFILE = res.profile;
  $("state").innerHTML =
    `<span class="pill ok">READY</span>Profile loaded — ${PROFILE._meta.total}, ${PROFILE._meta.positions} roles.`;
  $("fill").disabled = false;
}

$("fill").onclick = async () => {
  const tab = await activeTab();
  $("fill").disabled = true;
  $("fill").textContent = "Filling…";
  const r = await chrome.tabs.sendMessage(tab.id, { type: "fill", profile: PROFILE });
  $("fill").textContent = "Fill this form";
  $("fill").disabled = false;

  if (!r || !r.ok) {
    $("result").innerHTML = `<span class="pill bad">FAILED</span>${r?.error || "no response"}`;
    return;
  }
  const { filled, flagged } = r.result;
  $("result").innerHTML =
    `<b>${filled.length} field${filled.length === 1 ? "" : "s"} filled</b>` +
    (filled.length ? `<ul>${filled.map((f) => `<li>✓ ${f.replace(/_/g," ")}</li>`).join("")}</ul>` : "") +
    (flagged.length
      ? `<div style="margin-top:10px"><b style="color:#D97706">${flagged.length} left for you</b>
         <ul>${flagged.map((f) => `<li>⚠ ${f.reason.replace(/_/g," ")}</li>`).join("")}</ul>
         <div style="font-size:11px;color:#7B8496;margin-top:6px">These are highlighted in amber on the page.</div></div>`
      : "");
};

$("settings").onclick = (e) => { e.preventDefault(); $("panel").hidden = !$("panel").hidden; };
$("save").onclick = async () => {
  const err = $("apiErr"); err.hidden = true;
  const raw = $("apiBase").value.trim().replace(/\/+$/, "");
  const token = $("token").value.trim();
  if (raw) {
    let u;
    try { u = new URL(raw); } catch (_) { err.textContent = "Enter a full address, e.g. https://api.example.com"; err.hidden = false; return; }
    const local = u.hostname === "localhost" || u.hostname === "127.0.0.1";
    if (!(u.protocol === "https:" || (u.protocol === "http:" && local))) {
      err.textContent = "Use https:// (http:// is only allowed for localhost)."; err.hidden = false; return;
    }
    // permissions.request needs the click's user gesture; do it before any slow work.
    const origins = [u.origin + "/*"];
    try {
      const has = await chrome.permissions.contains({ origins });
      const ok = has || await chrome.permissions.request({ origins });
      if (!ok) { err.textContent = "Permission to contact that address was declined, so it was not saved."; err.hidden = false; return; }
    } catch (e) { err.textContent = "Could not request permission: " + e.message; err.hidden = false; return; }
    await chrome.storage.local.set({ apiBase: u.origin, token });
  } else {
    await chrome.storage.local.remove("apiBase");
    await chrome.storage.local.set({ token });
  }
  $("panel").hidden = true;
  init();
};

init();
