const path=require('path');
const {JSDOM}=require('jsdom');const fs=require('fs');
const HTML=fs.readFileSync(path.join(__dirname,'..','index.html'),'utf8');
const dom=new JSDOM(HTML,{runScripts:"dangerously",pretendToBeVisual:true,url:"https://careerpilot.ai/"});
const w=dom.window,d=w.document;w.scrollTo=()=>{};w.open=()=>({focus(){}});
Object.defineProperty(w,"innerWidth",{value:1280,configurable:true});
let P=0,F=0;const fails=[];
const ok=(n,c,x)=>{c?P++:(F++,fails.push(n+(x?"  →  "+x:"")))};

setTimeout(()=>{
const $=i=>d.getElementById(i), qa=s=>[...d.querySelectorAll(s)];

console.log("\n╔═══ COURSE LINKS + BUTTON LABELS ═══╗\n");

console.log("── Every course has a real URL ──");
const missing = w.CP.COURSES.filter(c=>!c.url || !c.url.startsWith("http"));
ok("all 8 courses have a real URL",missing.length===0,missing.map(c=>c.n).join(", "));

console.log("── Courses page renders clickable links ──");
w.go("learn");
const links = qa(".courselink");
ok("course title links rendered",links.length>=1,links.length+"");
ok("  link points to a real URL",links[0].getAttribute("href").startsWith("http"),links[0].getAttribute("href"));
ok("  opens in a new tab",links[0].target==="_blank");
ok("  has noopener",links[0].rel.includes("noopener"));

const startBtns = qa('a.btn[href^="http"]').filter(a=>a.textContent.includes("Start course"));
ok("Start course buttons rendered",startBtns.length>=1,startBtns.length+"");
ok("  matches the course link's URL",startBtns[0].getAttribute("href")===links[0].getAttribute("href"));

console.log("── Job apply button no longer shows a raw ugly hostname ──");
w.go("jobs");
const sampleJob = w.CP.J.find(j=>j.sample && j.url);
ok("found a sample job to test",!!sampleJob);
const label = w.applyLabel(sampleJob);
ok("button says company name, not subdomain junk",label===`Search on ${sampleJob.co}`,label);
ok("  no raw hostname leaking into the label",!label.includes(".com")&&!label.includes(".workdayjobs"),label);

console.log("── Job detail panel shows the clean label too ──");
w.openJob(sampleJob.id);
const btn = [...d.querySelectorAll("#jobDetailPane button")].find(b=>b.textContent.startsWith("Search on")||b.textContent.startsWith("Apply on"));
ok("detail panel button uses the clean label",btn.textContent===label,btn.textContent);
ok("  fits without visual overflow risk",btn.textContent.length<40,btn.textContent.length+" chars");

console.log("\n"+"═".repeat(50));
console.log(`PASS ${P}    FAIL ${F}`);
if(F){console.log("\nFAILURES");fails.forEach(f=>console.log("  ✗ "+f))}else console.log("✓ ALL GREEN");
},700);
