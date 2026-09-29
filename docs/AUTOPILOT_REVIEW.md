# Autopilot: candid product review

Reviewed 2026-09-28 against the code on `main`. Nothing here is aspirational; each item was checked in code or in a local end-to-end run.

## What is strong
- **The trust model is right.** Nothing is ever sent. Approve opens the real posting and the user submits it. That removes the two worst failure modes of "auto-apply" products (flagged mailboxes, a bad AI message going out under your name).
- **Server-side, tab-closed operation** with an external cron that also wakes a sleeping host. Slot claiming before work prevents double spend.
- **Real matching.** Fit is computed from actual skills, titles, experience, work mode and a visa hard-block, and it says which signals it used. Autopilot now uses the same scorer as the board.
- Small, bounded blast radius: Pro-only, daily cap, per-run cap, queue cap, credits accounted per item.

## What was confusing or wrong (now fixed unless noted)
- Copy claimed "One tap sends the whole batch", "you see the exact email before anything sends" and "recipient". Nothing is emailed. Rewritten to say what actually happens.
- "Never repeats a company" was false (dedupe was by job id only). Now dedupes by job id and by company + title (re-listings).
- Candidate selection ignored the fit score: ad-hoc skill-overlap, and the visa rule dropped a job if ANY held status was excluded (a user with H1B + GC lost jobs that only exclude H1B) and dropped rows with NULL visa flags.
- No control over quality. There was no minimum fit, so weak matches were queued.
- Run history was misleading: "skipped" meant "found but not attempted this run"; an exhausted daily cap or empty credits both read as "AI unavailable".
- "Save flight plan" only saved work style; everything else saved on change. Now every control saves immediately and says so.
- Still true: the "Auto Reply" card is a placeholder ("isn't available yet"). Recommend removing it until it exists. "Approve all" marks a batch approved without opening postings, which is easy to misread as "applied"; the copy now says so, but consider making approve-all open a checklist of links instead.

## What was missing (added)
Minimum fit; why-it-matched chips (fit %, matched and missing skills, link verified); honest run history with reasons; dry-run "what would run next"; pause-until; empty-state when the profile has no skills; queue expiry when a posting closes; once-a-day summary email that only exists when Resend is configured.

## Still missing (deliberately not built)
- A per-role "why not" explorer (which specific jobs were filtered).
- Tailored resume PDF per role (today: summary + highlights + cover letter text).
- Per-user cost/usage view; feedback loop ("this was a bad match") to tune the minimum.
- Slot fairness at scale: one tick serves at most 40 users; unserved slots are retried for two hours, not longer.

## Operational notes
- GitHub scheduled workflows run only from the default branch (`main`, correct now), are best-effort (often 5-60 min late) and are auto-disabled after 60 days without repo activity on public repos. Late ticks are now covered by a 2-hour grace window.
- The tick returns 202 immediately; failures inside the background run are not visible to the workflow. Watch the Render logs (`[autopilot] tick done`) or the per-user run history.
- A slot inside a spring-forward gap does not exist on the clock; the grace window serves it an hour later.
