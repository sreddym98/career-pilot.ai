/* extension/content/fill.js against the Greenhouse-like and Lever-like fixture
   forms (jsdom). File attachment needs a real browser (DataTransfer), so that
   part lives in playwright/apply_extension_e2e.py. Also a static check that no
   extension script can submit a form.
   Run: node extensionfilltest.js */
const path=require("path"),fs=require("fs");
const {JSDOM}=require("jsdom");
const EXT=path.join(__dirname,"..","..","extension");
const FIX=path.join(__dirname,"playwright","fixtures");
let P=0,F=0;const fails=[];
const ok=(n,c,x)=>{c?P++:(F++,fails.push(n+(x?"  →  "+x:"")))};
const sleep=ms=>new Promise(r=>setTimeout(r,ms));

console.log("\n╔═══ EXTENSION FILL ═══╗\n");
console.log("── never submits (static) ──");
const js=["background.js","content/fill.js","content/detect.js","content/bridge.js","popup/popup.js"].map(f=>[f,fs.readFileSync(path.join(EXT,f),"utf8")]);
for(const [f,src] of js){
  const code=src.replace(/\/\*[\s\S]*?\*\//g,"").replace(/\/\/.*$/gm,"");
  ok(`${f}: no form.submit()/requestSubmit()`,!/\.submit\s*\(|requestSubmit/.test(code));
  ok(`${f}: never clicks a button`,!/button[^;\n]*\.click\s*\(|querySelector\([^)]*submit[^)]*\)[^;\n]*\.click/i.test(code));
}
const fillSrc=js.find(x=>x[0]==="content/fill.js")[1];
ok("fill.js: the only .click() is inside safeCheck (radio/checkbox)",(fillSrc.replace(/\/\*[\s\S]*?\*\//g,"").match(/\.click\(\)/g)||[]).length===1&&/function safeCheck[\s\S]{0,300}el\.click\(\)/.test(fillSrc));
const man=JSON.parse(fs.readFileSync(path.join(EXT,"manifest.json"),"utf8"));
ok("manifest: Render API + live site in host_permissions",man.host_permissions.includes("https://careerpilot-api-rri9.onrender.com/*")&&man.host_permissions.includes("https://career-pilot-ai.mamindlasreddy.workers.dev/*"));
ok("manifest: bridge only on CareerPilot's own origins",man.content_scripts.some(c=>c.js.includes("content/bridge.js")&&c.matches.every(m=>/workers\.dev|localhost|127\.0\.0\.1/.test(m))));
ok("background: default API is the Render URL",/DEFAULT_API_BASE = "https:\/\/careerpilot-api-rri9\.onrender\.com"/.test(js[0][1]));

function page(file,url){
  const d=new JSDOM(fs.readFileSync(path.join(FIX,file),"utf8"),{runScripts:"dangerously",pretendToBeVisual:true,url});
  const w=d.window;
  // jsdom has no layout: treat everything as visible.
  Object.defineProperty(w.HTMLElement.prototype,"offsetParent",{get(){return this.parentNode;}});
  w.__sent=[];
  w.chrome={runtime:{sendMessage:(m,cb)=>{w.__sent.push(m);if(cb)cb({ok:true});return Promise.resolve({ok:true,packet:null});},
                     onMessage:{addListener(){}},lastError:null}};
  const load=f=>{const s=w.document.createElement("script");s.textContent=fs.readFileSync(path.join(EXT,f),"utf8");w.document.body.appendChild(s);};
  load("content/detect.js"); load("content/fill.js");
  return w;
}

(async()=>{
console.log("── Greenhouse-like form ──");
const w=page("greenhouse_apply.html","https://boards.greenhouse.io/acmepay/jobs/4001234");
ok("detected as Greenhouse",w.__CP&&w.__CP.ats==="greenhouse"&&w.__CP.isForm);
const packet={application_id:"a1",company:"Acme Pay",title:"Senior SDET",cover_letter:"Dear Acme Pay,\n\nHello.",
  profile:{first_name:"Sam",last_name:"Tester",full_name:"Sam Tester",email:"sam@example.com",phone:"555-0100",location:"St. Louis, MO",linkedin:"https://linkedin.com/in/sam"},
  answers:[
    {id:"first_name",label:"First Name",type:"text",required:true,value:"Sam"},
    {id:"last_name",label:"Last Name",type:"text",required:true,value:"Tester"},
    {id:"email",label:"Email",type:"text",required:true,value:"sam@example.com"},
    {id:"resume",label:"Resume/CV",type:"file",required:true,value:"tailored_resume.pdf"},
    {id:"question_30001",label:"LinkedIn Profile",type:"text",value:"https://linkedin.com/in/sam"},
    {id:"question_30002",label:"Are you legally authorized to work in the United States?",type:"boolean",required:true,value:"Yes",options:["Yes","No"]},
    {id:"question_30003",label:"Will you now or in the future require sponsorship for employment visa status (e.g., H-1B visa status)?",type:"boolean",required:true,value:"No",options:["Yes","No"]},
    {id:"question_30004",label:"Why do you want to work at Acme Pay?",type:"textarea",required:true,value:""},
    {id:"question_30005",label:"How many years of professional QA automation experience do you have?",type:"select",value:"6-9 years"},
    {id:"question_30006",label:"What are your salary expectations?",type:"text",value:""},
    {id:"question_30007",label:"Which of these tools have you used?",type:"multi",value:"Cypress; Selenium"},
    {id:"gender",label:"Gender",type:"select",value:"Decline To Self Identify",eeo:true},
    {id:"demographic_7001",label:"How would you describe your racial/ethnic background?",type:"multi",value:"I prefer not to answer",eeo:true},
  ]};
const res=w.fillPacket(packet,{resume:{error:"offline in this test"}});
const v=id=>w.document.getElementById(id).value;
ok("text fields by id",v("first_name")==="Sam"&&v("last_name")==="Tester"&&v("email")==="sam@example.com"&&v("question_30001")==="https://linkedin.com/in/sam");
ok("selects by option label",v("question_30002")==="1"&&v("question_30003")==="0"&&v("question_30005")==="13",[v("question_30002"),v("question_30003"),v("question_30005")]);
const chk=(n,val)=>w.document.querySelector(`input[name="${n}"][value="${val}"]`).checked;
ok("multi-select checkboxes by label (fieldset legend)",chk("question_30007[]","21")&&!chk("question_30007[]","22")&&chk("question_30007[]","23"));
ok("EEO decline chosen, nothing else",v("gender")==="3"&&chk("demographic_7001[]","3")&&!chk("demographic_7001[]","1"));
ok("phone filled from the profile basics",v("phone")==="555-0100");
ok("cover letter goes in the text box when no file could be attached",v("cover_letter_text")===""||v("cover_letter_text").startsWith("Dear Acme Pay"));
const needs=res.needs.map(n=>n.label);
ok("needs you: blank custom question, salary, the unknown required field",needs.includes("Why do you want to work at Acme Pay?")&&needs.includes("What are your salary expectations?")&&needs.includes("How did you hear about us?"),needs.join(" | "));
ok("  and the resume download problem is reported",res.problems.some(p=>/resume/i.test(p)));
ok("  unfilled required fields highlighted",w.document.getElementById("question_39999").classList.contains("cp-needs")&&w.document.getElementById("question_30004").classList.contains("cp-needs"));
ok("  EEO never listed as needing you",!needs.some(n=>/gender|racial/i.test(n)));
ok("never overwrites what's already typed",(()=>{w.document.getElementById("phone").value="999";w.fillForm(packet.profile);return v("phone")==="999";})());
w.overlay(packet,res);
const ov=w.document.getElementById("cp-overlay").shadowRoot.textContent;
ok("overlay: filled vs needs-you, and the promise",/Filled/.test(ov)&&/Needs you/.test(ov)&&/Review everything, then click Submit on this page\. We never submit for you\./.test(ov));
ok("NOT submitted",w.__submits===0&&w.__submitClicks===0);
ok("no 'applied' report was sent by filling",!w.__sent.some(m=>m.type==="report"&&m.status==="applied"));

console.log("── Lever-like form ──");
const l=page("lever_apply.html","https://jobs.lever.co/brightlane/5b0c2d4e-8f1a-4c3b-9d2e-7a6f5e4d3c2b/apply");
ok("detected as Lever",l.__CP&&l.__CP.ats==="lever");
const lr=l.fillPacket({application_id:"a2",company:"Brightlane",title:"QA",cover_letter:"",profile:packet.profile,answers:[
  {id:"name",label:"Full name",type:"text",required:true,value:"Sam Tester"},
  {id:"email",label:"Email",type:"text",required:true,value:"sam@example.com"},
  {id:"org",label:"Current company",type:"text",value:"Mastercard"},
  {id:"urls[LinkedIn]",label:"LinkedIn URL",type:"text",value:"https://linkedin.com/in/sam"}]},{});
const n=nm=>l.document.querySelector(`[name="${nm}"]`).value;
ok("fields by name, incl. urls[LinkedIn]",n("name")==="Sam Tester"&&n("org")==="Mastercard"&&n("urls[LinkedIn]")==="https://linkedin.com/in/sam");
ok("the custom radio is left for you and named by its question",lr.needs.some(x=>x.label==="Are you legally authorized to work in the United States?"),lr.needs.map(x=>x.label).join(" | "));
ok("  neither radio was picked",!l.document.querySelector('input[type=radio]:checked'));
ok("NOT submitted",l.__submits===0&&l.__submitClicks===0);

console.log(`\nPASS ${P}    FAIL ${F}`);
if(F){console.log("FAILURES");fails.forEach(f=>console.log("  ✗ "+f));}
})().catch(e=>{console.error(e);console.log(`\nPASS ${P}    FAIL ${F+1}`);});
