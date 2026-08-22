const path=require('path');
const {JSDOM}=require('jsdom');const fs=require('fs');
const HTML=fs.readFileSync(path.join(__dirname,'..','index.html'),'utf8');
const mk=()=>{const d=new JSDOM(HTML,{runScripts:"dangerously",pretendToBeVisual:true,url:"https://careerpilot.ai/"});
  const w=d.window;w.scrollTo=()=>{};w.confirm=()=>true;w.print=()=>{};
  Object.defineProperty(w,"innerWidth",{value:1200,configurable:true});
  w.navigator.clipboard={writeText:()=>Promise.resolve()};
  w.__o=[];w.open=u=>{w.__o.push(u);return{focus(){}}};return w;};
let P=0,F=0;const fails=[];
const ok=(n,c,x)=>{c?P++:(F++,fails.push(n+(x?"  →  "+x:"")))};
const sleep=ms=>new Promise(r=>setTimeout(r,ms));

(async()=>{
const w=mk(); await sleep(700);
const d=w.document,$=i=>d.getElementById(i),qa=s=>[...d.querySelectorAll(s)];
const click=e=>{if(!e)throw new Error("missing element");e.dispatchEvent(new w.MouseEvent("click",{bubbles:true}))};

console.log("\n╔═══ ACCOUNTS — seeker or recruiter ═══╗\n");

console.log("── Signed out, nothing changes ──");
// The demo has to keep working with no account. If this breaks, every other
// test file in here breaks with it.
ok("no session on a cold load", w.CP.SESSION===null);
ok("the sign-in screen is not in the way", !$("authGate").classList.contains("on"));
ok("both modes still offered", qa(".modeb").length===2);
ok("mode switch still visible", d.querySelector(".modesw").style.display!=="none");
ok("still starts in seeker mode", w.CP.MODE==="seeker");
click(qa(".modeb").find(b=>b.dataset.m==="recruiter")); await sleep(60);
ok("  and still toggles freely", w.CP.MODE==="recruiter");
click(qa(".modeb").find(b=>b.dataset.m==="seeker")); await sleep(60);
ok("  back again", w.CP.MODE==="seeker");
ok("sidebar offers a way in", !!d.querySelector(".sbsignin"));

console.log("\n── The sign-in screen ──");
w.CP.openAuth("in"); await sleep(60);
ok("opens", $("authGate").classList.contains("on"));
ok("  defaults to signing in", $("authTabIn").classList.contains("on"));
ok("  no role picker when signing in", $("authRolePick").style.display==="none");
ok("  no name field when signing in", $("authNameFld").style.display==="none");
ok("  button says Sign in", $("authGo").textContent.trim()==="Sign in");

w.CP.authTab("up"); await sleep(60);
ok("create-account tab asks which kind", $("authRolePick").style.display!=="none");
ok("  and asks for a name", $("authNameFld").style.display!=="none");
ok("  button changes", $("authGo").textContent.trim()==="Create account");
ok("  password field switches to new-password",
   $("au-pass").getAttribute("autocomplete")==="new-password", $("au-pass").getAttribute("autocomplete"));
ok("  two account types offered", qa(".roleopt").length===2);
ok("  seeker preselected", d.querySelector('.roleopt[data-role="seeker"]').classList.contains("on"));
ok("  says the choice is permanent",
   /can't be changed/i.test(d.querySelector(".rolenote").textContent));

click(d.querySelector('.roleopt[data-role="recruiter"]')); await sleep(40);
ok("picking recruiter sticks", w.CP.AUTH_ROLE==="recruiter");
ok("  and is announced to screen readers",
   d.querySelector('.roleopt[data-role="recruiter"]').getAttribute("aria-checked")==="true");
ok("  seeker deselected", !d.querySelector('.roleopt[data-role="seeker"]').classList.contains("on"));

console.log("\n── Refusing bad input before it reaches the server ──");
$("au-email").value=""; $("au-pass").value="";
await w.CP.authSubmit(); await sleep(40);
ok("empty email is caught here", $("authErr").classList.contains("on"));
$("au-email").value="sam@example.com"; $("au-pass").value="short";
await w.CP.authSubmit(); await sleep(40);
ok("short password is caught here", /8 characters/.test($("authErr").textContent), $("authErr").textContent);
w.CP.closeAuth(); await sleep(40);
ok("closing dismisses it", !$("authGate").classList.contains("on"));

console.log("\n── A signed-in recruiter ──");
w.CP.applySession({id:"r1",email:"rita@example.com",name:"Rita",
                   account_type:"recruiter",plan:"free",bench_limit:3});
await sleep(80);
ok("session is held", w.CP.SESSION.account_type==="recruiter");
ok("lands on the bench", w.CP.MODE==="recruiter");
ok("  bench page is showing", $("p-bench").classList.contains("on"));
ok("the mode switch is gone", d.querySelector(".modesw").style.display==="none");
ok("  because the account already answered that",
   d.body.dataset.role==="recruiter", d.body.dataset.role);
ok("recruiter nav visible", d.querySelector('.sbgroup[data-only="recruiter"]').style.display!=="none");
ok("seeker nav hidden", d.querySelector('.sbgroup[data-only="seeker"]').style.display==="none");
ok("who's signed in is shown", /rita@example.com/.test($("sbUser").textContent));
ok("  labelled Recruiter", /Recruiter/.test(d.querySelector(".sburole").textContent));
ok("  with a way out", !!d.querySelector(".sbsignout"));

console.log("\n── Hard separation in the client ──");
// The server 403s these anyway; this stops the UI from pretending otherwise.
w.CP.setMode("seeker"); await sleep(60);
ok("a recruiter can't switch to seeker mode", w.CP.MODE==="recruiter");
w.go("resume"); await sleep(60);
ok("  can't open the resume builder", !$("p-resume").classList.contains("on"));
ok("  gets sent to their own home", $("p-bench").classList.contains("on"));
w.go("me"); await sleep(60);
ok("  can't open the seeker profile", !$("p-me").classList.contains("on"));
w.go("jobs"); await sleep(60);
ok("  shared pages still open", $("p-jobs").classList.contains("on"));
w.go("plan"); await sleep(60);
ok("  billing is shared too", $("p-plan").classList.contains("on"));

console.log("\n── A signed-in seeker ──");
const w2=mk(); await sleep(700);
const d2=w2.document;
w2.CP.applySession({id:"s1",email:"sam@example.com",name:"Sam",
                    account_type:"seeker",plan:"pro"});
await sleep(80);
ok("lands on jobs", w2.CP.MODE==="seeker");
ok("  seeker nav visible", d2.querySelector('.sbgroup[data-only="seeker"]').style.display!=="none");
ok("  bench nav hidden", d2.querySelector('.sbgroup[data-only="recruiter"]').style.display==="none");
ok("  no mode switch either", d2.querySelector(".modesw").style.display==="none");
ok("  plan badge reflects the account",
   d2.getElementById("m-plan").textContent==="Pro", d2.getElementById("m-plan").textContent);
w2.CP.setMode("recruiter"); await sleep(60);
ok("a seeker can't switch to the bench", w2.CP.MODE==="seeker");
w2.go("bench"); await sleep(60);
ok("  and can't open it directly", !d2.getElementById("p-bench").classList.contains("on"));
ok("  no bench_limit shown to a seeker", w2.CP.SESSION.bench_limit===undefined);

console.log("\n── Sync only ever runs for a signed-in seeker ──");
// The rule that matters most: a browser sitting on seed data must not push it
// over a real account. Nothing is sent until the initial pull has finished.
const w3=mk(); await sleep(700);
ok("signed out, syncing is disarmed", w3.CP.SYNC_ARMED===false);
w3.CP.scheduleSync();
await sleep(60);
ok("  and scheduling it does nothing", w3.CP.SYNC_STATE==="idle", w3.CP.SYNC_STATE);
await w3.CP.pushSeekerData();
ok("  even pushing directly is a no-op", w3.CP.SYNC_STATE==="idle", w3.CP.SYNC_STATE);
await w3.CP.syncApplication({co:"X",ti:"Y",lo:"Z",st:"sent"});
ok("  and marking an application sends nothing", w3.CP.SYNC_STATE==="idle");

console.log("\n── Signing out leaves nothing behind ──");
// The bug this guards: SKEY holds positions, skills, applications AND the
// name/email/phone fields. Leaving it behind handed the next person at this
// browser the previous user's profile.
const SK="cp_state_v1";
ok("the profile blob is cleared on sign-out", w3.CP.ACCOUNT_KEYS.includes(SK),
   w3.CP.ACCOUNT_KEYS.join(","));
["cp_token","cp_role","cp_bench","cp_subs"].forEach(k=>
  ok(`  so is ${k}`, w3.CP.ACCOUNT_KEYS.includes(k)));
w3.localStorage.setItem(SK, JSON.stringify({exp:[{co:"Previous User Inc"}]}));
w3.localStorage.setItem("cp_token", JSON.stringify("tok"));
w3.CP.clearAccountData();
ok("clearing really removes the profile blob", w3.localStorage.getItem(SK)===null,
   String(w3.localStorage.getItem(SK)));
ok("  and the token", w3.localStorage.getItem("cp_token")===null);
ok("  and disarms sync so nothing is pushed after", w3.CP.SYNC_ARMED===false);

console.log("\n── Work authorization is never invented ──");
// The p-auth select ships with h1b marked selected, so an untouched form
// reads as H1B. That must not be persisted as if the user said it.
ok("unknown until the server or the user says so", w3.CP.WORK_AUTH_KNOWN===false);
ok("  even though the control shows a value",
   !!w3.document.getElementById("p-auth").value, w3.document.getElementById("p-auth").value);

console.log("\n── Dates the API will accept ──");
ok('"May 2024" becomes a real date', w3.CP.toISODate("May 2024")==="2024-05-01", w3.CP.toISODate("May 2024"));
ok('"Sep 2019" too', w3.CP.toISODate("Sep 2019")==="2019-09-01", w3.CP.toISODate("Sep 2019"));
ok('"Present" is null, not a date', w3.CP.toISODate("Present")===null);
ok("empty is null", w3.CP.toISODate("")===null);
ok("nonsense is null, never a bad date", w3.CP.toISODate("whenever")===null, w3.CP.toISODate("whenever"));
ok("a server id is recognised",
   w3.CP.isServerId("c76c4027-ea5f-4d33-b580-3ed83c013a9c"));
ok("  a demo integer id is not", !w3.CP.isServerId(3));
ok("  nor a short string", !w3.CP.isServerId("abc"));

console.log("\n── Every page is accounted for ──");
const pages=[...new Set([...d.querySelectorAll(".sbi[data-p]")].map(b=>b.dataset.p))];
const unmapped=pages.filter(p=>!(p in w.CP.PAGE_ROLE));
ok(`every sidebar page has a role mapping (${pages.length} pages)`,
   unmapped.length===0, unmapped.join(", "));
ok("both roles have somewhere to land",
   !!w.CP.HOME_PAGE.seeker && !!w.CP.HOME_PAGE.recruiter);

console.log(`\n${"─".repeat(46)}\nPASS ${P}    FAIL ${F}`);
fails.forEach(f=>console.log("  ✗",f));
process.exit(F?1:0);
})();
