// Captures d'écran de la maquette avec Edge headless (même moteur Chromium que WebView2).
//
// usage : node tools/capture.mjs <url> <plan.json> <dossier-sortie> [largeur=1160] [hauteur=760]
//
// plan.json = liste de captures : [{ "nom": "accueil_clair", "js": "__demo('theme','light')", "attente": 300 }]
//   js      : code exécuté dans la page avant la capture (après rechargement de la page)
//   attente : délai en ms avant la capture
//   survol  : sélecteur CSS d'un élément à survoler avant la capture (facultatif)
//   mouvement : true pour NE PAS émuler « mouvement réduit » (par défaut, on l'émule : captures stables)
//   url     : adresse propre à cette capture (facultatif ; sinon <url>), ex. "http://localhost:1420/?scenario=expire&capture"
import { spawn, spawnSync } from "node:child_process";
import { mkdtempSync, mkdirSync, writeFileSync, readFileSync, existsSync } from "node:fs";
import { tmpdir } from "node:os";
import { join, resolve } from "node:path";

const [url, planFichier, sortie = "captures", L = "1160", H = "760"] = process.argv.slice(2);
if (!url || !planFichier) {
  console.error("usage : node tools/capture.mjs <url> <plan.json> <dossier-sortie> [largeur] [hauteur]");
  process.exit(1);
}
const W = +L, HT = +H;
const plan = JSON.parse(readFileSync(planFichier, "utf8"));
const outDir = resolve(sortie);
mkdirSync(outDir, { recursive: true });

const EDGE = "C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe";
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const profil = mkdtempSync(join(tmpdir(), "helpva-capture-"));
const edge = spawn(EDGE, [
  "--headless=new", "--remote-debugging-port=0", `--user-data-dir=${profil}`, `--window-size=${W},${HT}`,
  "--hide-scrollbars", "--no-first-run", "--no-default-browser-check", "--disable-extensions",
  "--force-color-profile=srgb", "about:blank",
], { stdio: "ignore" });
const tuerEdge = () => { try { spawnSync("taskkill", ["/PID", String(edge.pid), "/T", "/F"], { stdio: "ignore" }); } catch {} };
process.on("exit", tuerEdge);
process.on("uncaughtException", (e) => { console.error(e); tuerEdge(); process.exit(1); });
process.on("unhandledRejection", (e) => { console.error(e); tuerEdge(); process.exit(1); });

let port, cibles;
for (let i = 0; i < 300 && !port; i++) {
  const f = join(profil, "DevToolsActivePort");
  if (existsSync(f)) port = +readFileSync(f, "utf8").split(/\r?\n/)[0]; else await sleep(100);
}
if (!port) throw new Error("Edge n'a pas démarré");
for (let i = 0; i < 100; i++) {
  try { cibles = await (await fetch(`http://127.0.0.1:${port}/json/list`)).json(); if (cibles.some((t) => t.type === "page")) break; } catch {}
  await sleep(100);
}
const ws = new WebSocket(cibles.find((t) => t.type === "page").webSocketDebuggerUrl);
await new Promise((r, j) => { ws.onopen = r; ws.onerror = j; });
let seq = 0; const attente = new Map(); const ecoute = new Map(); const logs = [];
ws.onmessage = (m) => {
  const d = JSON.parse(m.data);
  if (d.id && attente.has(d.id)) { const { r, j } = attente.get(d.id); attente.delete(d.id); d.error ? j(new Error(JSON.stringify(d.error))) : r(d.result); }
  else if (d.method === "Runtime.exceptionThrown") logs.push("EXCEPTION " + (d.params.exceptionDetails.exception?.description || d.params.exceptionDetails.text));
  else if (d.method === "Runtime.consoleAPICalled" && ["error", "warning"].includes(d.params.type)) logs.push(d.params.type + " " + d.params.args.map((a) => a.value ?? a.description).join(" "));
  else if (d.method && ecoute.has(d.method)) { ecoute.get(d.method)(d.params); ecoute.delete(d.method); }
};
const cmd = (method, params = {}) => new Promise((r, j) => {
  const id = ++seq; const to = setTimeout(() => { attente.delete(id); j(new Error(`CDP timeout: ${method}`)); }, 60000);
  attente.set(id, { r: (v) => { clearTimeout(to); r(v); }, j: (e) => { clearTimeout(to); j(e); } });
  ws.send(JSON.stringify({ id, method, params }));
});
const une = (method) => new Promise((r) => ecoute.set(method, r));
const evalJs = async (expression) => {
  const res = await cmd("Runtime.evaluate", { expression, awaitPromise: true, returnByValue: true });
  if (res.exceptionDetails) throw new Error(res.exceptionDetails.exception?.description || res.exceptionDetails.text);
  return res.result.value;
};

await cmd("Page.enable"); await cmd("Runtime.enable");
await cmd("Emulation.setDeviceMetricsOverride", { width: W, height: HT, deviceScaleFactor: 1, mobile: false });

for (const c of plan) {
  await cmd("Emulation.setEmulatedMedia", {
    features: [{ name: "prefers-reduced-motion", value: c.mouvement ? "no-preference" : "reduce" }],
  });
  const charge = une("Page.loadEventFired");
  await cmd("Page.navigate", { url: c.url ?? url });
  await charge;
  await evalJs("document.fonts.ready.then(() => true)");
  await sleep(150);
  if (c.js) await evalJs(c.js);
  if (c.survol) {
    const box = await evalJs(`(() => { const r = document.querySelector(${JSON.stringify(c.survol)}).getBoundingClientRect(); return { x: r.x + r.width / 2, y: r.y + r.height / 2 }; })()`);
    await cmd("Input.dispatchMouseEvent", { type: "mouseMoved", x: box.x, y: box.y });
  }
  await sleep(c.attente ?? 300);
  const { data } = await cmd("Page.captureScreenshot", { format: "png" });
  const f = join(outDir, `${c.nom}.png`);
  writeFileSync(f, Buffer.from(data, "base64"));
  console.log("ok", f);
}
if (logs.length) console.log("CONSOLE:\n" + [...new Set(logs)].join("\n"));
tuerEdge();
process.exit(0);
