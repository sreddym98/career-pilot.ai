/* The Apply page (jsdom, mocked API). Covers: the job description is fetched
   when a job is opened; the Apply page shows the employer's questions
   pre-answered, saves edits, downloads the tailored resume PDF, keeps the cover
   letter editable; extension install steps / connect / send-to-employer hand
   off; and nothing is ever submitted for the user.
   Run: node applypagetest.js */
const path=require("path"),fs=require("fs");
const {JSDOM}=require("jsdom");
const HTML=fs.readFileSync(path.join(__dirname,"..","index.html"),"utf8");
let P=0,F=0;const fails=[];
const ok=(n,c,x)=>{c?P++:(F++,fails.push(n+(x?"  →  "+x:"")))};
const sleep=ms=>new Promise(r=>setTimeout(r,ms));

const GH="https://boards.greenhouse.io/acmepay/jobs/4001234";
const JOB={fingerprint:"fpA",company:"Acme Pay",title:"Senior SDET",location:"Remote",work_mode:"remote",employment:"fulltime",
  apply_url:GH,comp:{},exp:{},visa:{usc:"u",gc:"u",h1b:"u",opt:"u"},skills:["Cypress"],days_live:1,seen_count:1,
  competition:"lo",referrals:[],fit:null,verified:true,direct:true,source:"greenhouse"};
const DESC="Own quality for payments.\n\nWHAT YOU'LL DO\n• Cypress suites\n• SQL checks <img src=x onerror=\"window.__xss=1\">";
const Q=[
  {id:"first_name",label:"First Name",type:"text",required:true,options:[],eeo:false,value:"Sam",source:"profile",needs_you:false},
  {id:"email",label:"Email",type:"text",required:true,options:[],eeo:false,value:"sam@example.com",source:"profile",needs_you:false},
  {id:"resume",label:"Resume/CV",type:"file",required:true,options:[],eeo:false,value:"tailored_resume.pdf",source:"file",needs_you:false},
  {id:"question_2",label:"Will you now or in the future require sponsorship?",type:"boolean",required:true,options:["Yes","No"],eeo:false,value:"Yes",source:"derived",needs_you:false,note:"From your work authorization (H-1B)"},
  {id:"question_4",label:"Why do you want to work at Acme Pay?",type:"textarea",required:true,options:[],eeo:false,value:"",source:"",needs_you:true,note:"You answer this"},
  {id:"question_6",label:"What are your salary expectations?",type:"text",required:false,options:[],eeo:false,value:"",source:"",needs_you:true,note:"You decide this number"},
  {id:"question_7",label:"Which tools?",type:"multi",required:false,options:["Cypress","Playwright"],eeo:false,value:"",source:"",needs_you:true},
  {id:"gender",label:"Gender",type:"select",required:false,options:["Male","Female","Decline To Self Identify"],eeo:true,value:"Decline To Self Identify",source:"decline",needs_you:false},
];
const CUR={};
function view(extra={}){
  return {application:{id:"app-1",status:"opened",origin:"manual",company:"Acme Pay",title:"Senior SDET",location:"Remote"},
    job:{fingerprint:"fpA",company:"Acme Pay",title:"Senior SDET",location:"Remote",work_mode:"remote",employment:"fulltime",
         apply_url:GH,active:true,description:DESC},
    questions:{supported:true,ats:"greenhouse",partial:false},answers:JSON.parse(JSON.stringify(CUR.answers||Q)),checklist:{},
    resume:{summary:"SDET <b>who</b> tests payments.",skills:["Cypress","SQL","Java"],ai:false,
      roles:[{id:"p1",company:"Mastercard",role:"Senior SDET",dates:"Jan 2021 – Present",location:"",bullets:["Built Cypress suites"]}]},
    cover_letter:"Dear Acme Pay hiring team,\n\nI'm applying.",resume_cost:1,credits_remaining:9,...extra};
}
function server(){
  const S={calls:[],descFetches:0}; delete CUR.answers;
  const res=(status,body,headers={})=>({ok:status<400,status,json:async()=>body,
    blob:async()=>new (S.w.Blob)(["%PDF-1.4 fake"],{type:"application/pdf"}),
    headers:{get:k=>headers[k.toLowerCase()]||null}});
  S.fetch=async(url,opts={})=>{
    const u=new URL(url),p=u.pathname,m=(opts.method||"GET").toUpperCase();
    const body=opts.body?JSON.parse(opts.body):null;
    S.calls.push({m,p,body,auth:(opts.headers||{}).Authorization});
    if(p==="/api/jobs"&&m==="GET") return res(200,{total:1,offset:0,limit:100,fit_available:false,jobs:[JOB]});
    if(p==="/api/jobs/fpA"){S.descFetches++; return res(200,{...JOB,description:DESC});}
    if(p==="/api/apply/start") return res(200,view());
    if(p==="/api/apply/app-1"&&m==="PUT"){
      CUR.answers=CUR.answers||JSON.parse(JSON.stringify(Q));
      for(const [k,v] of Object.entries(body.answers||{})){const q=CUR.answers.find(x=>x.id===k); if(q){q.value=v;q.source="you";}}
      return res(200,{saved:true});}
    if(p==="/api/apply/app-1/resume"&&m==="POST") return res(200,view({resume:{...view().resume,ai:true,summary:"Tailored summary."},cover_letter:"AI letter"}));
    if(p==="/api/apply/app-1/resume.pdf") return res(200,null,{"content-disposition":'attachment; filename="Sam_Resume.pdf"'});
    if(p==="/api/auth/extension-token") return res(200,{token:"aaa.bbb.ccc",scope:"extension"});
    if(p==="/api/apply/app-1/handoff") return res(200,{id:"app-1",status:"opened"});
    if(p==="/api/applications"&&m==="POST") return res(200,{id:"app-1",status:body.status});
    if(p==="/api/applications") return res(200,{total:0,counts:{},applications:[]});
    if(p==="/api/profile") return res(200,{positions:[],skills:[],work_auth:["h1b"]});
    if(p.startsWith("/api/autopilot")) return res(200,{on:false,slots:[9],queue:[],runs:[],plan:"pro",dailyCap:60});
    return res(404,{detail:"Not found"});
  };
  return S;
}
function mk(S,{ext=false}={}){
  const d=new JSDOM(HTML,{runScripts:"dangerously",pretendToBeVisual:true,url:"https://careerpilot.ai/",
    beforeParse(w){
      S.w=w;
      w.CP_CONFIG={api:"http://api.test"};
      w.fetch=(u,o)=>S.fetch(u,o);
      w.scrollTo=()=>{};w.confirm=()=>true;
      w.__clip=[];w.navigator.clipboard={writeText:t=>{w.__clip.push(t);return Promise.resolve();}};
      w.__o=[];w.__seq=[];w.open=(u)=>{w.__o.push(u);w.__seq.push("open");return null;};
      w.URL.createObjectURL=()=>"blob:mock";w.URL.revokeObjectURL=()=>{};
      w.__dl=[];
      w.HTMLAnchorElement.prototype.click=function(){w.__dl.push({href:this.href,download:this.download});};
      w.__ext=[];
      const pm=w.postMessage.bind(w);
      w.postMessage=(m,o)=>{ if(m&&m.type==="cp_handoff") w.__seq.push("handoff"); return pm(m,o); };
      if(ext){
        // A stand-in for extension/content/bridge.js: answers the page like the real one.
        let connected=false;
        const say=(type,extra)=>w.dispatchEvent(new w.MessageEvent("message",{data:{source:"careerpilot-ext",type,version:"1.2.0",...extra},origin:"https://careerpilot.ai",source:w}));
        w.addEventListener("message",e=>{
          const m=e.data; if(!m||m.source!=="careerpilot-web") return;
          w.__ext.push(m);
          setTimeout(()=>{
            if(m.type==="cp_ping") say("cp_pong",{connected,id:m.id});
            if(m.type==="cp_connect"){connected=!!m.token; say("cp_connected",{ok:connected,id:m.id});}
            if(m.type==="cp_handoff") say("cp_handoff_ok",{ok:true,id:m.id});
          },5);
        });
      }
    }});
  return d.window;
}

(async()=>{
console.log("\n╔═══ APPLY PAGE ═══╗\n");
const S=server(); const w=mk(S); await sleep(700);
const d=w.document,$=i=>d.getElementById(i),qa=s=>[...d.querySelectorAll(s)];
const click=e=>{if(!e)throw new Error("missing");e.dispatchEvent(new w.MouseEvent("click",{bubbles:true}))};
const calls=(m,p)=>S.calls.filter(c=>c.m===m&&(p instanceof RegExp?p.test(c.p):c.p===p));
w.localStorage.setItem("cp_token",JSON.stringify("tok"));
w.CP.applySession({id:"s1",email:"sam@example.com",name:"Sam",account_type:"seeker",plan:"pro"});
await sleep(400);
ok("signed in as a seeker → live",w.CP.apLive()===true);
ok("the board loaded the live job",w.CP.J.some(j=>j.id==="fpA"),w.CP.J.map(j=>j.id).join());

console.log("── Job detail fetches the description ──");
w.openJob("fpA"); await sleep(30);
const pane=()=>$("jdBox");
ok("opening a job asks the server for its detail",S.descFetches===1&&calls("GET","/api/jobs/fpA")[0].auth==="Bearer tok");
await sleep(60);
ok("  the description shows (not 'No description available')",pane()&&pane().textContent.includes("Own quality for payments")&&!/No description available/.test(pane().textContent),pane()&&pane().textContent.slice(0,80));
ok("  headings and bullets rendered",pane().querySelector("h5")&&pane().querySelectorAll("li").length===2);
ok("  hostile markup stays text",!pane().querySelector("img")&&!w.__xss&&pane().textContent.includes("<img"));
w.closeM&&w.closeM(); w.openJob("fpA"); await sleep(60);
ok("  cached: opening it again doesn't refetch",S.descFetches===1&&pane().textContent.includes("Own quality"));
ok("  the detail offers Apply with CareerPilot",qa("button").some(b=>b.textContent==="Apply with CareerPilot"));

console.log("── Apply page ──");
await w.CP.openApplyPage("fpA"); await sleep(50);
const md=$("md");
ok("opens as a modal",$("ov").classList.contains("on")&&md.classList.contains("applymd"));
ok("  started on the server for that job",calls("POST","/api/apply/start")[0].body.fingerprint==="fpA");
ok("  job summary + full description",md.textContent.includes("Apply: Senior SDET")&&$("aplJd").textContent.includes("SQL checks"));
ok("  checklist 'Ready: N of M answered'",/Ready: 4 of 7 answered/.test($("apl-ready").textContent),$("apl-ready").textContent);
ok("  and says what's left",/1 required left for you/.test($("apl-ready").textContent),$("apl-ready").textContent);
const qEl=id=>md.querySelector(`.aplq[data-qid="${id}"]`);
ok("pre-answered from the profile",qEl("first_name").querySelector("input").value==="Sam"&&/From your profile/.test(qEl("first_name").textContent));
ok("  sponsorship pre-answered from work authorization",qEl("question_2").querySelector("select").value==="Yes"&&/H-1B/.test(qEl("question_2").textContent));
ok("  custom question blank and flagged 'you answer this'",qEl("question_4").querySelector("textarea").value===""&&qEl("question_4").classList.contains("aplneeds")&&/You answer this/.test(qEl("question_4").textContent));
ok("  salary blank for the user",qEl("question_6").querySelector("input").value===""&&/You decide this number/.test(qEl("question_6").textContent));
ok("  resume shown as attached, not a text box",/tailored resume PDF is attached/.test(qEl("resume").textContent)&&!qEl("resume").querySelector("input"));
ok("  EEO tucked away and set to decline",md.querySelector("details.apleeo")&&md.querySelector("details.apleeo").contains(qEl("gender"))&&qEl("gender").querySelector("select").value==="Decline To Self Identify");
ok("  server text is escaped (resume summary)",!md.querySelector(".aplsum b")&&md.querySelector(".aplsum").textContent.includes("<b>who</b>"));

console.log("── Editing saves ──");
const ta=qEl("question_4").querySelector("textarea");
ta.value="I build payment test suites."; ta.dispatchEvent(new w.Event("input",{bubbles:true}));
ok("checklist updates as you type",/Ready: 5 of 7 answered/.test($("apl-ready").textContent)&&/every required question/.test($("apl-ready").textContent),$("apl-ready").textContent);
ok("  the field is no longer flagged",!qEl("question_4").classList.contains("aplneeds"));
await sleep(900);
let put=calls("PUT","/api/apply/app-1").pop();
ok("  answer saved to the application",put&&put.body.answers.question_4==="I build payment test suites.",JSON.stringify(put&&put.body));
const multi=qEl("question_7").querySelectorAll("input[type=checkbox]");
multi[0].checked=true; multi[0].dispatchEvent(new w.Event("change",{bubbles:true}));
multi[1].checked=true; multi[1].dispatchEvent(new w.Event("change",{bubbles:true}));
const cl=$("apl-cl"); cl.value="Dear Acme Pay,\n\nEdited by me."; cl.dispatchEvent(new w.Event("input",{bubbles:true}));
await sleep(900);
put=calls("PUT","/api/apply/app-1").pop();
ok("cover letter is editable and saved",put&&put.body.cover_letter==="Dear Acme Pay,\n\nEdited by me.",JSON.stringify(put&&put.body));
ok("  multi-select saved as a list",put&&put.body.answers&&put.body.answers.question_7==="Cypress; Playwright",JSON.stringify(put&&put.body));

console.log("── Resume ──");
await w.CP.downloadApplyPdf(); await sleep(20);
ok("download PDF fetches the owner-only endpoint with the session",calls("GET","/api/apply/app-1/resume.pdf").length===1&&calls("GET","/api/apply/app-1/resume.pdf")[0].auth==="Bearer tok");
ok("  saves it as a file",w.__dl.some(x=>x.download==="Sam_Resume.pdf"),JSON.stringify(w.__dl));
ok("  says it costs one generation",/Tailor with AI · 1 generation/.test($("apl-tailor").textContent),$("apl-tailor").textContent);
await w.CP.tailorApplyResume(); await sleep(30);
ok("Tailor with AI → POST and re-render",calls("POST","/api/apply/app-1/resume").length===1&&/Tailored to this job/.test(md.textContent)&&$("apl-cl").value==="AI letter");

console.log("── No extension: install steps and fallbacks ──");
const send=()=>$("apl-send");
ok("install steps shown",/Load unpacked/.test(send().textContent)&&/chrome:\/\/extensions/.test(send().textContent)&&/Developer mode/.test(send().textContent));
ok("  fallbacks: resume PDF, cover letter, answers",["Download resume PDF","Copy cover letter","Copy answers"].every(t=>qa("#apl-send button").some(b=>b.textContent===t)));
click(qa("#apl-send button").find(b=>b.textContent==="Copy answers")); await sleep(20);
ok("  copy answers includes the questions and your answers",w.__clip.some(t=>t.includes("Why do you want to work at Acme Pay?")&&t.includes("I build payment test suites.")&&t.includes("(you answer this)")),w.__clip.join("|").slice(0,200));
ok("the promise, in plain words",/You'll click Submit on Acme Pay's page\. We fill it in; we never submit for you\./.test(send().textContent));
ok("  button says what it does without the extension",$("apl-go").textContent==="Open Acme Pay's form");
w.CP.closeApply(); await sleep(20);

console.log("── With the extension: connect, then send ──");
const S2=server(); const w2=mk(S2,{ext:true}); await sleep(700);
const d2=w2.document,$2=i=>d2.getElementById(i),qa2=s=>[...d2.querySelectorAll(s)];
const calls2=(m,p)=>S2.calls.filter(c=>c.m===m&&(p instanceof RegExp?p.test(c.p):c.p===p));
w2.localStorage.setItem("cp_token",JSON.stringify("tok"));
w2.CP.applySession({id:"s1",email:"sam@example.com",name:"Sam",account_type:"seeker",plan:"pro"});
await sleep(400);
await w2.CP.openApplyPage("fpA"); await sleep(80);
ok("extension detected, not yet connected → Connect extension",w2.CP.EXT.present&&!w2.CP.EXT.connected&&!!$2("apl-connect"),$2("apl-send").textContent.slice(0,120));
await w2.CP.connectExtension(); await sleep(40);
ok("connect asks the server for a scoped key",calls2("POST","/api/auth/extension-token").length===1);
const conn=w2.__ext.find(m=>m.type==="cp_connect");
ok("  and hands it to the extension with the API address",conn&&conn.token==="aaa.bbb.ccc"&&conn.apiBase==="http://api.test");
ok("  connected: the button now says Send to employer",w2.CP.EXT.connected&&$2("apl-go").textContent==="Send to employer"&&$2("apl-extok"));
ok("  a copy-paste code is available as a fallback",w2.CP.EXT.code==="aaa.bbb.ccc");
w2.document.dispatchEvent&&0;
w2.__seq.length=0;
await w2.CP.sendToEmployer(); await sleep(50);
const ho=w2.__ext.find(m=>m.type==="cp_handoff");
ok("Send hands the application to the extension",ho&&ho.applicationId==="app-1"&&ho.applyUrl===GH);
ok("  before opening the posting",w2.__seq.join()==="handoff,open",w2.__seq.join());
ok("  opens the employer's form",w2.__o[0]===GH,w2.__o.join());
ok("  tells the server it was handed off (not applied)",calls2("POST","/api/apply/app-1/handoff").length===1);
const tracked=calls2("POST","/api/applications");
ok("  tracker: opened, not applied",tracked.length>=1&&tracked.every(c=>c.body.status==="opened"),JSON.stringify(tracked.map(c=>c.body.status)));
ok("  modal closed",!$2("ov").classList.contains("on"));
Object.defineProperty(d2,"hidden",{value:true,configurable:true}); d2.dispatchEvent(new w2.Event("visibilitychange")); await sleep(20);
Object.defineProperty(d2,"hidden",{value:false,configurable:true}); d2.dispatchEvent(new w2.Event("visibilitychange")); await sleep(750);
ok("back from the employer's page: 'Did you apply?'",$2("askbar")&&$2("askbar").textContent.includes("Senior SDET"));
click(qa2("#askbar button").find(b=>b.textContent.includes("Yes"))); await sleep(60);
ok("  Yes → recorded as applied, by the user",calls2("POST","/api/applications").some(c=>c.body.status==="sent"||c.body.status==="submitted"));

console.log("── Never submits ──");
const all=[...S.calls,...S2.calls].map(c=>c.p);
ok("no request anywhere submits to an employer",!all.some(p=>/submit/i.test(p)));
ok("Lever links go to the form, not the posting",w.CP.applyTarget("https://jobs.lever.co/acme/5b0c2d4e-8f1a-4c3b-9d2e-7a6f5e4d3c2b")==="https://jobs.lever.co/acme/5b0c2d4e-8f1a-4c3b-9d2e-7a6f5e4d3c2b/apply"
   &&w.CP.applyTarget(GH)===GH);

console.log("── Signed out / demo keeps the old path ──");
const S3=server(); const w3=mk(S3); await sleep(700);
w3.CP.openApplyPage("fpA"); await sleep(50);
ok("signed out: asks you to sign in, calls nothing",w3.document.getElementById("authGate").classList.contains("on")&&!S3.calls.some(c=>c.p.startsWith("/api/apply")));

console.log(`\nPASS ${P}    FAIL ${F}`);
if(F){console.log("FAILURES");fails.forEach(f=>console.log("  ✗ "+f));}
process.exit(0);
})().catch(e=>{console.error(e);console.log(`\nPASS ${P}    FAIL ${F+1}`);process.exit(1);});
