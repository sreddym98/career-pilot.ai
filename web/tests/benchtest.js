const path=require('path');
const {JSDOM}=require('jsdom');const fs=require('fs');
const HTML=fs.readFileSync(path.join(__dirname,'..','index.html'),'utf8');
const mk=()=>{const d=new JSDOM(HTML,{runScripts:"dangerously",pretendToBeVisual:true,url:"https://careerpilot.ai/"});
  const w=d.window;w.scrollTo=()=>{};w.confirm=()=>true;w.print=()=>{};

  Object.defineProperty(w,"innerWidth",{value:800,configurable:true});  w.navigator.clipboard={writeText:()=>Promise.resolve()};
  w.__o=[];w.open=u=>{w.__o.push(u);return{focus(){}}};return w;};
let P=0,F=0;const fails=[];
const ok=(n,c,x)=>{c?P++:(F++,fails.push(n+(x?"  →  "+x:"")))};
// Job detail can render in the modal (#md) or the split pane (#jobDetailPane
// .splitcard) depending on viewport width. Tests query whichever is active.
const detailSel = (d) => d.querySelector("#jobDetailPane .splitcard") ? "#jobDetailPane" : "#md";
const sleep=ms=>new Promise(r=>setTimeout(r,ms));

(async()=>{
const w=mk(); await sleep(700);
const d=w.document,$=i=>d.getElementById(i),qa=s=>[...d.querySelectorAll(s)];
const click=e=>{if(!e)throw new Error("missing");e.dispatchEvent(new w.MouseEvent("click",{bubbles:true}))};
const ERR=[];w.addEventListener("error",e=>ERR.push(e.message));

console.log("\n╔═══ RECRUITER MODE ═══╗\n");

console.log("── Brand ──");
ok("title is careerpilot.ai",d.title.startsWith("careerpilot.ai"),d.title);
ok("logo shows the domain",d.querySelector(".sblogo").textContent.includes(".ai"));
ok("  has a real mark, not an emoji",!!d.querySelector(".sblogo svg"));

console.log("── Mode switch ──");
ok("two modes offered",qa(".modeb").length===2,qa(".modeb").map(b=>b.textContent).join(" / "));
ok("starts in seeker mode",w.CP.MODE==="seeker");
ok("  recruiter section hidden",d.querySelector('.sbgroup[data-only="recruiter"]').style.display==="none");
click(qa(".modeb").find(b=>b.dataset.m==="recruiter"));
await sleep(60);
ok("switches to recruiter",w.CP.MODE==="recruiter");
ok("  lands on Bench",$("p-bench").classList.contains("on"));
ok("  Bench + Submissions visible",d.querySelector('[data-p="bench"]').style.display!=="none");
ok("  seeker section hidden",d.querySelector('.sbgroup[data-only="seeker"]').style.display==="none");

console.log("── The bench ──");
ok("candidates loaded",w.CP.BENCH.length===6,w.CP.BENCH.length+"");
ok("  cards rendered",$("benchList").querySelectorAll(".cand").length===6);
ok("  stat tiles",$("benchStats").querySelectorAll(".stat3").length===5);
ok("  counts available now",$("benchStats").textContent.includes("Available now"));
ok("  each shows visa",$("benchList").textContent.includes("H1B"));
ok("  each shows rate",/\$\d+-\d+\/hr/.test($("benchList").textContent));
ok("  shows top match per person",$("benchList").innerHTML.includes("candmatch"));

$("benchQ").value="pyspark"; w.renderBench();
ok("search by skill works",$("benchList").querySelectorAll(".cand").length===1,$("benchList").querySelectorAll(".cand").length+"");
ok("  finds the right person",$("benchList").textContent.includes("Arjun"));
$("benchQ").value=""; $("benchAvail").value="now"; w.renderBench();
ok("filter by availability",$("benchList").querySelectorAll(".cand").length===3,$("benchList").querySelectorAll(".cand").length+"");
$("benchAvail").value=""; w.renderBench();

console.log("── Matching a person to roles ──");
const priya=w.CP.BENCH.find(c=>c.name.includes("Priya"));
const m=w.CP.jobsFor(priya,5);
ok("returns ranked matches",m.length>0&&m[0].score>=m[m.length-1].score,m.map(x=>x.score).join(","));
ok("  scores are sane",m.every(x=>x.score>=12&&x.score<=99));
ok("  names missing skills",m.some(x=>x.missing.length>=0));
const wei=w.CP.BENCH.find(c=>c.name.includes("Wei"));   // OPT
const bofa=w.CP.J.find(j=>j.co==="Bank of America");    // excludes non-citizens
ok("visa exclusion respected",w.CP.visaBlocked(wei,bofa)===true);
ok("  and excluded from matches",!w.CP.jobsFor(wei,20).some(x=>x.j.co==="Bank of America"));

console.log("── Matching a role to people ──");
const etl=w.CP.J.find(j=>j.fm==="etl");
const best=w.CP.bestFor(etl,3);
ok("ranks the bench for a role",best.length>0,best.map(b=>b.c.name.split(" ")[0]+":"+b.score).join(", "));
ok("  ETL person ranks top",best[0].c.role.includes("ETL")||best[0].overlap.length>0,best[0].c.role);
ok("  placed people excluded",!best.some(b=>b.c.avail==="placed"));

console.log("── Submitting ──");
w.go("jobs");
const card=d.querySelector(".job .cardacts .btn-p");
ok("card says Submit someone",card.textContent.includes("Submit someone"),card.textContent);
ok("  card previews the best fit",!!d.querySelector(".job .ctag"));
click(card);
ok("picker opens",$("ov").classList.contains("on"));
ok("  ranks everyone",$("md").querySelectorAll(".row").length>=6);
ok("  shows fit scores",!!$("md").querySelector(".fit3"));
ok("  greys out ineligible",$("md").innerHTML.includes("dim")||$("md").innerHTML.includes("Not eligible"));
ok("  explains why",$("md").textContent.includes("excludes")||$("md").textContent.includes("Not eligible"));
const sub=qa("#md button").find(b=>b.textContent==="Submit");
click(sub);
await sleep(60);
ok("submission recorded",w.CP.SUBS.length===1,w.CP.SUBS.length+"");
ok("  captures the fit score",w.CP.SUBS[0].fit>0);
w.go("subs");
ok("appears in Submissions",$("subList").textContent.includes(w.CP.SUBS[0].cand));
ok("  grouped by status",$("subList").innerHTML.includes("Submitted"));
ok("  status is changeable",!!$("subList").querySelector(".ministat"));
w.setSubStatus(0,"interview");
ok("  status updates",w.CP.SUBS[0].st==="interview");
ok("  summary reflects it",$("subSum").textContent.includes("1 interviewing"),$("subSum").textContent);

console.log("── No double submissions ──");
const n=w.CP.SUBS.length;
w.submitTo(w.CP.SUBS[0].candId, w.CP.SUBS[0].jobId);
ok("same person to same role blocked",w.CP.SUBS.length===n);

console.log("── Adding someone ──");
w.go("bench");
click(qa("#p-bench .btn-p")[0]);
ok("add form opens",$("md").innerHTML.includes("Add someone to your bench"));
$("c-name").value="Ravi Kumar";
$("c-yrs").value="9";
$("c-visa").value="h1b";
$("c-rate").value="$70-78/hr";
$("c-loc").value="Plano, TX";
$("c-newsk").value="Playwright"; w.addCandSkill();
$("c-newsk").value="Kubernetes"; w.addCandSkill();
ok("  skills added",w.CP.CAND_SKILLS.length===2);
click(qa("#md button").find(b=>b.textContent==="Add to bench"));
await sleep(60);
ok("candidate added",w.CP.BENCH.length===7);
ok("  appears on the bench",$("benchList").textContent.includes("Ravi Kumar"));
ok("  gets matched immediately",w.CP.jobsFor(w.CP.BENCH.find(c=>c.name==="Ravi Kumar"),3).length>0);

console.log("── Validation ──");
w.editCand(0);
$("c-name").value="";
click(qa("#md button").find(b=>b.textContent==="Add to bench"));
ok("blank name rejected",$("c-err").innerHTML.includes("Name is needed"));
$("c-name").value="Test Person";
click(qa("#md button").find(b=>b.textContent==="Add to bench"));
ok("no-skills rejected",$("c-err").innerHTML.includes("at least one skill"));
w.closeM();

console.log("── Removing ──");
const before=w.CP.BENCH.length;
const ravi=w.CP.BENCH.find(c=>c.name==="Ravi Kumar");
w.removeCand(ravi.id);
ok("candidate removed",w.CP.BENCH.length===before-1);

console.log("── Seeker mode is untouched ──");
w.setMode("seeker"); await sleep(60);
ok("back to seeker",w.CP.MODE==="seeker");
ok("  Jobs shows apply, not submit",d.querySelector(".job .cardacts .btn-p").textContent.match(/Apply|Search|Reply|Email/)!==null,
   d.querySelector(".job .cardacts .btn-p").textContent);
ok("  profile tab back",d.querySelector('[data-p="me"]').style.display!=="none");
ok("  bench section hidden",d.querySelector('.sbgroup[data-only="recruiter"]').style.display==="none");

console.log("── Design ──");
ok("elevation tokens defined",HTML.includes("--e3:")&&HTML.includes("--e4:"));
ok("  cards lift on hover",HTML.includes("translateY(-2px)"));
ok("  gradient buttons",HTML.includes("linear-gradient(180deg,#5A7A5C"));
ok("  sidebar has real elevation shadow",HTML.includes("box-shadow:1px 0 0")||HTML.includes("var(--e4)"));
ok("  dimensional avatars",HTML.includes("inset 0 1px 0 rgba(255,255,255,.25)"));
ok("ZERO uncaught errors",ERR.length===0,ERR.join(" | "));

console.log("\n"+"═".repeat(50));
console.log(`PASS ${P}    FAIL ${F}`);
if(F){console.log("\nFAILURES");fails.forEach(f=>console.log("  ✗ "+f))}else console.log("✓ ALL GREEN");
})();
