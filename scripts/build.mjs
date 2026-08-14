import { cp, mkdir, rm, stat } from "node:fs/promises";
import { existsSync } from "node:fs";
import { spawnSync } from "node:child_process";
import path from "node:path";
const root=path.resolve(import.meta.dirname,"..");
const target=path.join(root,"rust_core/target/wasm32-unknown-unknown/release/roast_core.wasm");
const source=path.join(root,"rust_core/src/lib.rs");
let needsBuild=!existsSync(target);
if(!needsBuild)needsBuild=(await stat(source)).mtimeMs>(await stat(target)).mtimeMs;
if(needsBuild){
  console.log("Building Rust core for wasm32-unknown-unknown…");
  const result=spawnSync("cargo",["build","--manifest-path",path.join(root,"rust_core/Cargo.toml"),"--target","wasm32-unknown-unknown","--release"],{stdio:"inherit",env:{...process.env,RUSTFLAGS:`${process.env.RUSTFLAGS||""} -C target-feature=+simd128`.trim()}});
  if(result.error?.code==="ENOENT")throw new Error("cargo not found; enter `nix develop` or install the Rust toolchain");
  if(result.status!==0)process.exit(result.status||1);
}
const dist=path.join(root,"dist");await rm(dist,{recursive:true,force:true});await mkdir(dist,{recursive:true});
for(const file of ["index.html","styles.css","app.js","solver-worker.js","ui-utils.js"])await cp(path.join(root,"web",file),path.join(dist,file));
await cp(target,path.join(dist,"roast_core.wasm"));
console.log(`Static production app built at ${path.relative(root,dist)}/`);
