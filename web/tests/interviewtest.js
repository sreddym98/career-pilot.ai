const path=require('path');
const {JSDOM}=require('jsdom');const fs=require('fs');
const HTML=fs.readFileSync(path.join(__dirname,'..','index.html'),'utf8');
const mk=()=>{const d=new JSDOM(HTML,{runScripts:"dangerously",pretendToBeVisual:true,url:"https://careerpilot.ai/"});
  const w=d.window;w.scrollTo=()=>{};w.confirm=()=>true;
  Object.defineProperty(w,"innerWidth",{value:1280,configurable:true});
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
console.log("\n╔═══ MOCK INTERVIEW ═══╗\n");

const w=mk(); await sleep(700);
const d=w.document,$=i=>d.getElementById(i),qa=s=>[...d.querySelectorAll(s)];
const click=e=>{if(!e)throw new Error("missing");e.dispatchEvent(new w.MouseEvent("click",{bubbles:true}))};
const ERR=[];w.addEventListener("error",e=>ERR.push(e.message));

console.log("── Reachable from sidebar ──");
click(qa(".sbi[data-p]").find(b=>b.textContent.includes("Mock Interview")));
await sleep(60);
ok("navigates to interview page",$("p-interview").classList.contains("on"));

console.log("── Blocks without a resume ──");
click(qa("#p-interview .btn-p")[0]);
await sleep(60);
ok("redirects to profile",$("p-me").classList.contains("on"));
ok("  explains why",$("toast").textContent.includes("Upload your resume"));

console.log("── Requires a target role ──");
w.parseResume(RESUME,"r.txt"); await sleep(60);
w.go("interview");
click(qa("#p-interview .btn-p")[0]);
await sleep(60);
ok("blank title rejected",$("toast").textContent.includes("role you're preparing"));

console.log("── Generates in demo mode, grounded in real data ──");
$("iv-title").value="Senior SDET";
$("iv-company").value="Acme";
$("iv-jd").value="Looking for Playwright expertise.";
click(qa("#p-interview .btn-p")[0]);
await sleep(1100);
ok("output renders",$("iv-out").innerHTML.length>500);
ok("  skills tested shown",$("iv-out").innerHTML.includes("Skills this role tests"));
ok("  technical questions present",!!d.querySelector(".ivq"));
ok("  behavioral section present",$("iv-out").innerHTML.includes("Behavioral questions"));
ok("  answers reference the REAL company from the resume",$("iv-out").innerHTML.includes("Mastercard"));
ok("  weak spots / gaps section present",$("iv-out").innerHTML.includes("Worth addressing"));
ok("  questions to ask them present",$("iv-out").innerHTML.includes("Questions worth asking"));
ok("  marked as demo, not claimed as real",$("iv-out").innerHTML.includes("Demo mode"));
ok("  says rehearsal, not guarantee",$("iv-out").innerHTML.includes("not a guarantee"));

console.log("── Answers start collapsed, reveal on click ──");
const firstQ = d.querySelector(".ivqhead");
ok("body starts collapsed",!d.querySelector(".ivqbody").classList.contains("open"));
click(firstQ);
await sleep(60);
ok("clicking reveals the answer",d.querySelector(".ivqbody").classList.contains("open"));
click(firstQ);
await sleep(60);
ok("clicking again collapses it",!d.querySelector(".ivqbody").classList.contains("open"));

console.log("── Linked from a job's detail panel ──");
w.go("jobs");
const job = w.CP.J[0];
w.openJob(job.id);
await sleep(60);
const practiceBtn = [...d.querySelectorAll("button")].find(b=>b.textContent.includes("Practice interview"));
ok("practice-interview button exists on job detail",!!practiceBtn);
click(practiceBtn);
await sleep(60);
ok("navigates to interview page",$("p-interview").classList.contains("on"));
ok("  prefills the role from the job",$("iv-title").value===job.ti,$("iv-title").value);
ok("  prefills the company",$("iv-company").value===job.co);

console.log("── State persists across reload ──");
const saved = w.localStorage.getItem("cp_interview_last");
ok("last interview saved",!!saved && JSON.parse(saved).title);

ok("ZERO uncaught errors",ERR.length===0,ERR.join(" | "));

console.log("\n"+"═".repeat(50));
console.log(`PASS ${P}    FAIL ${F}`);
if(F){console.log("\nFAILURES");fails.forEach(f=>console.log("  ✗ "+f))}else console.log("✓ ALL GREEN");
})();
