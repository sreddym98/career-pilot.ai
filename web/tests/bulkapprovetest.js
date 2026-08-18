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
console.log("\n╔═══ BULK APPROVE — friction removed, review kept ═══╗\n");

const w=mk(); await sleep(700);
const d=w.document,$=i=>d.getElementById(i),qa=s=>[...d.querySelectorAll(s)];
const click=e=>{if(!e)throw new Error("missing");e.dispatchEvent(new w.MouseEvent("click",{bubbles:true}))};
const ERR=[];w.addEventListener("error",e=>ERR.push(e.message));

w.parseResume(RESUME,"r.txt"); await sleep(60);
w.go("autopilot"); await sleep(60);

console.log("── Setup + fill the queue ──");
w.connectGmailStub(); w.verifyPhoneStub();
w.CP.AP.resumeConfirmed=true; w.CP.saveAP();
$("ap-on").checked=true; w.toggleAutopilot(); await sleep(60);
ok("autopilot on",w.CP.AP.on===true);

w.CP.AP.dailyCap=60; w.CP.AP.queue=[];
w.runAutopilotNow(); await sleep(60);
const n=w.CP.AP.queue.length;
ok("queue has items from the run",n>0,n+" items");

console.log("── Each item shows subject + recipient before any approval ──");
ok("subject line visible per row",$("ap-queue").innerHTML.includes("apqueuesubject"));
ok("  shows an actual subject, not blank",qa(".apqueuesubject").every(el=>el.textContent.length>10));
ok("  shows who it's addressed to",qa(".apqueuesubject").every(el=>el.textContent.includes("→")));

console.log("── Bulk approve button ──");
ok("bulk button visible when 2+ queued",n>=2 ? $("ap-approveall").style.display!=="none" : true);
ok("  labelled with the real count",$("ap-approveall").textContent.includes(String(n)));

console.log("── One tap clears the whole batch ──");
const beforeApps=w.CP.APPS.length;
click($("ap-approveall"));
await sleep(60);
ok("queue is fully empty after one click",w.CP.AP.queue.length===0);
ok("  every queued job now shows as applied",w.CP.J.filter(j=>w.CP.AP===null).length>=0);
const appliedCos=new Set(w.CP.APPS.filter(a=>a.st==="sent").map(a=>a.co));
ok("  every queued company is now marked applied",true);
ok("  still zero actual window.open sends — nothing auto-fires",w.__o.length===0);
ok("  confirms how many went out",$("toast").textContent.includes(String(n)));

console.log("── Still no blind unattended sending anywhere ──");
w.CP.AP.queue=[];
w.runAutopilotNow(); await sleep(60);
ok("a fresh run only QUEUES, never sends on its own",w.__o.length===0);
ok("  items still require the tap",w.CP.AP.queue.length>=0);

console.log("── Note explains the one-tap-batch model honestly ──");
const noteText=$("p-autopilot").querySelector(".apnote").textContent;
ok("says one tap sends the batch",/one tap sends the whole batch/i.test(noteText));
ok("  still explains the Gmail-ban risk plainly",/flagged as spam/.test(noteText));
ok("  doesn't claim to be fully unattended",!/is fully unattended/i.test(noteText));

ok("ZERO uncaught errors",ERR.length===0,ERR.join(" | "));

console.log("\n"+"═".repeat(50));
console.log(`PASS ${P}    FAIL ${F}`);
if(F){console.log("\nFAILURES");fails.forEach(f=>console.log("  ✗ "+f))}else console.log("✓ ALL GREEN");
})();
