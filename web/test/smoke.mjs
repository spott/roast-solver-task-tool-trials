import { existsSync, readFileSync } from 'node:fs';
for (const file of ['dist/index.html','web/pkg/roast_core_bg.wasm','web/pkg/roast_core.js']) {
  if (!existsSync(file)) throw new Error(`missing production artifact: ${file}`);
}
const html=readFileSync('dist/index.html','utf8');
if (!html.includes('type="module"')) throw new Error('Vite module bundle missing');
const wasm=readFileSync('web/pkg/roast_core_bg.wasm');
if (wasm.length<1000) throw new Error('unexpectedly empty WASM core');
console.log(`static build smoke OK (${wasm.length} byte WASM core)`);
