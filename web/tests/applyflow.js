const path=require('path');
const {JSDOM}=require('jsdom');const fs=require('fs');
const dom=new JSDOM(fs.readFileSync(path.join(__dirname,'..','index.html'),'utf8'),
  {runScripts:"dangerously",pretendToBeVisual:true,url:"https://careerpilot.ai/"});
const w=dom.window,d=w.document;
Object.defineProperty(w,"innerWidth",{value:800,configurable:true});
w.scrollTo=()=>{};w.navigator.clipboard={writeText:()=>Promise.resolve()};
w.URL.createObjectURL=w.URL.createObjectURL||(()=>"blob:mock");
w.URL.revokeObjectURL=w.URL.revokeObjectURL||(()=>{});
class _MockZipNode{constructor(r){this._root=r;}file(n,c){this._root._files[n]=c;return this;}
  folder(n){return new _MockZipNode(this._root);}async generateAsync(){return new w.Blob(["mock"]);}}
w.JSZip=class extends _MockZipNode{constructor(){super(null);this._root=this;this._files={};}};
let opened=[];w.open=u=>{opened.push(u);return{focus(){}}};
const $=i=>d.getElementById(i),qa=s=>[...d.querySelectorAll(s)];
const click=e=>{if(!e)throw new Error("missing");e.dispatchEvent(new w.MouseEvent("click",{bubbles:true}))};
let P=0,F=0;const fails=[];
const ok=(n,c,x)=>{c?P++:(F++,fails.push(n+(x?"  →  "+x:"")))};
// Job detail can render in the modal (#md) or the split pane (#jobDetailPane
// .splitcard) depending on viewport width. Tests query whichever is active.
const detailSel = (d) => d.querySelector("#jobDetailPane .splitcard") ? "#jobDetailPane" : "#md";
const sleep=ms=>new Promise(r=>setTimeout(r,ms));
// simulate leaving the tab and coming back
const leaveAndReturn=async()=>{
  Object.defineProperty(d,"hidden",{value:true,configurable:true});
  d.dispatchEvent(new w.Event("visibilitychange"));
  await sleep(20);
  Object.defineProperty(d,"hidden",{value:false,configurable:true});
  d.dispatchEvent(new w.Event("visibilitychange"));
  await sleep(750);
};

setTimeout(async()=>{
const CP=w.CP;
console.log("\n╔═══ APPLY FLOW ═══╗\n");

console.log("── No modal in the way ──");
const card=d.querySelector(".job");
ok("apply button on the card",!!card.querySelector(".cardacts .btn-p"));
ok("  details is separate + secondary",card.querySelector(".cardacts .btn-g").textContent==="Details");
ok("  card actions don't open the modal",(click(card.querySelector(".cardacts")),!$("ov").classList.contains("on")));

console.log("── Sample links are honest ──");
const ft=CP.J.find(j=>j.em==="fulltime"&&j.url);
ok("sample flagged in data",!!ft.sample);
ok("  button says Search, not Apply",w.applyLabel(ft).startsWith("Search on"),w.applyLabel(ft));
opened=[];
w.applyTo(ft.id);
ok("  opens a REAL page",/search|results|open-positions|[?&]q=/i.test(opened[0]),opened[0]);
ok("  carries the job title",decodeURIComponent(opened[0].replace(/\+/g," ")).includes("SDET"),opened[0]);
ok("  no invented job id",!/\/job\/R-\d|\/jobs\/\d{6,}/.test(opened[0]),opened[0]);
w.openJob(ft.id);
ok("  detail explains it's an example",/Example listing/.test($("md").innerHTML));
ok("  says what applying does",/live search/.test($("md").innerHTML));
w.closeM();

console.log("── Did you apply? ──");
CP.APPS.length=0;
opened=[];
w.applyTo(ft.id);
ok("marked as opened, NOT applied",CP.APPS[0].st==="opened",CP.APPS[0].st);
ok("  card shows 'did you apply?'",d.querySelector(".ctag.open")!==null);
ok("  no ask bar while you're away",!$("askbar"));
await leaveAndReturn();
ok("asks when you come back",!!$("askbar"));
ok("  names the role",$("askbar").textContent.includes(ft.ti));
ok("  three honest options",qa("#askbar button").length===3,qa("#askbar button").map(b=>b.textContent).join(" / "));

click(qa("#askbar button").find(b=>b.textContent.includes("Yes")));
await sleep(60);
ok("Yes → recorded as applied",CP.APPS[0].st==="sent",CP.APPS[0].st);
ok("  bar dismissed",!$("askbar")||!$("askbar").classList.contains("on"));
w.rn();
ok("  card shows ✓ Applied",d.querySelector(".ctag.done")!==null);

console.log("── Not yet ──");
CP.APPS.length=0;
const j2=CP.J.filter(x=>x.url)[1];
w.applyTo(j2.id); await leaveAndReturn();
click(qa("#askbar button").find(b=>b.textContent.includes("Not yet")));
await sleep(60);
ok("stays as opened",CP.APPS[0].st==="opened");
w.go("apps");
ok("  flagged as unfinished",$("appSum").innerHTML.includes("opened but not finished"),$("appSum").textContent);
ok("  listed under its own heading",$("appList").innerHTML.includes("Opened, not applied"));

console.log("── Not for me ──");
CP.APPS.length=0;
const j3=CP.J.filter(x=>x.url)[2];
w.applyTo(j3.id); await leaveAndReturn();
click(qa("#askbar button").find(b=>b.textContent.includes("Not for me")));
await sleep(60);
ok("recorded as passed",CP.APPS[0].st==="skipped");
w.go("jobs"); w.rn();
ok("  removed from the board",!$("list").innerHTML.includes(j3.ti));
$("f-showall").checked=true; w.rn();
ok("  'Show passed' brings it back",$("list").innerHTML.includes(j3.ti));
ok("  marked Skipped",d.querySelector(".ctag.skip")!==null);
$("f-showall").checked=false; w.rn();

console.log("── Agency email path ──");
CP.APPS.length=0;
const ag=CP.J.find(x=>!x.url&&x.rec&&x.rec.e);
w.applyTo(ag.id);
ok("opens the draft",!!$("r-body"));
opened=[];
CP.preloadLib("jszip");
await CP.handleResumeStep(ag.id);
await sleep(60);
click(qa("#md button").find(b=>b.textContent.includes("Open in email")));
ok("marked opened after sending",CP.APPS[0].st==="opened");
await leaveAndReturn();
ok("  asks about the email too",!!$("askbar"));
click(qa("#askbar button").find(b=>b.textContent.includes("Yes")));
await sleep(60);
ok("  confirms as applied",CP.APPS[0].st==="sent");

console.log("── Never double-counts ──");
const before=CP.APPS.length;
w.applyTo(ag.id);
ok("re-applying updates, not duplicates",CP.APPS.length===before,CP.APPS.length+" vs "+before);
ok("  one entry per role",new Set(CP.APPS.map(a=>a.co+a.ti)).size===CP.APPS.length);

console.log("\n"+"═".repeat(48));
console.log(`PASS ${P}    FAIL ${F}`);
if(F){console.log("\nFAILURES");fails.forEach(f=>console.log("  ✗ "+f))}else console.log("✓ ALL GREEN");
},700);
