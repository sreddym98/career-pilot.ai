# CareerPilot Autofill — install and test

**It is not "in review".** That was placeholder copy. The extension is built,
tested (38/38 against real ATS markup), and you can load it in about a minute.

Store listings only matter for letting *other people* one-click install. For
your own use, Developer Mode loads the identical extension.

---

## Install — Chrome, Edge, Brave, Arc

1. Unzip `careerpilot-backend.zip`. Keep the folder somewhere permanent —
   Chrome reloads it from that exact path on every launch.
2. Go to `chrome://extensions` (Edge: `edge://extensions`)
3. Toggle **Developer mode**, top-right
4. Click **Load unpacked**, top-left
5. Select the `extension` folder — the one containing `manifest.json`
6. Pin the ✈ icon to your toolbar

## Install — Firefox

`about:debugging#/runtime/this-firefox` → **Load Temporary Add-on** →
select `extension/manifest.json`.

Firefox drops temporary add-ons when you quit. Chrome keeps them. Use Chrome
for anything day-to-day.

---

## Test it in 30 seconds, without applying to anything

1. Open `extension/test-form.html` in the browser (File → Open, or drag it in)
2. Click the ✈ icon → **Fill this form**

A mock application using the real field names Greenhouse, Workday, Lever, and
iCIMS use. What you should see:

| | |
|---|---|
| **16 fields fill** | blue outline — name, email, phone, location, LinkedIn, GitHub, cover letter, across all three ATS layouts |
| **6 fields stay blank** | amber outline with a note — salary, visa sponsorship, work authorization, start date, gender, veteran status |
| **1 field untouched** | the pre-filled email keeps the value you typed |
| **Nothing submits** | the Submit button is never clicked |

The amber fields are the point. An agent that guesses your salary expectation
or answers a sponsorship question wrong costs you the application — those three
questions are exactly where a machine shouldn't decide for you.

---

## Connect it to your account

1. Sign in on CareerPilot, open any job and press **Apply with CareerPilot**.
2. In the **Send to employer** section press **Connect extension**. The site
   hands the extension a *scoped key*: it can only read the application you
   send, download your tailored resume and report "filled". It is not your
   session and can't see or change anything else.
3. If that doesn't connect (another browser profile, a blocked script), the
   Apply page shows a code. Click ✈ → **Settings**, paste it into
   **Connect code**, Save.

**Disconnect** in ✈ → Settings forgets the key on this browser. Signing out
everywhere / revoking is `DELETE /api/auth/extension-token`.

| Setting | |
|---|---|
| Connect code | Only needed if **Connect extension** didn't work |
| API address | Blank = `https://careerpilot-api-rri9.onrender.com`. For local testing enter `http://localhost:8000` (connecting from a local site sets this for you) |

Saving an address outside the manifest's `host_permissions` makes Chrome ask
for permission to contact it; decline and nothing is saved. Only `https://` is
accepted, except `localhost` and `127.0.0.1`. The default is
`DEFAULT_API_BASE` at the top of `background.js`.

---

## Applying

**From the Apply page (recommended).** Review the job, your tailored resume,
the cover letter and the employer's questions (pre-answered from your
profile; edit anything), then press **Send to employer**. The posting opens
and, on Greenhouse, Lever and Ashby forms, the extension:

- fills every field it can match with the answers you saved,
- attaches your tailored resume PDF and your cover letter,
- answers the work-authorization and sponsorship questions *with the answers
  you reviewed*, and leaves demographic questions on "decline",
- shows a panel listing what it filled and what still **needs you**, with the
  empty required fields outlined in red,
- ends with: *Review everything, then click Submit on this page.*

**It never submits.** You click the employer's Submit button. Afterwards,
press **I submitted it** in the panel (or answer "Did you apply?" back on
CareerPilot) and it's tracked as applied. Nothing marks an application
applied unless you say so.

**Any other form** (Workday, iCIMS, SmartRecruiters, or a posting you opened
yourself): click ✈ → **Fill this form** for your name, email, phone,
location and LinkedIn. Salary, sponsorship, start date and demographic
questions are left for you (amber).

---

## Publishing to the Chrome Web Store — later

Only needed so strangers can install it.

1. [Developer account](https://chrome.google.com/webstore/devconsole) — $5 once
2. Zip the `extension` folder contents (not the folder itself)
3. You'll need: a privacy policy URL, 1280×800 screenshots, a 128px icon,
   and a justification for each permission
4. Review takes 1–3 weeks. First submissions are commonly rejected over
   privacy-policy wording — write that page before you submit

Permissions justification, listing text, data disclosures and the Google OAuth
(gmail.send) checklist are in `docs/STORE_LISTING.md`. Privacy policy: `web/privacy.html`
(served at `/privacy`).
