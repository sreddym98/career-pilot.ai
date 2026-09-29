/* Regression: the Autopilot on/off switch must always answer.
   Bug: toggleAutopilot() ran the whole first run (AI tailoring, up to a minute
   or more) inside apAct(), so clicking OFF while it ran was silently dropped and
   the switch snapped back to ON. Also: free users were told to "finish setup"
   (resume + phone) instead of that Autopilot is Pro, and phone was named even
   when it isn't required. */
const path=require('path');const {JSDOM}=require('jsdom');const fs=require('fs');
const HTML=fs.readFileSync(process.env.AP_HTML||path.join(__dirname,'..','index.html'),'utf8');
let P=0,F=0;const fails=[];
const ok=(n,c,x)=>{c?P++:(F++,fails.push(n+(x?"  →  "+x:"")))};
const sleep=ms=>new Promise(r=>setTimeout(r,ms));

function makeServer(o={}){
  const S={plan:"pro",on:false,resume:true,phoneRequired:false,runMs:600,down:false,calls:[],...o};
  const state=()=>({on:S.on,slots:[9,13],tz:null,titles:[],skills:[],workStyle:"",dailyCap:S.plan==="free"?0:60,plan:S.plan,
    gmailConnected:false,phoneVerified:false,resumeConfirmed:S.resume,phoneRequired:S.phoneRequired,queue:[],runs:[],credits_remaining:5});
  const res=(s,b)=>({ok:s<400,status:s,json:async()=>b});
  S.fetch=async(url,opts={})=>{
    const p=new URL(url).pathname,m=(opts.method||"GET").toUpperCase(),body=opts.body?JSON.parse(opts.body):null;
    if(!p.startsWith("/api/autopilot")&&p!=="/api/integrations/status") return res(404,{detail:"nf"});
    S.calls.push({m,p,body});
    if(p==="/api/integrations/status") return res(200,{gmail:{connected:false},phone:{verified:false}});
    if(S.down) throw new TypeError("Failed to fetch");
    if(p==="/api/autopilot"&&m==="GET") return res(200,state());
    if(p==="/api/autopilot"&&m==="PUT"){
      if(body.on===true){ if(S.plan==="free") return res(402,{detail:"Autopilot is part of Pro. Upgrade to turn it on."}); S.on=true; }
      else if(body.on===false) S.on=false;
      return res(200,state());
    }
    if(p==="/api/autopilot/run"){ await sleep(S.runMs); if(!S.on) return res(400,{detail:"Turn Autopilot on first"});
      return res(200,{...state(),runs:[{at:new Date().toISOString(),found:0,prepared:0,skipped:0,note:"nothing new"}]}); }
    return res(404,{detail:"nf"});
  };
  return S;
}
function boot(S){
  const d=new JSDOM(HTML,{runScripts:"dangerously",pretendToBeVisual:true,url:"https://careerpilot.ai/",
    beforeParse(w){w.CP_CONFIG={api:"http://api.test"};w.fetch=(u,o)=>S.fetch(u,o);w.scrollTo=()=>{};w.confirm=()=>true;
      w.HTMLElement.prototype.scrollIntoView=function(){w.__scrolled=this.id;};}});
  return d.window;
}
async function signedIn(S,plan){
  const w=boot(S); await sleep(500);
  w.localStorage.setItem("cp_token",JSON.stringify("tok"));
  w.CP.applySession({id:"u1",email:"a@b.co",name:"A",account_type:"seeker",plan});
  await sleep(100); w.go("autopilot"); await sleep(250); return w;
}
const flip=(w,v)=>{const el=w.document.getElementById("ap-on"); el.checked=v; return w.toggleAutopilot();};

(async()=>{
console.log("\n╔═══ AUTOPILOT TOGGLE ═══╗\n");
{ // OFF is honoured while the first run is still in flight
  const S=makeServer(); const w=await signedIn(S,"pro"); const $=i=>w.document.getElementById(i);
  flip(w,true); await sleep(120);   // deliberately not awaited: the user clicks again while it runs
  ok("on: PUT sent, switch on",S.on===true&&$("ap-on").checked===true);
  ok("  run started in background (still in flight)",S.calls.some(c=>c.p==="/api/autopilot/run")&&w.CP.AP.on===true);
  await flip(w,false); await sleep(80);
  ok("OFF during a run is NOT dropped",S.on===false&&w.CP.AP.on===false&&$("ap-on").checked===false,`server.on=${S.on} AP.on=${w.CP.AP.on}`);
  ok("  label says paused",$("ap-toggle-label").textContent.includes("paused"));
  await sleep(800);
  ok("run finishing later doesn't flip it back on",S.on===false&&$("ap-on").checked===false);
  ok("  no scary 'Turn Autopilot on first' toast",!$("toast").textContent.includes("Turn Autopilot on first"),$("toast").textContent);
}
{ // free plan: honest message, no setup detour, no PUT
  const S=makeServer({plan:"free",resume:false}); const w=await signedIn(S,"free"); const $=i=>w.document.getElementById(i);
  const n=S.calls.filter(c=>c.m==="PUT").length;
  await flip(w,true); await sleep(60);
  ok("free: says it's Pro",/Pro/.test($("toast").textContent)&&!/setup/i.test($("toast").textContent),$("toast").textContent);
  ok("  switch snaps back off, no PUT",$("ap-on").checked===false&&S.calls.filter(c=>c.m==="PUT").length===n);
  ok("  upgrade path: sent to the plan page",w.document.getElementById("page-plan")?w.document.getElementById("page-plan").classList.contains("on"):true);
}
{ // resume missing, phone not required
  const S=makeServer({resume:false}); const w=await signedIn(S,"pro"); const $=i=>w.document.getElementById(i);
  ok("checklist has only the resume step when phone isn't required",$("ap-setup-count").textContent.includes("0/1"),$("ap-setup-count").textContent);
  await flip(w,true); await sleep(60);
  ok("message names only the resume",/confirm your resume/.test($("toast").textContent)&&!/phone/i.test($("toast").textContent),$("toast").textContent);
  ok("  bounces back off and scrolls to the checklist",$("ap-on").checked===false&&w.__scrolled==="ap-checklist");
}
{ // phone required + missing
  const S=makeServer({resume:false,phoneRequired:true}); const w=await signedIn(S,"pro"); const $=i=>w.document.getElementById(i);
  await flip(w,true); await sleep(60);
  ok("phone required: names both",/resume/.test($("toast").textContent)&&/phone/.test($("toast").textContent),$("toast").textContent);
}
{ // network failure
  const S=makeServer(); const w=await signedIn(S,"pro"); const $=i=>w.document.getElementById(i);
  S.down=true; await flip(w,true); await sleep(80);
  ok("network down: switch reverts to off",$("ap-on").checked===false&&w.CP.AP.on===false);
  ok("  readable message, not 'Failed to fetch'",/reach the server/.test($("toast").textContent),$("toast").textContent);
}
console.log("\n"+"═".repeat(50));
console.log(`PASS ${P}    FAIL ${F}`);
if(F){console.log("\nFAILURES");fails.forEach(f=>console.log("  ✗ "+f))}else console.log("✓ ALL GREEN");
process.exit(0);
})();
