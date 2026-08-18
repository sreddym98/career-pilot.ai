const path=require('path');
const {JSDOM}=require('jsdom');const fs=require('fs');
const HTML=fs.readFileSync(path.join(__dirname,'..','index.html'),'utf8');
const mk=(shareSupported)=>{const d=new JSDOM(HTML,{runScripts:"dangerously",pretendToBeVisual:true,url:"https://careerpilot.ai/"});
  const w=d.window;w.scrollTo=()=>{};w.confirm=()=>true;w.requestAnimationFrame=cb=>setTimeout(cb,0);
  Object.defineProperty(w,"innerWidth",{value:1280,configurable:true});
  w.navigator.clipboard={writeText:()=>Promise.resolve()};
  w.URL.createObjectURL=w.URL.createObjectURL||(()=>"blob:mock");
  w.URL.revokeObjectURL=w.URL.revokeObjectURL||(()=>{});
  class _MockZipNode{constructor(r){this._root=r;}file(n,c){this._root._files[n]=c;return this;}
    folder(n){return new _MockZipNode(this._root);}async generateAsync(){return new w.Blob(["REAL DOCX BYTES"]);}}
  w.JSZip=class extends _MockZipNode{constructor(){super(null);this._root=this;this._files={};}};
  if(shareSupported){
    w.navigator.canShare=()=>true;
    w.navigator.share=async()=>Promise.resolve();
  } else {
    delete w.navigator.share; delete w.navigator.canShare;
  }
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
console.log("\n╔═══ ATTACH FALLBACK — desktop browsers that can't share files ═══╗\n");

console.log("── Desktop Chrome/macOS/Firefox: no Web Share file support ──");
{
const w=mk(false); await sleep(700);
const d=w.document,$=i=>d.getElementById(i),qa=s=>[...d.querySelectorAll(s)];
const click=e=>{if(!e)throw new Error("missing");e.dispatchEvent(new w.MouseEvent("click",{bubbles:true}))};
w.CP.preloadLib("jszip");
w.parseResume(RESUME,"r.txt"); await sleep(60);
const ag = w.CP.J.find(j=>!j.url);
w.writeRecruiter(ag);
await w.CP.handleResumeStep(ag.id);
await sleep(60);

console.log("── Button and note reflect the real limitation, not a fake promise ──");
ok("button doesn't claim one-tap attach on unsupported browsers",
   !$("share-attach-btn").innerHTML.includes("one tap"));
ok("  button IS still clickable — not just disabled and stuck",$("share-attach-btn").disabled===false);
ok("note names the ACTUAL filename to drag in",$("attach-note").innerHTML.includes(".docx"),$("attach-note").textContent.slice(0,100));
ok("note is honest it's a browser limit, not this app's fault",$("attach-note").textContent.includes("browser limit"));

console.log("── THE FIX: clicking Attach on an unsupported browser now DOES something ──");
$("r-to").value = "recruiter@agency.com";
let opened=[]; w.__o=[];
click($("share-attach-btn"));
await sleep(60);
ok("clicking it actually opens the email — not a dead end",w.__o.length===1,w.__o.length+" opens");
ok("  the mailto goes to the address typed in",w.__o[0]?.startsWith("mailto:recruiter@agency.com"),w.__o[0]);
ok("  follow-up names the exact file to drag in",$("mailto-followup").innerHTML.includes(".docx"),$("mailto-followup").textContent.slice(0,100));
ok("  modal stays open with a real fallback rather than an unconfirmed close",$("ov").classList.contains("on")&&$("mailto-followup").style.display!=="none");
ok("  logged as an application, same as the normal send path",w.CP.APPS.some(a=>a.co===ag.co));
}

console.log("── Mobile Safari / supporting browsers: real Web Share ──");
{
const w=mk(true); await sleep(700);
const d=w.document,$=i=>d.getElementById(i),qa=s=>[...d.querySelectorAll(s)];
const click=e=>{if(!e)throw new Error("missing");e.dispatchEvent(new w.MouseEvent("click",{bubbles:true}))};
w.CP.preloadLib("jszip");
w.parseResume(RESUME,"r.txt"); await sleep(60);
const ag = w.CP.J.find(j=>!j.url);
w.writeRecruiter(ag);
await w.CP.handleResumeStep(ag.id);
await sleep(60);
ok("button DOES promise one-tap here — genuinely supported",
   $("share-attach-btn").innerHTML.includes("one tap"));
let shared=false;
w.navigator.share=async(opts)=>{shared=true; ok("real File object handed to the OS share sheet",
   opts.files[0] instanceof w.File);};
click($("share-attach-btn"));
await sleep(60);
ok("navigator.share was actually invoked",shared===true);
}

console.log("\n"+"═".repeat(50));
console.log(`PASS ${P}    FAIL ${F}`);
if(F){console.log("\nFAILURES");fails.forEach(f=>console.log("  ✗ "+f))}else console.log("✓ ALL GREEN");
})();
