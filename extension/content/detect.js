/* CareerPilot AI — Copyright (c) 2026 Santosh Reddy Mamindla.
   Proprietary and confidential. See LICENSE. */
/* Which applicant tracking system are we looking at?
   Each ATS lays out its form differently, so everything downstream
   depends on getting this right. */
(() => {
  const H = location.hostname;

  const ATS = [
    { id: "workday",         test: () => /myworkdayjobs\.com$/.test(H) || !!document.querySelector('[data-automation-id]') },
    { id: "greenhouse",      test: () => /greenhouse\.io$/.test(H) || !!document.querySelector('#application_form, [id^="job_application"]') },
    { id: "lever",           test: () => /lever\.co$/.test(H) || !!document.querySelector('.application-form') },
    { id: "ashby",           test: () => /ashbyhq\.com$/.test(H) },
    { id: "icims",           test: () => /icims\.com$/.test(H) || !!document.querySelector('.iCIMS_MainWrapper') },
    { id: "smartrecruiters", test: () => /smartrecruiters\.com$/.test(H) },
  ];

  let detected = null;
  for (const a of ATS) { try { if (a.test()) { detected = a.id; break; } } catch (_) {} }

  // Is this an application form, or just a listing page?
  const isForm = !!document.querySelector(
    'input[type="email"], input[name*="email" i], input[name*="first" i], form input[type="file"]'
  );

  window.__CP = { ats: detected, isForm, url: location.href };

  if (detected && isForm) {
    chrome.runtime.sendMessage({ type: "ats_detected", ats: detected, url: location.href });
  }
})();
