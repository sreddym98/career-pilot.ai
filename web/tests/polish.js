const path=require('path');
const {JSDOM}=require('jsdom');const fs=require('fs');
const HTML=fs.readFileSync(path.join(__dirname,'..','index.html'),'utf8');
const mk=()=>{const d=new JSDOM(HTML,{runScripts:"dangerously",pretendToBeVisual:true,url:"https://careerpilot.ai/"});
  const w=d.window;w.scrollTo=()=>{};w.print=()=>{};w.confirm=()=>true;

  Object.defineProperty(w,"innerWidth",{value:800,configurable:true});  w.navigator.clipboard={writeText:()=>Promise.resolve()};
  w.__opened=[];w.open=u=>{w.__opened.push(u);return{focus(){}}};return w;};
let P=0,F=0;const fails=[];
const ok=(n,c,x)=>{c?P++:(F++,fails.push(n+(x?"  →  "+x:"")))};
const sleep=ms=>new Promise(r=>setTimeout(r,ms));

const RESUME=`Santosh Reddy Mamindla
+1 919-454-6356 | mamindlasreddy@gmail.com

Mastercard | Sr. SDET | O'Fallon, MO | May 2024 - Present
• Built Playwright and Selenium automation for payment platforms with POM architecture
• Led ETL testing for payment pipelines with medallion lakehouse validation
• PEGA functional testing across case management and payment workflows

Tata Consultancy Services | QA Automation Engineer | Hyderabad | Sep 2019 - Dec 2023
• HL7 FHIR validation and HIPAA compliance for healthcare payer systems
• PySpark ETL frameworks across distributed big data environments

CashAPona | QA Engineer | Hyderabad | Sep 2018 - Jul 2019
• E-commerce checkout and payment gateway automation with Selenium

SKILLS
Playwright, Cypress, Selenium, RestAssured, Postman, PySpark, Redshift, SQL, Java, Python, Jenkins, Docker`;

(async()=>{
console.log("\n╔═══ PRODUCTION READINESS ═══╗\n");

// ── 1. survives refresh ──
console.log("── Nothing is lost on refresh ──");
{
const w=mk(); await sleep(650);
const d=w.document,$=i=>d.getElementById(i);
w.parseResume(RESUME,"my_resume.txt"); await sleep(60);
$("ab"+w.CP.EXP[0].id).value="An extra line I typed myself";
w.addBullet(w.CP.EXP[0].id);
w.applyTo(w.CP.J.find(j=>j.url).id);
$("p-li").value="linkedin.com/in/santoshreddy"; w.saveState();
const bullets=w.CP.EXP[0].b.length, apps=w.CP.APPS.length;

// reload, sharing the same storage
const w2=new JSDOM(HTML,{runScripts:"dangerously",pretendToBeVisual:true,url:"https://careerpilot.ai/",
  storageQuota:1e7}).window;
// jsdom gives each window its own storage, so replay through the same API
w2.scrollTo=()=>{};w2.open=()=>({focus(){}});
await sleep(650);
try{ w2.localStorage.setItem("cp_state_v1", w.localStorage.getItem("cp_state_v1")); }catch(e){}
const restored=w2.loadState();
ok("profile restored after reload",restored===true);
ok("  roles come back",w2.CP.EXP.length===3,w2.CP.EXP.length+"");
ok("  my typed bullet survived",w2.CP.EXP[0].b.length===bullets,w2.CP.EXP[0].b.length+" vs "+bullets);
ok("  applications survived",w2.CP.APPS.length===apps,w2.CP.APPS.length+" vs "+apps);
ok("  LinkedIn field survived",w2.document.getElementById("p-li").value.includes("santoshreddy"));
}

// ── 2. resume fully editable ──
console.log("── The resume is editable, not fixed ──");
{
const w=mk(); await sleep(650);
const d=w.document,$=i=>d.getElementById(i);
w.parseResume(RESUME,"r.txt"); await sleep(50);
w.go("resume");
w.fetch=(u,o)=>{const c=JSON.parse(o.body).messages[0].content;
  const hdr=c.includes("header of a senior");
  return Promise.resolve({ok:true,status:200,text:()=>Promise.resolve(JSON.stringify({content:[{type:"text",
    text:hdr?'{"summary":"Original summary text.","skill_groups":[{"label":"Automation","items":["Playwright","Cypress"]},{"label":"Data","items":["PySpark"]}]}'
      :'{"bullets":["First generated point about automation work","Second point","Third point"]}'}]}))});};
await w.buildResume(); await sleep(500);
ok("resume rendered",!!$("doc"));
ok("  it's marked editable",$("doc").classList.contains("editable"));
ok("  tells you it's editable",/Click any line to edit/.test($("b-out").innerHTML));
const eds=d.querySelectorAll("#doc [contenteditable]");
ok("  every part editable",eds.length>=8,eds.length+" fields");

// edit the summary
const sum=d.querySelector('[data-k="summary"]');
sum.textContent="My own rewritten summary."; w.syncEdit(sum);
ok("summary edit saved",w.CP.LAST.summary==="My own rewritten summary.",w.CP.LAST.summary);
// edit a bullet
const b0=d.querySelector('[data-k="bullet"][data-r="0"][data-b="0"]');
b0.textContent="I rewrote this line myself"; w.syncEdit(b0);
ok("bullet edit saved",w.CP.LAST.roles[0].bullets[0]==="I rewrote this line myself");
// rename a role
const rt=d.querySelector('[data-k="rtitle"][data-r="0"]');
rt.textContent="Mastercard — Principal SDET"; w.syncEdit(rt);
ok("role title edit saved",w.CP.LAST.roles[0].role==="Principal SDET",w.CP.LAST.roles[0].role);
// add and remove lines
const n0=w.CP.LAST.roles[0].bullets.length;
w.addBulletTo(0);
ok("can add a line",w.CP.LAST.roles[0].bullets.length===n0+1);
w.dropBullet(0,0);
ok("can remove a line",w.CP.LAST.roles[0].bullets.length===n0);
const sg=w.CP.LAST.skills.length;
w.dropSkillGroup(0);
ok("can remove a skill group",w.CP.LAST.skills.length===sg-1);
ok("  count updates live",$("bulletCount").textContent.includes("points"));
ok("  marked as edited",$("editState").textContent==="edited");
// last line protected
while(w.CP.LAST.roles[0].bullets.length>1)w.CP.LAST.roles[0].bullets.pop();
w.redrawDoc(); w.dropBullet(0,0);
ok("  won't delete the last line",w.CP.LAST.roles[0].bullets.length===1);
}

// ── 3. profile editing ──
console.log("── Profile is fully under your control ──");
{
const w=mk(); await sleep(650);
const d=w.document;
w.parseResume(RESUME,"r.txt"); await sleep(50);
w.go("me");
const first=w.CP.EXP[0].co;
w.moveRole(w.CP.EXP[0].id,1);
ok("roles reorder",w.CP.EXP[1].co===first,w.CP.EXP.map(e=>e.co).join(" → "));
ok("  up/down buttons render",d.querySelectorAll("#expList .mini").length>=4);
ok("  first row can't move up",d.querySelector("#expList .mini").disabled===true);
const n=w.CP.EXP.length;
w.delRole(w.CP.EXP[2].id);
ok("roles delete",w.CP.EXP.length===n-1);
while(w.CP.EXP.length>1)w.CP.EXP.pop();
w.renderProfile(); w.delRole(w.CP.EXP[0].id);
ok("  last role protected",w.CP.EXP.length===1);
}

// ── 4. sample links hit the right role ──
console.log("── Sample links target the exact job ──");
{
const w=mk(); await sleep(650);
const d=w.document;
let bad=[];
w.CP.J.filter(j=>j.url).forEach(j=>{
  const u=w.CP.sampleUrl(j);
  const q=decodeURIComponent(u).toLowerCase();
  const word=j.ti.toLowerCase().split(/[\s—–]+/).filter(x=>x.length>3)[0];
  if(!q.includes(word))bad.push(`${j.co}: "${word}" not in ${u.slice(0,60)}`);
});
ok("every sample search carries the job title",bad.length===0,bad.slice(0,2).join(" | "));
const mc=w.CP.J.find(j=>j.co==="Mastercard");
const u=w.CP.sampleUrl(mc);
ok("  Mastercard searches its title",decodeURIComponent(u.replace(/\+/g," ")).includes("Senior SDET"),u);
ok("  and it's a real host",u.startsWith("https://careers.mastercard.com"));
w.go("jobs");
ok("banner explains sample data",d.getElementById("sampleBar").style.display!=="none");
ok("  explains demo plainly",/Demo board/.test(d.getElementById("sampleBar").textContent));
ok("  no setup prompt for customers",!d.getElementById("sampleBar").querySelector("button"));
}

// ── 5. no dead ends anywhere ──
console.log("── Every button does something ──");
{
const w=mk(); await sleep(650);
const d=w.document;
w.parseResume(RESUME,"r.txt"); await sleep(50);
const errs=[];
w.addEventListener("error",e=>errs.push(e.message));
let clicked=0;
for(const p of ["jobs","me","apps","learn","people","resume","refer","plan"]){
  w.go(p);
  d.querySelectorAll(`#p-${p} button, #p-${p} a[onclick]`).forEach(b=>{
    try{ b.dispatchEvent(new w.MouseEvent("click",{bubbles:true})); clicked++;
      const ov=d.getElementById("ov");
      if(ov.classList.contains("on")){ w.closeM(); }
    }catch(e){ errs.push(`${p}: ${b.textContent.trim().slice(0,24)} — ${e.message}`); }
  });
}
ok(`${clicked} buttons clicked, none threw`,errs.length===0,errs.slice(0,2).join(" | "));
}

console.log("\n"+"═".repeat(50));
console.log(`PASS ${P}    FAIL ${F}`);
if(F){console.log("\nFAILURES");fails.forEach(f=>console.log("  ✗ "+f))}else console.log("✓ ALL GREEN");
})();
