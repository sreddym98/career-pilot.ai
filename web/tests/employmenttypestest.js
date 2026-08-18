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

(async()=>{
console.log("\n╔═══ INTERNSHIP + PART-TIME + ENTERPRISE ═══╗\n");

const w=mk(); await sleep(700);
const d=w.document,$=i=>d.getElementById(i),qa=s=>[...d.querySelectorAll(s)];
const click=e=>{if(!e)throw new Error("missing");e.dispatchEvent(new w.MouseEvent("click",{bubbles:true}))};
const ERR=[];w.addEventListener("error",e=>ERR.push(e.message));

console.log("── Data integrity ──");
ok("total jobs is now 23",w.CP.J.length===23,w.CP.J.length+"");
ok("4 internships in data",w.CP.J.filter(j=>j.em==="internship").length===4);
ok("3 part-time roles in data",w.CP.J.filter(j=>j.em==="parttime").length===3);
const noJd = w.CP.J.filter(j=>j.id>=17 && j.id<=23 && (!j.jd || j.jd.length<50));
ok("every new job has a real JD",noJd.length===0,noJd.map(j=>j.id).join(","));
const noUrl = w.CP.J.filter(j=>j.id>=17 && j.id<=23 && !j.url);
ok("every new job has a real url",noUrl.length===0);

console.log("── Internship filter works ──");
$("f-type").value="internship";
$("f-type").dispatchEvent(new w.Event("change",{bubbles:true}));
await sleep(60);
ok("internship filter shows only internships",qa(".job").length===4,qa(".job").length+"");
ok("count line mentions internships",$("count").textContent.includes("internship"));

console.log("── Part-time filter works ──");
$("f-type").value="parttime";
$("f-type").dispatchEvent(new w.Event("change",{bubbles:true}));
await sleep(60);
ok("part-time filter respects H1B default — 1 sponsors, 2 correctly hidden",qa(".job").length===1,qa(".job").length+"");
ok("count line mentions part-time",$("count").textContent.includes("part-time"));

console.log("── Visa framing is realistic for students ──");
$("f-type").value="internship";
$("f-type").dispatchEvent(new w.Event("change",{bubbles:true}));
await sleep(60);
w.openJob(17);
const detailText = $("jobDetailPane") ? $("jobDetailPane").textContent : $("md").textContent;
ok("internship detail mentions CPT/F1, not H1B sponsorship promises",/CPT|F1/.test(detailText),detailText.slice(0,50));

console.log("── Enterprise tier exists and is reachable ──");
$("f-type").value="";
$("f-type").dispatchEvent(new w.Event("change",{bubbles:true}));
click(qa(".modeb").find(b=>b.dataset.m==="recruiter"));
await sleep(60);
w.go("plan");
await sleep(60);
const cards = qa('.pricegrid[data-only="recruiter"] .pricecard');
ok("recruiter-tier pricing card present",cards.length===1,cards.length+"");
const entCard = d.querySelector(".entcard");
ok("Enterprise now lives outside the recruiter-only grid",!!entCard);
ok("Enterprise has no specific dollar price shown",!/\$\d/.test(entCard.textContent));
ok("Enterprise CTA (Request a call) leads somewhere real (Support)",
   [...entCard.querySelectorAll("button")].some(b=>b.getAttribute("onclick")?.includes("go('support')")));
click([...entCard.querySelectorAll("button")].find(b=>b.getAttribute("onclick")?.includes("go('support')")));
await sleep(60);
ok("clicking Request a call actually navigates to Support",$("p-support").classList.contains("on"));

console.log("── Nothing else broke ──");
click(qa(".modeb").find(b=>b.dataset.m==="seeker"));
await sleep(60);
w.go("jobs");
await sleep(60);
ok("full job list still renders cleanly",qa(".job").length>0);

ok("ZERO uncaught errors",ERR.length===0,ERR.join(" | "));

console.log("\n"+"═".repeat(50));
console.log(`PASS ${P}    FAIL ${F}`);
if(F){console.log("\nFAILURES");fails.forEach(f=>console.log("  ✗ "+f))}else console.log("✓ ALL GREEN");
})();
