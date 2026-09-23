# careerpilot.ai Extension — install and test

**It is not "in review".** That was placeholder copy. The extension is built
and you can load it in about a minute.

Before loading it, `node extension/validate.js` checks the things that stop
Chrome accepting it at all — a manifest naming a file nobody wrote, a missing
service worker, a script that doesn't parse — along with the promises made
below: that nothing submits a form, and that salary, sponsorship, start date
and demographic questions are still left alone. It runs in CI too.

Store listings only matter for letting *other people* one-click install. For
your own use, Developer Mode loads the identical extension.

---

## Install — Chrome, Edge, Brave, Arc

1. Keep the `extension/` folder somewhere permanent — Chrome reloads it from
   that exact path on every launch.
2. Go to `chrome://extensions` (Edge: `edge://extensions`)
3. Toggle **Developer mode**, top-right
4. Click **Load unpacked**, top-left
5. Select the `extension` folder — the one containing `manifest.json`
6. Pin the CareerPilot icon to your toolbar

## Install — Firefox

`about:debugging#/runtime/this-firefox` → **Load Temporary Add-on** →
select `extension/manifest.json`.

Firefox drops temporary add-ons when you quit. Chrome keeps them. Use Chrome
for anything day-to-day.

---

## Test it in 30 seconds, without applying to anything

1. Open `extension/test-form.html` in the browser (File → Open, or drag it in)
2. Click the CareerPilot icon → **Fill this form**

A mock application using the real field names Greenhouse, Workday, Lever, and
iCIMS use. What you should see:

| | |
|---|---|
| **Contact fields fill** | moss-green outline — name, email, phone, location, LinkedIn, profile URL, across all three ATS layouts |
| **6 fields stay blank** | amber outline with a note — salary, visa sponsorship, work authorization, start date, gender, veteran status |
| **1 field untouched** | the pre-filled email keeps the value you typed |
| **Nothing submits** | the Submit button is never clicked |

The amber fields are the point. An agent that guesses your salary expectation
or answers a sponsorship question wrong costs you the application — those three
questions are exactly where a machine shouldn't decide for you.

---

## Connect it to your data

**Sign in at careerpilot.ai. That's the whole step.**

A content script that runs only on CareerPilot's own pages reads the session
the site already holds and hands it to the extension. There is no token to copy
across, and the Settings panel no longer asks for one — pasting credentials
between windows is a habit worth not teaching.

Running everything locally works the same way: `make dev`, sign in at
`http://localhost:3000`, and the extension detects that the session came from
localhost and talks to `http://localhost:8000` without being told. The API
address box exists only to override that.

The popup then names the account it is using — *"Signed in as you@example.com"*
— followed by *"Profile loaded — 7 yrs 7 mos, 3 roles."*

Two things it will tell you rather than failing quietly:

- **Signed in as a recruiter.** Autofill fills *your* application from *your*
  profile, so it is a job-seeker feature and the server refuses it outright.
  The popup says so instead of showing a bare 403.
- **Empty profile.** Nothing to fill from yet; add your experience first.

---

## Using it on a real application

Open any job application on Workday, Greenhouse, Lever, Ashby, iCIMS, or
SmartRecruiters. The icon shows a moss-green dot when it recognises a form.
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

> `storage` — keeps the user's own API address and the session token their
> CareerPilot account already issued, locally on their machine.
> `activeTab` / `scripting` — reads form field labels on the page the user is
> actively applying through, in order to fill them.
> Host permissions cover six named ATS domains plus `careerpilot.ai` itself.
> The CareerPilot host permission exists solely so a content script can read
> the user's own signed-in session from our own site, which is what removes
> the need for them to copy an access token by hand. Nothing is collected,
> sold, or transmitted anywhere except the user's own CareerPilot account.
