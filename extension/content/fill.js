/* CareerPilot AI — Copyright (c) 2026 Santosh Reddy Mamindla.
   Proprietary and confidential. See LICENSE. */
/* Fills the form. Never submits — see NEVER_TOUCH below.
   Field naming differs wildly between ATS vendors, so we match on a
   combination of name, id, label text, and (for Workday) data-automation-id. */

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

/* Anything here is left for the human. An agent that guesses your salary
   or your visa answer is worse than no agent. */
const NEVER_TOUCH = {
  salary:      [/salary/i, /compensation/i, /desired[\s_-]?(pay|rate)/i, /expected[\s_-]?(pay|ctc)/i, /rate[\s_-]?expect/i],
  sponsorship: [/sponsor/i, /visa/i, /work[\s_-]?authoriz/i, /require.*(visa|sponsor)/i, /legally[\s_-]?authorized/i],
  demographic: [/gender/i, /race/i, /ethnic/i, /veteran/i, /disability/i, /hispanic/i],
  start_date:  [/start[\s_-]?date/i, /available.*(from|date)/i, /notice[\s_-]?period/i],
};

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

  if (el.id) {
    let esc = el.id;
    try { esc = CSS.escape(el.id); } catch (_) {}
    const l = document.querySelector(`label[for="${esc}"]`);
    if (l) push(l.textContent);
  }
  const wrapLabel = el.closest("label");
  if (wrapLabel) push(wrapLabel.textContent);

  const wrap = el.closest(".field, .form-group, [class*='field']");
  if (wrap) push((wrap.textContent || "").slice(0, 120));

  return bits;
};

const matches = (bits, pats) => bits.some((b) => pats.some((p) => p.test(b)));

function setValue(el, val) {
  // React and Angular ignore plain .value assignment — go through the
  // native setter and fire the events the framework is listening for.
  const proto = el instanceof HTMLTextAreaElement
    ? HTMLTextAreaElement.prototype : HTMLInputElement.prototype;
  const setter = Object.getOwnPropertyDescriptor(proto, "value").set;
  setter.call(el, val);
  el.dispatchEvent(new Event("input",  { bubbles: true }));
  el.dispatchEvent(new Event("change", { bubbles: true }));
  el.dispatchEvent(new Event("blur",   { bubbles: true }));
}

function flag(el, reason) {
  el.classList.add("cp-flagged");
  if (el.parentElement && !el.parentElement.querySelector(".cp-flag-note")) {
    const n = document.createElement("div");
    n.className = "cp-flag-note";
    n.textContent = reason;
    el.parentElement.appendChild(n);
  }
}

function fillForm(profile) {
  const inputs = [...document.querySelectorAll("input, textarea")]
    .filter((el) => !el.disabled && el.type !== "hidden" && el.type !== "submit"
                    && el.type !== "button" && el.offsetParent !== null);

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
        out.filled.push(key);
        done = true;
        break;
      }
    }
    if (!done) out.skipped++;
  }
  return out;
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
