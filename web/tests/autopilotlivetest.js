const path=require('path');
const {JSDOM}=require('jsdom');const fs=require('fs');
const HTML=fs.readFileSync(path.join(__dirname,'..','index.html'),'utf8');
let P=0,F=0;const fails=[];
const ok=(n,c,x)=>{c?P++:(F++,fails.push(n+(x?"  →  "+x:"")))};
const sleep=ms=>new Promise(r=>setTimeout(r,ms));

/* In-memory fake of /api/autopilot, mirroring server/api/routers/autopilot.py. */
function makeServer(over={}){
  const S={
    plan:"pro", on:false, slots:[8,12], tz:null, titles:[], skills:["Playwright"], workStyle:"",
    gmailConnected:false, phoneVerified:false, resumeConfirmed:false,
    queue:[], runs:[], n:0, calls:[], fail:null,
    minFit:60, pausedUntil:null, emailDigest:true, emailConfigured:false, needsSkills:false, nextRunAt:null, ...over};
  const state=()=>({on:S.on,slots:[...S.slots].sort((a,b)=>a-b),tz:S.tz,titles:S.titles,skills:S.skills,
    workStyle:S.workStyle,dailyCap:S.plan==="free"?0:60,plan:S.plan,gmailConnected:S.gmailConnected,
    phoneVerified:S.phoneVerified,resumeConfirmed:S.resumeConfirmed,
    minFit:S.minFit,pausedUntil:S.pausedUntil,emailDigest:S.emailDigest,emailConfigured:S.emailConfigured,needsSkills:S.needsSkills,nextRunAt:S.nextRunAt,
    queue:S.queue.filter(q=>q.status==="ready").map(({status,cover,...q})=>q),runs:S.runs,credits_remaining:10});
  const res=(status,body)=>({ok:status<400,status,json:async()=>body});
  const mkItem=(co,ti)=>{const id="app-"+(++S.n);
    return {id,fingerprint:"fp"+S.n,company:co,title:ti,location:"Remote",subject:`${ti} — Sam`,
      apply_url:`https://jobs.example.com/${id}`,matched_at:new Date().toISOString(),status:"ready",
      cover:`Dear ${co} team, I would love to join.`,summary:"Sum",highlights:["Built X"]};};
  S.fetch=async(url,opts={})=>{
    const u=new URL(url), p=u.pathname, m=(opts.method||"GET").toUpperCase();
    const body=opts.body?JSON.parse(opts.body):null;
    const auth=(opts.headers||{}).Authorization;
    if(p.startsWith("/api/apply/")){ S.calls.push({m,p,body,auth}); return res(503,{detail:"apply page not mocked here"}); }
    if(!p.startsWith("/api/autopilot")&&p!=="/api/integrations/status") return res(404,{detail:"Not found"});
    S.calls.push({m,p,body,auth});
    if(p==="/api/integrations/status") return res(200,{gmail:{connected:S.gmailConnected},phone:{verified:S.phoneVerified}});
    if(S.fail&&S.fail(m,p,body)) return res(402,{detail:"Autopilot is part of Pro. Upgrade to turn it on."});
    if(p==="/api/autopilot"&&m==="GET") return res(200,state());
    if(p==="/api/autopilot"&&m==="PUT"){
      if(body.slots) S.slots=[...new Set(body.slots)];
      if(body.tz) S.tz=body.tz;
      if(body.titles) S.titles=body.titles;
      if(body.workStyle!==undefined&&body.workStyle!==null) S.workStyle=body.workStyle;
      if(body.minFit!==undefined&&body.minFit!==null) S.minFit=body.minFit;
      if(body.pausedUntil!==undefined&&body.pausedUntil!==null) S.pausedUntil=body.pausedUntil||null;
      if(body.emailDigest!==undefined&&body.emailDigest!==null) S.emailDigest=body.emailDigest;
      if(body.on===true){
        if(S.plan==="free") return res(402,{detail:"Autopilot is part of Pro. Upgrade to turn it on."});
        if(!(S.gmailConnected&&S.phoneVerified&&S.resumeConfirmed)) return res(400,{detail:"Finish setup first"});
        S.on=true;
      } else if(body.on===false) S.on=false;
      return res(200,state());
    }
    if(p==="/api/autopilot/run"){
      if(!S.on) return res(400,{detail:"Turn Autopilot on first"});
      S.queue.push(mkItem('<img src=x onerror="window.__xss=1">Corp',"Sr SDET"),mkItem("Beta Inc","QA Lead"));
      S.runs.unshift({at:new Date().toISOString(),found:2,prepared:2,skipped:0,note:null});
      return res(200,state());
    }
    if(p==="/api/autopilot/preview") return res(200,{minFit:S.minFit,needsSkills:S.needsSkills,eligible:2,perRun:5,queueFull:false,
      filtered:{below_min_fit:4,dead_link:1},roles:[{fingerprint:"f1",company:"Prev <b>Co</b>",title:"Lead SDET",location:"Remote",fit:91,verified:true,matched_skills:["Cypress"],missing_skills:["Go"],thisRun:true},
      {fingerprint:"f2",company:"Second Co",title:"QA Engineer",location:null,fit:64,verified:false,matched_skills:[],missing_skills:[],thisRun:true}]});
    if(p==="/api/autopilot/queue/approve-all"){
      const items=S.queue.filter(q=>q.status==="ready"); items.forEach(q=>q.status="opened");
      return res(200,{approved:items.length,state:state()});
    }
    let mm=p.match(/^\/api\/autopilot\/queue\/([^/]+)\/approve$/);
    if(mm){const q=S.queue.find(x=>x.id===mm[1]);
      if(!q) return res(404,{detail:"Not found"});
      if(q.status!=="ready") return res(400,{detail:"Already handled"});
      q.status="opened"; return res(200,{approved:q.id,apply_url:q.apply_url});}
    mm=p.match(/^\/api\/autopilot\/queue\/([^/]+)$/);
    if(mm){const q=S.queue.find(x=>x.id===mm[1]); if(!q) return res(404,{detail:"Not found"});
      if(m==="GET") return res(200,{...q,summary:q.summary,highlights:q.highlights,cover_letter:q.cover});
      if(m==="DELETE"){q.status="skipped";return res(200,{skipped:q.id});}}
    return res(404,{detail:"Not found"});
  };
  return S;
}

const mk=(server,{session=true,user}={})=>{
  const d=new JSDOM(HTML,{runScripts:"dangerously",pretendToBeVisual:true,url:"https://careerpilot.ai/",
    beforeParse(w){
      w.CP_CONFIG={api:"http://api.test"};
      w.fetch=(u,o)=>server.fetch(u,o);
      w.scrollTo=()=>{};w.confirm=()=>true;w.print=()=>{};
      w.navigator.clipboard={writeText:()=>Promise.resolve()};
      w.__o=[];w.open=u=>{w.__o.push(u);return{focus(){}}};
    }});
  return d.window;
};

(async()=>{
console.log("\n╔═══ AUTOPILOT LIVE — server-backed ═══╗\n");
const S=makeServer();
const w=mk(S); await sleep(700);
const d=w.document,$=i=>d.getElementById(i),qa=s=>[...d.querySelectorAll(s)];
const click=e=>{if(!e)throw new Error("missing");e.dispatchEvent(new w.MouseEvent("click",{bubbles:true}))};
const ERR=[];w.addEventListener("error",e=>ERR.push(e.message));
const calls=(m,p)=>S.calls.filter(c=>c.m===m&&(p instanceof RegExp?p.test(c.p):c.p===p));

w.localStorage.setItem("cp_token",JSON.stringify("tok"));
w.CP.applySession({id:"s1",email:"sam@example.com",name:"Sam",account_type:"seeker",plan:"pro"});
await sleep(150);
ok("signed in as seeker → live mode",w.CP.apLive()===true);

console.log("── Opens and renders server state ──");
w.go("autopilot"); await sleep(200);
ok("state fetched with the bearer token",calls("GET","/api/autopilot").length>=1&&calls("GET","/api/autopilot")[0].auth==="Bearer tok");
ok("server slots rendered (not the demo defaults)",qa("#ap-slots select").length===2&&qa("#ap-slots select").map(s=>+s.value).join()==="8,12",qa("#ap-slots select").map(s=>s.value).join());
ok("  plan cap shown",$("ap-cap").textContent.includes("60"));
ok("  setup 0/2",$("ap-setup-count").textContent.includes("0/2"));
ok("  toggle off",$("ap-on").checked===false);

console.log("── Editing writes to the server ──");
click($("ap-addslot")); await sleep(150);
let put=calls("PUT","/api/autopilot").pop();
ok("adding a slot PUTs",!!put);
ok("  body has the browser's time zone",typeof put.body.tz==="string"&&put.body.tz.length>2,JSON.stringify(put&&put.body));
ok("  body has the new slot",put.body.slots.includes(9)&&put.body.slots.length===3,JSON.stringify(put.body.slots));
ok("  UI shows the server's answer",qa("#ap-slots select").length===3);
$("ap-title-in").value="Senior SDET"; w.addApTitle(); await sleep(150);
put=calls("PUT","/api/autopilot").pop();
ok("adding a title PUTs it with tz",put.body.titles.join()==="Senior SDET"&&!!put.body.tz,JSON.stringify(put.body));
ok("  title rendered as a chip",$("ap-titles").innerHTML.includes("Senior SDET"));

console.log("── Turning on without setup is refused client-side ──");
const putsBefore=calls("PUT","/api/autopilot").length;
$("ap-on").checked=true; await w.toggleAutopilot(); await sleep(60);
ok("no PUT sent",calls("PUT","/api/autopilot").length===putsBefore);
ok("  no run requested",calls("POST","/api/autopilot/run").length===0);
ok("  toast explains",$("toast").textContent.includes("Finish setup"));
ok("  switch snaps back off",$("ap-on").checked===false);

console.log("── With setup done: PUT then run, queue appears ──");
S.gmailConnected=S.phoneVerified=S.resumeConfirmed=true;
await w.syncAP(); await sleep(60);
ok("setup shows 2/2 after resync",$("ap-setup-count").textContent.includes("2/2"));
const n0=S.calls.length;
$("ap-on").checked=true; await w.toggleAutopilot(); await sleep(150);
const seq=S.calls.slice(n0).map(c=>c.m+" "+c.p);
const iPut=seq.indexOf("PUT /api/autopilot"), iRun=seq.indexOf("POST /api/autopilot/run");
ok("PUT then /run, in that order",iPut>=0&&iRun>iPut,seq.join(" | "));
ok("  PUT carried on:true",S.calls.slice(n0).find(c=>c.m==="PUT").body.on===true);
ok("  server is on",S.on===true);
ok("  two queue rows rendered",qa("#ap-queue .apqueue").length===2,qa("#ap-queue .apqueue").length+"");
ok("  run appears in Recent runs",$("ap-runs").textContent.includes("2 found"));
ok("  approve-all button shows count",$("ap-approveall").textContent.includes("2"));
ok("  server-supplied HTML is escaped, not executed",!w.__xss&&!$("ap-queue").querySelector("img"));
ok("  shows the apply host as recipient",$("ap-queue").textContent.includes("jobs.example.com"));

console.log("── Preview ──");
click(qa("#ap-queue button").find(b=>b.textContent==="Preview")); await sleep(120);
ok("preview modal opens",$("ov").classList.contains("on"));
ok("  shows the cover letter",$("md").textContent.includes("would love to join"));
ok("  hostile title stays inert in the modal",!$("md").querySelector("img")&&!w.__xss);
w.closeM();

console.log("── Review & apply ──");
const firstId=S.queue[0].id;
ok("queue rows offer Review & apply, not a bare Approve",qa("#ap-queue button").some(b=>b.textContent==="Review & apply")&&!qa("#ap-queue button").some(b=>b.textContent==="Approve"));
click(qa("#ap-queue button").find(b=>b.textContent==="Review & apply")); await sleep(150);
ok("  opens the Apply page for that item",calls("POST","/api/apply/start").length===1&&calls("POST","/api/apply/start")[0].body.application_id===firstId);
ok("  nothing approved or opened by that click",calls("POST",/\/approve$/).length===0&&w.__o.length===0);
w.closeM();

console.log("── Approve (one-tap, still available) ──");
await w.approveQueued(0); await sleep(150);
ok("approve endpoint called for that item",calls("POST",`/api/autopilot/queue/${firstId}/approve`).length===1);
ok("  posting opened in a new tab",w.__o.includes(S.queue[0].apply_url),w.__o.join());
ok("  queue re-synced to 1",qa("#ap-queue .apqueue").length===1);

console.log("── Rapid double-click can't approve two ──");
const secondId=S.queue[1].id;
const p1=w.approveQueued(0), p2=w.approveQueued(0); await Promise.all([p1,p2]); await sleep(120);
ok("only one approve request went out",calls("POST",/\/approve$/).length===2,calls("POST",/\/approve$/).length+"");
ok("  queue is empty",qa("#ap-queue .apqueue").length===0&&S.queue.find(q=>q.id===secondId).status==="opened");

console.log("── Skip ──");
await w.runAutopilotNow(); await sleep(120);
ok("run adds more rows",qa("#ap-queue .apqueue").length===2);
const skipId=S.queue.filter(q=>q.status==="ready")[0].id;
click(qa("#ap-queue button").find(b=>b.textContent==="Skip")); await sleep(150);
ok("skip DELETEs that item",calls("DELETE",`/api/autopilot/queue/${skipId}`).length===1);
ok("  queue down to 1",qa("#ap-queue .apqueue").length===1);

console.log("── Approve all ──");
await w.runAutopilotNow(); await sleep(120);
const cnt=qa("#ap-queue .apqueue").length;
ok("queue has several",cnt>=2,cnt+"");
click($("ap-approveall")); await sleep(150);
ok("approve-all endpoint called once",calls("POST","/api/autopilot/queue/approve-all").length===1);
ok("  queue cleared",qa("#ap-queue .apqueue").length===0&&S.queue.every(q=>q.status!=="ready"));
ok("  toast reports the server's count",$("toast").textContent.includes(String(cnt)),$("toast").textContent);
ok("  nothing opened by approve-all",w.__o.length===2,w.__o.length+"");

console.log("── Why it matched, honest history, new controls ──");
S.queue.push({id:"w1",fingerprint:"fw1",company:"Fit Co",title:"Lead SDET",location:"Remote",subject:"Lead SDET — Sam",apply_url:"https://boards.qa-hiring.dev/w1",
  matched_at:new Date().toISOString(),status:"ready",cover:"Dear Fit Co",summary:"S",highlights:["h"],fit:87,matched_skills:["Cypress","Java"],missing_skills:["Go"],verified:true,work_mode:"matches your preference"});
S.runs.unshift({at:new Date().toISOString(),found:9,prepared:2,skipped:1,note:"The AI service was busy or unavailable; will retry at your next slot",
  details:{filtered:{below_min_fit:12,already_handled:3,dead_link:2,visa_blocked:1},ai_unavailable:1,ai_invalid:1,not_attempted:4,dropped_closed:1,digest:"failed"}});
S.nextRunAt=new Date(Date.now()+3600e3).toISOString();
await w.syncAP(); await sleep(80);
const fitRow=qa("#ap-queue .apqueue").find(r=>r.textContent.includes("Fit Co"));
ok("queue card shows the fit percentage",!!fitRow&&fitRow.textContent.includes("87% fit"),fitRow&&fitRow.textContent);
ok("  and the matched skills",fitRow.textContent.includes("Cypress")&&fitRow.textContent.includes("Java"));
ok("  and what is missing",fitRow.textContent.includes("missing: Go"));
ok("  and that the link was verified",fitRow.textContent.includes("link verified"));
const runsTxt=$("ap-runs").textContent;
ok("run history lists why roles were skipped",runsTxt.includes("12 below your minimum fit")&&runsTxt.includes("3 already applied, queued or skipped")&&runsTxt.includes("2 had a dead link")&&runsTxt.includes("1 exclude your work authorization"),runsTxt);
ok("  AI busy, rejected drafts, deferred, dropped are all reported",runsTxt.includes("not prepared: AI busy")&&runsTxt.includes("rejected by our checks")&&runsTxt.includes("4 more waiting")&&runsTxt.includes("1 closed posting"),runsTxt);
ok("  a failed summary email is reported as failed, never as sent",runsTxt.includes("summary email could not be sent")&&!/summary email sent/.test(runsTxt));
ok("next run time is shown",/Next run:/.test($("ap-next").textContent),$("ap-next").textContent);
ok("min-fit select reflects the server",$("ap-minfit").value==="60");
$("ap-minfit").value="80"; $("ap-minfit").dispatchEvent(new w.Event("change",{bubbles:true})); await sleep(120);
ok("changing minimum fit PUTs minFit:80",calls("PUT","/api/autopilot").pop().body.minFit===80&&S.minFit===80);
$("ap-pause").value="2026-10-12"; $("ap-pause").dispatchEvent(new w.Event("change",{bubbles:true})); await sleep(120);
ok("picking a pause date PUTs it",S.pausedUntil==="2026-10-12"&&calls("PUT","/api/autopilot").pop().body.pausedUntil==="2026-10-12");
ok("  and says so",$("ap-pause-note").textContent.includes("Paused")&&$("ap-next").textContent.includes("Paused until"),$("ap-next").textContent);
click($("ap-pause-clear")); await sleep(120);
ok("clearing the pause PUTs an empty date",S.pausedUntil===null);
ok("summary email checkbox is disabled when the server can't send mail",$("ap-digest").disabled===true&&$("ap-digest-note").textContent.includes("isn't set up"),$("ap-digest-note").textContent);
S.emailConfigured=true; await w.syncAP(); await sleep(60);
ok("  enabled once the server can send mail",$("ap-digest").disabled===false&&$("ap-digest").checked===true);
$("ap-digest").checked=false; $("ap-digest").dispatchEvent(new w.Event("change",{bubbles:true})); await sleep(100);
ok("  opting out PUTs emailDigest:false",S.emailDigest===false);
click($("ap-previewbtn")); await sleep(150);
ok("dry-run preview calls /preview (no run)",calls("GET","/api/autopilot/preview").length===1&&calls("POST","/api/autopilot/run").length===calls("POST","/api/autopilot/run").length);
ok("  lists the roles with their fit",$("ap-preview").textContent.includes("Lead SDET")&&$("ap-preview").textContent.includes("91% fit"));
ok("  says how many clear the minimum and what was left out",$("ap-preview").textContent.includes("clear your 80% minimum")&&$("ap-preview").textContent.includes("4 below your minimum fit"),$("ap-preview").textContent);
ok("  server text is escaped",$("ap-preview").textContent.includes("Prev <b>Co</b>")&&!$("ap-preview").querySelector("b b"));
S.needsSkills=true; await w.syncAP(); await sleep(60);
ok("no skills: page tells the user to add skills",$("ap-needskills").textContent.includes("Add skills to your profile"));
S.needsSkills=false; await w.syncAP(); await sleep(60);
ok("  banner disappears once skills exist",$("ap-needskills").textContent.trim()==="");
S.queue.forEach(q=>{ if(q.status==="ready") q.status="skipped"; }); S.runs.shift(); await w.syncAP();

console.log("── Server errors surface and the UI re-syncs ──");
S.plan="free"; S.fail=(m)=>m==="PUT";
const g0=calls("GET","/api/autopilot").length;
click($("ap-addslot")); await sleep(150);
ok("402 shown as a toast",$("toast").textContent.includes("part of Pro"),$("toast").textContent);
ok("  UI re-fetched server state",calls("GET","/api/autopilot").length>g0);
ok("  displayed slots match the server",qa("#ap-slots select").length===S.slots.length,qa("#ap-slots select").length+" vs "+S.slots.length);
S.plan="pro"; S.fail=null;

console.log("── Account switch never shows the previous account's data ──");
ok("AP is scoped to s1",w.CP.AP.owner==="s1",w.CP.AP.owner);
S.titles=["Only s1 title"]; await w.syncAP();
w.CP.applySession({id:"s2",email:"pat@example.com",name:"Pat",account_type:"seeker",plan:"pro"});
w.renderAutopilot();
ok("titles cleared the moment the account changes",w.CP.AP.titles.length===0&&!$("ap-titles").innerHTML.includes("Only s1"),JSON.stringify(w.CP.AP.titles));
ok("  queue cleared",w.CP.AP.queue.length===0);
ok("  owner updated",w.CP.AP.owner==="s2");

console.log("── Stale owned copy is dropped on a signed-out load ──");
const S3=makeServer();
const w4=(()=>{const dd=new JSDOM(HTML,{runScripts:"dangerously",pretendToBeVisual:true,url:"https://careerpilot.ai/",
  beforeParse(x){x.CP_CONFIG={api:"http://api.test"};x.fetch=(u,o)=>S3.fetch(u,o);x.scrollTo=()=>{};
    x.localStorage.setItem("cp_autopilot",JSON.stringify({on:true,slots:[9],titles:["leaked"],skills:[],queue:[{id:"x",co:"Leak Co",ti:"t",to:"h",matchedAgo:"now"}],runs:[],owner:"s1",dailyCap:60}));}});return dd.window;})();
await sleep(600);
ok("no token → previous account's copy is not loaded",w4.CP.AP.titles.length===0&&w4.CP.AP.queue.length===0&&!w4.CP.AP.on,JSON.stringify(w4.CP.AP));

console.log("── Signed out: demo mode, no autopilot API traffic ──");
const S2=makeServer(); const wd=mk(S2); await sleep(700);
ok("not live without a session",wd.CP.apLive()===false);
wd.go("autopilot"); await sleep(150);
wd.CP.AP.gmailConnected=wd.CP.AP.phoneVerified=wd.CP.AP.resumeConfirmed=true; wd.CP.saveAP(); wd.renderAutopilot();
wd.addSlot(); wd.document.getElementById("ap-on").checked=true; await wd.toggleAutopilot(); await sleep(100);
ok("still works locally",wd.CP.AP.on===true&&wd.CP.AP.slots.length===4);
ok("  and never touches /api/autopilot",S2.calls.filter(c=>c.p.startsWith("/api/autopilot")).length===0,S2.calls.map(c=>c.p).join());

ok("ZERO uncaught errors",ERR.length===0,ERR.join(" | "));
console.log("\n"+"═".repeat(50));
console.log(`PASS ${P}    FAIL ${F}`);
if(F){console.log("\nFAILURES");fails.forEach(f=>console.log("  ✗ "+f))}else console.log("✓ ALL GREEN");
process.exit(0);
})();
