import { readFile, stat } from 'node:fs/promises';
import { join, resolve } from 'node:path';

const root = resolve('dist');
const required = ['index.html','styles.css','app.js','worker.js','wasm/roast_solver_web_core.js','wasm/roast_solver_web_core_bg.wasm'];
for (const path of required) {
  const info = await stat(join(root, path));
  if (!info.isFile() || info.size === 0) throw new Error(`Missing or empty build asset: ${path}`);
}
const [html, app, worker] = await Promise.all(['index.html','app.js','worker.js'].map(p => readFile(join(root,p),'utf8')));
for (const id of ['simulation-form','curve-canvas','slice-canvas','pasteurization','carryover']) {
  if (!html.includes(`id="${id}"`)) throw new Error(`UI contract missing #${id}`);
}
if (!app.includes("new Worker(new URL('./worker.js'")) throw new Error('App does not construct the module worker');
if (!worker.includes("from './wasm/roast_solver_web_core.js'")) throw new Error('Worker does not import production WASM');
console.log(`Static build check passed (${required.length} required assets and UI/worker contracts).`);
