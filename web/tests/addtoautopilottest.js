/* "Add to Autopilot" on every job (list cards + job detail), the free allowance counter,
   the upgrade path, and the Autopilot page for free accounts. The API is an in-memory
   fake that mirrors server/api/routers/autopilot.py (add-job, the allowance in
   GET /api/autopilot) and server/api/routers/jobs.py (`autopilot` on each job). */
const path=require('path');
const {JSDOM}=require('jsdom');const fs=require('fs');
const HTML=fs.readFileSync(path.join(__dirname,'..','index.html'),'utf8');
let P=0,F=0;const fails=[];
const ok=(n,c,x)=>{c?P++:(F++,fails.push(n+(x?"  →  "+x:"")))};
const sleep=ms=>new Promise(r=>setTimeout(r,ms));
const ALLOW=5;

function makeServer(over={}){
  const S={plan:"free", used:0, queue:[], approved:new Set(), calls:[], delay:60, next:null, n:0,
    jobs:["A","B","C","D","E","F","G"].map(k=>({fingerprint:"fp"+k,company:k+" Corp",title:"SDET "+k,location:"Remote",
      work_mode:"remote",employment:"contract",company_type:"employer",is_fortune500:false,apply_url:"https://jobs.example.com/"+k,
      comp:{},exp:{min:3,max:8},visa:{usc:"u",gc:"u",h1b:"u",opt:"u"},role_family:"ui",skills:["Cypress"],days_live:1,seen_count:1,
      competition:"lo",referrals:[],fit:80,fit_reasons:{matched_skills:["Cypress"],missing_skills:[]},verified:true,link_status:"ok",source:"x",direct:false})),
    ...over};
  const free=()=>S.plan!=="pro";
  const allowance=()=>({plan:S.plan,freeAllowance:ALLOW,freeUsed:S.used,freeLeft:free()?Math.max(0,ALLOW-S.used):null});
  const state=()=>({on:false,slots:[9,13,17],tz:null,titles:[],skills:["Cypress"],workStyle:"",dailyCap:free()?0:60,
    scheduledAvailable:!free(),...allowance(),gmailConnected:false,phoneVerified:false,resumeConfirmed:false,phoneRequired:false,
    minFit:60,pausedUntil:null,emailDigest:true,emailConfigured:false,needsSkills:false,nextRunAt:null,
    queue:S.queue.map(({status,...q})=>q),runs:[],credits_remaining:10});
  const res=(status,body)=>({ok:status<400,status,json:async()=>body});
  S.fetch=async(url,opts={})=>{
    const u=new URL(url),p=u.pathname,m=(opts.method||"GET").toUpperCase();
    const body=opts.body?JSON.parse(opts.body):null, auth=(opts.headers||{}).Authorization;
    S.calls.push({m,p,body,auth});
    if(p==="/api/jobs") return res(200,{total:S.jobs.length,fit_available:true,jobs:S.jobs.map(j=>({...j,
      autopilot:S.queue.some(q=>q.fingerprint===j.fingerprint)?"queued":S.approved.has(j.fingerprint)?"approved":null}))});
    if(p==="/api/autopilot"&&m==="GET") return res(200,state());
    if(p==="/api/autopilot/progress") return res(200,{now:new Date().toISOString(),on:false,nextRunAt:null,pausedUntil:null,run:null});
    if(p==="/api/autopilot/add-job"){
      await sleep(S.delay);
      if(S.next){const n=S.next;S.next=null;return res(n[0],{detail:n[1]});}
      const j=S.jobs.find(x=>x.fingerprint===body.fingerprint); if(!j) return res(404,{detail:"That job isn't on the board any more."});
      const have=S.queue.find(q=>q.fingerprint===j.fingerprint);
      if(have) return res(200,{item:have,alreadyQueued:true,...allowance(),belowMinFit:false,minFit:60});
      if(free()&&S.used>=ALLOW) return res(402,{detail:`You've used all ${ALLOW} of your free Autopilot applications. Upgrade to Pro to add more, and to run Autopilot on a schedule.`});
      const it={id:"app-"+(++S.n),fingerprint:j.fingerprint,company:j.company,title:j.title,location:j.location,subject:j.title+" — Sam",
        apply_url:j.apply_url,matched_at:new Date().toISOString(),status:"ready",fit:80,matched_skills:["Cypress"],missing_skills:[]};
      S.queue.push(it); if(free()) S.used++;
      return res(200,{item:it,alreadyQueued:false,...allowance(),belowMinFit:false,minFit:60});
    }
    if(p==="/api/profile") return res(200,{positions:[],skills:[],name:"Sam",email:"sam@example.com",work_auth:[]});
    return res(404,{detail:"Not found"});
  };
  return S;
}
const mk=(S,{token=true,user={id:"s1",email:"sam@example.com",name:"Sam",account_type:"seeker",plan:"free"},width=1280}={})=>{
  const d=new JSDOM(HTML,{runScripts:"dangerously",pretendToBeVisual:true,url:"https://careerpilot.ai/",
    beforeParse(w){
      w.CP_CONFIG={api:"http://api.test"};
      if(token) w.localStorage.setItem("cp_token",JSON.stringify("tok"));
      w.fetch=(u,o)=>S.fetch(u,o);
      w.scrollTo=()=>{};w.confirm=()=>true;w.print=()=>{};
      Object.defineProperty(w,"innerWidth",{value:width,configurable:true});
      w.navigator.clipboard={writeText:()=>Promise.resolve()};
      w.__o=[];w.open=u=>{w.__o.push(u);return{focus(){}}};
    }});
  return d.window;
};
const boot=async(S,opts)=>{
  const w=mk(S,opts); await sleep(500);
  if(opts&&opts.token===false) return w;
  w.CP.applySession((opts&&opts.user)||{id:"s1",email:"sam@example.com",name:"Sam",account_type:"seeker",plan:"free"});
  await sleep(200); await w.loadJobs(); await sleep(250);
  return w;
};
const H=w=>{const d=w.document;return{d,$:i=>d.getElementById(i),qa:s=>[...d.querySelectorAll(s)],
  click:e=>{if(!e)throw new Error("missing element");e.dispatchEvent(new w.MouseEvent("click",{bubbles:true,cancelable:true}))},
  card:fp=>d.querySelector(`.job[data-jid="${fp}"]`),
  wrap:(fp,ctx)=>d.querySelector(`.apadd[data-apid="${fp}"][data-apctx="${ctx}"]`)};};
const addCalls=S=>S.calls.filter(c=>c.p==="/api/autopilot/add-job");

(async()=>{
console.log("\n╔═══ ADD TO AUTOPILOT — every job, free allowance, upgrade path ═══╗\n");

console.log("── Signed out ──");
{
  const S=makeServer(); const w=await boot(S,{token:false}); const {$,qa,click,card,d}=H(w);
  ok("job cards are showing",qa(".job").length===7,qa(".job").length);
  ok("EVERY card has an Add to Autopilot button",qa(".job").every(c=>c.querySelector(".apadd button")&&/Add to Autopilot/.test(c.querySelector(".apadd").textContent)));
  ok("  no allowance counter when signed out",qa(".apadd-note").length===0);
  click(card("fpA").querySelector(".apadd button")); await sleep(80);
  ok("clicking asks you to sign in (sign-in screen opens)",$("authGate").classList.contains("on"));
  ok("  and nothing was sent to the server",addCalls(S).length===0);
  w.close();
}

console.log("── Free account: buttons, counter, busy, no double-submit ──");
const S=makeServer();
let w=await boot(S); let {$,qa,click,card,wrap,d}=H(w);
ok("state came from the server (GET /api/autopilot) after sign-in",S.calls.some(c=>c.m==="GET"&&c.p==="/api/autopilot"&&c.auth==="Bearer tok"));
ok("every card has the button + '5 of 5 free left'",qa(".job").length===7&&qa(".job").every(c=>/Add to Autopilot/.test(c.querySelector(".apadd").textContent)&&/5 of 5 free left/.test(c.querySelector(".apadd").textContent)),qa(".apadd").map(x=>x.textContent).join("|"));
const b0=card("fpA").querySelector(".apadd button");
ok("it is a real <button> (keyboard-focusable)",b0.tagName==="BUTTON"&&b0.type==="button"&&b0.tabIndex>=0);
b0.focus(); b0.dispatchEvent(new w.KeyboardEvent("keydown",{key:"Enter",bubbles:true,cancelable:true}));
ok("pressing Enter on the button does not also open the job detail",w.eval("SELECTED_JOB")==null,String(w.eval("SELECTED_JOB")));
click(b0); click(b0); click(card("fpA").querySelector(".apadd button")||b0);      // a frantic triple-click
await sleep(20);
let busy=card("fpA").querySelector(".apadd");
ok("while preparing: disabled 'Preparing…' with a spinner and aria-busy",busy.querySelector("button").disabled&&/Preparing…/.test(busy.textContent)&&busy.querySelector("button").getAttribute("aria-busy")==="true"&&!!busy.querySelector(".apadd-spin"),busy.textContent);
ok("  other jobs stay usable",!card("fpB").querySelector(".apadd button").disabled);
await sleep(300);
ok("triple-click sent ONE request",addCalls(S).length===1&&addCalls(S)[0].body.fingerprint==="fpA"&&addCalls(S)[0].auth==="Bearer tok",JSON.stringify(addCalls(S).map(c=>c.body)));
let done=card("fpA").querySelector(".apadd");
ok("done: 'In your Autopilot queue', a link to the queue",done.classList.contains("done")&&/In your Autopilot queue/.test(done.textContent)&&done.querySelector("a")&&done.querySelector("a").getAttribute("href")==="#autopilot");
ok("  the other cards now say '4 of 5 free left'",qa(".job").filter(c=>c.dataset.jid!=="fpA").every(c=>/4 of 5 free left/.test(c.querySelector(".apadd").textContent)));
ok("  the item is in the Autopilot queue (same queue as scheduled runs)",w.eval("AP.queue.length")===1&&w.eval("AP.queue[0].jobId")==="fpA");
ok("  the list was not re-rendered under you (card node kept)",card("fpA")===d.querySelector('.job[data-jid="fpA"]'));
click(done.querySelector("a")); await sleep(50);
ok("clicking the link opens the Autopilot page",$("p-autopilot").classList.contains("on"));
ok("  free account: shows 'You have 4 of 5 free Autopilot applications'",/You have 4 of 5 free Autopilot applications/.test($("ap-free").textContent)&&!$("ap-free").hidden,$("ap-free").textContent);
ok("  explains scheduled Autopilot is Pro, and the allowance is not per day",/Scheduled Autopilot/.test($("ap-free").textContent)&&/Pro/.test($("ap-free").textContent)&&/not per day/.test($("ap-free").textContent));
ok("  the queue stays visible with the added item",/SDET A/.test($("ap-queue").textContent)&&$("ap-queuecard").style.display!=="none");
ok("  Setup / scheduled-run cards are hidden for free",qa("#p-autopilot [data-sched]").every(e=>e.style.display==="none"));
ok("  the Flight plan (toggle) is still there, marked Pro",!$("ap-flightplan").style.display&&!$("ap-flight-pro").hidden&&/part of Pro/.test($("ap-cap").textContent));
w.go("jobs"); await sleep(30);

console.log("── Job detail ──");
w.openJob("fpB"); await sleep(80);
const detailRoot=$("jobDetailPane")&&$("jobDetailPane").querySelector(".splitcard")?$("jobDetailPane"):$("md");
const dw=detailRoot.querySelector('.apadd[data-apctx="detail"]');
ok("the detail has the button too (next to Apply / Tailor)",!!dw&&/Add to Autopilot/.test(dw.textContent)&&/4 of 5 free left/.test(dw.textContent)&&!!dw.closest(".acts"));
ok("  detail of an already-added job shows the queue link",(()=>{w.openJob("fpA");const r=$("jobDetailPane")&&$("jobDetailPane").querySelector(".splitcard")?$("jobDetailPane"):$("md");return /In your Autopilot queue/.test(r.querySelector('.apadd[data-apctx="detail"]').textContent);})());
w.openJob("fpB"); await sleep(50);
click(detailRoot.querySelector('.apadd[data-apctx="detail"] button')); await sleep(15);
ok("  detail button goes busy, and so does the same job's list card (one state)",/Preparing…/.test(detailRoot.querySelector('.apadd[data-apctx="detail"]').textContent)&&/Preparing…/.test(wrap("fpB","card").textContent));
await sleep(300);
ok("  after: both places say 'In your Autopilot queue'; counter 3 of 5",/In your Autopilot queue/.test(detailRoot.querySelector('.apadd[data-apctx="detail"]').textContent)&&/In your Autopilot queue/.test(wrap("fpB","card").textContent)&&/3 of 5 free left/.test(wrap("fpC","card").textContent));

console.log("── Running out: the 6th prompts an upgrade ──");
for(const k of ["fpC","fpD","fpE"]){ click(wrap(k,"card").querySelector("button")); await sleep(180); }
ok("five added; five in the queue",addCalls(S).length===5&&S.used===5&&w.eval("AP.queue.length")===5,`${addCalls(S).length} ${S.used} ${w.eval("AP.queue.length")}`);
const f=wrap("fpF","card");
ok("at 0 left the remaining buttons become 'Upgrade for more Autopilot'",qa(".job").filter(c=>!/In your Autopilot queue/.test(c.querySelector(".apadd").textContent)).every(c=>/Upgrade for more Autopilot/.test(c.querySelector(".apadd").textContent)),qa(".apadd").map(x=>x.textContent).join("|"));
ok("  with an honest message",/used your 5 free Autopilot applications/.test(f.textContent));
click(f.querySelector("button")); await sleep(60);
ok("  the upgrade button goes to the plan page, without calling add-job",$("p-plan").classList.contains("on")&&addCalls(S).length===5);
ok("  Autopilot page says so, offers an upgrade, and the queue still works",(w.go("autopilot"),/used your 5 free Autopilot applications/.test($("ap-free").textContent)&&/Upgrade for more Autopilot/.test($("ap-free").textContent)&&/SDET A/.test($("ap-queue").textContent)&&$("ap-queue").querySelectorAll(".apqueue").length===5));
w.go("jobs"); await sleep(30);

console.log("── After a reload the state comes from the server ──");
w.close();
w=await boot(S); ({$,qa,click,card,wrap,d}=H(w));
ok("added jobs still say 'In your Autopilot queue' (from the jobs API, not the browser)",["fpA","fpB","fpC","fpD","fpE"].every(k=>/In your Autopilot queue/.test(wrap(k,"card").textContent)));
ok("  the rest still say Upgrade (allowance from the server)",/Upgrade for more Autopilot/.test(wrap("fpF","card").textContent)&&/Upgrade for more Autopilot/.test(wrap("fpG","card").textContent));
ok("  a second reload cannot re-add an existing job (button is a link, not an add)",!wrap("fpA","card").querySelector("button"));
S.approved.add("fpA"); S.queue=S.queue.filter(q=>q.fingerprint!=="fpA"); await w.loadJobs(); await sleep(100);
ok("approved jobs read 'Approved in Autopilot'",/Approved in Autopilot/.test(wrap("fpA","card").textContent));
w.close();

console.log("── Errors are plain English, the button recovers ──");
const E=makeServer(); w=await boot(E); ({$,qa,click,card,wrap,d}=H(w));
const tryErr=async(status,msg,fp)=>{E.next=[status,msg];click(wrap(fp,"card").querySelector("button")); await sleep(150); return wrap(fp,"card");};
let el=await tryErr(400,"Add your skills first. Autopilot scores every job against your skills and writes the tailored application from your profile.","fpA");
ok("no skills: message + link to your profile, button back to Add",/Add your skills first/.test(el.textContent)&&/Open your profile/.test(el.textContent)&&/Add to Autopilot/.test(el.textContent)&&!el.querySelector("button").disabled,el.textContent);
ok("  the error is announced (role=alert)",!!el.querySelector('[role="alert"]'));
el=await tryErr(400,"This posting says it won't accept H-1B, so it isn't one you can apply to.","fpB");
ok("work authorization excluded",/won't accept H-1B/.test(el.textContent));
el=await tryErr(503,"The AI is busy right now, so this wasn't prepared. Nothing was used from your free allowance. Try again in a minute.","fpC");
ok("AI busy: says nothing was used, counter unchanged (5 of 5)",/AI is busy/.test(el.textContent)&&/Nothing was used/.test(el.textContent)&&/5 of 5 free left/.test(el.textContent),el.textContent);
el=await tryErr(409,"Your Autopilot queue is full (25). Approve or skip a few, then add this one.","fpD");
ok("queue full",/queue is full/.test(el.textContent));
el=await tryErr(409,"You already have this job in your applications.","fpE");
ok("already added / applied",/already have this job/.test(el.textContent));
click(wrap("fpA","card").querySelector("button")); await sleep(200);
ok("retrying clears the old error and works",/In your Autopilot queue/.test(wrap("fpA","card").textContent)&&!/Add your skills/.test(wrap("fpA","card").textContent));
const realFetch=E.fetch; E.fetch=async(u,o)=>{ if(/add-job/.test(u)) throw new TypeError("network down"); return realFetch(u,o); };
click(wrap("fpF","card").querySelector("button")); await sleep(200);
ok("network failure: says nothing was used and to retry",/Couldn't reach the server, so nothing was used/.test(wrap("fpF","card").textContent)&&/Add to Autopilot/.test(wrap("fpF","card").textContent));
E.fetch=realFetch;
// the server says 402 when the counter is stale (used up in another tab)
E.used=ALLOW;
click(wrap("fpG","card").querySelector("button")); await sleep(250);
ok("402 from another tab's spending: every button flips to Upgrade",/Upgrade for more Autopilot/.test(wrap("fpG","card").textContent)&&/Upgrade for more Autopilot/.test(wrap("fpF","card").textContent)&&/used your 5 free/.test(wrap("fpG","card").textContent));
w.close();

console.log("── Pro: no counter, no upgrade prompt ──");
const PR=makeServer({plan:"pro"}); w=await boot(PR,{user:{id:"p1",email:"pro@example.com",name:"Pro",account_type:"seeker",plan:"pro"}}); ({$,qa,click,card,wrap,d}=H(w));
ok("Pro sees the button on every card and NO 'free left' counter",qa(".job").every(c=>/Add to Autopilot/.test(c.querySelector(".apadd").textContent))&&!/free left/.test($("list").textContent));
for(const k of ["fpA","fpB","fpC","fpD","fpE","fpF"]){ click(wrap(k,"card").querySelector("button")); await sleep(160); }
ok("Pro can add past 5, and is never asked to upgrade",addCalls(PR).length===6&&PR.queue.length===6&&!/Upgrade for more Autopilot/.test($("list").textContent));
ok("  Autopilot page for Pro has no free-allowance card and shows the scheduled controls",(w.go("autopilot"),$("ap-free").hidden&&qa("#p-autopilot [data-sched]").every(e=>e.style.display!=="none")));
w.close();

console.log("── Recruiters don't get it ──");
const RC=makeServer(); w=await boot(RC,{user:{id:"r1",email:"rec@example.com",name:"Rec",account_type:"recruiter",plan:"free"}}); ({$,qa,click,card,wrap,d}=H(w));
ok("no Add to Autopilot on a recruiter's cards",qa(".job").length>0&&qa(".apadd").length===0);
w.close();

console.log("── Static copy ──");
{
  const w2=mk(makeServer(),{token:false}); await sleep(300); const {$,qa}=H(w2);
  w2.go("plan"); await sleep(50);
  const cards=qa('.pricegrid[data-only="seeker"] .pricecard');
  ok("Free plan lists '5 Autopilot applications'",/5 Autopilot applications/.test(cards[0].textContent));
  ok("Pro plan lists Scheduled Autopilot",/Scheduled Autopilot/.test(cards[1].textContent));
  ok("Free plan no longer says Autopilot is 'Pro only'",!/Autopilot[^]*Pro only/.test(cards[0].textContent));
  w2.close();
}

console.log(`\n${"=".repeat(46)}\nPASS ${P}    FAIL ${F}`);
if(F){console.log("\nFAILURES");fails.forEach(f=>console.log("  x "+f));process.exit(1);}
console.log("ALL GREEN");
})();
