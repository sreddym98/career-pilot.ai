const path=require('path');
const {JSDOM}=require('jsdom');const fs=require('fs');
const HTML=fs.readFileSync(path.join(__dirname,'..','index.html'),'utf8');
const mk=()=>{const d=new JSDOM(HTML,{runScripts:"dangerously",pretendToBeVisual:true,url:"https://careerpilot.ai/"});
  const w=d.window;w.scrollTo=()=>{};w.confirm=()=>true;w.requestAnimationFrame=cb=>setTimeout(cb,0);
  Object.defineProperty(w,"innerWidth",{value:1280,configurable:true});
  let clipboard = "";
  w.navigator.clipboard = {writeText: t => { clipboard = t; return Promise.resolve(); }};
  w.__clip = () => clipboard;
  w.URL.createObjectURL=w.URL.createObjectURL||(()=>"blob:mock");
  w.URL.revokeObjectURL=w.URL.revokeObjectURL||(()=>{});
  class _MockZipNode{constructor(r){this._root=r;}file(n,c){this._root._files[n]=c;return this;}
    folder(n){return new _MockZipNode(this._root);}async generateAsync(){return new w.Blob(["REAL DOCX"]);}}
  w.JSZip=class extends _MockZipNode{constructor(){super(null);this._root=this;this._files={};}};
  delete w.navigator.share; delete w.navigator.canShare;   // desktop, no Web Share
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
console.log("\n╔═══ MAILTO FOLLOW-UP — no overclaiming, a real fallback ═══╗\n");

const w=mk(); await sleep(700);
const d=w.document,$=i=>d.getElementById(i),qa=s=>[...d.querySelectorAll(s)];
const click=e=>{if(!e)throw new Error("missing");e.dispatchEvent(new w.MouseEvent("click",{bubbles:true}))};
const ERR=[];w.addEventListener("error",e=>ERR.push(e.message));

w.CP.preloadLib("jszip");
w.parseResume(RESUME,"r.txt"); await sleep(60);
const ag = w.CP.J.find(j=>!j.url);
w.writeRecruiter(ag);
await w.CP.handleResumeStep(ag.id);
await sleep(60);
w.downloadCoverLetter(ag, qa("#step-cover button")[0]);
await sleep(60);
$("r-to").value = "recruiter@agency.com";

console.log("── Follow-up starts hidden ──");
ok("mailto follow-up hidden before any attempt",$("mailto-followup").style.display==="none");

console.log("── Clicking Attach: modal STAYS OPEN, no false claim ──");
click($("share-attach-btn"));
await sleep(60);
ok("modal did NOT close on an unconfirmed mailto attempt",$("ov").classList.contains("on")===true);
ok("follow-up now visible",$("mailto-followup").style.display!=="none");
ok("mentions both possible outcomes honestly",
   $("mailto-followup").textContent.includes("If a new email just opened") &&
   $("mailto-followup").textContent.includes("If nothing opened"));
ok("explains WHY nothing might open (webmail)",$("mailto-followup").textContent.includes("Gmail"));
ok("names the exact files to drag in",$("mailto-followup").innerHTML.includes(".docx")&&$("mailto-followup").innerHTML.includes(".txt"));

console.log("── The fallback actually works — real clipboard content ──");
click(qa("#mailto-followup button")[0]);
await sleep(60);
const copied = w.__clip();
ok("copy button copies something real",copied.length>50,copied.length+" chars");
ok("  includes the recipient",copied.includes("recruiter@agency.com"));
ok("  includes the subject",copied.includes($("r-sub").value));
ok("  includes the full message body",copied.includes($("r-body").value.slice(0,40)));
ok("confirms the copy",$("toast").textContent.includes("Copied"));

console.log("── Same fix applies to the plain 'Open in email' button ──");
w.writeRecruiter(ag);
await sleep(60);
await w.CP.handleResumeStep(ag.id);
await sleep(60);
$("r-to").value = "another@agency.com";
w.sendMail(ag.id);
await sleep(60);
ok("plain send button also stays open, doesn't overclaim",$("ov").classList.contains("on")===true);
ok("  also shows the honest follow-up",$("mailto-followup").style.display!=="none");

console.log("── Nothing was falsely marked applied just from an attempt ──");
ok("app was NOT marked 'sent' just from clicking — only from a real confirmed action",
   !w.CP.APPS.some(a=>a.co===ag.co&&a.st==="sent"));

ok("ZERO uncaught errors",ERR.length===0,ERR.join(" | "));

console.log("\n"+"═".repeat(50));
console.log(`PASS ${P}    FAIL ${F}`);
if(F){console.log("\nFAILURES");fails.forEach(f=>console.log("  ✗ "+f))}else console.log("✓ ALL GREEN");
})();
