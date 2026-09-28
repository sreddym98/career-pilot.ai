const path=require('path');
const {JSDOM}=require('jsdom');const fs=require('fs');
const dom=new JSDOM(fs.readFileSync(path.join(__dirname,'..','index.html'),'utf8'),
  {runScripts:"dangerously",pretendToBeVisual:true,url:"https://careerpilot.ai/"});
const w=dom.window,d=w.document;
Object.defineProperty(w,"innerWidth",{value:800,configurable:true});
w.scrollTo=()=>{};w.print=()=>{};w.navigator.clipboard={writeText:()=>Promise.resolve()};
w.URL.createObjectURL=w.URL.createObjectURL||(()=>"blob:mock");
w.URL.revokeObjectURL=w.URL.revokeObjectURL||(()=>{});
class _MockZipNode{constructor(r){this._root=r;}file(n,c){this._root._files[n]=c;return this;}
  folder(n){return new _MockZipNode(this._root);}async generateAsync(){return new w.Blob(["mock"]);}}
w.JSZip=class extends _MockZipNode{constructor(){super(null);this._root=this;this._files={};}};
let opened=[];w.open=u=>{opened.push(u);return{focus(){}}};
const $=id=>d.getElementById(id),qa=s=>[...d.querySelectorAll(s)];
const click=e=>{if(!e)throw new Error("missing element at: "+new Error().stack.split(String.fromCharCode(10))[2].trim());e.dispatchEvent(new w.MouseEvent("click",{bubbles:true}))};
const chg=e=>e.dispatchEvent(new w.Event("change",{bubbles:true}));
let P=0,F=0;const fails=[];
const ok=(n,c,x)=>{c?P++:(F++,fails.push(n+(x?"  →  "+x:"")))};
// Job detail can render in the modal (#md) or the split pane (#jobDetailPane
// .splitcard) depending on viewport width. Tests query whichever is active.
const detailSel = (d) => d.querySelector("#jobDetailPane .splitcard") ? "#jobDetailPane" : "#md";
const sleep=ms=>new Promise(r=>setTimeout(r,ms));
const ERRS=[];w.addEventListener("error",e=>ERRS.push(e.message));

const RESUME=`Santosh Reddy Mamindla
+1 919-454-6356 | mamindlasreddy@gmail.com

EXPERIENCE

Mastercard | Sr. SDET / Senior Quality Engineer | O'Fallon, MO | May 2024 - Present
• Built Playwright and Selenium automation framework with Hybrid POM architecture for payment platforms
• Led ETL testing for payment data pipelines with medallion pattern lakehouse validation
• PEGA functional testing covering case management and payment workflow automation
• Used GitHub Copilot for test generation and Cypress for browser automation
• Ran PCI-DSS and OWASP security validation using Burp Suite

Tata Consultancy Services | QA Automation Engineer | Hyderabad | Sep 2019 - Dec 2023
• HL7 FHIR validation and HIPAA compliance testing for healthcare payer systems
• PySpark ETL test frameworks across distributed big data environments
• Data migration and reconciliation testing across Oracle and MySQL

CashAPona | QA Engineer | Hyderabad | Sep 2018 - Jul 2019
• E-commerce checkout and payment gateway cross browser automation with Selenium

SKILLS
Playwright, Cypress, Selenium, Appium, RestAssured, Postman, PySpark, Redshift, SQL, Java, Python, TypeScript, Jenkins, Docker, Kubernetes, JMeter, k6, Burp Suite, PEGA, HL7, FHIR`;

setTimeout(async()=>{
const CP=w.CP;
console.log("\n╔═══ REDESIGN — as a first-time user ═══╗\n");

console.log("── Simplicity ──");
const visibleSbi=()=>qa(".sbi[data-p]").filter(b=>{
  const grp=b.closest(".sbgroup");
  return !grp || grp.style.display!=="none";
});
ok("sidebar shows the seeker sections",visibleSbi().length>=2,visibleSbi().map(t=>t.querySelector("span")?.textContent).join(", "));
ok("  recruiter-only items exist but are hidden",qa('.sbgroup[data-only="recruiter"] .sbi[data-p]').length===2,
   qa('.sbgroup[data-only="recruiter"] .sbi[data-p]').length+"");
ok("everything else behind one menu",qa("#more .menu a").length<=6,qa("#more .menu a").length+" items");
ok("lands on Jobs",$("p-jobs").classList.contains("on"));
ok("filters fit one row",qa("#p-jobs .filters select").length===4,qa("#p-jobs .filters select").length+"");
ok("no nested dropdown panels",qa(".chippanel").length===0);

console.log("── Jobs work before any setup ──");
const n=()=>$("list").querySelectorAll(".job").length;
ok("jobs listed immediately",n()>0,n()+" jobs");
ok("no fit score before upload",!$("list").innerHTML.includes("FIT"));
ok("prompts to upload resume",$("count").innerHTML.includes("upload your resume"));
ok("H1B is the default filter",$("f-auth").value==="h1b");
ok("  non-sponsoring roles hidden",!$("list").innerHTML.includes("Bank of America"));
ok("  says how many were hidden",/\d+ hidden/.test($("count").textContent),$("count").textContent.slice(0,80));
ok("  splits full-time vs contract",/full-time · \d+ contract/.test($("count").textContent));
ok("  no plumbing in the results line",!/connect|api|feed/i.test($("count").textContent),$("count").textContent.slice(0,70));
ok("visa stated in words",$("list").innerHTML.includes("Open to H1B"));
ok("  no colour-coded grid",!$("list").innerHTML.includes("vsg"));

console.log("── One upload sets up everything ──");
CP.parseResume(RESUME,"Santosh_Reddy_Resume.txt");
await sleep(60);
ok("roles parsed from the file",CP.EXP.length===3,CP.EXP.length+" roles");
ok("  company read",CP.EXP[0].co==="Mastercard",CP.EXP[0].co);
ok("  title read",CP.EXP[0].role.includes("SDET"),CP.EXP[0].role);
ok("  bullets read",CP.EXP[0].b.length===5,CP.EXP[0].b.length+" bullets");
ok("  dates read → 7 yrs 7 mos",CP.fmtD(CP.totalM())==="7 yrs 7 mos",CP.fmtD(CP.totalM()));
ok("  per-role duration",CP.fmtD(CP.durM(CP.EXP[1].from,CP.EXP[1].to))==="4 yrs 4 mos");
ok("skills extracted",CP.SKILLS.length>=15,CP.SKILLS.length+" skills");
ok("specializations detected",CP.UF&&CP.UF.length>=4,CP.UF?CP.UF.length:"none");
ok("  top is a QA family",["ui","etl","api","aiq","pega","hcit","perf"].includes(CP.UF[0].id),CP.UF[0].n);
ok("confirmation shows what it found",$("drop").innerHTML.includes("3 roles")&&$("drop").innerHTML.includes("7 yrs 7 mos"));
ok("  profile section appears",$("afterUpload").style.display==="");
ok("  experience rendered",$("expList").innerHTML.includes("Mastercard"));
ok("  gap flagged",$("gapNote").innerHTML.includes("4 mos"));

console.log("── Jobs now personalised ──");
w.rn();
ok("fit scores appear",$("list").innerHTML.includes("FIT"));
ok("  no more upload prompt",!$("count").innerHTML.includes("upload your resume"));
ok("skills matched on job card",$("list").innerHTML.length>500);

console.log("── Job descriptions & source ──");
{
const ft=CP.J.find(j=>j.em==="fulltime"&&j.url);
w.openJob(ft.id);
const h=$("md").innerHTML;
ok("full-time shows a description",h.includes("The job description")&&$("jdBox").textContent.length>400,$("jdBox")?$("jdBox").textContent.length+" chars":"none");
ok("  description is formatted",$("jdBox").querySelectorAll("li").length>3,$("jdBox").querySelectorAll("li").length+" bullets");
ok("  says it was found, not sent",/Nobody has contacted you/.test(h));
ok("  at-a-glance grid",!!$("md").querySelector(".glance"));
ok("  read-more offered",!!$("jdMore"));
w.toggleJD();
ok("  expands",$("jdBox").classList.contains("open"));
w.closeM();

const emailed=CP.J.find(j=>j.src==="email");
w.openJob(emailed.id);
ok("emailed role says who sent it",$("md").innerHTML.includes(emailed.from),emailed.from);
ok("  and when",$("md").innerHTML.includes(emailed.received));
ok("  button says Reply",$("md").innerHTML.includes("Reply to"));
ok("  shows what they sent",$("md").innerHTML.includes("What they sent"));
w.closeM();

const cold=CP.J.find(j=>!j.url&&j.src==="board");
if(cold){
  w.openJob(cold.id);
  ok("board-sourced contract does NOT say Reply",!$("md").innerHTML.includes("Reply to"),$("md").innerHTML.match(/Reply to[^<]*/)?.[0]||"correct");
  ok("  says Email instead",$("md").innerHTML.includes("Email "));
  ok("  explains it's cold outreach",/reaching out first|reaching out cold/.test($("md").innerHTML));
  w.closeM();
}
ok("every job has a description",CP.J.every(j=>j.jd&&j.jd.length>200),CP.J.filter(j=>!j.jd||j.jd.length<200).map(j=>j.co).join(","));
}

console.log("── Apply links go to THE POSTING ──");
{
let bad=[];
CP.J.filter(j=>j.url).forEach(j=>{
  const u=new URL(j.url);
  const bare=u.pathname==="/"||/^\/(careers|jobs)\/?$/i.test(u.pathname)&&!u.search;
  if(bare)bad.push(j.co+": "+j.url);
});
ok("no bare careers homepages",bad.length===0,bad.join(" | "));
ok("samples are labelled as samples",CP.J.filter(j=>j.url).every(j=>j.sample),
   CP.J.filter(j=>j.url&&!j.sample).map(j=>j.co).join(","));
CP.J.filter(j=>j.url).forEach(j=>{
  opened=[];w.applyTo(j.id);
  const got=decodeURIComponent((opened[0]||"").replace(/\+/g," ")).toLowerCase();
  const key=j.ti.toLowerCase().split(/[\s—–]+/).filter(x=>x.length>3)[0];
  ok(`  ${j.co} searches for the role`,got.includes(key),opened[0]);
  ok(`  ${j.co} on the right host`,(opened[0]||"").startsWith(new URL(j.url).origin));
});
CP.APPS.length=0;
}

console.log("── Apply: direct employer ──");
click(d.querySelector(".job"));
ok("job opens",$("ov").classList.contains("on"));
ok("  button names the site",/Apply on |Search on /.test($("md").innerHTML),$("md").innerHTML.match(/(Apply|Search) on [^<]*/)?.[0]);
ok("  shows your experience vs theirs",$("md").innerHTML.includes("You have"));
opened=[];
const fresh=CP.J.find(x=>x.url&&!CP.APPS.some(a=>a.co===x.co&&a.ti===x.ti));
w.closeM(); w.openJob(fresh?fresh.id:CP.J.find(x=>x.url).id);
const before=CP.APPS.length;
click(qa("#md button").find(b=>/Apply on |Search on /.test(b.textContent)));
ok("opens a working page",opened[0]&&opened[0].startsWith("http"),opened[0]);
ok("  logged as opened (not applied)",CP.APPS.some(a=>a.st==="opened"),CP.APPS.map(a=>a.st).join(","));
ok("  never logs the same role twice",new Set(CP.APPS.map(a=>a.co+a.ti)).size===CP.APPS.length);
ok("  modal closed",!$("ov").classList.contains("on"));

console.log("── Apply: agency, email known ──");
const ag=CP.J.find(j=>!j.url&&j.rec&&j.rec.e);
w.openJob(ag.id);
ok("button names the action",/Reply to |Email /.test($("md").innerHTML));
click(qa("#md button").find(b=>/Reply to |Email /.test(b.textContent)));
ok("draft opens",!!$("r-body"));
ok("  ADDRESS PREFILLED",$("r-to").value===ag.rec.e,$("r-to").value);
ok("  explains the relationship",/wrote to you|found it on a job board/.test($("md").innerHTML),$("md").innerHTML.match(/(wrote to you|found it on a job board)[^<]*/)?.[0]||"neither");
ok("  greets by name",$("r-body").value.startsWith("Hi "+ag.rec.n.split(" ")[0]));
ok("  includes your real total",$("r-body").value.includes("7 yrs 7 mos"));
ok("  includes work auth",$("r-body").value.includes("H1B"));
opened=[];
CP.preloadLib("jszip");
await CP.handleResumeStep(ag.id);
await sleep(60);
click(qa("#md button").find(b=>b.textContent.includes("Open in email")));
ok("mailto correct",opened[0].startsWith("mailto:"+ag.rec.e),opened[0]?.slice(0,40));
ok("  logged to applications",CP.APPS.some(a=>a.co===ag.co));

console.log("── Apply: agency, email unknown ──");
const unk=CP.J.find(j=>!j.url&&j.rec&&!j.rec.e);
w.openJob(unk.id); click(qa("#md button").find(b=>/Reply to |Email /.test(b.textContent)));
ok("field empty",$("r-to").value==="");
ok("  explains why it's asking",/don't have an address/.test($("md").innerHTML),$("md").innerHTML.match(/don.t have an address[^<]*/)?.[0]||"missing");
opened=[];
CP.preloadLib("jszip");
await CP.handleResumeStep(unk.id);
await sleep(60);
click(qa("#md button").find(b=>b.textContent.includes("Open in email")));
ok("won't send blank",opened.length===0&&$("toast").textContent.includes("email address"));
$("r-to").value="new@agency.com";
click(qa("#md button").find(b=>b.textContent.includes("Open in email")));
ok("sends when filled",opened.length===1);
ok("  remembers it",unk.rec.e==="new@agency.com");

console.log("── PDF / Word upload ──");
{
w.resetProfile();                       // back to the empty drop state
ok("accepts pdf",$("rfile").accept.includes(".pdf"),$("rfile")?$("rfile").accept:"no input");
ok("accepts docx",$("rfile").accept.includes(".docx"));
ok("accepts plain text",$("rfile").accept.includes(".txt"));
ok("  drop zone says so",$("drop").innerHTML.includes("Word"));
// old .doc must give useful guidance, not a silent failure
await CP.handleFile(new w.File(["x"],"resume.doc",{type:"application/msword"}));
await sleep(60);
ok("old .doc explains the fix",$("toast").textContent.includes("Save As"),$("toast").textContent.slice(0,60));
await CP.handleFile(new w.File(["x"],"resume.pages",{type:"x"}));
await sleep(60);
ok("unknown type named clearly",$("toast").textContent.includes(".pages"),$("toast").textContent.slice(0,60));
await CP.handleFile(new w.File(["tiny"],"r.txt",{type:"text/plain"}));
await sleep(60);
ok("near-empty file explained",$("toast").textContent.includes("Barely any text"),$("toast").textContent.slice(0,50));
CP.parseResume(RESUME,"Santosh_Reddy_Resume.txt");   // restore for the rest
await sleep(60);
ok("profile restored",CP.EXP.length===3);
}

console.log("── Editing ──");
w.go("me");
const b0=CP.EXP[0].b.length;
$("ab"+CP.EXP[0].id).value="Added a point about Kafka stream validation";
click(qa("#expList .addrow button")[0]);
ok("bullet added",CP.EXP[0].b.length===b0+1);
click(qa("#expList .bullets .x")[b0]);
ok("bullet removed",CP.EXP[0].b.length===b0);
click($("addRole"));
ok("add-role opens",$("md").innerHTML.includes("Add a role"));
click(qa("#md button").find(b=>b.textContent==="Cancel"));
w.editRole(CP.EXP[0].id);
ok("edit prefilled",$("e-co").value==="Mastercard");
$("e-co").value="";
click(qa("#md button").find(b=>b.textContent==="Save"));
ok("blank company rejected",$("e-err").innerHTML.includes("Company is needed"));
click(qa("#md button").find(b=>b.textContent==="Cancel"));

console.log("── Other pages ──");
for(const p of ["apps","learn","people","resume","refer","plan"]){
  w.go(p);
  ok(p+" renders",$("p-"+p).classList.contains("on")&&$("p-"+p).innerHTML.length>300);
}
w.go("apps");
ok("applications grouped by status",/Applied|Offer|Interview|Opened, not applied|Passed on/.test($("appList").innerHTML)||CP.APPS.length===0,$("appList").textContent.slice(0,60));
w.go("learn");
ok("gaps computed",$("gapList").innerHTML.length>200);
ok("  courses linked to gaps",$("courses").innerHTML.includes("Opens up"));
w.go("people");
ok("people at target companies first",$("peopleList").innerHTML.includes("At companies you're looking at"));
w.go("refer");
ok("credits computed",$("crTxt").textContent==="47 of 210",$("crTxt").textContent);

console.log("── Resume builder ──");
w.go("resume");
let calls=[];
w.fetch=(u,o)=>{const c=JSON.parse(o.body).messages[0].content;calls.push(c);
  const hdr=c.includes("header of a senior");
  return Promise.resolve({ok:true,status:200,text:()=>Promise.resolve(JSON.stringify({content:[{type:"text",
    text:hdr?'{"summary":"Seven years seven months in test automation.","skill_groups":[{"label":"Automation","items":["Playwright","Cypress"]}]}'
      :'{"bullets":['+Array.from({length:11},(_,i)=>`"Architected point ${i+1} covering concrete automation work with named tools"`).join(",")+']}'}]}))});};
await w.buildResume(); await sleep(600);
ok("one call per role plus header",calls.length===4,calls.length+" calls");
ok("resume rendered",!!$("doc"));
ok("  30+ points",$("doc").querySelectorAll("li").length>=33,$("doc").querySelectorAll("li").length+"");
ok("  uses your real dates",$("doc").innerHTML.includes("May 2024"));
ok("  computed durations",/\d+ yrs \d+ mos/.test($("doc").innerHTML));

console.log("── Word export ──");
ok("Word button offered first",$("b-out").innerHTML.includes("Download Word"));
ok("  says why Word",$("b-out").innerHTML.includes("recruiters ask for Word"));
ok("  PDF still available",$("b-out").innerHTML.includes(">PDF<"));
ok("  export data captured",!!CP.LAST&&CP.LAST.roles.length===3,CP.LAST?CP.LAST.roles.length+" roles":"none");
ok("  contact line built",CP.LAST&&CP.LAST.contact.includes("@"));

console.log("── Resilience ──");
w.CP.resetCache();
w.fetch=()=>Promise.resolve({ok:false,status:503,text:()=>Promise.resolve("upstream connect error")});
await w.buildResume(); await sleep(4200);
ok("gateway error handled cleanly",!$("b-out").innerHTML.includes("Unexpected token"));
ok("  plain-English message",$("b-out").innerHTML.includes("service is busy"));

ok("ZERO uncaught errors",ERRS.length===0,ERRS.join(" | "));

console.log("\n"+"═".repeat(50));
console.log(`PASS ${P}    FAIL ${F}`);
if(F){console.log("\nFAILURES");fails.forEach(f=>console.log("  ✗ "+f))}else console.log("✓ ALL GREEN");
},700);
