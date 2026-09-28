const path=require('path');
const {JSDOM}=require('jsdom');const fs=require('fs');
const HTML=fs.readFileSync(path.join(__dirname,'..','index.html'),'utf8');
let P=0,F=0;const fails=[];
const ok=(n,c,x)=>{c?P++:(F++,fails.push(n+(x?"  →  "+x:"")))};
// Job detail can render in the modal (#md) or the split pane (#jobDetailPane
// .splitcard) depending on viewport width. Tests query whichever is active.
const detailSel = (d) => d.querySelector("#jobDetailPane .splitcard") ? "#jobDetailPane" : "#md";
const mk=(url="https://careerpilot.ai/")=>{
  const d=new JSDOM(HTML,{runScripts:"dangerously",pretendToBeVisual:true,url});
  const w=d.window;w.scrollTo=()=>{};w.print=()=>{};w.confirm=()=>true;

  Object.defineProperty(w,"innerWidth",{value:800,configurable:true});  w.navigator.clipboard={writeText:()=>Promise.resolve()};
  w.__o=[];w.open=u=>{w.__o.push(u);return{focus(){}}};return w;};
const sleep=ms=>new Promise(r=>setTimeout(r,ms));

(async()=>{
console.log("\n╔═══ WHAT A CUSTOMER CAN SEE ═══╗\n");
const w=mk(); await sleep(650);
const d=w.document,$=i=>d.getElementById(i);

console.log("── Nothing technical in the navigation ──");
const navItems=[...d.querySelectorAll(".sbi span:not(.sbbadge)")].map(a=>a.textContent.trim()).filter(Boolean);
ok("no 'Job feed' item",!navItems.some(m=>/feed/i.test(m)),navItems.join(" | "));
ok("no API or connect item",!navItems.some(m=>/\bapi\b|connect|setup|config/i.test(m)),navItems.join(" | "));
ok("sidebar has plain-English items only",
   navItems.length>0 && navItems.every(t=>/^[A-Za-z0-9 &\-]+$/.test(t)),
   navItems.join(", "));
const seekerVisible=[...d.querySelectorAll('.sbgroup[data-only="seeker"] .sbi span:not(.sbbadge)')].map(a=>a.textContent.trim());
ok("  seeker sidebar items visible",seekerVisible.length>=4,seekerVisible.join(", "));

console.log("── Demo notice reads like a product, not a TODO ──");
w.go("jobs");
const bar=$("sampleBar");
ok("demo notice shown",bar.style.display!=="none");
const bt=bar.textContent;
ok("  no 'backend'",!/backend/i.test(bt));
ok("  no 'aggregator'",!/aggregator/i.test(bt));
ok("  no 'connect' button",!bar.querySelector("button"),bar.querySelector("button")?.textContent||"none");
ok("  explains it plainly",/Demo board/.test(bt)&&/work exactly as they will/.test(bt),bt.trim().slice(0,80));

console.log("── Results line has no plumbing ──");
const cnt=$("count").textContent;
ok("no 'connect your job feed'",!/connect/i.test(cnt),cnt.slice(0,90));
ok("no 'samples — board offline'",!/offline/i.test(cnt));
ok("shows real counts",/full-time/.test(cnt)&&/contract/.test(cnt),cnt.slice(0,70));

console.log("── Setup is unreachable by clicking ──");
const clickable=[...d.querySelectorAll("[onclick]")]
  .filter(e=>/openConnect/.test(e.getAttribute("onclick")||""));
ok("nothing links to setup",clickable.length===0,clickable.map(e=>e.textContent.trim()).join(" | "));
ok("  but it still exists for you",typeof w.openConnect==="function");

console.log("── ?setup=1 opens it for the developer ──");
{
const w2=mk("https://careerpilot.ai/?setup=1"); await sleep(900);
ok("setup opens with the flag",w2.document.getElementById("ov").classList.contains("on"));
ok("  labelled internal",w2.document.getElementById("md").innerHTML.includes("Internal setup"));
ok("  says customers can't see it",w2.document.getElementById("md").innerHTML.includes("Not visible to customers"));
}

console.log("── Job detail speaks plainly ──");
w.openJob(w.CP.J[0].id);
// exclude the job description itself — employers legitimately write
// "data pipelines"; we're checking OUR copy, not theirs
const jd=$("jdBox"); const jdText=jd?jd.textContent:"";
const md=$("md").textContent.replace(jdText,"");
ok("no 'sample data'",!/sample data/i.test(md));
ok("no 'ingest' in our copy",!/\bingest\b/i.test(md));
ok("no 'backend' in our copy",!/\bbackend\b/i.test(md));
ok("says 'Example listing'",/Example listing/.test(md));
ok("  and what applying does",/live search/.test(md),md.match(/Applying opens[^.]*/)?.[0]||"");
w.closeM();

console.log("── Deep sweep of every page ──");
const BAD=/\b(api|endpoint|localhost|backend|ingest|aggregator|slug|schema|fingerprint|bearer|json|payload|env var|rapidapi|adzuna|cron|uvicorn|sqlite|postgres)\b/i;
for(const p of ["jobs","me","apps","learn","people","resume","refer","plan"]){
  w.go(p);
  let txt=$("p-"+p).textContent.replace(/\s+/g," ");
  // job descriptions are employer content, not our UI copy
  d.querySelectorAll("#p-"+p+" .jd").forEach(n=>{txt=txt.replace(n.textContent.replace(/\s+/g," "),"");});
  const hit=txt.match(BAD);
  ok(`${p} page is clean`,!hit,hit?`"${hit[0]}" in: ${txt.slice(Math.max(0,hit.index-40),hit.index+50)}`:"");
}

console.log("── Upload copy is human ──");
w.go("me");
const drop=$("drop").textContent;
ok("no file-format jargon",!/\.txt|\.md|mime|parse/i.test(drop),drop.replace(/\s+/g," ").slice(0,80));
ok("says PDF and Word",/PDF/.test(drop)&&/Word/.test(drop));
ok("reassures on privacy",/never leaves your machine/.test(drop));

console.log("\n"+"═".repeat(50));
console.log(`PASS ${P}    FAIL ${F}`);
if(F){console.log("\nFAILURES");fails.forEach(f=>console.log("  ✗ "+f))}else console.log("✓ ALL GREEN");
})();
