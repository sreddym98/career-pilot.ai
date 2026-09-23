/* CareerPilot AI — Copyright (c) 2026 Santosh Reddy Mamindla.
   Proprietary and confidential. See LICENSE. */
const $ = (id) => document.getElementById(id);
const ATS_NAME = { workday:"Workday", greenhouse:"Greenhouse", lever:"Lever",
                   ashby:"Ashby", icims:"iCIMS", smartrecruiters:"SmartRecruiters" };
const esc = (s) => String(s == null ? "" : s)
  .replace(/[<>&"]/g, (c) => ({ "<":"&lt;", ">":"&gt;", "&":"&amp;", '"':"&quot;" }[c]));

let PROFILE = null;

async function activeTab() {
  const [t] = await chrome.tabs.query({ active: true, currentWindow: true });
  return t;
}

const SIGN_IN_HINT =
  `<span class="pill bad">NOT SIGNED IN</span>Open
   <a href="https://careerpilot.ai" target="_blank">careerpilot.ai</a> and sign
   in. This picks up the session on its own — nothing to copy across.`;

async function init() {
  const { apiBase } = await chrome.storage.local.get("apiBase");
  $("apiBase").value = apiBase || "";

  // Who is connected, independent of what page we're on. Worth showing even
  // when the tab isn't an application form, because "why is it not working"
  // is nearly always "signed in as the wrong account" or "not signed in".
  const who = await chrome.runtime.sendMessage({ type: "get_session" });
  if (who.ok) {
    const u = who.user;
    $("who").innerHTML = `<div class="who">Signed in as <b>${esc(u.email)}</b>` +
      (u.account_type === "recruiter" ? ` <span class="pill warn">RECRUITER</span>` : "") +
      `</div>`;
    if (u.account_type === "recruiter") {
      $("state").innerHTML = `<span class="pill bad">WRONG ACCOUNT</span>
        Autofill fills <i>your</i> application from <i>your</i> profile, so it
        only works on a job-seeker account.`;
      return;
    }
  } else {
    $("who").innerHTML = "";
    $("state").innerHTML = /signed in/i.test(who.error)
      ? SIGN_IN_HINT
      : `<span class="pill bad">PROBLEM</span>${esc(who.error)}`;
    return;
  }

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
    $("state").innerHTML = `<span class="pill bad">CAN'T LOAD PROFILE</span>${esc(res.error)}`;
    return;
  }
  PROFILE = res.profile;

  if (!PROFILE._meta.positions) {
    $("state").innerHTML = `<span class="pill warn">PROFILE EMPTY</span>
      Add your experience on CareerPilot first — there's nothing to fill from yet.`;
    return;
  }

  $("state").innerHTML =
    `<span class="pill ok">READY</span>Profile loaded — ${esc(PROFILE._meta.total)}, ${PROFILE._meta.positions} roles.`;
  $("fill").disabled = false;
}

$("fill").onclick = async () => {
  const tab = await activeTab();
  $("fill").disabled = true;
  $("fill").textContent = "Filling…";
  let r = null;
  try { r = await chrome.tabs.sendMessage(tab.id, { type: "fill", profile: PROFILE }); }
  catch (e) { r = { ok: false, error: "The page reloaded — try again." }; }
  $("fill").textContent = "Fill this form";
  $("fill").disabled = false;

  if (!r || !r.ok) {
    $("result").innerHTML = `<span class="pill bad">FAILED</span>${esc(r?.error || "no response")}`;
    return;
  }
  const { filled, flagged } = r.result;
  $("result").innerHTML =
    `<b>${filled.length} field${filled.length === 1 ? "" : "s"} filled</b>` +
    (filled.length ? `<ul>${filled.map((f) => `<li>✓ ${esc(f.replace(/_/g," "))}</li>`).join("")}</ul>` : "") +
    (flagged.length
      ? `<div style="margin-top:10px"><b style="color:#D97706">${flagged.length} left for you</b>
         <ul>${flagged.map((f) => `<li>⚠ ${esc(f.reason.replace(/_/g," "))}</li>`).join("")}</ul>
         <div style="font-size:11px;color:#7B8496;margin-top:6px">These are highlighted in amber on the page.</div></div>`
      : "");
};

$("settings").onclick = (e) => { e.preventDefault(); $("panel").hidden = !$("panel").hidden; };
$("save").onclick = async () => {
  await chrome.storage.local.set({ apiBase: $("apiBase").value.trim() });
  $("panel").hidden = true;
  $("result").innerHTML = "";
  init();
};

init();
