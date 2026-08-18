/* CareerPilot AI — Copyright (c) 2026 Santosh Reddy Mamindla.
   Proprietary and confidential. See LICENSE. */
/* CareerPilot API client.
 *
 * Drop this in a <script> tag before the main app script, then set:
 *     CP_API.base  = "https://api.careerpilot.ai"   (or http://localhost:8000)
 *     CP_API.token = "<jwt from Supabase>"
 *
 * Replaces the hardcoded J / EXP / SKILLS / NET / CRS constants in
 * careerpilot.html, and — critically — routes every AI call through your
 * own server so the Anthropic key never reaches a browser.
 */
const CP_API = {
  base: localStorage.getItem("cp_api") || "http://localhost:8000",
  token: localStorage.getItem("cp_token") || null,

  _headers() {
    const h = { "Content-Type": "application/json" };
    if (this.token) h.Authorization = `Bearer ${this.token}`;
    return h;
  },

  async _req(path, opts = {}) {
    const r = await fetch(this.base + path, { ...opts, headers: this._headers() });
    if (r.status === 401) throw new Error("Session expired — sign in again.");
    if (r.status === 402) throw new Error("This is a Pro feature.");
    if (r.status === 429) {
      const d = await r.json().catch(() => ({}));
      throw new Error(d.detail || "Monthly generation limit reached.");
    }
    if (!r.ok) {
      const d = await r.json().catch(() => ({}));
      throw new Error(d.detail || `Request failed (${r.status})`);
    }
    return r.json();
  },

  // ── jobs ──
  jobs(f = {}) {
    const p = new URLSearchParams();
    const map = { q:"q", auth:"auth", fields:"fields", families:"families",
                  employment:"employment", modes:"modes", company:"company",
                  fresh_days:"fresh_days", hide_reposts:"hide_reposts",
                  limit:"limit", offset:"offset", sort:"sort" };
    for (const [k, v] of Object.entries(f)) {
      if (v === undefined || v === null || v === "" ) continue;
      p.set(map[k] || k, Array.isArray(v) ? v.join(",") : v);
    }
    return this._req(`/api/jobs?${p}`);
  },
  job(fp) { return this._req(`/api/jobs/${fp}`); },

  // ── profile ──
  profile() { return this._req("/api/profile"); },
  addPosition(p)      { return this._req("/api/positions", { method:"POST", body: JSON.stringify(p) }); },
  editPosition(id, p) { return this._req(`/api/positions/${id}`, { method:"PUT", body: JSON.stringify(p) }); },
  delPosition(id)     { return this._req(`/api/positions/${id}`, { method:"DELETE" }); },
  publicProfile(slug) { return this._req(`/api/u/${slug}`); },

  // ── AI (server-proxied — key stays on your server) ──
  buildResume(o)  { return this._req("/api/ai/resume",       { method:"POST", body: JSON.stringify(o) }); },
  coverLetter(o)  { return this._req("/api/ai/cover-letter", { method:"POST", body: JSON.stringify(o) }); },
  credits()       { return this._req("/api/ai/credits"); },

  // ── referrals ──
  referrals()        { return this._req("/api/referrals"); },
  invite(emails)     { return this._req("/api/referrals/invite", { method:"POST", body: JSON.stringify({ emails }) }); },
  attribute(code)    { return this._req(`/api/referrals/attribute/${code}`, { method:"POST" }); },

  // ── billing ──
  async checkout(plan) {
    const { url } = await this._req(`/api/billing/checkout?plan=${plan}`, { method:"POST" });
    window.location = url;
  },
  async portal() {
    const { url } = await this._req("/api/billing/portal", { method:"POST" });
    window.location = url;
  },

  configure(base, token) {
    this.base = base; this.token = token;
    localStorage.setItem("cp_api", base);
    if (token) localStorage.setItem("cp_token", token);
  },
};

/* ── Wiring the prototype's in-memory data to live endpoints ──
 * Call once on load, after CP_API.configure().
 */
async function hydrateFromAPI() {
  const me = await CP_API.profile();

  // durations arrive computed server-side, from dates — never stored
  const EXP_LIVE = me.positions.map((p, i) => ({
    id: p.id, co: p.company, role: p.role,
    from: fmtMonth(p.started_on),
    to: p.finished_on ? fmtMonth(p.finished_on) : "Present",
    loc: p.location || "—", b: p.bullets || [],
    c: `linear-gradient(145deg,${cc(p.company)},${cc(p.company)}cc)`,
  }));

  const { jobs } = await CP_API.jobs({ limit: 100 });
  const J_LIVE = jobs.map((j) => ({
    id: j.fingerprint, co: j.company, f5: j.is_fortune500 ? 1 : 0,
    tp: j.company_type, ti: j.title, lo: j.location, md: j.work_mode,
    em: j.employment, fm: j.role_family,
    rt: fmtComp(j.comp), d: j.days_live, sn: j.seen_count,
    yr: j.exp.min ? `${j.exp.min}–${j.exp.max || "+"}` : "—",
    cp: j.competition, url: j.apply_url,
    ref: (j.referrals || []).length,
    au: j.visa, sk: j.skills || [], need: [], hm: null, hi: [], gp: [],
  }));

  return { EXP: EXP_LIVE, J: J_LIVE, SKILLS: me.skills, me };
}

const MON = ["Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec"];
function fmtMonth(iso) { const d = new Date(iso); return `${MON[d.getUTCMonth()]} ${d.getUTCFullYear()}`; }
function fmtComp(c) {
  if (!c || !c.min) return "—";
  const k = (n) => c.unit === "yr" ? `$${Math.round(n/1000)}k` : `$${n}`;
  return c.min === c.max ? `${k(c.min)}/${c.unit}` : `${k(c.min)}–${k(c.max)}/${c.unit}`;
}
