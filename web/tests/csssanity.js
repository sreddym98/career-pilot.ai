const path=require('path');
// Guards against the exact bug that just shipped: a CSS rule referenced by
// the HTML/JS but never actually present in the stylesheet, because an
// edit silently failed to match its anchor. Run this after every assembly.
const fs = require('fs');
const h = fs.readFileSync(path.join(__dirname,'..','index.html'), 'utf8');
const css = h.slice(h.indexOf('<style>') + 7, h.indexOf('</style>'));
const html = h.slice(h.indexOf('<body') > -1 ? h.indexOf('<body') : 0, h.indexOf('<script>'));

let P = 0, F = 0; const fails = [];
const ok = (n, c, x) => { c ? P++ : (F++, fails.push(n + (x ? '  →  ' + x : ''))); };

// 1. Brace balance
let depth = 0;
for (const ch of css) { if (ch === '{') depth++; else if (ch === '}') depth--; }
ok('CSS braces balance', depth === 0, `off by ${depth}`);

// 2. Every class referenced in the static HTML has a rule that defines it —
//    at minimum a bare `.classname{` or `.classname ` combinator somewhere.
const classesUsed = new Set();
[...html.matchAll(/class="([^"]+)"/g)].forEach(m => m[1].split(/\s+/).forEach(c => c && classesUsed.add(c)));
const structural = ['on', 'open', 'selected', 'done', 'good', 'warn', 'bad', 'cool', 'ok', 'a', 'b', 'c', 'sm', 'lg', 'price', 'new'];
const missing = [...classesUsed].filter(c =>
  !structural.includes(c) &&
  !css.includes('.' + c + '{') &&
  !css.includes('.' + c + ' ') &&
  !css.includes('.' + c + ':') &&
  !css.includes('.' + c + '.') &&
  !css.includes('.' + c + ',')
);
ok(`every static class has a CSS rule (${classesUsed.size} classes checked)`, missing.length === 0, missing.slice(0, 15).join(', '));

// 3. No leftover selectors from a removed layout (the exact bug this time)
const deadSelectors = ['header{', '.tb{', '.tb:', '.tb.on', '.more{', '.menu{', '.menu ', 'main{'];
const zombies = deadSelectors.filter(s => css.includes(s));
ok('no dead selectors from the old top-nav', zombies.length === 0, zombies.join(', '));

// 4. Key structural selectors from the current design exist
const required = ['.appshell{', '.sidebar{', '.sbi{', '.sblogo .mark{', '.mainarea{', '.splitpane{'];
const req_missing = required.filter(s => !css.includes(s));
ok('current layout selectors all present', req_missing.length === 0, req_missing.join(', '));

console.log('\n' + '='.repeat(50));
console.log(`PASS ${P}    FAIL ${F}`);
if (F) { console.log('\nFAILURES'); fails.forEach(f => console.log('  ✗ ' + f)); process.exit(1); }
else console.log('✓ ALL GREEN — no orphaned CSS references');
