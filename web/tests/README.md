# Frontend tests

21 files, 626 tests total, all currently passing against `../index.html`. These are what were actually used to build and verify this product — not written after the fact.

## Run everything
```bash
cd web/tests
npm install
bash run-all.sh
```

## Run one file
```bash
node v2test.js          # the core user-journey suite, 144 tests
node autopilottest.js   # Autopilot's prepare-then-approve flow
node emailtest.js       # the recruiter email + attachment flow
```

Each file is self-contained: it loads `../index.html` into a simulated browser (jsdom), clicks through the actual UI the way a person would, and checks what rendered. No mocking of the app's own logic — only external things the app can't control in a test environment (network calls, the OS mail app, browser file-sharing APIs) are stubbed, and each of those is commented explaining why.

## What each file covers
| File | Covers |
|---|---|
| `v2test.js` | Core job search, filtering, apply flow, resume upload — the main journey |
| `applyflow.js` | The "did you apply?" tracking that fires when you return to the tab |
| `benchtest.js` | Recruiter mode: bench management, candidate matching |
| `autopilottest.js` | Autopilot scheduling and the approve-before-send safeguard |
| `bulkapprovetest.js` | Approving a whole batch of Autopilot-prepared applications at once |
| `emailtest.js` | The recruiter email flow, including the resume-attachment checklist |
| `attachfixtest.js` | Per-job resume tailoring doesn't leak across different job applications |
| `attachfallbacktest.js` | What happens when the browser can't attach a file directly |
| `mailtofollowuptest.js` | Honest handling when `mailto:` links silently fail (common with webmail) |
| `evaltest.js` | The $5 profile evaluation flow |
| `interviewtest.js` | Mock interview generation |
| `supporttest.js` | Support ticket priority routing |
| `pricingtest.js` / `pricingv2test.js` | Plan pricing display and the multi-month term picker |
| `employmenttypestest.js` | Internship / part-time filters and Enterprise plan visibility |
| `sidebartest.js` | Sidebar navigation and the split-pane job view |
| `funneltest.js` | Evaluation-to-subscription funnel messaging |
| `coursefixtest.js` | Skill-gap course links are real and clickable |
| `clean.js` | No developer jargon leaks into anything customer-facing |
| `polish.js` | State persistence across page reloads |
| `csssanity.js` | Catches the single most common bug in this build's history: a CSS class referenced in the HTML with no matching rule in the stylesheet |

## Why csssanity.js exists
Early in this build, an edit silently failed to land — the entire sidebar's CSS was referenced everywhere but never actually written to the stylesheet, and nothing caught it until a screenshot showed a broken layout. This file exists specifically so that never happens silently again: it parses the assembled HTML and fails loudly if any class used in markup has no matching CSS rule.
