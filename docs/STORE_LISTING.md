# Chrome Web Store and Google OAuth checklist

Placeholders to fill: `[LEGAL ENTITY NAME]`, `[SUPPORT EMAIL]`, real API origin.
Privacy policy URL: `https://careerpilot.ai/privacy` (source: `web/privacy.html`, still a legal-review draft). Terms: `/terms`.

## Listing text

**Short description (max 132 chars):**
Fill job application forms from your CareerPilot profile. Never submits for you; sensitive questions are left to you.

**Detailed description:**
CareerPilot Autofill saves time on applications for QA and SDET roles. On supported applicant-tracking sites (Workday, Greenhouse, Lever, Ashby, iCIMS, SmartRecruiters) it detects the application form and, when you click "Fill this form", fills name, contact details, links and cover letter from your CareerPilot profile.

- You stay in control: it never clicks Submit.
- Salary, visa sponsorship, work authorization, start date and demographic questions are highlighted and left for you.
- Fields you already filled are not overwritten.
- Requires a free CareerPilot account. Your profile is fetched from the CareerPilot API using a session token you paste into the extension.

**Single-purpose statement:** Autofill job application forms on supported applicant-tracking sites using the user's own CareerPilot profile.

## Permissions found and justification

| Permission | Why the code needs it |
|---|---|
| `storage` | Saves the user's API address and session token (`chrome.storage.local`). |
| `activeTab` | Popup messages the content script on the tab the user is currently applying on. |
| `scripting` | Declared in the manifest; current code injects via static content_scripts and does not call `chrome.scripting`. **Remove before submission unless a feature needs it** (reviewers flag unused permissions). |
| host_permissions: `*.myworkdayjobs.com`, `boards.greenhouse.io`, `job-boards.greenhouse.io`, `jobs.lever.co`, `jobs.ashbyhq.com`, `*.icims.com`, `*.smartrecruiters.com` | Content scripts detect and fill application forms on these sites only. |
| host_permissions: `https://api.careerpilot.ai/*` | Default production API for fetching the user's profile. Keep in sync with `DEFAULT_API_BASE_PLACEHOLDER` in `background.js`. |
| optional_host_permissions: `https://*/*`, `http://localhost/*`, `http://127.0.0.1/*` | Only used when the user saves a different API address in Settings; Chrome then prompts for that single origin. Reviewers may question the broad pattern: justify as "self-hosted or staging API chosen by the user". If unwanted, drop it and ship a fixed host. |

Removed in 1.1.0: the hardcoded `http://localhost:8000/*` and `https://*.careerpilot.ai/*` host permissions.

## Data usage disclosures (must match the privacy page)

- Collected/handled: personally identifiable information (name, email, phone, location), website content (form-field labels on supported pages, read locally to fill them), authentication information (session token, stored locally).
- Sent off-device: only a request to the configured CareerPilot API to fetch the user's own profile. Page content is not transmitted.
- Not sold; not used for unrelated purposes; not used for creditworthiness or lending.
- Tick the three certifications (no sale, no unrelated use, no creditworthiness use).

## Remote code statement
The extension does not load or execute remote code. All JavaScript ships in the package; it only fetches JSON from the configured API.

## Screenshots (1280x800, up to 5) and assets
1. Popup showing "Profile loaded" on a Greenhouse form.
2. Form after fill: blue-outlined filled fields.
3. Amber-highlighted fields left for the user (salary, sponsorship).
4. Settings panel with API address field.
5. CareerPilot profile page it fills from.
Also: 128px icon (present), small promo tile 440x280, support URL/email.

## Google OAuth verification (gmail.send is a restricted scope)

Requesting `https://www.googleapis.com/auth/gmail.send` requires app verification before more than 100 users can connect and before removing the "unverified app" warning.

Checklist:
- [ ] Homepage URL on a verified domain (careerpilot.ai) in Search Console.
- [ ] Privacy policy URL linked from the homepage, containing the Limited Use sentence (present in `web/privacy.html` section 4).
- [ ] Authorized redirect URI is the production callback (not localhost).
- [ ] Scope justification: send-only, used to send applications the user explicitly approved; no inbox reading.
- [ ] Demo video (unlisted YouTube) showing the OAuth consent screen with client ID visible, the full flow, and the in-app feature that uses the scope.
- [ ] Branding: app name, logo, support email match.
- [ ] Domain-ownership and OAuth consent screen set to "In production".

**Lead-time risk:** restricted scopes can additionally require an independent CASA security assessment (annual, third-party, paid). Verification plus assessment can take weeks to months. Start early.

**Fallback (no restricted scope):** approve today returns the job's apply URL and does not need Gmail; applications can be sent from the user's own mail client (mailto link / copy to clipboard). Launch without the Gmail connect button if verification is not complete.
