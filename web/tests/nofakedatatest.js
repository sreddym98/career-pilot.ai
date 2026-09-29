/* Guards the owner's rule: no hardcoded sample data may reach a real user.
   With window.CP_CONFIG.api set (production), every sample structure must be
   empty and unreachable; the built-in sample only exists in the no-backend
   demo. Each screen is rendered and its text scanned for the known sample
   strings, so a new code path that reads a sample constant fails here. */
const path=require('path');
const {JSDOM}=require('jsdom');const fs=require('fs');
const HTML=fs.readFileSync(path.join(__dirname,'..','index.html'),'utf8');
let P=0,F=0;const fails=[];
const ok=(n,c,x)=>{c?P++:(F++,fails.push(n+(x?"  →  "+x:"")))};
const sleep=ms=>new Promise(r=>setTimeout(r,ms));

// Everything the page used to ship as sample content.
const SAMPLE_STRINGS=["Vaspire","STG Consulting","Priya Venkatesan","Arjun Mehta","Lakshmi Rao","Daniel Osei","Sofia Ramirez",
  "priya.v@example.com","Anil Kumar","Meera Sundaram","Deepa Nair","James Okoro","Sarah Lindqvist","Chen Wu","Priyanka Das",
  "santoshreddy","Jane · Ampstek","Tata Consultancy","CashAPona","Example listing","Demo board","Mastercard is hiring",
  "Techrakers","Xchange Software","Net2Source","Bentonville","Priya Raman"];
const leaks=t=>SAMPLE_STRINGS.filter(x=>t.includes(x));

function mk({live=true,token=null,role=null,search="",api,ls={}}={}){
  const calls=[];
  const dom=new JSDOM(HTML,{runScripts:"dangerously",pretendToBeVisual:true,url:"https://careerpilot.ai/"+search,
    beforeParse(w){
      if(live) w.CP_CONFIG={api:"http://api.test"};
      w.scrollTo=()=>{};w.confirm=()=>true;w.print=()=>{};
      Object.defineProperty(w,"innerWidth",{value:1200,configurable:true});
      w.navigator.clipboard={writeText:()=>Promise.resolve()};
      w.open=()=>({focus(){}});
      if(token) w.localStorage.setItem("cp_token",JSON.stringify(token));
      if(role) w.localStorage.setItem("cp_role",JSON.stringify(role));
      for(const [k,v] of Object.entries(ls)) w.localStorage.setItem(k,JSON.stringify(v));
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
const emptyBoard=p=>p.startsWith("/api/jobs")?{status:200,json:{jobs:[],total:0}}:null;
const visibleText=t=>[...t.d.querySelectorAll(".pg,.sidebar")].map(e=>e.textContent).join("\n")+t.$("md").textContent;
const RESUME_SKILLS_ONLY=`Skills and tools I use every day include Playwright, Selenium, Cypress, Postman, RestAssured, SQL, Python, Java and Jenkins for automation in a CI pipeline.\nNothing here has a date range so no role can be parsed from it at all, which used to fall back to a built-in profile.`;

(async()=>{
console.log("\n╔═══ NO SAMPLE DATA WITH AN API CONFIGURED ═══╗\n");

console.log("── Signed-out visitor on the live site ──");
{
  const t=mk({api:emptyBoard});await sleep(400);const {w,$}=t;
  ok("live mode is not demo",w.CP.DEMO===false&&!!w.CP.CP_API);
  ok("no sample roles",w.CP.J.length===0,w.CP.J.length);
  ok("no sample applications",w.CP.APPS.length===0,w.CP.APPS.length);
  ok("no sample contacts",w.CP.peopleNow().length===0);
  ok("board says it is empty, not 'Nothing matches'",/No roles yet/.test($("list").textContent),$("list").textContent.slice(0,80));
  ok("no demo banner",$("sampleBar").style.display==="none");
  for(const pg of ["jobs","apps","me","learn","people","refer","plan","support","autopilot","interview","resume"]){
    w.go(pg);await sleep(40);
    const l=leaks(visibleText(t));
    ok(`page '${pg}' shows no sample strings`,l.length===0,l.join(", "));
  }
  w.CP.setMode("recruiter");await sleep(80);
  ok("recruiter mode starts with an empty bench",w.CP.BENCH.length===0);
  for(const pg of ["bench","subs"]){ w.go(pg);await sleep(40); const l=leaks(visibleText(t)); ok(`page '${pg}' shows no sample strings`,l.length===0,l.join(", ")); }
  ok("empty-bench state offered",/Your bench is empty/.test($("benchList").textContent));
  ok("no submissions",w.CP.SUBS.length===0);
}
console.log("── Referral link is the user's own, or absent ──");
{
  const t=mk({api:emptyBoard});await sleep(300);const {w,$}=t;
  w.go("refer");await sleep(40);
  ok("signed out: no link is shown",$("refLink").value==="",$("refLink").value);
  ok("  copy/share refuse instead of sharing nothing",(w.copyRef(),$("toast").textContent.includes("Sign in"))&&w.CP.REF_LINK==="");
  ok("  no invented credit numbers or invitees",!/47 of/.test($("crTxt").textContent)&&/Sign in/.test($("refList").textContent));
}
{
  const api=(p,m)=>{
    if(p==="/api/auth/session")return{status:200,json:{user:{id:"u1",email:"a@x.com",name:"Ana",account_type:"seeker",plan:"free",referral_code:"ANA123"}}};
    if(p==="/api/referrals")return{status:200,json:{link:"https://careerpilot.ai/join/ANA123",sent:0,joined:0,active:0,bonus_credits:0,allowance:10,cap:700,base:10,referrals:[]}};
    if(p==="/api/ai/credits")return{status:200,json:{used:2,allowance:10}};
    if(p==="/api/profile")return{status:200,json:{positions:[],skills:[],name:"Ana",email:"a@x.com"}};
    if(p==="/api/connections")return{status:200,json:{companies:[]}};
    if(p==="/api/applications")return{status:200,json:{total:0,counts:{},applications:[]}};
    return emptyBoard(p);};
  const t=mk({token:"good",role:"seeker",api});await sleep(900);const {w,$}=t;
  w.go("refer");await sleep(300);
  ok("signed in: link uses the account's referral code",$("refLink").value==="careerpilot.ai/join/ANA123"&&w.CP.REF_LINK==="https://careerpilot.ai/join/ANA123",$("refLink").value);
  ok("  credits are the server's numbers",$("crTxt").textContent==="2 of 10",$("crTxt").textContent);
  ok("  invite list is honestly empty",/Nobody yet/.test($("refList").textContent));
  ok("  no sample strings on the page",leaks(visibleText(t)).length===0);
}
console.log("── Invite links are attributed at signup ──");
{
  const attrib=[];
  const api=(p,m,body)=>{
    if(p==="/api/auth/signup")return{status:201,json:{access_token:"tok-new",user:{id:"u2",email:"new@x.com",name:"New",account_type:"seeker",plan:"free",referral_code:"NEW999"}}};
    if(p.startsWith("/api/referrals/attribute/")){attrib.push(p);return{status:200,json:{attributed_to:"ANA123",unlocks_in_days:7}};}
    if(p==="/api/profile")return{status:200,json:{positions:[],skills:[]}};
    if(p==="/api/connections")return{status:200,json:{companies:[]}};
    if(p==="/api/applications")return{status:200,json:{total:0,counts:{},applications:[]}};
    return emptyBoard(p);};
  const t=mk({search:"?ref=ANA123",api});await sleep(900);const {w,$,calls}=t;
  ok("code remembered and stripped from the address bar",w.localStorage.getItem("cp_ref")==='"ANA123"'&&!w.location.search.includes("ref="),w.location.href);
  ok("sign-up screen opens for an invited visitor",$("authGate").classList.contains("on"));
  w.authTab("up");$("au-name").value="New";$("au-email").value="new@x.com";$("au-pass").value="a-long-passphrase";
  await w.CP.authSubmit();await sleep(400);
  ok("attribution called once with the code",attrib.length===1&&attrib[0]==="/api/referrals/attribute/ANA123",attrib.join());
  ok("  and with the new account's token",calls.find(c=>c.p.startsWith("/api/referrals/attribute/")).auth==="Bearer tok-new");
  ok("  code is consumed",w.localStorage.getItem("cp_ref")===null);
}
{
  const t=mk({live:false,search:"?ref=ANA123"});await sleep(200);
  ok("with no backend a stray ?ref does not open sign-up",!t.$("authGate").classList.contains("on"));
}

console.log("── Skills-only résumé no longer becomes someone else's career ──");
{
  const t=mk({api:emptyBoard});await sleep(300);const {w,$}=t;
  w.CP.parseResume(RESUME_SKILLS_ONLY,"skills.txt");await sleep(100);
  ok("skills are kept",w.CP.SKILLS.includes("Playwright")&&w.CP.SKILLS.includes("Java"));
  ok("no roles are invented",w.CP.EXP.length===0,w.CP.EXP.map(e=>e.co).join());
  ok("nothing from the built-in profile appears",!/Mastercard|Tata|CashAPona/.test($("p-me").textContent));
  ok("person is told to add roles",/add your roles/i.test($("toast").textContent),$("toast").textContent);
  $("p-name").value="Ana";
  ok("email/cover text carries no invented employer or name",!/Mastercard|Santosh|St\. Louis/.test(w.CP.coverLetterText({co:"Acme",ti:"SDET",lo:"",sk:[],src:"board"})));
}
console.log("── Sample rows saved by an older build are dropped ──");
{
  const t=mk({api:emptyBoard,ls:{
    cp_bench:[{id:1,name:"Priya Venkatesan",email:"priya.v@example.com",role:"Senior SDET",skills:["Java"],yrs:8,avail:"now",visa:"h1b",rate:"$1",loc:"x"},
              {id:9,name:"Real Person",email:"real@agency.com",role:"QA",skills:["SQL"],yrs:3,avail:"now",visa:"usc",rate:"$1",loc:"x"}],
    cp_subs:[{candId:1,jobId:"1",cand:"Priya Venkatesan",title:"x",company:"y",fit:80,st:"submitted",when:"Just now"}],
    cp_state_v1:{exp:[],skills:[],apps:[{co:"Vaspire Technologies",ti:"Senior SDET — GenAI",lo:"x",st:"offer",when:"Offer discussion today"},
                                    {co:"Mine Co",ti:"SDET",lo:"Remote",st:"sent",when:"",at:Date.now(),_id:"fp"}]},
    cp_support_tickets:[{subject:"hi",priority:"standard",when:"Just now (demo — not actually sent)"}],
  }});await sleep(300);const {w,$}=t;
  ok("saved sample application dropped, the real one kept",w.CP.APPS.length===1&&w.CP.APPS[0].co==="Mine Co",w.CP.APPS.map(a=>a.co).join());
  w.CP.setMode("recruiter");await sleep(80);
  ok("saved sample bench person dropped, the real one kept",w.CP.BENCH.length===1&&w.CP.BENCH[0].name==="Real Person",w.CP.BENCH.map(c=>c.name).join());
  ok("submissions for dropped people are dropped",w.CP.SUBS.length===0);
  ok("demo-mode support leftovers dropped",w.CP.SUP_TICKETS.length===0);
}

console.log("── Time is stored as a time, never as the words 'Just now' ──");
{
  const api=(p,m,body)=>{
    if(p==="/api/auth/session")return{status:200,json:{user:{id:"s1",email:"s@x.com",name:"S",account_type:"seeker",plan:"free"}}};
    if(p==="/api/applications"&&m==="GET")return{status:200,json:{total:0,counts:{},applications:[]}};
    if(p==="/api/applications"&&m==="POST")return{status:200,json:{id:"55555555-5555-5555-5555-555555555555",...body}};
    if(p==="/api/profile")return{status:200,json:{positions:[],skills:[]}};
    if(p==="/api/connections")return{status:200,json:{companies:[]}};
    return emptyBoard(p);};
  const t=mk({token:"good",role:"seeker",api});await sleep(900);const {w,$}=t;
  const job={id:"fp-1",co:"Acme",ti:"SDET",lo:"Remote",sk:[],md:"remote",em:"fulltime",fm:"ui",rt:"",yr:"",d:1,sn:1};
  w.CP.J.push(job);
  w.mark?.(job,"sent");
  ok("application carries a timestamp, not stored words",w.CP.APPS[0].at>Date.now()-5000&&w.CP.APPS[0].when==="",JSON.stringify(w.CP.APPS[0]));
  ok("age is worked out when drawn",w.CP.whenText(w.CP.APPS[0])==="Just now");
  const old={at:Date.now()-3*864e5};
  ok("  and moves on by itself",w.CP.whenText(old)==="3 days ago"&&w.CP.whenText({at:Date.now()-864e5})==="Yesterday");
  ok("  a person's own note is kept next to it",w.CP.whenText({when:"Negotiating rate",at:Date.now()-864e5})==="Negotiating rate · Yesterday");
}

console.log("── People I know is real: add, ask, remove ──");
{
  const rows=[];
  const api=(p,m,body)=>{
    if(p==="/api/auth/session")return{status:200,json:{user:{id:"s1",email:"s@x.com",name:"Sam",account_type:"seeker",plan:"free"}}};
    if(p==="/api/connections"&&m==="GET")return{status:200,json:{companies:[...new Set(rows.map(r=>r.company))].map(c=>({company:c,open_roles:0,people:rows.filter(r=>r.company===c)}))}};
    if(p==="/api/connections"&&m==="POST"){const r={id:"c"+rows.length,name:body.name,role:body.role,company:body.company,degree:body.degree,how_known:body.how_known};rows.push(r);return{status:200,json:r};}
    if(/^\/api\/connections\//.test(p)&&m==="DELETE"){rows.splice(0,1);return{status:200,json:{deleted:true}};}
    if(p==="/api/profile")return{status:200,json:{positions:[],skills:[]}};
    if(p==="/api/applications")return{status:200,json:{total:0,counts:{},applications:[]}};
    return emptyBoard(p);};
  const t=mk({token:"good",role:"seeker",api});await sleep(900);const {w,$}=t;
  w.go("people");await sleep(40);
  ok("starts empty with an honest message",/Nobody added yet/.test($("peopleList").textContent)&&leaks(visibleText(t)).length===0);
  w.editPerson();await sleep(20);
  $("pp-name").value="Ravi Kumar";$("pp-co").value="Acme";$("pp-role").value="QA Lead";$("pp-how").value="Worked together";
  await w.savePerson();await sleep(60);
  ok("saved through the API",rows.length===1&&rows[0].name==="Ravi Kumar");
  ok("  and listed",$("peopleList").textContent.includes("Ravi Kumar")&&$("peopleList").textContent.includes("QA Lead"));
  w.askIntro(0);await sleep(20);
  ok("'ask for an intro' drafts a message and says nothing was sent",/Hi Ravi/.test($("intro-body").value)&&/nothing has been sent/i.test($("md").textContent));
  w.closeM();
  await w.removePerson(0);await sleep(40);
  ok("removed on the server and in the list",rows.length===0&&/Nobody added yet/.test($("peopleList").textContent));
}
console.log("── Support uses the account's real plan and history ──");
{
  const api=(p,m)=>{
    if(p==="/api/auth/session")return{status:200,json:{user:{id:"s1",email:"s@x.com",name:"S",account_type:"seeker",plan:"pro"}}};
    if(p==="/api/support/mine")return{status:200,json:[{id:"t1",subject:"Billing question",status:"open",priority:"priority",created_at:new Date(Date.now()-2*864e5).toISOString()}]};
    if(p==="/api/profile")return{status:200,json:{positions:[],skills:[]}};
    if(p==="/api/connections")return{status:200,json:{companies:[]}};
    if(p==="/api/applications")return{status:200,json:{total:0,counts:{},applications:[]}};
    return emptyBoard(p);};
  const t=mk({token:"good",role:"seeker",api});await sleep(900);const {w,$}=t;
  w.go("support");await sleep(300);
  ok("Pro account sees priority SLA (was hardcoded 'free')",/Priority support/.test($("slaBanner").textContent)&&/4 hours/.test($("slaBanner").textContent),$("slaBanner").textContent);
  ok("history comes from the server with a real age",/Billing question/.test($("sup-history").textContent)&&/2 days ago/.test($("sup-history").textContent),$("sup-history").textContent);
}

console.log("── The demo still works when NO backend is configured ──");
{
  const t=mk({live:false});await sleep(300);const {w,$}=t;
  ok("demo mode is on",w.CP.DEMO===true&&!w.CP.CP_API);
  ok("sample roles are available",w.CP.J.length>=20);
  ok("sample bench is available",(w.CP.setMode("recruiter"),w.CP.BENCH.length===6));
  ok("sample contacts are available",w.CP.peopleNow().length===6);
  ok("demo banner says it is a demo",/Demo board/.test($("sampleBar").textContent));
}
console.log("── An API set through the internal ?setup screen also leaves demo ──");
{
  const dom=new JSDOM(HTML,{runScripts:"dangerously",pretendToBeVisual:true,url:"https://careerpilot.ai/",
    beforeParse(w){w.scrollTo=()=>{};w.localStorage.setItem("cp_api",JSON.stringify("http://api.test"));w.fetch=async()=>({ok:true,status:200,json:async()=>({jobs:[],total:0}),text:async()=>""});}});
  await sleep(300);
  ok("saved API address means no sample data",dom.window.CP.DEMO===false&&dom.window.CP.J.length===0);
}

console.log("\n══════════════════════════════════════════════════");
console.log(`PASS ${P}    FAIL ${F}`);
if(F){console.log("\nFAILURES");fails.forEach(f=>console.log("  ✗ ",f));process.exit(1);}
process.exit(0);
})();
