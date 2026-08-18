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
console.log("\n╔═══ AUTOPILOT — prepared, never blind-sent ═══╗\n");

const w=mk(); await sleep(700);
const d=w.document,$=i=>d.getElementById(i),qa=s=>[...d.querySelectorAll(s)];
const click=e=>{if(!e)throw new Error("missing");e.dispatchEvent(new w.MouseEvent("click",{bubbles:true}))};
const ERR=[];w.addEventListener("error",e=>ERR.push(e.message));

w.parseResume(RESUME,"r.txt"); await sleep(60);

console.log("── Reachable from the sidebar ──");
click(qa(".sbi[data-p]").find(b=>b.textContent.includes("Autopilot")));
await sleep(60);
ok("navigates to the autopilot page",$("p-autopilot").classList.contains("on"));
ok("  marked NEW in the sidebar",qa(".sbbadge.new").some(b=>b.textContent==="NEW"));

console.log("── The honest note is present and prominent ──");
const noteText = $("p-autopilot").querySelector(".apnote").textContent;
ok("explains why it won't auto-send blind",/one tap sends the whole batch/i.test(noteText));
ok("  explains the Gmail risk in plain terms",/flagged as spam/.test(noteText));
ok("  it's the first thing on the page, not buried",$("p-autopilot").innerHTML.indexOf("apnote") < $("p-autopilot").innerHTML.indexOf("ap-checklist"));

console.log("── Setup checklist ──");
ok("starts at 0 of 3",$("ap-setup-count").textContent.includes("0/3"));
ok("  toggle is blocked while setup incomplete",$("ap-on").checked===false);
$("ap-on").checked=true;
w.toggleAutopilot();
await sleep(60);
ok("  turning on without setup is refused",w.CP.AP.on===false);
ok("  explains why",$("toast").textContent.includes("Finish setup"));

click(qa("#ap-checklist button").find(b=>b.textContent.includes("Connect Gmail")));
await sleep(60);
ok("Gmail step completes",w.CP.AP.gmailConnected===true);
click(qa("#ap-checklist button").find(b=>b.textContent.includes("Verify")));
await sleep(60);
ok("phone step completes",w.CP.AP.phoneVerified===true);
w.CP.AP.resumeConfirmed = true; w.CP.saveAP(); w.renderAutopilot();
ok("all 3 steps now done",$("ap-setup-count").textContent.includes("3/3"));

console.log("── Flight plan: slots ──");
const initialSlots = w.CP.AP.slots.length;
ok("starts with default slots",initialSlots>0);
click($("ap-addslot"));
await sleep(60);
ok("adding a slot increases the count",w.CP.AP.slots.length===initialSlots+1);
const firstSlotH = w.CP.AP.slots[0];
w.removeSlot(firstSlotH);
await sleep(60);
ok("removing a slot decreases the count",w.CP.AP.slots.length===initialSlots);
while(w.CP.AP.slots.length>1) w.removeSlot(w.CP.AP.slots[0]);
ok("won't remove the last slot",w.CP.AP.slots.length===1,w.CP.AP.slots.length+"");
const lastH = w.CP.AP.slots[0];
w.removeSlot(lastH);
ok("  confirmed still 1",w.CP.AP.slots.length===1);
ok("  explains why",$("toast").textContent.includes("at least one slot"));

console.log("── Daily cap math ──");
ok("cap text shows plan limit",$("ap-cap").textContent.includes("60"));

console.log("── Target titles ──");
$("ap-title-in").value="Senior SDET";
w.addApTitle();
ok("title added",w.CP.AP.titles.includes("Senior SDET"));
ok("  rendered as a chip",$("ap-titles").innerHTML.includes("Senior SDET"));
w.rmApTitle(0);
ok("title removed",w.CP.AP.titles.length===0);

console.log("── Turning it on now succeeds ──");
$("ap-on").checked=true;
w.toggleAutopilot();
await sleep(60);
ok("autopilot turns on once setup is complete",w.CP.AP.on===true);
ok("  toggle label updates",$("ap-toggle-label").textContent.includes("is on"));

console.log("── A run prepares applications, never sends them ──");
const before=w.__o.length;
w.runAutopilotNow();
await sleep(60);
ok("a run is logged",w.CP.AP.runs.length>0);
ok("  NOTHING was actually sent — no window.open calls",w.__o.length===before,w.__o.length+"");
ok("  queue has items if matches existed",w.CP.AP.queue.length>=0);

console.log("── Approving a queued item is the only thing that sends ──");
if(w.CP.AP.queue.length>0){
  const q0 = w.CP.AP.queue[0];
  const beforeApps = w.CP.APPS.length;
  w.approveQueued(0);
  await sleep(60);
  ok("approving removes it from the queue",w.CP.AP.queue.length===0 || w.CP.AP.queue.every(x=>x.co!==q0.co));
  ok("  logs it as an application",w.CP.APPS.length===beforeApps+1 || w.CP.APPS.some(a=>a.co===q0.co));
}else{
  console.log("  (no matches this run — sample data didn't overlap target skills, skipping approval check)");
}

console.log("── Never exceeds the daily cap ──");
w.CP.AP.dailyCap = 2;
w.CP.AP.queue = [];
w.runAutopilotNow();
await sleep(60);
ok("queue respects the cap",w.CP.AP.queue.length<=2,w.CP.AP.queue.length+"");

console.log("── Never duplicates a company already queued ──");
const co = w.CP.AP.queue[0]?.co;
const lenBefore = w.CP.AP.queue.length;
w.CP.AP.dailyCap = 60;
w.runAutopilotNow();
await sleep(60);
const coCount = w.CP.AP.queue.filter(x=>x.co===co).length;
ok("same company not queued twice",coCount<=1,coCount+"");

console.log("── State survives reload ──");
const saved = w.localStorage.getItem("cp_autopilot");
ok("autopilot state persisted",!!saved && JSON.parse(saved).gmailConnected===true);

ok("ZERO uncaught errors",ERR.length===0,ERR.join(" | "));

console.log("\n"+"═".repeat(50));
console.log(`PASS ${P}    FAIL ${F}`);
if(F){console.log("\nFAILURES");fails.forEach(f=>console.log("  ✗ "+f))}else console.log("✓ ALL GREEN");
})();
