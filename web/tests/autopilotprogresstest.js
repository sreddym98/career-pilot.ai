/* Autopilot live progress: the progress card renders every state, the status
   strip says the right thing, and polling starts, stops and never doubles up. */
const path=require('path');
const {JSDOM}=require('jsdom');const fs=require('fs');
const HTML=fs.readFileSync(path.join(__dirname,'..','index.html'),'utf8');
let P=0,F=0;const fails=[];
const ok=(n,c,x)=>{c?P++:(F++,fails.push(n+(x?"  →  "+x:"")))};
const sleep=ms=>new Promise(r=>setTimeout(r,ms));

/* Fake server whose /progress answers whatever S.run currently is. */
function makeServer(){
  const S={calls:[],run:null,on:true,nextRunAt:null,pausedUntil:null,progFail:false,progDelay:0,inflight:0,maxInflight:0,runHold:null,runStatus:200,queue:[]};
  const state=()=>({on:S.on,slots:[9],tz:"America/Chicago",titles:[],skills:["Cypress"],workStyle:"",dailyCap:60,plan:"pro",
    gmailConnected:true,phoneVerified:true,resumeConfirmed:true,phoneRequired:false,minFit:60,pausedUntil:S.pausedUntil,emailDigest:true,
    emailConfigured:false,needsSkills:false,nextRunAt:S.nextRunAt,queue:S.queue,runs:[],credits_remaining:10});
  const res=(status,body)=>({ok:status<400,status,json:async()=>body});
  S.fetch=async(url,opts={})=>{
    const u=new URL(url),p=u.pathname,m=(opts.method||"GET").toUpperCase();
    S.calls.push({m,p});
    if(p==="/api/integrations/status") return res(200,{gmail:{connected:true},phone:{verified:true}});
    if(p==="/api/autopilot/progress"){
      S.inflight++;S.maxInflight=Math.max(S.maxInflight,S.inflight);
      try{ if(S.progDelay) await sleep(S.progDelay);
        if(S.progFail) return res(500,{detail:"boom"});
        return res(200,{now:new Date().toISOString(),on:S.on,nextRunAt:S.nextRunAt,pausedUntil:S.pausedUntil,run:S.run}); }
      finally{S.inflight--;}
    }
    if(p==="/api/autopilot/run"&&m==="POST"){ if(S.runHold) await S.runHold; if(S.runStatus!==200) return res(S.runStatus,{detail:S.runStatus===409?"A run is already in progress":"nope"}); return res(200,state()); }
    if(p==="/api/autopilot") return res(200,state());
    return res(404,{detail:"Not found"});
  };
  return S;
}
const iso=(ms)=>new Date(Date.now()+ms).toISOString();
const item=(co,ti,st,extra={})=>({company:co,title:ti,fit:80,state:st,reason:null,...extra});
const run=(o={})=>({id:"r1",state:"running",stage:"Scoring 120 jobs against your profile",startedAt:iso(-42000),updatedAt:iso(-1000),finishedAt:null,
  found:0,prepared:0,skipped:0,total:null,note:null,outcome:null,minFit:60,filtered:{},items:[],...o});

const mk=(server,{hidden=false}={})=>{
  const d=new JSDOM(HTML,{runScripts:"dangerously",pretendToBeVisual:true,url:"https://careerpilot.ai/",
    beforeParse(w){
      w.CP_CONFIG={api:"http://api.test"};
      w.fetch=(u,o)=>server.fetch(u,o);
      w.scrollTo=()=>{};w.confirm=()=>true;w.print=()=>{};
      Element_scroll(w);
    }});
  return d.window;
};
function Element_scroll(w){ w.Element.prototype.scrollIntoView=function(){ (w.__scrolled=w.__scrolled||[]).push(this.id); }; }

(async()=>{
console.log("\n╔═══ AUTOPILOT PROGRESS ═══╗\n");
const S=makeServer();
const w=mk(S);await sleep(600);
const d=w.document,$=i=>d.getElementById(i);
const click=e=>e.dispatchEvent(new w.MouseEvent("click",{bubbles:true}));
const hits=()=>S.calls.filter(c=>c.p==="/api/autopilot/progress").length;
w.localStorage.setItem("cp_token",JSON.stringify("tok"));
w.CP.applySession({id:"s1",email:"sam@example.com",name:"Sam",account_type:"seeker",plan:"pro"});
await sleep(100);

console.log("── Nothing running: card hidden, strip says Off/On ──");
S.on=false; w.go("autopilot"); await sleep(250);
ok("no run yet -> progress card hidden",$("ap-prog").hidden===true);
ok("strip says Off",$("ap-strip-text").textContent==="Off",$("ap-strip-text").textContent);
ok("  Run now hidden while off",$("ap-strip-run").hidden===true);
ok("  strip text is an aria-live=polite status",$("ap-strip-text").getAttribute("aria-live")==="polite"&&$("ap-strip-text").getAttribute("role")==="status");
ok("  idle page: exactly one progress request, no polling",hits()===1&&w.CP.APR.timer===null,hits());

S.on=true; S.nextRunAt="2026-09-29T14:00:00Z";
await w.syncAP(); await sleep(50);
ok("strip says On - next run <day time>",/^On - next run [A-Z][a-z]{2} \d{1,2}:\d\d [AP]M$/.test($("ap-strip-text").textContent),$("ap-strip-text").textContent);
ok("  Run now visible when on",$("ap-strip-run").hidden===false);
S.pausedUntil="2026-10-03"; await w.syncAP(); await sleep(50);
ok("strip says Paused until Oct 3",$("ap-strip-text").textContent==="Paused until Oct 3",$("ap-strip-text").textContent);
S.pausedUntil=null; await w.syncAP();

console.log("── A run already in progress on page load (e.g. hourly tick) ──");
S.run=run(); const h0=hits();
w.go("apps"); w.go("autopilot"); await sleep(250);
ok("progress card shown",$("ap-prog").hidden===false);
ok("  stage line is the server's stage, verbatim",$("ap-prog-stage").textContent==="Scoring 120 jobs against your profile",$("ap-prog-stage").textContent);
ok("  stage is a polite live region",$("ap-prog-stage").getAttribute("aria-live")==="polite");
ok("  total unknown -> indeterminate bar (no value, no aria-valuenow)",!$("ap-prog-bar").hasAttribute("value")&&!$("ap-prog-bar").hasAttribute("aria-valuenow"));
ok("  elapsed time shown from the server's start time",/^Elapsed 0:4\d$/.test($("ap-prog-time").textContent),$("ap-prog-time").textContent);
ok("  strip says Running now",$("ap-strip-text").textContent==="Running now");
ok("  Run now hidden while running",$("ap-strip-run").hidden===true);
ok("  no list of roles yet (none invented)",$("ap-prog-items").children.length===0);
ok("  polling has started",w.CP.APR.timer!==null);

console.log("── Determinate progress + live per-role list ──");
S.run=run({stage:"Preparing application 2 of 3: Beta Inc — QA Lead",found:5,prepared:1,total:3,
  items:[item("Acme","Senior SDET","ready"),item("Beta Inc","QA Lead","preparing"),item("Gamma","SDET II","queued")]});
await sleep(2300);
ok("stage names the current role",$("ap-prog-stage").textContent==="Preparing application 2 of 3: Beta Inc — QA Lead",$("ap-prog-stage").textContent);
const bar=$("ap-prog-bar");
ok("determinate bar: value/max/aria-valuenow",bar.max===3&&bar.value===1&&bar.getAttribute("aria-valuenow")==="1"&&bar.getAttribute("aria-valuemax")==="3",bar.outerHTML);
ok("  count text",$("ap-prog-count").textContent==="1 of 3 ready");
const lis=[...$("ap-prog-items").children];
ok("three roles listed with company, role and fit",lis.length===3&&lis[0].textContent.includes("Acme")&&lis[0].textContent.includes("Senior SDET")&&lis[0].textContent.includes("80% fit"));
ok("  states: ready / preparing / queued",lis.map(l=>l.className).join()==="ready,preparing,queued",lis.map(l=>l.className).join());
ok("  ready row has a checkmark",lis[0].querySelector(".aic").textContent==="✓");
ok("  state is stated in words, not only by icon",lis[0].textContent.includes("Ready")&&lis[1].textContent.includes("Preparing")&&lis[2].textContent.includes("Waiting"));
S.run=run({stage:"Preparing application 3 of 3: Gamma — SDET II",found:5,prepared:2,total:3,
  items:[item("Acme","Senior SDET","ready"),item("Beta Inc","QA Lead","skipped",{reason:"AI busy — try again later"}),item("Gamma","SDET II","preparing")]});
await sleep(2300);
const l2=[...$("ap-prog-items").children];
ok("a skipped role shows why",l2[1].className==="skipped"&&l2[1].textContent.includes("AI busy — try again later"),l2[1].textContent);
ok("  elapsed keeps ticking",/^Elapsed 0:[4-5]\d$/.test($("ap-prog-time").textContent),$("ap-prog-time").textContent);
ok("never more than one progress request in flight",S.maxInflight===1,S.maxInflight);

console.log("── Finished: honest summary, polling stops, queue/history refresh ──");
S.queue=[{id:"a1",fingerprint:"f1",company:"Acme",title:"Senior SDET",location:"Remote",subject:"s",apply_url:"https://x.test/1",matched_at:iso(0),fit:80,matched_skills:[],missing_skills:[]}];
S.run=run({state:"done",stage:"Done",found:5,prepared:3,skipped:0,total:3,outcome:"ready",startedAt:iso(-70000),finishedAt:iso(-1000),
  items:[item("Acme","Senior SDET","ready"),item("Beta Inc","QA Lead","ready"),item("Gamma","SDET II","ready")]});
const stateHits0=S.calls.filter(c=>c.p==="/api/autopilot").length;
await sleep(2300);
ok("final line: 3 applications ready for your approval",$("ap-prog-stage").textContent==="3 applications ready for your approval",$("ap-prog-stage").textContent);
ok("  progress bar hidden once done",$("ap-prog-barrow").hidden===true);
ok("  all three ticked",[...$("ap-prog-items").children].every(l=>l.className==="ready"));
ok("  elapsed becomes 'Took 1:0x'",/^Took 1:(0\d|1\d)$/.test($("ap-prog-time").textContent),$("ap-prog-time").textContent);
ok("  button jumps to the queue",/Review them now/.test($("ap-prog-acts").textContent));
click($("ap-prog-acts").querySelector("button"));
ok("  ...and scrolls the queue card into view",(w.__scrolled||[]).includes("ap-queuecard"),JSON.stringify(w.__scrolled));
const hAfter=hits(); await sleep(2600);
ok("polling stopped after the run finished",hits()===hAfter&&w.CP.APR.timer===null,`${hAfter} -> ${hits()}`);
ok("  queue + history were refreshed once the run ended",S.calls.filter(c=>c.p==="/api/autopilot").length>stateHits0);
ok("  strip is back to On - next run",/^On - next run/.test($("ap-strip-text").textContent),$("ap-strip-text").textContent);
click([...$("ap-prog-acts").querySelectorAll("button")].find(b=>b.textContent==="Dismiss"));
ok("Dismiss hides the card and it stays hidden after a reload of state",$("ap-prog").hidden===true&&(await w.apProgFetch(),$("ap-prog").hidden===true));

console.log("── Honest reasons when nothing was queued ──");
const empties=[
  ["below_min_fit",{minFit:70,filtered:{below_min_fit:14}},/no new roles at or above your 70% minimum fit/,/14 scored lower/,"Change minimum fit"],
  ["needs_skills",{},/your profile has no skills/,/rather than guessing/,"Open your profile"],
  ["daily_cap",{note:"Daily limit reached (60/day) — more will be prepared tomorrow"},/today's limit/,/Daily limit reached/,null],
  ["ai_busy",{note:"The AI service was busy or unavailable; will retry at your next slot",skipped:2,items:[item("A","B","skipped",{reason:"AI busy — try again later"})]},/AI service was busy/,/No generations were used/,"Retry now"],
  ["no_matches",{filtered:{already_handled:3,dead_link:1}},/No new matching roles/,/3 already applied, queued or skipped/,null],
  ["queue_full",{},/approval queue is full/,/Approve or skip/,"Open the queue"],
];
let rid=10;
for(const [code,extra,head,detail,btn] of empties){
  S.run=run({id:"r"+(++rid),state:"done",stage:"Done",outcome:code,prepared:0,finishedAt:iso(-500),startedAt:iso(-9000),...extra});
  await w.apProgFetch();
  ok(`${code}: headline`,head.test($("ap-prog-stage").textContent),$("ap-prog-stage").textContent);
  ok(`${code}: reason`,detail.test($("ap-prog-sum").textContent),$("ap-prog-sum").textContent);
  const labels=[...$("ap-prog-acts").querySelectorAll("button")].map(b=>b.textContent).filter(t=>t!=="Dismiss");
  ok(`${code}: action ${btn||"none"}`,btn?labels[0]===btn:labels.length===0,labels.join());
  ok(`${code}: never claims applications are ready`,!/ready for your approval/.test($("ap-prog-card")||$("ap-prog").textContent));
}

console.log("── Stale / stopped / failed: never a spinner forever ──");
for(const [st,head] of [["stale","This run stopped early"],["stopped","This run stopped early"],["failed","This run hit an error and stopped"]]){
  S.run=run({id:"s-"+st,state:st,stage:"Preparing application 2 of 3: X — Y",prepared:1,total:3,updatedAt:iso(-400000),startedAt:iso(-500000),
    finishedAt:st==="stale"?null:iso(-390000),items:[item("Acme","Senior SDET","ready"),item("X","Y","preparing")]});
  await w.apProgFetch();
  ok(`${st}: says '${head}'`,$("ap-prog-stage").textContent===head,$("ap-prog-stage").textContent);
  ok(`${st}: has a Retry button`,[...$("ap-prog-acts").querySelectorAll("button")].some(b=>b.textContent==="Retry"));
  ok(`${st}: no bar, and the card is not busy`,$("ap-prog-barrow").hidden===true&&$("ap-prog").getAttribute("aria-busy")==="false");
  ok(`${st}: says what was already prepared and that nothing was sent`,/1 application was prepared/.test($("ap-prog-sum").textContent)&&/Nothing was sent/.test($("ap-prog-sum").textContent),$("ap-prog-sum").textContent);
  ok(`${st}: does not poll`,w.CP.APR.timer===null&&w.CP.APR.tick===null);
  ok(`${st}: no row is left spinning`,![...$("ap-prog-items").children].some(l=>l.className==="preparing"||l.className==="queued"));
}
S.run=run({id:"s-stale2",state:"stale",updatedAt:iso(-400000),startedAt:iso(-500000)});
await w.apProgFetch();
ok("stale: the strip is not stuck on 'Running now'",$("ap-strip-text").textContent!=="Running now",$("ap-strip-text").textContent);
const before=S.calls.filter(c=>c.p==="/api/autopilot/run").length;
click([...$("ap-prog-acts").querySelectorAll("button")].find(b=>b.textContent==="Retry")); await sleep(200);
ok("Retry asks the server to run again",S.calls.filter(c=>c.p==="/api/autopilot/run").length===before+1);

console.log("── Clicking Run now: instant honest feedback, then the server's row takes over ──");
S.run=run({id:"old",state:"done",stage:"Done",outcome:"ready",prepared:2,finishedAt:iso(-600000),startedAt:iso(-660000)});
await w.apProgFetch(); w.apProgDismiss();
let release; S.runHold=new Promise(r=>release=r);
click($("ap-strip-run")); await sleep(120);
ok("card appears at once as 'Starting your run…'",$("ap-prog").hidden===false&&$("ap-prog-stage").textContent==="Starting your run…",$("ap-prog-stage").textContent);
ok("  strip says Running now",$("ap-strip-text").textContent==="Running now");
await sleep(1000);
ok("  the previous (old) run is NOT shown as this run",$("ap-prog-stage").textContent==="Starting your run…",$("ap-prog-stage").textContent);
S.run=run({id:"new",stage:"Scoring 88 jobs against your profile",startedAt:iso(-1500)});
await sleep(2300);
ok("  once the server has the new run, its stage replaces 'Starting'",$("ap-prog-stage").textContent==="Scoring 88 jobs against your profile",$("ap-prog-stage").textContent);
S.run=run({id:"new",state:"done",stage:"Done",outcome:"ready",prepared:1,total:1,finishedAt:iso(-100),startedAt:iso(-9000),items:[item("Acme","Senior SDET","ready")]});
release(); await sleep(400);
ok("  after the run request returns: final summary, no polling",$("ap-prog-stage").textContent==="1 application ready for your approval"&&w.CP.APR.timer===null,$("ap-prog-stage").textContent);
S.runHold=null;

console.log("── Run refused (409: already running) just watches it ──");
S.runStatus=409; S.run=run({id:"tick-run",stage:"Preparing application 1 of 2: Z — Q",total:2,items:[item("Z","Q","preparing")]});
w.apProgReset(); click($("ap-strip-run")); await sleep(500);
ok("409 shows the running run, not an error",$("ap-prog-stage").textContent==="Preparing application 1 of 2: Z — Q"&&w.CP.APR.timer!==null,$("ap-prog-stage").textContent);
S.runStatus=200; S.run=run({id:"tick-run",state:"done",stage:"Done",outcome:"ready",prepared:2,total:2,finishedAt:iso(-100)});
await sleep(2300); w.apProgReset();

console.log("── Errors back off; hidden tab stops polling ──");
S.run=run({id:"long",stage:"Preparing application 1 of 3: Z — Q",total:3}); S.progFail=false;
w.apProgReset(); await w.apProgFetch(); await sleep(50);
ok("polling active again",w.CP.APR.timer!==null);
S.progFail=true; const e0=hits();
await sleep(2300);
ok("first failure noticed, reconnect message shown, run stays visible",$("ap-prog-sum").textContent.includes("Can't reach the server")&&$("ap-prog").hidden===false,$("ap-prog-sum").textContent);
await sleep(2500);
const eN=hits()-e0;
ok("failing polls back off (2s, then 4s: at most 2 requests in ~5s)",eN>=1&&eN<=2,eN);
S.progFail=false;
Object.defineProperty(d,"hidden",{configurable:true,get:()=>true});
d.dispatchEvent(new w.Event("visibilitychange")); await sleep(50);
const hh=hits(); await sleep(6500);
ok("hidden tab: no requests",hits()===hh&&w.CP.APR.timer===null,`${hh} -> ${hits()}`);
Object.defineProperty(d,"hidden",{configurable:true,get:()=>false});
d.dispatchEvent(new w.Event("visibilitychange")); await sleep(300);
ok("tab visible again: checks immediately and resumes",hits()>hh&&$("ap-prog-sum").textContent.includes("Can't reach")===false);
w.go("apps"); const ha=hits(); await sleep(2600);
ok("leaving the Autopilot page stops polling",hits()<=ha+1&&w.CP.APR.timer===null,`${ha} -> ${hits()}`);
w.apProgReset();

console.log("── XSS + older servers ──");
S.progFail=false; S.run=run({id:"x1",state:"done",stage:"Done",outcome:"ready",prepared:1,total:1,finishedAt:iso(-100),items:[item('<img src=x onerror="window.__xss=1">Co','<b>t</b>',"ready")]});
w.go("autopilot"); await sleep(300);
ok("company/role text is escaped",!w.__xss&&!$("ap-prog-items").querySelector("img"));
const S2=makeServer(); const orig=S2.fetch; S2.fetch=async(u,o)=>u.includes("/progress")?{ok:false,status:404,json:async()=>({detail:"Not found"})}:orig(u,o);
const w2=mk(S2); await sleep(500);
w2.localStorage.setItem("cp_token",JSON.stringify("tok"));
w2.CP.applySession({id:"s1",email:"sam@example.com",name:"Sam",account_type:"seeker",plan:"pro"}); await sleep(100);
w2.go("autopilot"); await sleep(400);
ok("server without /progress: page still works, card hidden, no retry storm",w2.document.getElementById("ap-prog").hidden===true&&S2.calls.filter(c=>c.p.endsWith("/progress")).length<=2,S2.calls.filter(c=>c.p.endsWith("/progress")).length);

console.log(`\nPASS ${P}   FAIL ${F}`);
if(F){console.log("\nFAILURES");fails.forEach(f=>console.log("  x "+f));process.exit(1);}
console.log("ALL GREEN");process.exit(0);
})();
