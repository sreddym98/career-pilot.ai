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
console.log("\n╔═══ SUPPORT ═══╗\n");

const w=mk(); await sleep(700);
const d=w.document,$=i=>d.getElementById(i),qa=s=>[...d.querySelectorAll(s)];
const click=e=>{if(!e)throw new Error("missing");e.dispatchEvent(new w.MouseEvent("click",{bubbles:true}))};
const ERR=[];w.addEventListener("error",e=>ERR.push(e.message));

console.log("── Reachable from the sidebar ──");
click(qa(".sbi[data-p]").find(b=>b.textContent.includes("Support")));
await sleep(60);
ok("navigates to support page",$("p-support").classList.contains("on"));

console.log("── SLA is stated up front, not hidden ──");
const banner = $("slaBanner").textContent;
ok("states the response window before submitting",/\d+ hours/.test(banner));
ok("free plan sees 48 hours",banner.includes("48 hours"));
ok("offers the upsell honestly",$("slaBanner").innerHTML.includes("Pro cuts this to 4 hours"));

console.log("── Validation ──");
click($("sup-send"));
await sleep(60);
ok("blank submission rejected",$("sup-err").innerHTML.includes("subject"));
$("sup-subject").value="ab";
$("sup-message").value="short";
click($("sup-send"));
await sleep(60);
ok("too-short fields rejected",$("sup-err").innerHTML.includes("subject")||$("sup-err").innerHTML.includes("detail"));

console.log("── Character counter works ──");
$("sup-message").value="A real description of the problem I am having with the app.";
$("sup-message").dispatchEvent(new w.Event("input",{bubbles:true}));
await sleep(30);
ok("counter updates",$("sup-count").textContent.includes(String($("sup-message").value.length)));

console.log("── Demo mode is honest about not sending ──");
$("sup-subject").value="Resume upload not working";
click($("sup-send"));
await sleep(60);
ok("demo submission is HONEST — says nothing was actually sent",/demo mode/i.test($("toast").textContent)&&/nothing was actually sent/i.test($("toast").textContent),$("toast").textContent);
ok("  still records it locally so the person sees their history",w.CP.SUP_TICKETS.length>0);
ok("  history card appears",$("sup-history-card").style.display!=="none");
ok("  form clears after submit",$("sup-subject").value==="");

console.log("── Direct email fallback works ──");
$("sup-subject").value="A billing question";
$("sup-message").value="I was charged twice this month for the Pro plan.";
opened=[]; w.__o=[];
w.emailSupportDirect();
ok("mailto opens to the real support address",w.__o[0].startsWith("mailto:support@careerpilot.ai"),w.__o[0]);
ok("  carries the subject",decodeURIComponent(w.__o[0]).includes("billing question"));

console.log("── ZERO uncaught errors ──");
ok("no crashes anywhere in the flow",ERR.length===0,ERR.join(" | "));

console.log("\n"+"═".repeat(50));
console.log(`PASS ${P}    FAIL ${F}`);
if(F){console.log("\nFAILURES");fails.forEach(f=>console.log("  ✗ "+f))}else console.log("✓ ALL GREEN");
})();
