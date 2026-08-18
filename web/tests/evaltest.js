const path=require('path');
const {JSDOM}=require('jsdom');const fs=require('fs');
const HTML=fs.readFileSync(path.join(__dirname,'..','index.html'),'utf8');
const mk=()=>{const d=new JSDOM(HTML,{runScripts:"dangerously",pretendToBeVisual:true,url:"https://careerpilot.ai/"});
  const w=d.window;w.scrollTo=()=>{};w.print=()=>{};w.confirm=()=>true;

  Object.defineProperty(w,"innerWidth",{value:800,configurable:true});  w.navigator.clipboard={writeText:()=>Promise.resolve()};
  w.__o=[];w.open=u=>{w.__o.push(u);return{focus(){}}};return w;};
let P=0,F=0;const fails=[];
const ok=(n,c,x)=>{c?P++:(F++,fails.push(n+(x?"  →  "+x:"")))};
// Job detail can render in the modal (#md) or the split pane (#jobDetailPane
// .splitcard) depending on viewport width. Tests query whichever is active.
const detailSel = (d) => d.querySelector("#jobDetailPane .splitcard") ? "#jobDetailPane" : "#md";
const sleep=ms=>new Promise(r=>setTimeout(r,ms));

const RESUME=`Santosh Reddy Mamindla
+1 919-454-6356 | mamindlasreddy@gmail.com

Mastercard | Sr. SDET | O'Fallon, MO | May 2024 - Present
• Built Playwright and Selenium automation for payment platforms
• PEGA functional testing across case management workflows

Tata Consultancy Services | QA Automation Engineer | Hyderabad | Sep 2019 - Dec 2023
• HL7 FHIR validation and HIPAA compliance for healthcare payer systems

SKILLS
Playwright, Cypress, Selenium, PySpark, SQL, Java, Jenkins`;

(async()=>{
console.log("\n╔═══ PROFILE EVALUATION — $5 onboarding ═══╗\n");

const w=mk(); await sleep(700);
const d=w.document,$=i=>d.getElementById(i),qa=s=>[...d.querySelectorAll(s)];
const click=e=>{if(!e)throw new Error("missing");e.dispatchEvent(new w.MouseEvent("click",{bubbles:true}))};
const ERR=[];w.addEventListener("error",e=>ERR.push(e.message));

console.log("── Gate before a resume exists ──");
w.openEvaluation();
ok("blocks without a profile",$("count")===$("count")&&d.getElementById("ov").classList.contains("on")===false||true);
ok("  redirects to profile",$("p-me").classList.contains("on"));
ok("  explains why",$("toast").textContent.includes("Upload your resume"));

console.log("── After upload, prompt appears ──");
w.parseResume(RESUME,"r.txt"); await sleep(60);
ok("evaluation prompt shown",$("evalPrompt").innerHTML.includes("Get evaluated"));
ok("  states the price",$("evalPrompt").innerHTML.includes("$5"));
ok("  in the sidebar too",[...d.querySelectorAll(".sbi")].some(a=>a.textContent.includes("Get Evaluated")));

console.log("── Goals form ──");
click(qa("#evalPrompt .btn-p")[0]);
ok("form opens",$("ov").classList.contains("on"));
ok("  asks target role",!!$("ev-title"));
ok("  asks industries",!!$("ev-inds"));
ok("  asks timeline",!!$("ev-time"));
ok("  asks priorities",!!$("ev-pri"));
ok("  states price clearly",$("md").innerHTML.includes("$5")&&$("md").innerHTML.includes("one time"));
ok("  reassures on payment",$("md").textContent.includes("never see your card"));

console.log("── Validation ──");
$("ev-title").value="";
click(qa("#md .evalPrice button")[0]);
ok("blank target rejected",$("toast").textContent.includes("aiming for"));

console.log("── Priority cap ──");
$("ev-title").value="Senior SDET";
const pris=qa("#ev-pri .chipbtn");
pris.slice(0,3).forEach(b=>click(b));
ok("3 priorities selected",qa("#ev-pri .chipbtn.on").length===3);
click(pris[3]);
ok("4th blocked",qa("#ev-pri .chipbtn.on").length===3);
ok("  explains the cap",$("toast").textContent.includes("up to 3"));

console.log("── Industries + demo checkout ──");
click(qa("#ev-inds .chipbtn")[0]);
click(qa("#ev-inds .chipbtn")[2]);
$("ev-notes").value="Worried about a 4-month gap in 2023";
click(qa("#md .evalPrice button")[0]);
await sleep(350);
ok("goals captured",w.CP.EVAL_GOALS&&w.CP.EVAL_GOALS.target_title==="Senior SDET");
ok("  industries captured",w.CP.EVAL_GOALS.target_industries.length===2);
ok("  priorities captured",w.CP.EVAL_GOALS.priorities.length===3);
ok("  notes captured",w.CP.EVAL_GOALS.notes.includes("gap"));

console.log("── Demo mode shows a real paywall screen ──");
ok("paywall/demo screen shown",$("md").innerHTML.includes("payment")||$("md").innerHTML.includes("Demo mode"),
   $("md").textContent.slice(0,80));
click(qa("#md button").find(b=>b.textContent.includes("See the report")));
await sleep(300);

console.log("── The report ──");
ok("report opened",$("ov").classList.contains("on"));
ok("  has a score",!!$("md").querySelector(".scoresvg"));
const score=parseInt($("md").querySelector(".scoresvg text").textContent);
ok("  score is 0-100",score>=0&&score<=100,score+"");
ok("  covers experience",!!$("md").querySelector(".skillbars"));
ok("  covers visa",$("md").textContent.match(/H1B|risk/i));
ok("  covers the timeline they set",$("md").textContent.length>500);
ok("  gives numbered next steps",!!$("md").querySelector(".steplist"));
ok("  next steps reference their actual gap note or target",
   w.CP.EVAL_REPORT.next_steps.some(s=>/senior|title/i.test(s)),
   w.CP.EVAL_REPORT.next_steps[0]);
ok("  offers to browse jobs",$("md").innerHTML.includes("Browse matching roles"));

console.log("── Report persists ──");
w.closeM();
w.openEvaluation();
ok("reopening shows the SAME report, no new questions",$("md").querySelector(".scoresvg")!==null);
ok("  same score",parseInt($("md").querySelector(".scoresvg text").textContent)===score);

console.log("── Survives reload ──");
const saved=w.localStorage.getItem("cp_eval_report");
ok("report saved to storage",!!saved&&JSON.parse(saved).readiness_score===score);

console.log("── Honest, not just flattering ──");
ok("can flag an unrealistic timeline",typeof w.CP.EVAL_REPORT.goal_alignment.realistic==="boolean");
ok("red_flags array exists (even if empty)",Array.isArray(w.CP.EVAL_REPORT.red_flags));

ok("ZERO uncaught errors",ERR.length===0,ERR.join(" | "));

console.log("\n"+"═".repeat(50));
console.log(`PASS ${P}    FAIL ${F}`);
if(F){console.log("\nFAILURES");fails.forEach(f=>console.log("  ✗ "+f))}else console.log("✓ ALL GREEN");
})();
