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

## Connect it to your data

Click ✈ → **Settings**:

| | |
|---|---|
| API address | `http://localhost:8000` while testing, your deployed URL later |
| Session token | leave blank in dev mode — the API signs you in as a dev user |

Then `make dev` in the `be/` folder and the popup will show
*"Profile loaded — 7 yrs 7 mos, 3 roles."*

---

## Using it on a real application

Open any job application on Workday, Greenhouse, Lever, Ashby, iCIMS, or
SmartRecruiters. The ✈ icon shows a blue dot when it recognises a form.
Click it, hit **Fill this form**, answer the amber fields yourself, review
everything, then submit.

---

## Publishing to the Chrome Web Store — later

Only needed so strangers can install it.

1. [Developer account](https://chrome.google.com/webstore/devconsole) — $5 once
2. Zip the `extension` folder contents (not the folder itself)
3. You'll need: a privacy policy URL, 1280×800 screenshots, a 128px icon,
   and a justification for each permission
4. Review takes 1–3 weeks. First submissions are commonly rejected over
   privacy-policy wording — write that page before you submit

Your permissions justification, ready to paste:

> `storage` — saves the user's own API address and session token locally.
> `activeTab` / `scripting` — reads form field labels on the page the user is
> actively applying through, in order to fill them. Host permissions are
> limited to six named ATS domains. No data is collected, sold, or transmitted
> anywhere except the user's own CareerPilot account.
