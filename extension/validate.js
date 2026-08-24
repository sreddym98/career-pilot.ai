/* CareerPilot AI — Copyright (c) 2026 Santosh Reddy Mamindla.
   Proprietary and confidential. See LICENSE. */
/* Run:  node extension/validate.js
   Needs no browser and no dependencies. Catches the failures that stop
   Chrome loading the extension at all — a missing service worker, a file
   the manifest names but nobody wrote — plus the promises the popup makes
   about never submitting and never touching salary or sponsorship. */
// Validates the extension without a browser: manifest shape, that every file
// it names exists, that each script parses, and that the pieces agree on the
// message types they send each other.
const fs = require("fs"), path = require("path");
const vm = require("vm");
const EXT = __dirname;
let P = 0, F = 0; const fails = [];
const ok = (n, c, x) => { c ? P++ : (F++, fails.push(n + (x ? "  →  " + x : ""))); };

let m;
try { m = JSON.parse(fs.readFileSync(path.join(EXT, "manifest.json"), "utf8")); ok("manifest is valid JSON", true); }
catch (e) { ok("manifest is valid JSON", false, e.message); console.log("PASS 0 FAIL 1"); process.exit(1); }

ok("manifest v3", m.manifest_version === 3, String(m.manifest_version));
ok("named CareerPilot AI", m.name === "CareerPilot AI", m.name);
ok("action title matches the name", m.action.default_title === m.name, m.action.default_title);
ok("has a version", /^\d+\.\d+\.\d+$/.test(m.version), m.version);

// Every referenced file must exist, or Chrome refuses to load the extension.
const refs = [];
(m.content_scripts || []).forEach(cs => (cs.js || []).concat(cs.css || []).forEach(f => refs.push(f)));
if (m.background?.service_worker) refs.push(m.background.service_worker);
if (m.action?.default_popup) refs.push(m.action.default_popup);
Object.values(m.icons || {}).forEach(f => refs.push(f));
const missing = refs.filter(f => !fs.existsSync(path.join(EXT, f)));
ok(`every referenced file exists (${refs.length} checked)`, missing.length === 0, missing.join(", "));

// A service worker is required for the background message handlers.
ok("declares a service worker", !!m.background?.service_worker, JSON.stringify(m.background));

// Scripts must parse.
const scripts = ["background.js", "content/detect.js", "content/fill.js",
                 "content/session.js", "popup/popup.js"];
scripts.forEach(f => {
  const p = path.join(EXT, f);
  if (!fs.existsSync(p)) return ok(`${f} parses`, false, "missing");
  try { new vm.Script(fs.readFileSync(p, "utf8"), { filename: f }); ok(`${f} parses`, true); }
  catch (e) { ok(`${f} parses`, false, e.message); }
});

const read = f => fs.readFileSync(path.join(EXT, f), "utf8");
const bg = read("background.js"), popup = read("popup/popup.js");
const session = read("content/session.js"), fill = read("content/fill.js");

// Message types must line up on both ends, or a click does nothing at all.
const sent = new Set();
[popup, session, read("content/detect.js")].forEach(src =>
  [...src.matchAll(/type:\s*"([a-z_]+)"/g)].forEach(x => sent.add(x[1])));
const handled = new Set([...bg.matchAll(/msg\.type === "([a-z_]+)"/g)].map(x => x[1])
  .concat([...fill.matchAll(/msg\.type === "([a-z_]+)"/g)].map(x => x[1])));
const unhandled = [...sent].filter(t => !handled.has(t));
ok(`every message sent has a handler (${sent.size} types)`, unhandled.length === 0, unhandled.join(", "));

// The session bridge only belongs on our own origins.
const sessionMatches = (m.content_scripts || []).find(cs => (cs.js || []).includes("content/session.js"))?.matches || [];
ok("session bridge is declared", sessionMatches.length > 0);
const foreign = sessionMatches.filter(p => !/careerpilot\.ai|localhost/.test(p));
ok("  and only on CareerPilot origins", foreign.length === 0, foreign.join(", "));
ok("  reads the token, never writes it", !/localStorage\.setItem/.test(session));
ok("  handles the JSON-encoded value", /JSON\.parse/.test(session),
   "raw getItem yields a quoted string and every request would 401");

// The ATS content scripts must NOT run on our own site, and vice versa.
const atsMatches = (m.content_scripts || []).find(cs => (cs.js || []).includes("content/fill.js"))?.matches || [];
ok("autofill does not run on careerpilot.ai itself",
   !atsMatches.some(p => /careerpilot\.ai/.test(p)), atsMatches.filter(p => /careerpilot/.test(p)).join(", "));

// The safety promise the popup makes to the user.
ok("nothing ever submits a form", !/\.submit\(|type=["']submit["']\s*\)\.click/.test(fill));
["salary", "sponsorship", "demographic", "start_date"].forEach(k =>
  ok(`  ${k} is still left for the human`, new RegExp(`${k}:\\s*\\[`).test(fill)));

// Token must not be interpolated into the page or logged.
ok("token is never written into the DOM", !/innerHTML[^\n]*token/i.test(popup + session));

console.log(`PASS ${P}    FAIL ${F}`);
fails.forEach(f => console.log("  ✗ " + f));
process.exit(F ? 1 : 0);
