const path=require('path');
const {JSDOM}=require('jsdom');const fs=require('fs');
const HTML=fs.readFileSync(path.join(__dirname,'..','index.html'),'utf8');
const mk=()=>{const d=new JSDOM(HTML,{runScripts:"dangerously",pretendToBeVisual:true,url:"https://careerpilot.ai/"});
  const w=d.window;w.scrollTo=()=>{};w.print=()=>{};w.confirm=()=>true;w.requestAnimationFrame=cb=>setTimeout(cb,0);

  Object.defineProperty(w,"innerWidth",{value:800,configurable:true});  w.navigator.clipboard={writeText:()=>Promise.resolve()};
  w.__o=[];w.open=u=>{w.__o.push(u);return{focus(){}}};return w;};
let P=0,F=0;const fails=[];
const ok=(n,c,x)=>{c?P++:(F++,fails.push(n+(x?"  →  "+x:"")))};
const sleep=ms=>new Promise(r=>setTimeout(r,ms));
const RESUME=`Santosh Reddy
+1 919-454-6356 | mamindlasreddy@gmail.com
Mastercard | Sr. SDET | O'Fallon, MO | May 2024 - Present
• Built Playwright and Selenium automation for payment platforms
Tata Consultancy Services | QA Automation Engineer | Hyderabad | Sep 2019 - Dec 2023
• HL7 FHIR validation and HIPAA compliance for healthcare payer systems
SKILLS
Playwright, Cypress, Selenium, PySpark, SQL, Java, Jenkins`;

async function runEval(w,d,$,qa,click,title,timeline){
  w.CP.resetProfile ? null : null;
  w.parseResume(RESUME,"r.txt"); await sleep(60);
  w.openEvaluation();
  $("ev-title").value=title;
  $("ev-time").value=timeline;
  click(qa("#md .evalPrice button")[0]);
  await sleep(350);
  click(qa("#md button").find(b=>b.textContent.includes("See the report")));
  await sleep(350);
}

(async()=>{
console.log("\n╔═══ EVALUATION → SUBSCRIPTION FUNNEL ═══╗\n");

console.log("── Infographics render ──");
{
const w=mk(); await sleep(700);
const d=w.document,$=i=>d.getElementById(i),qa=s=>[...d.querySelectorAll(s)];
const click=e=>{if(!e)throw new Error("missing");e.dispatchEvent(new w.MouseEvent("click",{bubbles:true}))};
await runEval(w,d,$,qa,click,"Senior SDET","Immediately");
ok("score arc SVG present",!!d.querySelector(".scoresvg svg, .scoresvg"));
ok("  real SVG element, not css",d.querySelector(".scoresvg").tagName.toLowerCase()==="svg");
ok("tri-axis panel (3 gauges)",d.querySelectorAll(".triitem").length===3,d.querySelectorAll(".triitem").length+"");
ok("  each has an SVG",d.querySelectorAll(".trisvg").length===3);
ok("skill bars render",!!d.querySelector(".skillbars"));
ok("  has fill bars",d.querySelectorAll(".sbfill").length>0);
ok("visa risk gauge",!!d.querySelector(".gaugesvg"));
ok("verdict block present",!!d.querySelector(".verdict"));
}

console.log("── Strong fit → pushes toward Pro ──");
{
const w=mk(); await sleep(700);
const d=w.document,$=i=>d.getElementById(i),qa=s=>[...d.querySelectorAll(s)];
const click=e=>{if(!e)throw new Error("missing");e.dispatchEvent(new w.MouseEvent("click",{bubbles:true}))};
// force a strong-fit scenario: senior title matched by real years, generous timeline
await runEval(w,d,$,qa,click,"QA Automation Engineer","3-6 months");
const score=w.CP.EVAL_REPORT.readiness_score;
const band=score>=75?"a":score>=50?"b":"c";
const cls={a:"good",b:"warn",c:"cool"}[band];
console.log(`   (scored ${score}, band ${band})`);
ok("verdict matches the band",!!d.querySelector(`.verdict.${cls}`),d.querySelector(".verdict")?.className);
if(band==="a"){
  ok("good band pitches Pro directly",d.querySelector(".verdict").innerHTML.includes("Pro"));
  ok("  names the price",d.querySelector(".verdict").innerHTML.includes("$19.99"));
}
click(qa(".verdict .btn-p, .verdict .btn-g").find(b=>b.textContent.includes("Pro")||b.textContent.includes("gaps"))
  || qa(".verdict button")[0]);
await sleep(60);
ok("navigates to Plan",$("p-plan").classList.contains("on"));
ok("  Plan shows evaluation context, not a cold pitch",$("planEvalNote").innerHTML.includes(String(score)));
ok("  context has its own mini gauge",!!d.querySelector(".planctxsvg"));
ok("  offers to review the evaluation again",$("planEvalNote").innerHTML.includes("Review evaluation"));
click(qa("#planEvalNote button")[0]);
await sleep(60);
ok("  re-opens the same report",$("ov").classList.contains("on")&&!!d.querySelector(".scoresvg"));
}

console.log("── Weak fit → does NOT push Pro first ──");
{
const w=mk(); await sleep(700);
const d=w.document,$=i=>d.getElementById(i),qa=s=>[...d.querySelectorAll(s)];
const click=e=>{if(!e)throw new Error("missing");e.dispatchEvent(new w.MouseEvent("click",{bubbles:true}))};
// deliberately mismatched: senior leadership title, immediate timeline, thin resume
await runEval(w,d,$,qa,click,"VP of Engineering","Immediately");
const score=w.CP.EVAL_REPORT.readiness_score;
const band=score>=75?"a":score>=50?"b":"c";
console.log(`   (scored ${score}, band ${band})`);
if(band==="c"){
  ok("weak band does NOT lead with Pro",!d.querySelector(".verdict").innerHTML.match(/^[\\s\\S]*Pro[\\s\\S]*btn-p/) || 
     !qa(".verdict .btn-p")[0]?.textContent.includes("Pro"),
     qa(".verdict button").map(b=>b.textContent).join(" | "));
  ok("  points to closing gaps instead",d.querySelector(".verdict").innerHTML.includes("gaps"));
  ok("  is honest that pushing hard now would waste effort",d.querySelector(".verdict").textContent.includes("rejections")||d.querySelector(".verdict").textContent.includes("structural"));
}
}

console.log("── Re-opening never re-asks or re-charges ──");
{
const w=mk(); await sleep(700);
const d=w.document,$=i=>d.getElementById(i),qa=s=>[...d.querySelectorAll(s)];
const click=e=>{if(!e)throw new Error("missing");e.dispatchEvent(new w.MouseEvent("click",{bubbles:true}))};
await runEval(w,d,$,qa,click,"Senior SDET","1-3 months");
const firstScore=w.CP.EVAL_REPORT.readiness_score;
w.closeM();
w.openEvaluation();
ok("same report, no new payment screen",d.querySelector(".scoresvg")&&
   parseInt(d.querySelector(".scoresvg text").textContent)===firstScore);
ok("  no goals form shown again",!d.getElementById("ev-title"));
}

console.log("\n"+"═".repeat(50));
console.log(`PASS ${P}    FAIL ${F}`);
if(F){console.log("\nFAILURES");fails.forEach(f=>console.log("  ✗ "+f))}else console.log("✓ ALL GREEN");
})();
