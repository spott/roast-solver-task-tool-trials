import { cp, mkdir, rm } from 'node:fs/promises';
import { spawnSync } from 'node:child_process';
import { dirname, join, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

const scriptDir = dirname(fileURLToPath(import.meta.url));
const root = resolve(scriptDir, '../..');
const web = join(root, 'web');
const dist = join(root, 'dist');

await rm(dist, { recursive: true, force: true });
await mkdir(join(dist, 'wasm'), { recursive: true });

console.log('Building Rust core for wasm32…');
const result = spawnSync('wasm-pack', [
  'build', join(root, 'web-core'), '--target', 'web',
  '--out-dir', '../dist/wasm', '--release',
], { cwd: root, stdio: 'inherit' });
if (result.error?.code === 'ENOENT') {
  console.error('\nwasm-pack was not found. Enter `nix develop` or install wasm-pack, then retry.');
  process.exit(1);
}
if (result.status !== 0) process.exit(result.status ?? 1);

await Promise.all(['index.html', 'styles.css', 'app.js', 'worker.js'].map(file =>
  cp(join(web, file), join(dist, file))
));
await mkdir(join(dist, 'docs'), { recursive: true });
await Promise.all(['PHYSICS.md', 'VALIDATION.md', 'CALIBRATION.md', 'PARITY.md'].map(file =>
  cp(join(root, 'docs', file), join(dist, 'docs', file))
));
console.log(`Production site built at ${dist}`);
