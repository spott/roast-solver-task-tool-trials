import { createReadStream, existsSync, statSync } from 'node:fs';
import { createServer } from 'node:http';
import { extname, resolve, sep } from 'node:path';

const root = resolve('dist');
const args = process.argv.slice(2);
let host = process.env.HOST || '127.0.0.1';
let port = Number(process.env.PORT || 4173);
for (let index = 0; index < args.length; index += 1) {
  const arg = args[index];
  if (arg === '--host') host = args[++index];
  else if (arg === '--port') port = Number(args[++index]);
  else if (/^\d+$/.test(arg)) port = Number(arg); // backwards-compatible positional port
  else {
    console.error(`Unknown argument: ${arg}\nUsage: npm run preview -- [--host ADDRESS] [--port PORT]`);
    process.exit(1);
  }
}
if (!host || !Number.isInteger(port) || port < 1 || port > 65535) {
  console.error('Host must be non-empty and port must be an integer from 1 to 65535.');
  process.exit(1);
}
const types = {
  '.html': 'text/html; charset=utf-8', '.js': 'text/javascript; charset=utf-8',
  '.css': 'text/css; charset=utf-8', '.wasm': 'application/wasm',
  '.json': 'application/json; charset=utf-8', '.md': 'text/markdown; charset=utf-8',
};
if (!existsSync(root)) {
  console.error('dist/ does not exist. Run `npm run build` first.');
  process.exit(1);
}
const server = createServer((request, response) => {
  const pathname = decodeURIComponent(new URL(request.url, 'http://localhost').pathname);
  let file = resolve(root, `.${pathname === '/' ? '/index.html' : pathname}`);
  if (file !== root && !file.startsWith(root + sep)) {
    response.writeHead(403).end('Forbidden'); return;
  }
  if (existsSync(file) && statSync(file).isDirectory()) file = resolve(file, 'index.html');
  if (!existsSync(file)) { response.writeHead(404).end('Not found'); return; }
  response.writeHead(200, {
    'Content-Type': types[extname(file)] || 'application/octet-stream',
    'Content-Length': statSync(file).size,
    'Cache-Control': 'no-cache',
    'Cross-Origin-Opener-Policy': 'same-origin',
    'Cross-Origin-Embedder-Policy': 'require-corp',
  });
  if (request.method === 'HEAD') response.end();
  else createReadStream(file).pipe(response);
});
server.listen(port, host, () => console.log(`Roast Solver: http://${host}:${port}`));
