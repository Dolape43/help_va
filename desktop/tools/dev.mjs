// tools/dev.mjs — tout le développement en UNE commande : npm run dev:moteur
//
//   1. le pont du moteur Python (engine/dev_bridge.py --sans-licence), sauf s'il tourne déjà ;
//   2. l'interface (Vite, http://localhost:1420), sauf si elle tourne déjà.
//
// Ctrl+C arrête les deux. « npm run tauri:dev » s'en sert aussi (beforeDevCommand dans
// src-tauri/tauri.dev.conf.json) : la fenêtre Tauri parle alors au moteur par le pont.
//
// Options :  --avec-licence   le moteur exige une vraie licence (pour tester les écrans de licence)
// Variable : HELPVA_PYTHON    l'exécutable Python à utiliser (défaut : python / python3)
import { spawn } from "node:child_process";
import { readFileSync } from "node:fs";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const DESKTOP = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const RACINE = resolve(DESKTOP, "..");
const PORT_PONT = 8765;
const URL_INTERFACE = "http://localhost:1420/";
const PYTHON = process.env.HELPVA_PYTHON || (process.platform === "win32" ? "python" : "python3");
const AVEC_LICENCE = process.argv.includes("--avec-licence");

const COULEURS = { moteur: "\x1b[35m", interface: "\x1b[36m", dev: "\x1b[90m" };
const dire = (nom, texte) => process.stdout.write(`${COULEURS[nom] ?? ""}[${nom}]\x1b[0m ${texte}\n`);

/** Le pont répond-il déjà (lancé dans un autre terminal, ou resté d'avant) ? */
async function pontVivant() {
  let jeton = "";
  try {
    jeton = readFileSync(join(RACINE, "engine", ".dev_token"), "utf8").trim();
  } catch {
    return false;
  }
  try {
    const r = await fetch(`http://127.0.0.1:${PORT_PONT}/health`, {
      headers: { "X-HelpVA-Token": jeton },
      signal: AbortSignal.timeout(1500),
    });
    if (!r.ok) return false;
    const d = await r.json();
    return Boolean(d.ok && d.moteur_vivant);
  } catch {
    return false;
  }
}

async function interfaceVivante() {
  try {
    const r = await fetch(URL_INTERFACE, { signal: AbortSignal.timeout(1500) });
    return r.ok;
  } catch {
    return false;
  }
}

const enfants = [];
let arret = false;

function arreter(code = 0) {
  if (arret) return;
  arret = true;
  for (const p of enfants) {
    try {
      p.kill(); // le moteur, lui, s'arrête proprement quand son pont disparaît (fin de son entrée)
    } catch {
      /* déjà arrêté */
    }
  }
  setTimeout(() => process.exit(code), 300);
}

function lancer(nom, cmd, args, cwd) {
  const p = spawn(cmd, args, {
    cwd,
    stdio: ["ignore", "pipe", "pipe"],
    env: { ...process.env, PYTHONIOENCODING: "utf-8" },
    windowsHide: true,
  });
  let reste = { stdout: "", stderr: "" };
  for (const flux of ["stdout", "stderr"]) {
    p[flux].setEncoding("utf8");
    p[flux].on("data", (morceau) => {
      const lignes = (reste[flux] + morceau).split(/\r?\n/);
      reste[flux] = lignes.pop() ?? "";
      for (const l of lignes) if (l.trim()) dire(nom, l);
    });
  }
  p.on("error", (e) => {
    dire(nom, `impossible de lancer « ${cmd} » : ${e.message}`);
    if (nom === "moteur") dire("dev", "Python est-il installé ? Sinon : HELPVA_PYTHON=chemin\\vers\\python.exe");
    arreter(1);
  });
  p.on("exit", (code) => {
    if (arret) return;
    dire(nom, `s'est arrêté (code ${code ?? "?"})`);
    arreter(code ?? 1);
  });
  enfants.push(p);
  return p;
}

process.on("SIGINT", () => arreter(0));
process.on("SIGTERM", () => arreter(0));

if (await pontVivant()) {
  dire("dev", `moteur déjà lancé sur http://127.0.0.1:${PORT_PONT} : on le réutilise`);
} else {
  const args = [join(RACINE, "engine", "dev_bridge.py")];
  if (!AVEC_LICENCE) args.push("--sans-licence");
  dire("dev", `lancement du moteur Python${AVEC_LICENCE ? " (licence exigée)" : " (sans licence, dev)"}…`);
  lancer("moteur", PYTHON, args, RACINE);
}

if (await interfaceVivante()) {
  dire("dev", `interface déjà lancée sur ${URL_INTERFACE} : on la réutilise`);
  // On reste en vie : « tauri dev » arrête la fenêtre si cette commande se termine.
  setInterval(() => {}, 1 << 30);
} else {
  lancer("interface", process.execPath, [join(DESKTOP, "node_modules", "vite", "bin", "vite.js"), "--strictPort"], DESKTOP);
}
