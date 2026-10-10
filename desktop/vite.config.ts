import { defineConfig, type Plugin } from "vite";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";

// LA version de l'app, écrite à un seul endroit : package.json. Tauri la lit aussi
// (tauri.conf.json > "version": "../package.json"). Après l'avoir changée, relancez Vite.
const { version } = JSON.parse(readFileSync(new URL("./package.json", import.meta.url), "utf8")) as { version: string };

/** Fichier où engine/dev_bridge.py écrit son jeton à chaque démarrage. */
const FICHIER_JETON = fileURLToPath(new URL("../engine/.dev_token", import.meta.url));

/**
 * Route de DÉVELOPPEMENT /__helpva/jeton : donne à la page le jeton du pont (engine/dev_bridge.py).
 *
 * Pourquoi une route plutôt qu'une variable VITE_… : le pont crée un NOUVEAU jeton à chaque
 * lancement. Une variable serait figée au démarrage de Vite. Ici on relit le fichier à chaque fois.
 *
 * Sécurité :
 *  - `apply: "serve"` : la route n'existe QUE dans `npm run dev`, jamais dans le build livré ;
 *  - on refuse si le navigateur dit que la demande vient d'un AUTRE site (en-tête Sec-Fetch-Site) ;
 *  - Vite refuse déjà les noms d'hôte inconnus (protection « DNS rebinding ») ;
 *  - le jeton ne protège qu'un serveur local de dev, lui-même limité à 127.0.0.1.
 */
function jetonPontDev(): Plugin {
  return {
    name: "helpva-jeton-pont-dev",
    apply: "serve",
    configureServer(server) {
      server.middlewares.use("/__helpva/jeton", (req, res) => {
        const site = req.headers["sec-fetch-site"];
        if (req.method !== "GET" || (site !== undefined && site !== "same-origin" && site !== "none")) {
          res.statusCode = 403;
          res.end();
          return;
        }
        let jeton = "";
        try {
          jeton = readFileSync(FICHIER_JETON, "utf8").trim();
        } catch {
          /* pont non lancé */
        }
        res.setHeader("Cache-Control", "no-store");
        if (!jeton) {
          res.statusCode = 404;
          res.end();
          return;
        }
        res.setHeader("Content-Type", "text/plain; charset=utf-8");
        res.end(jeton);
      });
    },
  };
}

// Réglages recommandés par Tauri v2 pour Vite :
// - port FIXE 1420 (tauri.conf.json > build.devUrl pointe dessus ; le pont de dev n'accepte
//   QUE l'origine http://localhost:1420) ;
// - on ne surveille pas src-tauri (sinon Vite recharge à chaque compilation Rust).
const host = process.env.TAURI_DEV_HOST;

export default defineConfig({
  plugins: [react(), tailwindcss(), jetonPontDev()],
  // Version affichée dans l'app (navigateur). Dans Tauri, on la lit avec getVersion().
  define: { __APP_VERSION__: JSON.stringify(version) },
  clearScreen: false,
  server: {
    port: 1420,
    strictPort: true,
    host: host || false,
    hmr: host ? { protocol: "ws", host, port: 1421 } : undefined,
    watch: { ignored: ["**/src-tauri/**"] },
  },
  // WebView2 (Windows) et WebKit récents : on peut viser un JS moderne.
  build: { target: "es2022" },
});
