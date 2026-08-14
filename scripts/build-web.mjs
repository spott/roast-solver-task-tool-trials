import {cp,rm,mkdir,access} from 'node:fs/promises';
import {spawnSync} from 'node:child_process';
const root=new URL('../',import.meta.url).pathname;
if(process.env.SKIP_WASM!=='1'){
  const r=spawnSync('bash',['scripts/build-wasm.sh'],{cwd:root,stdio:'inherit'});
  if(r.status!==0){const msg='WASM toolchain unavailable; static build will use the tested JavaScript worker fallback.';if(process.env.REQUIRE_WASM==='1')throw new Error(msg);console.warn('\n'+msg+'\nRun `npm run build:wasm` in `nix develop` to include Rust/WASM.');}
}
await rm(root+'dist',{recursive:true,force:true});await mkdir(root+'dist/wasm',{recursive:true});
await cp(root+'web/index.html',root+'dist/index.html');
await cp(root+'web/src/app.js',root+'dist/app.js');await cp(root+'web/src/worker.js',root+'dist/worker.js');await cp(root+'web/src/style.css',root+'dist/style.css');
try{await access(root+'web/public/wasm/roast_solver_core.wasm');await cp(root+'web/public/wasm/roast_solver_core.wasm',root+'dist/wasm/roast_solver_core.wasm')}catch{}
console.log('Static production build written to dist/');
