const path=require('path');
const {JSDOM}=require('jsdom');const fs=require('fs');
const HTML=fs.readFileSync(path.join(__dirname,'..','index.html'),'utf8');
const mk=(width)=>{const d=new JSDOM(HTML,{runScripts:"dangerously",pretendToBeVisual:true,url:"https://careerpilot.ai/"});
  const w=d.window;w.scrollTo=()=>{};w.print=()=>{};w.confirm=()=>true;w.requestAnimationFrame=cb=>setTimeout(cb,0);
  Object.defineProperty(w,"innerWidth",{value:width,configurable:true});
  w.navigator.clipboard={writeText:()=>Promise.resolve()};
  w.__o=[];w.open=u=>{w.__o.push(u);return{focus(){}}};return w;};
let P=0,F=0;const fails=[];
const ok=(n,c,x)=>{c?P++:(F++,fails.push(n+(x?"  →  "+x:"")))};
const sleep=ms=>new Promise(r=>setTimeout(r,ms));
const RESUME=`Santosh Reddy
+1 919-454-6356 | mamindlasreddy@gmail.com
Mastercard | Sr. SDET | O'Fallon, MO | May 2024 - Present
• Built Playwright and Selenium automation for payment platforms
SKILLS
Playwright, Cypress, Selenium, PySpark, SQL`;

(async()=>{
console.log("\n╔═══ SIDEBAR + SPLIT PANE ═══╗\n");

console.log("── Desktop: sidebar always visible, split pane ──");
{
const w=mk(1280); await sleep(700);
const d=w.document,$=i=>d.getElementById(i),qa=s=>[...d.querySelectorAll(s)];
const click=e=>{if(!e)throw new Error("missing");e.dispatchEvent(new w.MouseEvent("click",{bubbles:true}))};

ok("sidebar present",!!$("sidebar"));
ok("brand shows careerpilot.ai",$("sidebar").textContent.includes("careerpilot")&&$("sidebar").textContent.includes(".ai"));
ok("mode switch in sidebar",!!$("sidebar").querySelector(".modesw"));
ok("job search section",$("sidebar").textContent.includes("Explore Jobs")||$("sidebar").textContent.includes("Jobs"));
ok("workspace items always visible (no More menu)",
   qa(".sbi").some(b=>b.textContent.includes("Resume Builder"))&&
   qa(".sbi").some(b=>b.textContent.includes("Get Evaluated")),
   "resume+eval items present");
ok("no collapsed More dropdown exists",!$("more"));

click(qa(".sbi[data-p]").find(b=>b.textContent.includes("Applications")));
await sleep(60);
ok("sidebar nav switches pages",$("p-apps").classList.contains("on"));
ok("  active item highlighted",qa(".sbi.on").some(b=>b.textContent.includes("Applications")));

w.go("jobs");
ok("jobs page has split pane at desktop width",!!$("jobsSplit"));
ok("  list and detail both present",!!$("list")&&!!$("jobDetailPane"));
ok("  detail starts empty with a prompt",$("jobDetailPane").textContent.includes("Pick a role"));

const firstJob=w.CP.J[0];
click(d.querySelector(".job"));
await sleep(60);
ok("clicking a job fills the side panel",$("jobDetailPane").querySelector(".splitcard")!==null);
ok("  modal stays CLOSED (not used at this width)",!$("ov").classList.contains("on"));
ok("  the card is marked selected",d.querySelector(".job.selected")!==null);
ok("  list is still visible next to it",!!$("list").querySelector(".job"));


const secondCardTi = qa(".job h3")[1].textContent.trim();
click(qa(".job")[1]);
await sleep(60);
ok("clicking a different job replaces the panel content",$("jobDetailPane").textContent.includes(secondCardTi));
ok("  only one card selected at a time",qa(".job.selected").length===1);

click($("jobDetailPane").querySelector(".mx"));
await sleep(60);
ok("closing the panel deselects",qa(".job.selected").length===0);
ok("  panel returns to the empty state",$("jobDetailPane").textContent.includes("Pick a role"));
}

console.log("── Mobile: sidebar hidden by default, modal used ──");
{
const w=mk(700); await sleep(700);
const d=w.document,$=i=>d.getElementById(i),qa=s=>[...d.querySelectorAll(s)];
const click=e=>{if(!e)throw new Error("missing");e.dispatchEvent(new w.MouseEvent("click",{bubbles:true}))};

ok("mobile top bar shown",!!$("mobTop"));
ok("sidebar starts closed",!$("sidebar").classList.contains("open"));
click($("mobTop"));
await sleep(60);
ok("tapping the top bar opens the sidebar",$("sidebar").classList.contains("open"));
ok("  scrim appears behind it",$("sbScrim").classList.contains("on"));
click($("sbScrim"));
await sleep(60);
ok("tapping the scrim closes it",!$("sidebar").classList.contains("open"));

click(qa(".sbi[data-p]").find(b=>b.textContent.includes("Applications")));
await sleep(60);
ok("navigating auto-closes the sidebar on mobile",!$("sidebar").classList.contains("open"));

w.go("jobs");
click(d.querySelector(".job"));
await sleep(60);
ok("at mobile width, job detail opens in the MODAL",$("ov").classList.contains("on"));
ok("  split pane detail is not used",!$("jobDetailPane").querySelector(".splitcard"));
}

console.log("── Recruiter mode reflected in sidebar ──");
{
const w=mk(1280); await sleep(700);
const d=w.document,$=i=>d.getElementById(i),qa=s=>[...d.querySelectorAll(s)];
const click=e=>{if(!e)throw new Error("missing");e.dispatchEvent(new w.MouseEvent("click",{bubbles:true}))};
click(qa(".modeb").find(b=>b.dataset.m==="recruiter"));
await sleep(60);
ok("bench section appears",d.querySelector('.sbgroup[data-only="recruiter"]').style.display!=="none");
ok("seeker workspace section hides",d.querySelector('.sbgroup[data-only="seeker"]').style.display==="none");
ok("lands on My Bench",$("p-bench").classList.contains("on"));
}

console.log("── One thing pending: evaluation entry still reachable ──");
{
const w=mk(1280); await sleep(700);
const d=w.document,$=i=>d.getElementById(i),qa=s=>[...d.querySelectorAll(s)];
const click=e=>{if(!e)throw new Error("missing");e.dispatchEvent(new w.MouseEvent("click",{bubbles:true}))};
w.parseResume(RESUME,"r.txt"); await sleep(60);
click(qa(".sbi").find(b=>b.textContent.includes("Get Evaluated")));
await sleep(60);
ok("evaluation opens from the sidebar",$("ov").classList.contains("on"));
ok("  price badge shown in sidebar",qa(".sbbadge.price").some(b=>b.textContent==="$5"));
}

console.log("\n"+"═".repeat(50));
console.log(`PASS ${P}    FAIL ${F}`);
if(F){console.log("\nFAILURES");fails.forEach(f=>console.log("  ✗ "+f))}else console.log("✓ ALL GREEN");
})();
