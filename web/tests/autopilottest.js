const path=require('path');
const {JSDOM}=require('jsdom');const fs=require('fs');
const HTML=fs.readFileSync(path.join(__dirname,'..','index.html'),'utf8');
const mk=()=>{const d=new JSDOM(HTML,{runScripts:"dangerously",pretendToBeVisual:true,url:"https://careerpilot.ai/",beforeParse:w=>Object.defineProperty(w,"scrollTo",{value:()=>{},configurable:true})});
  const w=d.window;Object.defineProperty(w,"scrollTo",{value:()=>{},configurable:true});w.confirm=()=>true;w.innerWidth=1280;
  w.navigator.clipboard={writeText:()=>Promise.resolve()};return w;};
let P=0,F=0;const fails=[];const ok=(n,c,x)=>{c?P++:(F++,fails.push(n+(x?"  →  "+x:"")))};
const sleep=ms=>new Promise(r=>setTimeout(r,ms));

(async()=>{
console.log("\n╔═══ AUTOPILOT — current full-automation flow ═══╗\n");
const w=mk();await sleep(500);const d=w.document,$=i=>d.getElementById(i);
const click=e=>{if(!e)throw new Error("missing element");e.dispatchEvent(new w.MouseEvent("click",{bubbles:true}))};
const errors=[];w.addEventListener("error",e=>errors.push(e.message));

console.log("── Navigation and current design ──");
click(d.querySelector('.sbi[data-p="autopilot"]'));await sleep(50);
ok("Autopilot page is reachable",$("p-autopilot").classList.contains("on"));
ok("new Full Autopilot card is present",$("fullauto-btn-text")!=null);
ok("legacy approval cards are absent",!$("ap-setup-count")&&!$("ap-queue")&&!$("ap-runs"));

console.log("── Explore Jobs selection alignment ──");
const job=w.CP.J[0];
click(d.querySelector('[onclick*="addToAutopilot"]'));
ok("Explore Jobs action adds a selection",JSON.parse(w.localStorage.getItem("cp_fullauto_selected_v1")||"[]").length===1);
ok("selection is persisted",!!w.localStorage.getItem("cp_fullauto_selected_v1"));
ok("selected job renders",$("fullauto-jobs").querySelectorAll(".fullauto-job-item").length===1);

console.log("── Picker controls ──");
click(d.querySelector('button[onclick="selectJobsForFullAuto()"]'));await sleep(50);
ok("picker opens",d.querySelector(".fullauto-modal-overlay")!=null);
ok("picker has jobs",d.querySelectorAll(".fullauto-check").length>0);
ok("close button is visible",d.querySelector(".fullauto-modal-close")!=null);
ok("confirmation action is visible",d.querySelector(".fullauto-modal-actions button")!=null);
click(d.querySelector(".fullauto-modal-close"));
ok("close button closes picker",!d.querySelector(".fullauto-modal-overlay"));

console.log("── Persistence after navigation ──");
click(d.querySelector('[data-p="jobs"]'));click(d.querySelector('[data-p="autopilot"]'));await sleep(50);
ok("selection survives navigation",$("fullauto-selected").textContent.includes("1 job"));
ok("selection row survives navigation",$("fullauto-jobs").querySelectorAll(".fullauto-job-item").length===1);
ok("zero uncaught errors",errors.length===0,errors.join(" | "));

console.log("\n"+"═".repeat(50));console.log(`PASS ${P}    FAIL ${F}`);
if(F){console.log("\nFAILURES");fails.forEach(f=>console.log("  ✗ "+f))}else console.log("✓ ALL GREEN");
})();
