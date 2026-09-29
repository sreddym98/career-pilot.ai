/* CareerPilot AI — Copyright (c) 2026 Santosh Reddy Mamindla.
   Proprietary and confidential. See LICENSE. */
/* Fills the form. NEVER submits: nothing in this file clicks a submit button
   or calls form.submit()/requestSubmit(). The only clicks are on radio and
   checkbox inputs (safeCheck), which cannot submit a form. You review the
   page and click the employer's own Submit button yourself.

   Two ways in:
   1. You pressed "Send to employer" on CareerPilot's Apply page. The page
      handed this application to the extension, so on arrival we fetch the
      answers you reviewed there, fill every field we can match, attach your
      tailored resume, and show what still needs you.
   2. The popup's "Fill this form": profile basics only (name, email, ...).
   Field naming differs wildly between ATS vendors, so we match on name, id,
   label text and (for Workday) data-automation-id. */

const FIELDS = {
  first_name:  [/^first[\s_-]?name/i, /given[\s_-]?name/i, /legalNameSection_firstName/],
  last_name:   [/^last[\s_-]?name/i, /family[\s_-]?name/i, /surname/i, /legalNameSection_lastName/],
  full_name:   [/^(full[\s_-]?)?name$/i, /candidate[\s_-]?name/i],
  email:       [/e-?mail/i, /^email/i],
  phone:       [/phone/i, /mobile/i, /telephone/i, /contact[\s_-]?number/i],
  location:    [/^(current[\s_-]?)?(city|location)/i, /address[\s_-]?line/i],
  linkedin:    [/linked[\s_-]?in/i],
  github:      [/git[\s_-]?hub/i],
  website:     [/website/i, /portfolio/i, /personal[\s_-]?site/i],
  cover_letter:[/cover[\s_-]?letter/i, /why.*(interested|join|apply)/i, /tell us about/i],
};

/* In profile-only mode these are left for the human. (On the Apply page you
   reviewed your sponsorship and authorization answers yourself, so a handed-
   off application does fill those — from YOUR saved answers.) */
const NEVER_TOUCH = {
  salary:      [/salary/i, /compensation/i, /desired[\s_-]?(pay|rate)/i, /expected[\s_-]?(pay|ctc)/i, /rate[\s_-]?expect/i],
  sponsorship: [/sponsor/i, /visa/i, /work[\s_-]?authoriz/i, /require.*(visa|sponsor)/i, /legally[\s_-]?authorized/i],
  demographic: [/gender/i, /race/i, /ethnic/i, /veteran/i, /disability/i, /hispanic/i],
  start_date:  [/start[\s_-]?date/i, /available.*(from|date)/i, /notice[\s_-]?period/i],
};

const cssEsc = (s) => { try { return CSS.escape(s); } catch (_) { return String(s).replace(/["\\\]\[]/g, "\\$&"); } };
const norm = (s) => String(s || "").replace(/\*/g, "").replace(/\s+/g, " ").replace(/[:?]\s*$/, "").trim().toLowerCase();

/* Returns the candidate strings that might identify this field, most
   specific first. Each is tested separately — joining them into one blob
   breaks anchored patterns like /^first name/ when an opaque id ("f1")
   happens to sort ahead of the real label. */
const labelBits = (el) => {
  const bits = [];
  const push = (v) => { if (v && String(v).trim()) bits.push(String(v).trim()); };

  push(el.getAttribute("data-automation-id"));   // Workday
  push(el.name);
  push(el.id);
  push(el.placeholder);
  push(el.getAttribute("aria-label"));
  for (const t of labelTexts(el)) push(t);

  const wrap = el.closest(".field, .form-group, [class*='field']");
  if (wrap) push((wrap.textContent || "").slice(0, 120));

  return bits;
};

/* The visible label(s) of a control: <label for>, a wrapping <label>,
   aria-labelledby, or the <legend> of its fieldset (radio groups). */
function labelTexts(el) {
  const out = [];
  if (el.id) {
    const l = document.querySelector(`label[for="${cssEsc(el.id)}"]`);
    if (l) out.push(l.textContent);
  }
  const wrap = el.closest("label");
  if (wrap) out.push(wrap.textContent);
  const lb = el.getAttribute("aria-labelledby");
  if (lb) lb.split(/\s+/).forEach((id) => { const n = document.getElementById(id); if (n) out.push(n.textContent); });
  const fs = el.closest("fieldset");
  if (fs) { const lg = fs.querySelector("legend"); if (lg) out.push(lg.textContent); }
  return out.map((t) => t.trim()).filter(Boolean);
}

const matches = (bits, pats) => bits.some((b) => pats.some((p) => p.test(b)));

function setValue(el, val) {
  // React and Angular ignore plain .value assignment — go through the
  // native setter and fire the events the framework is listening for.
  const proto = el instanceof HTMLTextAreaElement ? HTMLTextAreaElement.prototype
    : el instanceof HTMLSelectElement ? HTMLSelectElement.prototype : HTMLInputElement.prototype;
  const setter = Object.getOwnPropertyDescriptor(proto, "value").set;
  setter.call(el, val);
  el.dispatchEvent(new Event("input",  { bubbles: true }));
  el.dispatchEvent(new Event("change", { bubbles: true }));
  el.dispatchEvent(new Event("blur",   { bubbles: true }));
}

/* Radios and checkboxes only. Refuses anything that could submit. */
function safeCheck(el, on = true) {
  if (!(el instanceof HTMLInputElement) || !["radio", "checkbox"].includes(el.type)) return false;
  if (el.checked === on) return true;
  el.click();                                   // frameworks listen for click on these
  if (el.checked !== on) { el.checked = on; el.dispatchEvent(new Event("change", { bubbles: true })); }
  return el.checked === on;
}

function groupLabel(el) {
  const fs = el.closest("fieldset");
  const lg = fs && fs.querySelector("legend");
  if (lg && lg.textContent.trim()) return lg.textContent.trim();
  const rg = el.closest("[role=radiogroup],[role=group]");
  const lb = rg && rg.getAttribute("aria-labelledby");
  const n = lb && document.getElementById(lb.split(/\s+/)[0]);
  return n ? n.textContent.trim() : "";
}

const cleanLabel = (t) => String(t || "").replace(/[\s*✱]+$/u, "").trim();

function flag(el, reason) {
  el.classList.add("cp-flagged");
  if ((el.type === "radio" || el.type === "checkbox") && el.closest("fieldset")) {
    const fs = el.closest("fieldset");                 // one note per group, not inside an option's label
    if (!fs.querySelector(".cp-flag-note")) {
      const n = document.createElement("div");
      n.className = "cp-flag-note"; n.textContent = reason; fs.appendChild(n);
    }
    return;
  }
  if (el.parentElement && !el.parentElement.querySelector(".cp-flag-note")) {
    const n = document.createElement("div");
    n.className = "cp-flag-note";
    n.textContent = reason;
    el.parentElement.appendChild(n);
  }
}

const visible = (el) => el.offsetParent !== null || el.type === "file" || el.getClientRects().length > 0;
const controls = () => [...document.querySelectorAll("input, textarea, select")]
  .filter((el) => !el.disabled && !["hidden", "submit", "button", "image", "reset"].includes(el.type));

function fillForm(profile) {
  const inputs = controls().filter((el) => el.tagName !== "SELECT" && el.type !== "file" && visible(el)
                                           && !el.dataset.cpFilled);
  const out = { filled: [], flagged: [], skipped: 0 };

  for (const el of inputs) {
    const bits = labelBits(el);
    if (!bits.length) { out.skipped++; continue; }

    let held = null;
    for (const [k, pats] of Object.entries(NEVER_TOUCH)) {
      if (matches(bits, pats)) { held = k; break; }
    }
    if (held) {
      const why = {
        salary: "You decide this number — not the agent",
        sponsorship: "Answer this yourself; getting it wrong costs the application",
        demographic: "Voluntary — your choice, left blank",
        start_date: "Depends on your notice period",
      }[held];
      flag(el, why);
      out.flagged.push({ field: bits[0].slice(0, 60), reason: held });
      continue;
    }

    let done = false;
    for (const [key, pats] of Object.entries(FIELDS)) {
      if (matches(bits, pats) && profile[key]) {
        if (el.value && el.value.trim()) { done = true; break; }  // don't overwrite
        setValue(el, profile[key]);
        el.classList.add("cp-filled");
        el.dataset.cpFilled = "1";
        out.filled.push(key);
        done = true;
        break;
      }
    }
    if (!done) out.skipped++;
  }
  return out;
}

/* ── handed-off application: fill from the reviewed answers ─────────── */

function findControls(ans) {
  const id = String(ans.id || "");
  const all = controls();
  let hit = [];
  if (id) {
    hit = all.filter((el) => el.id === id || el.name === id || (el.name || "").endsWith(`[${id}]`)
                             || el.getAttribute("data-qa") === id);
    if (!hit.length && /^question_\d+$/.test(id)) {
      const num = id.split("_")[1];                          // classic Greenhouse: answers_attributes + question_id
      const qid = document.querySelector(`input[type=hidden][value="${num}"][name*="question_id"]`);
      if (qid) {
        const prefix = qid.name.replace(/\[question_id\]$/, "");
        hit = all.filter((el) => (el.name || "").startsWith(prefix));
      }
    }
  }
  if (!hit.length && ans.label) {
    const want = norm(ans.label);
    hit = all.filter((el) => labelTexts(el).some((t) => {
      const got = norm(t);
      return got === want || (want.length >= 8 && (got.startsWith(want) || want.startsWith(got) && got.length >= 8));
    }));
  }
  // A radio group: every radio sharing the first hit's name.
  if (hit.length === 1 && hit[0].type === "radio" && hit[0].name) {
    hit = all.filter((el) => el.type === "radio" && el.name === hit[0].name);
  }
  return hit;
}

function optionLabel(el) {
  const t = labelTexts(el); return t.length ? t[0] : el.value;
}

function b64ToFile(f) {
  const bin = atob(f.b64); const bytes = new Uint8Array(bin.length);
  for (let i = 0; i < bin.length; i++) bytes[i] = bin.charCodeAt(i);
  return new File([bytes], f.name, { type: f.type });
}

function attach(input, file) {
  const dt = new DataTransfer();
  dt.items.add(file);
  input.files = dt.files;
  input.dispatchEvent(new Event("input", { bubbles: true }));
  input.dispatchEvent(new Event("change", { bubbles: true }));
  return input.files.length === 1;
}

function isRequired(el, ans) {
  if (ans && ans.required) return true;
  if (el.required || el.getAttribute("aria-required") === "true") return true;
  return labelTexts(el).some((t) => /\*\s*$|\(required\)/i.test(t));
}

function fillPacket(packet, files) {
  const done = new Set(), filled = [], needs = [], problems = [];
  const mark = (el) => { el.classList.add("cp-filled"); el.dataset.cpFilled = "1"; done.add(el); };
  const letterFile = packet.cover_letter
    ? new File([packet.cover_letter], "Cover_Letter.txt", { type: "text/plain" }) : null;

  for (const ans of packet.answers || []) {
    const els = findControls(ans).filter((el) => !done.has(el));
    const val = String(ans.value || "");
    if (!els.length) { if (!ans.eeo && (ans.required || val)) needs.push({ label: ans.label, el: null, missing: true }); continue; }
    const el = els[0];
    const kind = el.tagName === "SELECT" ? "select" : el.tagName === "TEXTAREA" ? "textarea" : el.type;
    let ok = false;

    if (kind === "file") {
      const isLetter = /cover/i.test(ans.id + " " + ans.label);
      const file = isLetter ? letterFile : (files.resume && !files.resume.error ? b64ToFile(files.resume) : null);
      if (file && !(el.files && el.files.length)) ok = attach(el, file);
      else if (el.files && el.files.length) ok = true;
      if (!file && !isLetter && files.resume && files.resume.error) problems.push("Couldn't download your resume: " + files.resume.error);
      if (ok) {
        mark(el);
        // The "or paste it" textarea next to Greenhouse file fields stays empty.
        filled.push(isLetter ? "Cover letter (attached)" : `Resume (${el.files[0].name})`);
      }
    } else if (!val) {
      ok = false;
    } else if (kind === "select") {
      const want = norm(val);
      const opt = [...el.options].find((o) => norm(o.textContent) === want || norm(o.value) === want)
               || [...el.options].find((o) => want.length > 1 && norm(o.textContent).startsWith(want));
      if (opt) { setValue(el, opt.value); ok = el.value === opt.value; }
    } else if (kind === "radio" || kind === "checkbox") {
      const wants = kind === "checkbox" && els.length > 1 ? val.split(/\s*[;,]\s*/).map(norm) : [norm(val)];
      for (const r of els) {
        const lab = norm(optionLabel(r));
        if (wants.includes(lab) || wants.includes(norm(r.value))) ok = safeCheck(r, true) || ok;
      }
      if (els.length === 1 && kind === "checkbox" && /^(yes|true)$/i.test(val)) ok = safeCheck(el, true);
    } else {
      if (el.value && el.value.trim()) ok = true;                        // never overwrite what's there
      else { setValue(el, val); ok = el.value === val; }
    }
    if (ok) { els.forEach(mark); if (kind !== "file") filled.push(ans.label); }
    else if (!ans.eeo || isRequired(el, ans)) needs.push({ label: ans.label, el });
  }

  // Cover letter as text when there's a box for it but no file field matched above.
  if (packet.cover_letter) {
    for (const el of controls().filter((x) => x.tagName === "TEXTAREA" && !done.has(x) && !x.value.trim())) {
      if (labelTexts(el).some((t) => /cover[\s_-]?letter/i.test(t)) || /cover_letter_text/.test(el.name || el.id)) {
        const fileTaken = [...done].some((d) => d.type === "file" && /cover/i.test(d.name + d.id));
        if (!fileTaken) { setValue(el, packet.cover_letter); mark(el); filled.push("Cover letter"); }
      }
    }
  }
  // Profile basics for anything the employer's form has that wasn't in the list.
  const extra = fillForm(packet.profile || {});
  filled.push(...extra.filled.map((k) => k.replace(/_/g, " ")));

  // Required fields still empty, wherever they came from.
  for (const el of controls()) {
    if (done.has(el) || el.dataset.cpFilled || !visible(el)) continue;
    const empty = el.type === "file" ? !(el.files && el.files.length)
      : (el.type === "radio" || el.type === "checkbox")
        ? !controls().some((x) => x.name === el.name && x.checked) : !String(el.value || "").trim();
    if (empty && isRequired(el) && !needs.some((n) => n.el === el || (n.el && el.type === "radio" && n.el.name === el.name))) {
      const group = (el.type === "radio" || el.type === "checkbox") ? groupLabel(el) : "";
      const lab = cleanLabel(group || labelTexts(el)[0] || el.name || el.id || "A required field");
      if ((el.type === "radio" || el.type === "checkbox") && needs.some((n) => n.label === lab)) continue;
      needs.push({ label: lab, el });
    }
  }
  for (const n of needs) if (n.el) n.el.classList.add("cp-needs");
  return { filled: [...new Set(filled)], needs, problems };
}

/* ── overlay ─────────────────────────────────────────────────────────── */

function overlay(packet, res) {
  const old = document.getElementById("cp-overlay"); if (old) old.remove();
  const host = document.createElement("div");
  host.id = "cp-overlay";
  const root = host.attachShadow({ mode: "open" });
  const esc = (s) => String(s || "").replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
  root.innerHTML = `<style>
    .box{position:fixed;right:16px;bottom:16px;z-index:2147483647;width:340px;max-width:calc(100vw - 32px);max-height:70vh;overflow:auto;
      background:#fff;color:#1B1F2A;border:1px solid #C9CEDA;border-radius:12px;box-shadow:0 12px 40px rgba(0,0,0,.18);
      font:13px/1.45 -apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;padding:14px 16px}
    h3{margin:0 0 4px;font-size:14px} .sub{color:#4A5163;margin:0 0 10px}
    ul{margin:4px 0 10px;padding-left:18px} li{margin:2px 0} .need li{color:#9A3412;cursor:pointer}
    .ok{color:#166534} b.n{color:#9A3412} .warn{background:#FEF3C7;border-radius:6px;padding:6px 8px;margin:6px 0}
    .final{background:#EEF0FE;border-radius:8px;padding:8px 10px;font-weight:600;margin:8px 0}
    .row{display:flex;gap:8px;flex-wrap:wrap} button{font:inherit;border-radius:8px;border:1px solid #C9CEDA;background:#fff;padding:6px 10px;cursor:pointer}
    button.p{background:#4F46E5;color:#fff;border-color:#4F46E5}</style>
    <div class="box" role="dialog" aria-label="CareerPilot fill summary">
      <h3>CareerPilot filled ${res.filled.length} field${res.filled.length === 1 ? "" : "s"}</h3>
      <p class="sub">${esc(packet.title)} at ${esc(packet.company)}</p>
      ${res.problems.map((p) => `<div class="warn">${esc(p)}</div>`).join("")}
      ${res.filled.length ? `<div class="ok"><b>Filled</b></div><ul class="filled">${res.filled.map((f) => `<li>${esc(f)}</li>`).join("")}</ul>` : ""}
      ${res.needs.length ? `<b class="n">Needs you (${res.needs.length})</b><ul class="need">${res.needs.map((n, i) => `<li data-i="${i}">${esc(n.label)}${n.missing ? " (not found on this page)" : ""}</li>`).join("")}</ul>` : ""}
      <div class="final">Review everything, then click Submit on this page. We never submit for you.</div>
      <div class="row"><button class="p" id="cp-done">I submitted it</button><button id="cp-hide">Hide</button></div>
      <div class="sub" id="cp-msg" style="margin-top:8px"></div>
    </div>`;
  root.querySelectorAll(".need li").forEach((li) => li.addEventListener("click", () => {
    const n = res.needs[+li.dataset.i]; if (n && n.el) { n.el.scrollIntoView({ block: "center" }); try { n.el.focus(); } catch (_) {} }
  }));
  root.getElementById("cp-hide").addEventListener("click", () => host.remove());
  root.getElementById("cp-done").addEventListener("click", () => {
    // Only ever sent because YOU pressed this button after submitting.
    chrome.runtime.sendMessage({ type: "report", status: "applied", applicationId: packet.application_id }, (r) => {
      root.getElementById("cp-msg").textContent = r && r.ok ? "Marked as applied in CareerPilot." : "Couldn't reach CareerPilot — mark it in the web app.";
    });
  });
  document.documentElement.appendChild(host);
  return host;
}

/* ── wiring ──────────────────────────────────────────────────────────── */

let HANDLED = false;
async function tryHandoff(attempt = 0) {
  if (HANDLED || !window.__CP || !window.__CP.ats) return;
  const hasForm = controls().some((el) => el.type === "email" || /email|first/i.test(el.name + el.id) || el.type === "file");
  if (!hasForm) { if (attempt < 20) setTimeout(() => tryHandoff(attempt + 1), 500); return; }   // SPA forms render late
  let r;
  try { r = await chrome.runtime.sendMessage({ type: "claim_pending", url: location.href }); } catch (_) { return; }
  if (!r || !r.ok || !r.packet || !r.packet.application_id) {
    if (attempt < 6) setTimeout(() => tryHandoff(attempt + 1), 700);  // the handoff may land a moment after the tab opened
    return;
  }
  HANDLED = true;
  const res = fillPacket(r.packet, { resume: r.resume });
  window.__CP.lastFill = { filled: res.filled, needs: res.needs.map((n) => n.label), problems: res.problems };
  overlay(r.packet, res);
  chrome.runtime.sendMessage({ type: "report", status: "filled", applicationId: r.packet.application_id,
                               filled: res.filled.length, needsYou: res.needs.length }, () => void chrome.runtime.lastError);
}

chrome.runtime.onMessage.addListener((msg, _s, reply) => {
  if (msg.type === "fill") {
    try { reply({ ok: true, result: fillForm(msg.profile) }); }
    catch (e) { reply({ ok: false, error: e.message }); }
    return true;
  }
  if (msg.type === "probe") {
    reply({ ats: window.__CP?.ats || null, isForm: window.__CP?.isForm || false });
    return true;
  }
});

tryHandoff();
