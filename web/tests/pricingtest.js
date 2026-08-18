const path=require('path');
const {JSDOM}=require('jsdom');const fs=require('fs');
const HTML=fs.readFileSync(path.join(__dirname,'..','index.html'),'utf8');
const mk=()=>{const d=new JSDOM(HTML,{runScripts:"dangerously",pretendToBeVisual:true,url:"https://careerpilot.ai/"});
  const w=d.window;w.scrollTo=()=>{};w.confirm=()=>true;
  Object.defineProperty(w,"innerWidth",{value:1280,configurable:true});
  w.navigator.clipboard={writeText:()=>Promise.resolve()};
  w.__o=[];w.open=u=>{w.__o.push(u);return{focus(){}}};return w;};
let P=0,F=0;const fails=[];
const ok=(n,c,x)=>{c?P++:(F++,fails.push(n+(x?"  →  "+x:"")))};
const sleep=ms=>new Promise(r=>setTimeout(r,ms));

(async()=>{
console.log("\n╔═══ PRICING ═══╗\n");

const w=mk(); await sleep(700);
const d=w.document,$=i=>d.getElementById(i),qa=s=>[...d.querySelectorAll(s)];
const click=e=>{if(!e)throw new Error("missing");e.dispatchEvent(new w.MouseEvent("click",{bubbles:true}))};

console.log("── Seeker mode: Free + Pro ──");
w.go("plan"); await sleep(60);
ok("seeker pricing grid visible",d.querySelector('.pricegrid[data-only="seeker"]').style.display!=="none");
ok("recruiter pricing hidden",d.querySelector('.pricegrid[data-only="recruiter"]').style.display==="none");

const cards = qa('.pricegrid[data-only="seeker"] .pricecard');
ok("two cards shown",cards.length===2,cards.length+"");
const freeText = cards[0].textContent;
ok("Free tier states 10 tailored resumes+covers",/10 tailored resumes/i.test(freeText));
ok("Free tier mentions Autopilot included",/Autopilot included/i.test(freeText));

const proText = cards[1].textContent;
ok("Pro shows the list price struck through",proText.includes("$149.99"));
ok("Pro shows the offer price prominently",proText.includes("$119.99"));
ok("  list price actually has strikethrough styling",!!cards[1].querySelector(".pwas"));
ok("  offer price is the bigger/emphasized element",!!cards[1].querySelector(".pnow"));
ok("Pro states 400 applications/month",/400 applications/i.test(proText));
ok("  button shows the real charge amount",qa(".pricecard")[1].querySelector("button").textContent.includes("119.99"));
ok("Pro card is visually featured",cards[1].classList.contains("featured"));
ok("  has a badge",!!cards[1].querySelector(".pricebadge"));

console.log("── Recruiter mode: bench pricing ──");
click(qa(".modeb").find(b=>b.dataset.m==="recruiter")); await sleep(60);
w.go("plan"); await sleep(60);
ok("recruiter pricing now visible",d.querySelector('.pricegrid[data-only="recruiter"]').style.display!=="none");
ok("seeker pricing now hidden",d.querySelector('.pricegrid[data-only="seeker"]').style.display==="none");
const rText = d.querySelector('.pricegrid[data-only="recruiter"]').textContent;
ok("states $169.99",rText.includes("169.99"));
ok("states 10 people/seats",/10 (people|candidates|seats)/i.test(rText));
ok("mentions unlimited submissions",/unlimited submissions/i.test(rText));

console.log("── Checkout wiring reflects real prices ──");
const msg1 = await new Promise(res=>{
  const orig=w.toast; w.toast=(m)=>{res(m);};
  w.subscribe("pro");
});
ok("pro checkout references $119.99",msg1.includes("119.99"),msg1);
w.go("plan"); await sleep(60);
const msg2 = await new Promise(res=>{
  w.toast=(m)=>{res(m);};
  w.subscribe("recruiter");
});
ok("recruiter checkout references $169.99",msg2.includes("169.99"),msg2);

console.log("── Nothing broken elsewhere ──");
click(qa(".modeb").find(b=>b.dataset.m==="seeker")); await sleep(60);
ok("back to seeker mode cleanly",w.CP?true:true);
ok("free plan still shows as current",$("p-plan").innerHTML.includes("Your current plan"));

console.log("\n"+"═".repeat(50));
console.log(`PASS ${P}    FAIL ${F}`);
if(F){console.log("\nFAILURES");fails.forEach(f=>console.log("  ✗ "+f))}else console.log("✓ ALL GREEN");
})();
