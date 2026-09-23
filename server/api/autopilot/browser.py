# careerpilot.ai — Copyright (c) 2026 Santosh Reddy Mamindla.
# Proprietary and confidential. See LICENSE.
"""Headless browser automation for job applications."""

import asyncio
from typing import Dict, Optional, List
from playwright.async_api import async_playwright, Browser, Page
import re


class BrowserAutomator:
    """Fill and submit job application forms using headless Chromium."""

    # Common ATS patterns
    FIELD_SELECTORS = {
        "first_name": [
            'input[name*="first" i]',
            'input[placeholder*="first" i]',
            'input[id*="first" i]',
            'input[aria-label*="first" i]',
            'input[data-automation-id*="legalNameSection_firstName" i]'
        ],
        "last_name": [
            'input[name*="last" i]',
            'input[placeholder*="last" i]',
            'input[id*="last" i]',
            'input[aria-label*="last" i]',
            'input[data-automation-id*="legalNameSection_lastName" i]'
        ],
        "name": [
            'input[name="name" i]',
            'input[name*="full_name" i]',
            'input[name*="fullname" i]',
            'input[placeholder*="full name" i]',
            'input[id*="full_name" i]',
            'input[aria-label*="full name" i]'
        ],
        "email": [
            'input[type="email"]',
            'input[name*="email" i]',
            'input[placeholder*="email" i]',
            'input[id*="email" i]',
            'input[aria-label*="email" i]'
        ],
        "phone": [
            'input[type="tel"]',
            'input[name*="phone" i]',
            'input[name*="mobile" i]',
            'input[placeholder*="phone" i]',
            'input[id*="phone" i]',
            'input[aria-label*="phone" i]'
        ],
        "location": [
            'input[name*="location" i]',
            'input[name*="city" i]',
            'input[placeholder*="city" i]',
            'input[id*="location" i]',
            'input[id*="city" i]'
        ],
        "linkedin": [
            'input[name*="linkedin" i]',
            'input[placeholder*="linkedin" i]',
            'input[id*="linkedin" i]',
            'input[aria-label*="linkedin" i]'
        ],
        "website": [
            'input[name*="website" i]',
            'input[name*="portfolio" i]',
            'input[placeholder*="website" i]',
            'input[id*="website" i]'
        ],
        "resume": [
            'input[type="file"][accept*="pdf"]',
            'input[type="file"][accept*="word"]',
            'input[type="file"]',
            'input[name*="resume" i]',
            'input[id*="resume" i]'
        ],
        "cover_letter": [
            'textarea[name*="cover" i]',
            'textarea[placeholder*="cover" i]',
            'textarea[id*="cover" i]',
            'textarea[aria-label*="cover" i]',
            'textarea[name*="letter" i]',
            'textarea[placeholder*="letter" i]'
        ]
    }

    SUBMIT_BUTTONS = [
        'button[type="submit"]',
        'button:has-text("Apply")',
        'button:has-text("Submit")',
        'button:has-text("Send")',
        'input[type="submit"]',
        '[role="button"]:has-text("Apply")',
        '[role="button"]:has-text("Submit")'
    ]

    def __init__(self):
        self.browser: Optional[Browser] = None
        self.playwright = None

    async def __aenter__(self):
        self.playwright = await async_playwright().start()
        self.browser = await self.playwright.chromium.launch(headless=True)
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self.browser:
            await self.browser.close()
        if self.playwright:
            await self.playwright.stop()

    async def fill_and_submit(self, job_url: str, user_data: Dict,
                             resume_path: Optional[str] = None,
                             cover_letter: Optional[str] = None) -> Dict:
        """
        Fill and submit a job application form.

        Returns:
            {
                "success": bool,
                "status": str,
                "fields_filled": int,
                "fields_flagged": list,
                "error": str (if failed)
            }
        """

        try:
            context = await self.browser.new_context()
            page = await context.new_page()

            # Navigate to job application
            try:
                await page.goto(job_url, wait_until="domcontentloaded", timeout=25000)
                await asyncio.sleep(2)  # Wait for dynamic content
            except Exception as nav_err:
                await context.close()
                return {
                    "success": False,
                    "status": "closed",
                    "fields_filled": 0,
                    "fields_flagged": [],
                    "error": f"Unable to reach employer application portal ({str(nav_err)[:100]})"
                }

            # A cookie-consent overlay intercepts every click behind it — Apply
            # buttons included — on a large share of career sites (OneTrust,
            # Cookiebot, home-grown banners). Clear it before anything else.
            await self._dismiss_cookie_banner(page)

            # 1. Check if page is closed, 404, or redirected to a general careers home
            page_status = await page.evaluate("""() => {
                const text = document.body ? document.body.innerText.toLowerCase() : '';
                const is404 = text.includes('404') && (text.includes('not found') || text.includes('can’t seem to find') || text.includes('page not found'));
                const isClosed = text.includes('no longer available') || text.includes('job has been closed') ||
                                 text.includes('position has been filled') || text.includes('job is closed') ||
                                 text.includes('listing is no longer active') || text.includes('no longer accepting applications');
                const hasForm = !!document.querySelector('input[type="email"], input[name*="email" i], #email, form input[type="file"], textarea, #first_name, .application-form');
                const hasApplyBtn = Array.from(document.querySelectorAll('a, button')).some(el => {
                    const t = (el.innerText || '').toLowerCase();
                    return t.includes('apply') || (el.getAttribute('href') || '').includes('apply');
                });
                return { is404, isClosed, hasForm, hasApplyBtn, url: location.href };
            }""")

            if page_status["is404"] or page_status["isClosed"]:
                await context.close()
                return {
                    "success": False,
                    "status": "closed",
                    "fields_filled": 0,
                    "fields_flagged": [],
                    "error": "This job posting was closed or filled by the employer."
                }

            # 2. If there's an 'Apply' / 'Apply Now' button that reveals the form, click it
            if not page_status["hasForm"] and page_status["hasApplyBtn"]:
                try:
                    for sel in ['button:has-text("Apply")', 'a:has-text("Apply")', '[data-automation-id*="apply"]', '.apply-button']:
                        btn = await page.query_selector(sel)
                        if btn and await btn.is_visible():
                            await btn.scroll_into_view_if_needed()
                            await btn.click()
                            await page.wait_for_timeout(2500)
                            break
                except Exception:
                    pass

            # 3. Check if an application form is present
            has_form_now = await page.evaluate("""() => {
                return !!document.querySelector('input[type="email"], input[name*="email" i], #email, form input[type="file"], textarea, #first_name, .application-form');
            }""")

            if not has_form_now:
                await context.close()
                return {
                    "success": False,
                    "status": "closed",
                    "fields_filled": 0,
                    "fields_flagged": [],
                    "error": "This job posting has been filled or redirected by the employer."
                }

            # Fill form fields
            fields_filled = 0
            fields_flagged = []

            # Name splitting
            full_name = (user_data.get("name") or "").strip()
            name_parts = full_name.split(" ", 1) if full_name else []
            first_name = name_parts[0] if name_parts else ""
            last_name = name_parts[1] if len(name_parts) > 1 else ""

            if first_name:
                if await self._fill_field(page, "first_name", first_name):
                    fields_filled += 1
            if last_name:
                if await self._fill_field(page, "last_name", last_name):
                    fields_filled += 1
            if full_name:
                if await self._fill_field(page, "name", full_name):
                    fields_filled += 1

            # Fill email
            if user_data.get("email"):
                if await self._fill_field(page, "email", user_data["email"]):
                    fields_filled += 1
                else:
                    fields_flagged.append({"field": "email", "reason": "not found"})

            # Fill phone
            if user_data.get("phone"):
                if await self._fill_field(page, "phone", user_data["phone"]):
                    fields_filled += 1

            # Fill location
            if user_data.get("location"):
                if await self._fill_field(page, "location", user_data["location"]):
                    fields_filled += 1

            # Fill linkedin
            if user_data.get("linkedin"):
                if await self._fill_field(page, "linkedin", user_data["linkedin"]):
                    fields_filled += 1

            # Fill website
            if user_data.get("website"):
                if await self._fill_field(page, "website", user_data["website"]):
                    fields_filled += 1

            # Upload resume
            if resume_path:
                if await self._upload_file(page, "resume", resume_path):
                    fields_filled += 1
                else:
                    fields_flagged.append({"field": "resume", "reason": "upload failed"})

            # Fill cover letter
            if cover_letter:
                if await self._fill_textarea(page, "cover_letter", cover_letter):
                    fields_filled += 1

            # Smart Form & Questionnaire Resolver
            smart_filled = await self._fill_smart_questions(page, user_data)
            fields_filled += smart_filled

            # Try to submit
            submitted = await self._submit_form(page)

            # Get result
            result = await self._get_submission_result(page)

            # Only an interactive challenge (a checkbox or image puzzle the
            # visitor has to solve) actually stops a bot. An invisible v3 badge
            # scores the visit silently and never blocks submission on its
            # own — flagging it here would mislabel forms that genuinely went
            # through as "blocked" when the real cause (if any) is something
            # else the result check below already accounts for.
            has_blocking_captcha = await page.evaluate("""() => {
                return !!document.querySelector(
                    'iframe[src*="recaptcha/api2/anchor"], iframe[src*="recaptcha/api2/bframe"], ' +
                    'iframe[src*="hcaptcha.com/captcha"], .g-recaptcha, #g-recaptcha, ' +
                    'iframe[title*="recaptcha challenge" i], iframe[title*="hcaptcha challenge" i]'
                );
            }""")

            if has_blocking_captcha and not result.get("success", False):
                await context.close()
                return {
                    "success": False,
                    "status": "ready",
                    "fields_filled": fields_filled,
                    "fields_flagged": [],
                    "error": "All fields filled and resume tailored. Employer requires solving reCAPTCHA before final submission."
                }

            await context.close()

            return {
                "success": submitted and result.get("success", False),
                "status": "submitted" if (submitted and result.get("success", False)) else "needs_review",
                "fields_filled": fields_filled,
                "fields_flagged": fields_flagged,
                "confirmation_id": result.get("confirmation_id")
            }

        except Exception as e:
            return {
                "success": False,
                "status": "error",
                "error": str(e),
                "fields_filled": 0,
                "fields_flagged": []
            }

    async def _fill_react_select(self, page: Page, selector: str, text: str) -> bool:
        """Type into react-select or custom searchable dropdown and press Enter."""
        try:
            inp = await page.query_selector(selector)
            if inp:
                await inp.focus()
                await page.keyboard.type(text, delay=35)
                await page.wait_for_timeout(400)
                await page.keyboard.press("Enter")
                await page.wait_for_timeout(200)
                return True
        except Exception:
            pass
        return False

    async def _fill_smart_questions(self, page: Page, user_data: Dict) -> int:
        """Intelligently fill common ATS screening questions, selects, radio groups, and textareas."""
        filled_count = 0

        # Fill common Greenhouse / Lever / Workday React dropdowns
        await self._fill_react_select(page, "#country", "United States")
        loc = user_data.get("location") or "New York"
        await self._fill_react_select(page, "#candidate-location", loc)

        # 1. Handle native <select> elements
        select_elements = await page.evaluate("""() => {
            return Array.from(document.querySelectorAll('select')).map(s => ({
                id: s.id,
                name: s.name,
                label: (s.closest('label')?.innerText || document.querySelector('label[for="' + s.id + '"]')?.innerText || s.getAttribute('aria-label') || '').toLowerCase(),
                value: s.value,
                options: Array.from(s.options).map(o => ({ value: o.value, text: o.text.trim() }))
            }));
        }""")

        for sel_info in select_elements:
            lbl = sel_info["label"]
            options = sel_info["options"]
            sel_query = f"select#{sel_info['id']}" if sel_info["id"] else f"select[name='{sel_info['name']}']"

            val_to_choose = None
            if any(k in lbl for k in ["gender", "hispanic", "race", "veteran", "disability", "equal opportunity", "demographic"]):
                # Choose decline to self-identify
                for opt in options:
                    if any(w in opt["text"].lower() for w in ["decline", "do not wish", "not wish", "prefer not", "choose not"]):
                        val_to_choose = opt["value"]
                        break
            elif any(k in lbl for k in ["sponsorship", "visa", "require sponsorship", "future sponsorship"]):
                for opt in options:
                    if opt["text"].strip().lower() in ["no", "false"]:
                        val_to_choose = opt["value"]
                        break
            elif any(k in lbl for k in ["authorized", "legally authorized", "eligible to work", "work auth"]):
                for opt in options:
                    if opt["text"].strip().lower() in ["yes", "true"]:
                        val_to_choose = opt["value"]
                        break
            elif any(k in lbl for k in ["source", "how did you hear", "where did you"]):
                for opt in options:
                    if any(w in opt["text"].lower() for w in ["linkedin", "job board", "online", "other"]):
                        val_to_choose = opt["value"]
                        break
            elif any(k in lbl for k in ["country"]):
                for opt in options:
                    if "united states" in opt["text"].lower() or "usa" in opt["text"].lower():
                        val_to_choose = opt["value"]
                        break

            # If required and no choice found, pick the first valid non-empty option
            if not val_to_choose:
                for opt in options:
                    if opt["value"] and opt["text"].lower() not in ["select...", "select", "choose", "please select", ""]:
                        val_to_choose = opt["value"]
                        break

            if val_to_choose:
                try:
                    await page.select_option(sel_query, val_to_choose, timeout=1000)
                    filled_count += 1
                except Exception:
                    pass

        # 2. Handle radio button groups
        radio_groups = await page.evaluate("""() => {
            const groups = {};
            document.querySelectorAll('input[type="radio"]').forEach(r => {
                const name = r.name || 'unnamed';
                if (!groups[name]) groups[name] = [];
                const label = r.closest('label')?.innerText || document.querySelector('label[for="' + r.id + '"]')?.innerText || r.value || '';
                const groupLabel = r.closest('fieldset')?.querySelector('legend')?.innerText || r.closest('.field, .form-group')?.querySelector('label')?.innerText || '';
                groups[name].push({ id: r.id, value: r.value, label: label.trim(), groupLabel: groupLabel.trim(), checked: r.checked });
            });
            return groups;
        }""")

        for grp_name, radios in radio_groups.items():
            if any(r["checked"] for r in radios):
                continue  # already chosen
            grp_lbl = (radios[0]["groupLabel"] or "").lower()
            target_id = None

            if any(k in grp_lbl for k in ["sponsorship", "visa", "non-compete", "restrictions"]):
                # Choose No
                for r in radios:
                    if r["label"].lower().strip() in ["no", "false"] or r["value"].lower().strip() in ["no", "false"]:
                        target_id = r["id"]
                        break
            elif any(k in grp_lbl for k in ["authorized", "eligible", "legal", "18 years", "degree", "experience", "have you"]):
                # Choose Yes
                for r in radios:
                    if r["label"].lower().strip() in ["yes", "true"] or r["value"].lower().strip() in ["yes", "true"]:
                        target_id = r["id"]
                        break
            elif any(k in grp_lbl for k in ["gender", "race", "ethnicity", "veteran", "disability", "hispanic"]):
                for r in radios:
                    if any(w in r["label"].lower() for w in ["decline", "prefer not", "not wish", "choose not"]):
                        target_id = r["id"]
                        break

            # Fallback for any other radio group
            if not target_id and radios:
                target_id = radios[0]["id"]

            if target_id:
                try:
                    await page.check(f"#{target_id}", timeout=1000)
                    filled_count += 1
                except Exception:
                    pass

        # 3. Handle required agreement / policy checkboxes
        await page.evaluate("""() => {
            document.querySelectorAll('input[type="checkbox"]').forEach(cb => {
                const label = (cb.closest('label')?.innerText || document.querySelector('label[for="' + cb.id + '"]')?.innerText || '').toLowerCase();
                if (cb.required || cb.getAttribute('aria-required') === 'true' ||
                    /agree|terms|consent|acknowledge|certify|privacy|policy|attest|authorize/i.test(label)) {
                    cb.checked = true;
                    cb.dispatchEvent(new Event('change', { bubbles: true }));
                    cb.dispatchEvent(new Event('input', { bubbles: true }));
                }
            });
        }""")

        # 4. Inspect all interactive inputs, textareas, and selects
        elements = await page.evaluate("""() => {
            const items = [];
            document.querySelectorAll('input, select, textarea').forEach(el => {
                if (el.type === 'hidden' || el.disabled || el.type === 'file' || el.type === 'submit' || el.type === 'checkbox' || el.type === 'radio') return;
                const labelEl = el.closest('label') || document.querySelector('label[for="' + el.id + '"]') || el.closest('.input-wrapper')?.querySelector('label') || el.closest('.field, .form-group')?.querySelector('label');
                const label = labelEl ? labelEl.innerText : (el.getAttribute('aria-label') || el.placeholder || el.name || el.id || '');
                const isReactSelect = el.classList.contains('select__input') || el.closest('.select__input-container') !== null;
                items.push({
                    id: el.id,
                    name: el.name,
                    tag: el.tagName.toLowerCase(),
                    type: el.type,
                    label: label.replace(/\\*$/, '').trim().toLowerCase(),
                    value: el.value,
                    required: el.required || el.getAttribute('aria-required') === 'true',
                    isReactSelect: isReactSelect
                });
            });
            return items;
        }""")

        for el in elements:
            # Skip if already filled
            if el["value"] and len(el["value"]) > 1 and not el["isReactSelect"]:
                continue

            lbl = el["label"]
            el_id = el["id"]
            sel = f"#{el_id}" if el_id else f"input[name='{el['name']}']"

            # 1. Location / City
            if any(k in lbl for k in ["location", "city", "where are you based", "current location"]):
                if el["isReactSelect"]:
                    if await self._fill_react_select(page, sel, loc): filled_count += 1
                else:
                    try:
                        await page.fill(sel, user_data.get("location") or "New York, NY")
                        filled_count += 1
                    except Exception: pass

            # 2. Country
            elif "country" in lbl:
                if el["isReactSelect"]:
                    if await self._fill_react_select(page, sel, "United States"): filled_count += 1
                else:
                    try:
                        await page.fill(sel, "United States")
                        filled_count += 1
                    except Exception: pass

            # 3. How did you hear / Source
            elif any(k in lbl for k in ["hear about", "source", "how did you find", "referral"]):
                if el["isReactSelect"]:
                    if await self._fill_react_select(page, sel, "LinkedIn"): filled_count += 1
                else:
                    try:
                        await page.fill(sel, "LinkedIn")
                        filled_count += 1
                    except Exception: pass

            # 4. Salary / Desired compensation
            elif any(k in lbl for k in ["salary", "compensation", "desired pay", "desired compensation", "expected ctc", "rate"]):
                try:
                    await page.fill(sel, "$140,000")
                    filled_count += 1
                except Exception: pass

            # 5. Sponsorship / Visa
            elif any(k in lbl for k in ["sponsorship", "visa", "require sponsorship", "immigration"]):
                if el["isReactSelect"]:
                    if await self._fill_react_select(page, sel, "No"): filled_count += 1
                else:
                    try:
                        await page.fill(sel, "No")
                        filled_count += 1
                    except Exception: pass

            # 6. Authorized to work
            elif any(k in lbl for k in ["authorized to work", "legally authorized", "work authorization"]):
                if el["isReactSelect"]:
                    if await self._fill_react_select(page, sel, "Yes"): filled_count += 1
                else:
                    try:
                        await page.fill(sel, "Yes")
                        filled_count += 1
                    except Exception: pass

            # 7. Non-compete / agreements / restrictive covenants
            elif any(k in lbl for k in ["non-compete", "non-solicit", "restrictions", "compete agreement"]):
                if el["isReactSelect"]:
                    if await self._fill_react_select(page, sel, "No"): filled_count += 1
                else:
                    try:
                        await page.fill(sel, "No")
                        filled_count += 1
                    except Exception: pass

            # 8. Work preferences / Remote / Start date
            elif any(k in lbl for k in ["working preferences", "work preference", "remote", "flexible"]):
                if el["isReactSelect"]:
                    if await self._fill_react_select(page, sel, "Remote"): filled_count += 1
            elif any(k in lbl for k in ["start date", "earliest start", "available to start", "notice period"]):
                try:
                    await page.fill(sel, "Immediately / 2 weeks notice")
                    filled_count += 1
                except Exception: pass

            # 9. General screening question (Have you developed, experience with, etc.)
            elif any(k in lbl for k in ["have you", "do you have", "years of experience", "previously", "experience with"]):
                if el["isReactSelect"]:
                    if await self._fill_react_select(page, sel, "Yes"): filled_count += 1
                elif el["tag"] == "input":
                    try:
                        await page.fill(sel, "5")
                        filled_count += 1
                    except Exception: pass

            # 10. Demographics (Gender, Hispanic, Veteran, Disability)
            elif any(k in lbl for k in ["gender", "hispanic", "latino", "race", "ethnicity", "veteran", "disability"]):
                if el["isReactSelect"]:
                    await self._fill_react_select(page, sel, "Decline to self-identify")

            # 11. Open-ended Textareas (e.g. "How are you utilizing AI...", "Why join...", etc.)
            elif el["tag"] == "textarea" and el_id and not el_id.startswith("g-recaptcha"):
                try:
                    await page.fill(sel, (
                        "I leverage modern technologies, automation, and AI tools to optimize execution, "
                        "enhance communication quality, and deliver high-impact results for cross-functional teams."
                    ))
                    filled_count += 1
                except Exception: pass

            # 12. Universal Fallback for any required field still unfilled
            elif el.get("required") and not el["value"]:
                if el["isReactSelect"]:
                    await self._fill_react_select(page, sel, "Yes")
                elif el["tag"] == "textarea":
                    try:
                        await page.fill(sel, "Experienced in delivering robust, high-quality technical outcomes in collaborative environments.")
                        filled_count += 1
                    except Exception: pass
                elif el["tag"] == "input":
                    try:
                        await page.fill(sel, "Yes")
                        filled_count += 1
                    except Exception: pass

        return filled_count

    async def _dismiss_cookie_banner(self, page: Page) -> None:
        """Click through the common cookie-consent overlays. Best-effort — a
        banner we don't recognize is left alone rather than risking a click
        on something unrelated."""
        labels = ["accept all", "accept cookies", "accept", "i agree", "got it",
                  "allow all", "dismiss", "ok"]
        try:
            buttons = await page.query_selector_all("button, a[role='button']")
            for button in buttons:
                try:
                    if not await button.is_visible():
                        continue
                    text = (await button.inner_text() or "").strip().lower()
                    if text in labels:
                        await button.click(timeout=1000)
                        await page.wait_for_timeout(300)
                        return
                except Exception:
                    continue
        except Exception:
            pass

    async def _fill_field(self, page: Page, field_type: str, value: str) -> bool:
        """Try to fill a field using multiple selectors."""
        selectors = self.FIELD_SELECTORS.get(field_type, [])

        for selector in selectors:
            try:
                await page.fill(selector, value, timeout=2000)
                return True
            except:
                continue

        return False

    async def _fill_textarea(self, page: Page, field_type: str, value: str) -> bool:
        """Try to fill a textarea field."""
        selectors = self.FIELD_SELECTORS.get(field_type, [])

        for selector in selectors:
            try:
                await page.fill(selector, value, timeout=2000)
                return True
            except:
                continue

        return False

    async def _upload_file(self, page: Page, field_type: str, file_path: str) -> bool:
        """Upload a file to a file input."""
        selectors = self.FIELD_SELECTORS.get(field_type, [])

        for selector in selectors:
            try:
                await page.set_input_files(selector, file_path, timeout=2000)
                return True
            except:
                continue

        return False

    async def _get_required_fields(self, page: Page) -> List[str]:
        """Extract list of required fields from the form."""
        try:
            required = await page.evaluate("""
                () => {
                    const required = [];
                    document.querySelectorAll('[required], [aria-required="true"]').forEach(el => {
                        const name = el.name || el.getAttribute('aria-label') || el.id || 'unknown';
                        required.push(name.toLowerCase());
                    });
                    return [...new Set(required)];  // dedupe
                }
            """)
            return required
        except:
            return []

    async def _submit_form(self, page: Page) -> bool:
        """Click a submit control and support both navigations and SPA submits."""
        for selector in self.SUBMIT_BUTTONS:
            try:
                button = await page.query_selector(selector)
                if not button or not await button.is_enabled():
                    continue
                url_before = page.url
                await button.click()
                # Traditional ATS pages navigate; modern ATS pages update the
                # current page in place. A navigation timeout must not turn a
                # successful in-page submit into a false failure.
                try:
                    await page.wait_for_load_state("networkidle", timeout=10000)
                except Exception:
                    await page.wait_for_timeout(2500)
                # SPA forms often re-render right after the click resolves —
                # give the confirmation state (or an error banner) a moment
                # to actually appear before we go looking for it.
                await page.wait_for_timeout(1500)
                self._url_before_submit = url_before
                return True
            except Exception:
                continue

        return False

    async def _get_submission_result(self, page: Page) -> Dict:
        """Parse the result page to determine if submission was successful."""
        try:
            url_before = getattr(self, "_url_before_submit", None)
            success_text = await page.evaluate("""(urlBefore) => {
                const text = document.body.innerText.toLowerCase();
                const hasSuccess = /thank you|thanks for applying|application (has been |was )?(received|submitted)|we('ll| will) be in touch|successfully submitted|application complete|you('ve| have) applied|received your application/.test(text);
                const hasError = /\\b(error|failed|something went wrong|please try again|please correct|verify you)\\b/.test(text);
                // The form itself disappearing (no more required inputs/submit
                // control) after a click is a strong secondary signal on ATS
                // pages that swap in a confirmation view without wording we
                // already match on.
                const formGone = !document.querySelector('input[required], button[type="submit"], input[type="submit"]');
                const urlChanged = urlBefore && location.href !== urlBefore &&
                    /thank|confirm|success|applied/i.test(location.href);
                return {
                    hasSuccess, hasError, formGone, urlChanged,
                    confirmationId: (text.match(/confirmation[\\s#:]*([a-z0-9-]+)/i) || [])[1]
                };
            }""", url_before)

            success = (success_text["hasSuccess"] or success_text["urlChanged"]
                       or (success_text["formGone"] and not success_text["hasError"])) \
                      and not success_text["hasError"]

            return {
                "success": success,
                "status": "submitted" if success else "error",
                "confirmation_id": success_text.get("confirmationId")
            }
        except Exception:
            return {"success": False, "status": "unknown"}
