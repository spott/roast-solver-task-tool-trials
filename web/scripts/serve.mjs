import { createReadStream, existsSync, statSync } from "node:fs";
import { createServer } from "node:http";
import { extname, join, resolve } from "node:path";

const root = resolve(process.argv[2] || "dist");
const mime = { ".html": "text/html; charset=utf-8", ".js": "text/javascript; charset=utf-8", ".css": "text/css; charset=utf-8", ".wasm": "application/wasm", ".json": "application/json" };
createServer((request, response) => {
  const url = new URL(request.url, "http://localhost");
  let file = join(root, decodeURIComponent(url.pathname));
  if (url.pathname === "/") file = join(root, "index.html");
  if (!file.startsWith(root) || !existsSync(file) || statSync(file).isDirectory()) { response.writeHead(404); response.end("Not found"); return; }
  response.setHeader("Content-Type", mime[extname(file)] || "application/octet-stream");
  response.setHeader("Cross-Origin-Resource-Policy", "same-origin");
  createReadStream(file).pipe(response);
}).listen(4173, "127.0.0.1", () => console.log("Roast Solver preview: http://127.0.0.1:4173"));
