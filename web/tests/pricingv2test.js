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
console.log("\n╔═══ TERM PRICING + ENTERPRISE VISIBILITY ═══╗\n");

const w=mk(); await sleep(700);
const d=w.document,$=i=>d.getElementById(i),qa=s=>[...d.querySelectorAll(s)];
const click=e=>{if(!e)throw new Error("missing");e.dispatchEvent(new w.MouseEvent("click",{bubbles:true}))};
const ERR=[];w.addEventListener("error",e=>ERR.push(e.message));

console.log("── Term picker exists with correct default ──");
w.go("plan");
await sleep(60);
ok("term picker rendered",!!$("termpicker"));
ok("3 term options",qa(".termbtn").length===3,qa(".termbtn").length+"");
ok("1-month selected by default",qa(".termbtn.on").length===1&&qa(".termbtn.on")[0].dataset.term==="1");
ok("default price shown is $119.99",$("pro-price").textContent==="$119.99");

console.log("── Clicking 3-month updates price and savings ──");
click(qa(".termbtn").find(b=>b.dataset.term==="3"));
await sleep(60);
ok("price updates to $99.99",$("pro-price").textContent==="$99.99");
ok("sub-line mentions the savings",$("pro-sub").textContent.includes("save $20/mo")||$("pro-sub").textContent.includes("$20"));
ok("CTA button text updates too",$("pro-cta").textContent.includes("99.99"));
ok("only one chip marked selected",qa(".termbtn.on").length===1);

console.log("── Clicking 6-month shows the bigger discount ──");
click(qa(".termbtn").find(b=>b.dataset.term==="6"));
await sleep(60);
ok("price updates to $89.99",$("pro-price").textContent==="$89.99");
ok("mentions $30 savings",$("pro-sub").textContent.includes("$30"));

console.log("── The selected term actually reaches checkout ──");
w.CP.selectTerm ? null : null;
click(qa(".termbtn").find(b=>b.dataset.term==="6"));
await sleep(60);
click($("pro-cta"));
await sleep(60);
ok("demo checkout mentions the term",$("toast").textContent.includes("6-month")||$("toast").textContent.includes("term"),$("toast").textContent);

console.log("── Enterprise is visible in SEEKER mode, not gated by mode ──");
ok("Enterprise card present without toggling to recruiter",
   [...d.querySelectorAll(".entcard")].length>0);
const entCard = d.querySelector(".entcard");
ok("mentions universities",entCard.textContent.toLowerCase().includes("universit"));
ok("mentions consultants",entCard.textContent.toLowerCase().includes("consultant"));
ok("mentions staffing agencies",entCard.textContent.toLowerCase().includes("agenc")||entCard.textContent.toLowerCase().includes("staffing"));
ok("shows NO specific dollar price",!/\\$\\d/.test(entCard.textContent));
ok("mentions email contact",entCard.innerHTML.includes("mailto:support@careerpilot.ai"));
ok("  uses the REAL configured support address, not a fake sales@ inbox",
   entCard.innerHTML.includes("support@careerpilot.ai") && !entCard.innerHTML.includes("sales@"));
ok("offers a call/contact path too",entCard.textContent.toLowerCase().includes("call"));

console.log("── Enterprise is STILL visible after switching to recruiter mode ──");
click(qa(".modeb").find(b=>b.dataset.m==="recruiter"));
await sleep(60);
w.go("plan");
await sleep(60);
ok("Enterprise card still present in recruiter mode",d.querySelector(".entcard")!==null);
ok("recruiter-tier card ALSO present",d.querySelector('.pricegrid[data-only="recruiter"] .pricecard')!==null);

console.log("── Clicking 'Request a call' routes to Support, doesn't fake a phone number ──");
const callBtn = [...entCard.querySelectorAll("button")].find(b=>b.textContent.includes("call"));
click(callBtn);
await sleep(60);
ok("routes to the real Support page",$("p-support").classList.contains("on"));

ok("ZERO uncaught errors",ERR.length===0,ERR.join(" | "));

console.log("\n"+"═".repeat(50));
console.log(`PASS ${P}    FAIL ${F}`);
if(F){console.log("\nFAILURES");fails.forEach(f=>console.log("  ✗ "+f))}else console.log("✓ ALL GREEN");
})();
