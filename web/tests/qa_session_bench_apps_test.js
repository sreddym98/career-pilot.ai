/* Regression tests from the end-to-end QA pass: session expiry, per-account
   data on sign-out, the recruiter bench (server-backed, plan-capped), and the
   applications tracker (status, removal, stale notes). A tiny in-memory API
   stands in for the server so the real client code paths run. */
const path=require('path');
const {JSDOM}=require('jsdom');const fs=require('fs');
const HTML=fs.readFileSync(path.join(__dirname,'..','index.html'),'utf8');
let P=0,F=0;const fails=[];
const ok=(n,c,x)=>{c?P++:(F++,fails.push(n+(x?"  →  "+x:"")))};
const sleep=ms=>new Promise(r=>setTimeout(r,ms));

function mk({token=null,role=null,expired=false,api}={}){
  const calls=[];
  const dom=new JSDOM(HTML,{runScripts:"dangerously",pretendToBeVisual:true,url:"https://careerpilot.ai/",
    beforeParse(w){
      w.CP_CONFIG={api:"http://api.test"};
      w.scrollTo=()=>{};w.confirm=()=>true;w.print=()=>{};
      Object.defineProperty(w,"innerWidth",{value:1200,configurable:true});
      w.navigator.clipboard={writeText:()=>Promise.resolve()};
      w.open=()=>({focus(){}});
      if(token) w.localStorage.setItem("cp_token",JSON.stringify(token));
      if(role) w.localStorage.setItem("cp_role",JSON.stringify(role));
      w.__reloads=0;
      w.fetch=async(url,opts={})=>{
        const p=String(url).replace("http://api.test","");
        const m=(opts.method||"GET").toUpperCase();
        let body=null; try{body=opts.body?JSON.parse(opts.body):null}catch(_){}
        calls.push({p,m,body,auth:(opts.headers||{}).Authorization});
        const r=api?api(p,m,body):null;
        const res=r||{status:404,json:{detail:"not found"}};
        return {ok:res.status<400,status:res.status,json:async()=>res.json,text:async()=>JSON.stringify(res.json)};
      };
    }});
  const w=dom.window;
  return {w,calls,d:w.document,$:i=>w.document.getElementById(i)};
}
const fill=(t,rec)=>{const {w,$}=t;
  $("c-name").value=rec.name; w.CP.CAND_SKILLS.push("SQL"); $("c-role").selectedIndex=0;};

(async()=>{
console.log("\n╔═══ QA REGRESSIONS ═══╗\n");

console.log("── Boot with a refused token ──");
{
  const t=mk({token:"stale",role:"recruiter",api:p=>p==="/api/auth/session"?{status:401,json:{detail:"Invalid or expired session"}}:null});
  t.w.localStorage.setItem("cp_bench",JSON.stringify([{id:1,name:"Someone",skills:["x"]}]));
  t.w.localStorage.setItem("cp_eval_report",JSON.stringify({x:1}));
  await sleep(800);
  const ls=k=>t.w.localStorage.getItem(k);
  ok("token dropped",ls("cp_token")===null);
  ok("remembered role dropped (no stranded recruiter sidebar)",ls("cp_role")===null,ls("cp_role"));
  ok("previous account's bench dropped",ls("cp_bench")===null);
  ok("previous account's evaluation dropped",ls("cp_eval_report")===null);
  ok("expiry noted for the next load",t.w.sessionStorage.getItem("cp_expired")==="1");
}
console.log("── Boot with the server unreachable ──");
{
  const t=mk({token:"good",role:"seeker",api:p=>p==="/api/auth/session"?{status:503,json:{detail:"down"}}:null});
  await sleep(800);
  ok("token kept when the server is merely down",t.w.localStorage.getItem("cp_token")!==null);
}
console.log("── Sign-out clears everything per-account ──");
{
  const t=mk();await sleep(300);
  const keys=["cp_token","cp_role","cp_mode","cp_bench","cp_subs","cp_autopilot","cp_eval_id","cp_eval_goals",
    "cp_eval_report","cp_interview_last","cp_support_tickets","cp_state_v1"];
  keys.forEach(k=>t.w.localStorage.setItem(k,'"x"'));
  t.w.CP.clearAccountData();
  ok("no account key survives",keys.every(k=>t.w.localStorage.getItem(k)===null),keys.filter(k=>t.w.localStorage.getItem(k)!==null).join());
}
console.log("── Mid-session 401 ──");
{
  let refuse=false;
  const t=mk({token:"good",role:"seeker",api:(p,m)=>{
    if(p==="/api/auth/session")return{status:200,json:{user:{id:"s1",email:"s@x.com",name:"S",account_type:"seeker",plan:"free"}}};
    if(p==="/api/profile"||p==="/api/connections"||p==="/api/applications")
      return refuse?{status:401,json:{detail:"Invalid or expired session"}}:{status:200,json:{positions:[],skills:[],applications:[],companies:[]}};
    return null;}});
  await sleep(800);
  ok("signed in",!!t.w.CP.SESSION);
  refuse=true;
  await t.w.CP.pullSeekerData(false).catch(()=>{});
  ok("a refused credential signs the client out",t.w.CP.SESSION===null&&t.w.localStorage.getItem("cp_token")===null);
}
console.log("── Sign-in errors ──");
{
  const t=mk({api:(p)=>p==="/api/auth/signup"?{status:422,json:{detail:[{msg:"value is not a valid email address: An email address must have an @-sign.",type:"value_error"}]}}
                                                :p==="/api/auth/login"?{status:401,json:{detail:"That email and password don't match"}}:null});
  await sleep(300);
  t.w.CP.openAuth("up");t.$("au-email").value="a@b";t.$("au-pass").value="Str0ngPass!x";
  await t.w.CP.authSubmit();
  ok("validation errors are readable, not [object Object]",!/object/i.test(t.$("authErr").textContent)&&/email/i.test(t.$("authErr").textContent),t.$("authErr").textContent);
  t.w.CP.authTab("in");t.$("au-email").value="a@b.co";t.$("au-pass").value="wrong-pass-1";
  await t.w.CP.authSubmit();
  ok("wrong password shows the message and does not sign out/reload",/don't match/.test(t.$("authErr").textContent));
}

console.log("── Recruiter bench ──");
{
  let doc=null,plan="free",limit=3;
  const api=(p,m,body)=>{
    if(p==="/api/bench"&&m==="GET")return{status:200,json:doc?{exists:true,...doc}:{exists:false,candidates:[],submissions:[]}};
    if(p==="/api/bench"&&m==="PUT"){
      if(limit!==null&&body.candidates.length>limit)return{status:402,json:{detail:`Your plan covers ${limit} people on the bench. Upgrade to add more.`}};
      doc=body;return{status:200,json:{exists:true,...doc}};}
    return null;};
  const t=mk({api});await sleep(300);const {w,$}=t;
  // signed-out demo keeps its six sample people
  w.CP.setMode("recruiter");await sleep(60);
  ok("signed-out demo bench is the six samples",w.CP.BENCH.length===6);
  w.CP.applySession({id:"r1",email:"r@x.com",name:"R",account_type:"recruiter",plan,bench_limit:limit},true);
  await sleep(300);
  ok("signed-in recruiter does not inherit the sample six",w.CP.BENCH.length===0,w.CP.BENCH.length);
  ok("empty bench says so and offers an add button",/Your bench is empty/.test($("benchList").textContent)&&!!$("benchList").querySelector(".btn-p"));
  ok("the limit is shown",/limit 3/.test($("benchStats").textContent));
  const add=async name=>{w.editCand(0);await sleep(20);$("c-name").value=name;w.CP.CAND_SKILLS.push("SQL");w.saveCand(0);await sleep(60);};
  await add("Ann");await add("Bo");await add("Cy");
  ok("three fit on the free plan",w.CP.BENCH.length===3);
  ok("and were saved to the server",doc&&doc.candidates.length===3,JSON.stringify(doc&&doc.candidates.length));
  w.editCand(0);await sleep(40);
  ok("a fourth opens the upgrade prompt, not the form",!$("c-name")&&/covers 3 people/.test($("md").textContent),$("md").textContent.slice(0,120));
  ok("  which offers the recruiter plan",/Upgrade/.test($("md").textContent));
  ok("  and adds nobody",w.CP.BENCH.length===3);
  w.closeM&&w.closeM();
  // fresh browser, same account: the bench comes from the server
  const t2=mk({token:"good",role:"recruiter",api:(p,m,b)=>p==="/api/auth/session"
    ?{status:200,json:{user:{id:"r1",email:"r@x.com",name:"R",account_type:"recruiter",plan,bench_limit:limit}}}:api(p,m,b)});
  await sleep(900);
  ok("a second device sees the same bench",t2.w.CP.BENCH.length===3&&t2.w.CP.BENCH.map(c=>c.name).join()==="Ann,Bo,Cy",t2.w.CP.BENCH.map(c=>c.name).join());
  // uncapped plan
  const t3=mk({api});await sleep(300);
  t3.w.CP.applySession({id:"r2",email:"e@x.com",name:"E",account_type:"recruiter",plan:"enterprise",bench_limit:null},true);await sleep(200);
  ok("no cap, no prompt",t3.w.CP.benchFull()===false);
  // a stale client (thinks it has room) is corrected by the server's 402
  limit=1;
  const t4=mk({token:"good",role:"recruiter",api:(p,m,b)=>p==="/api/auth/session"
    ?{status:200,json:{user:{id:"r1",email:"r@x.com",name:"R",account_type:"recruiter",plan:"recruiter",bench_limit:10}}}:api(p,m,b)});
  await sleep(900);
  t4.w.editCand(0);await sleep(30);t4.$("c-name").value="Dee";t4.w.CP.CAND_SKILLS.push("SQL");t4.w.saveCand(0);await sleep(400);
  ok("server 402 rolls back to the server's copy and shows the prompt",/covers|full/i.test(t4.$("md").textContent)&&t4.w.CP.BENCH.length===3,t4.w.CP.BENCH.length+" "+t4.$("md").textContent.slice(0,60));
}

console.log("── Applications tracker ──");
{
  const rows=[{id:"11111111-1111-1111-1111-111111111111",company:"Acme",title:"SDET",location:"Remote",status:"submitted",short:"sent",
               note:"Applied just now",updated_at:new Date(Date.now()-3*864e5).toISOString(),applied_at:null}];
  const api=(p,m,body)=>{
    if(p==="/api/auth/session")return{status:200,json:{user:{id:"s1",email:"s@x.com",name:"S",account_type:"seeker",plan:"free"}}};
    if(p==="/api/applications"&&m==="GET")return{status:200,json:{total:rows.length,counts:{},applications:rows}};
    if(p==="/api/applications"&&m==="POST"){
      let r=rows.find(x=>x.company===body.company&&x.title===body.title);
      if(!r){r={id:"2222222"+rows.length+"-2222-2222-2222-222222222222",company:body.company,title:body.title,location:body.location,note:body.note};rows.push(r);}
      r.status=body.status==="sent"?"submitted":body.status;r.short=body.status;return{status:200,json:r};}
    if(/^\/api\/applications\//.test(p)&&m==="PATCH"){const r=rows.find(x=>p.endsWith(x.id));r.short=body.status;return{status:200,json:r};}
    if(/^\/api\/applications\//.test(p)&&m==="DELETE"){const i=rows.findIndex(x=>p.endsWith(x.id));rows.splice(i,1);return{status:200,json:{deleted:true}};}
    if(p==="/api/profile")return{status:200,json:{positions:[],skills:[]}};
    if(p==="/api/connections")return{status:200,json:{companies:[]}};
    return null;};
  const t=mk({token:"good",role:"seeker",api});await sleep(1000);const {w,$}=t;
  const A=()=>w.CP.APPS;
  ok("loaded from the server",A().length===1&&A()[0].co==="Acme");
  ok("a stale auto-note is not shown as if it were current",A()[0].when==="3 days ago",A()[0].when);
}
{
  const rows=[];
  const api=(p,m,body)=>{
    if(p==="/api/auth/session")return{status:200,json:{user:{id:"s1",email:"s@x.com",name:"S",account_type:"seeker",plan:"free"}}};
    if(p==="/api/applications"&&m==="GET")return{status:200,json:{total:rows.length,counts:{},applications:rows}};
    if(p==="/api/applications"&&m==="POST"){
      let r=rows.find(x=>x.company===body.company&&x.title===body.title);
      if(!r){r={id:"3333333"+rows.length+"-3333-3333-3333-333333333333",company:body.company,title:body.title,note:body.note};rows.push(r);}
      r.short=body.status;r.status=body.status;return{status:200,json:r};}
    if(/^\/api\/applications\//.test(p)&&m==="PATCH"){const r=rows.find(x=>p.endsWith(x.id));r.short=body.status;return{status:200,json:r};}
    if(/^\/api\/applications\//.test(p)&&m==="DELETE"){const i=rows.findIndex(x=>p.endsWith(x.id));rows.splice(i,1);return{status:200,json:{deleted:true}};}
    if(p==="/api/profile")return{status:200,json:{positions:[],skills:[]}};
    if(p==="/api/connections")return{status:200,json:{companies:[]}};
    return null;};
  const t=mk({token:"good",role:"seeker",api});await sleep(1000);const {w,$,calls}=t;
  const job=w.CP.J[0];
  // Apply through the UI path: open the posting, then answer the ask bar.
  w.applyTo(job.id);await sleep(50);
  w.dispatchEvent(new w.Event("focus"));await sleep(900);
  const yes=[...t.d.querySelectorAll("#askbar button")].find(b=>/Yes, applied/.test(b.textContent));
  yes&&yes.dispatchEvent(new w.MouseEvent("click",{bubbles:true}));await sleep(200);
  const posts=calls.filter(c=>c.p==="/api/applications"&&c.m==="POST");
  ok("marking sends the status",posts.some(c=>c.body.status==="sent"));
  ok("  but never the throw-away 'Just now' text as a note",posts.every(c=>!c.body.note),JSON.stringify(posts.map(c=>c.body.note)));
  const mine=w.CP.APPS.find(a=>a.co===job.co&&a.ti===job.ti);
  ok("  and adopts the server id for later edits",mine&&/^3333/.test(mine.id||""),mine&&mine.id);
  const i=w.CP.APPS.indexOf(mine);
  w.CP.setAppStatus(i,"intv");await sleep(100);
  ok("changing status updates the row",w.CP.APPS[i].st==="intv");
  ok("  PATCHes the server",calls.some(c=>c.m==="PATCH"&&c.body.status==="intv"));
  ok("  and the summary and list agree",/1 in conversation/.test($("appSum").textContent)&&$("appList").querySelectorAll(".row").length===1,$("appSum").textContent);
  ok("  the list has a status control and a remove link",!!$("appList").querySelector("select.appst")&&!!$("appList").querySelector(".appdel"));
  w.CP.removeApp(i);await sleep(100);
  ok("removing drops the row",w.CP.APPS.length===0);
  ok("  DELETEs it on the server",calls.some(c=>c.m==="DELETE")&&rows.length===0);
  ok("  and the empty state returns",/No applications yet/.test($("appList").textContent));
}
console.log("── Signup carries up real local applications, not samples ──");
{
  const rows=[];
  const api=(p,m,body)=>{
    if(p==="/api/applications"&&m==="GET")return{status:200,json:{total:0,counts:{},applications:rows}};
    if(p==="/api/applications"&&m==="POST"){rows.push(body);return{status:200,json:{id:"44444444-4444-4444-4444-444444444444",...body}};}
    if(p==="/api/profile")return{status:200,json:{positions:[],skills:[]}};
    if(p==="/api/connections")return{status:200,json:{companies:[]}};
    return null;};
  const t=mk({api});await sleep(400);const {w}=t;
  w.CP.APPS.unshift({co:"Mine Co",ti:"SDET",lo:"Remote",st:"sent",when:"Applied just now"});
  w.CP.applySession({id:"s9",email:"n@x.com",name:"N",account_type:"seeker",plan:"free"},true);
  await sleep(600);
  ok("the sample rows are dropped",!w.CP.APPS.some(a=>a.co==="Vaspire Technologies"),w.CP.APPS.map(a=>a.co).join());
  ok("their own row is kept",w.CP.APPS.length===1&&w.CP.APPS[0].co==="Mine Co");
  ok("and uploaded, so a second device sees it",rows.length===1&&rows[0].company==="Mine Co",JSON.stringify(rows));
}

console.log("\n══════════════════════════════════════════════════");
console.log(`PASS ${P}    FAIL ${F}`);
if(F){console.log("\nFAILURES");fails.forEach(f=>console.log("  ✗ ",f));process.exit(1);}
process.exit(0);
})();
