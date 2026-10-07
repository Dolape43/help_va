/**
 * sidecar.ts — transport FINAL : l'app Tauri lance le moteur (helpva-engine.exe) et lui parle
 * par son entrée/sortie standard, grâce au plugin officiel @tauri-apps/plugin-shell.
 *
 * ⚠️ Pas encore testable : il faut Rust + MSVC (pour `tauri dev`) ET l'exe du moteur construit
 * avec PyInstaller, copié dans src-tauri/binaries/helpva-engine-x86_64-pc-windows-msvc.exe
 * (Tauri ajoute lui-même le suffixe de la plateforme). Voir desktop/README.md.
 *
 * Ce qui est déjà prévu côté Tauri :
 *   - tauri.conf.json  > bundle.externalBin = ["binaries/helpva-engine"]
 *   - capabilities/default.json : shell:allow-spawn (UNIQUEMENT ce sidecar), allow-stdin-write, allow-kill
 *   - src-tauri/src/lib.rs : .plugin(tauri_plugin_shell::init())
 */
import { Command, type Child } from "@tauri-apps/plugin-shell";
import { DecoupeurLignes, ErreurMoteur, estEvenement, type Evenement, type Requete } from "./protocole";
import type { FinTransport, Transport } from "./transport";

/** Même nom que dans tauri.conf.json > bundle.externalBin et dans la capability. */
export const NOM_SIDECAR = "binaries/helpva-engine";

/**
 * Temps laissé au moteur pour s'arrêter seul après « quitter », avant de le tuer.
 * D'habitude il s'arrête en moins d'une seconde. Mais il ATTEND jusqu'à 30 s une commande
 * « critique » en cours (licence_activer : couper au milieu pourrait consommer le code
 * sans enregistrer la licence). D'où 40 s. La fenêtre est déjà cachée pendant ce temps
 * (voir plateforme.ts > avantFermeture) : l'utilisateur n'attend pas.
 */
const DELAI_FERMETURE_MS = 40_000;

export class TransportSidecar implements Transport {
  readonly nom = "sidecar";
  private enfant: Child | null = null;
  private termine = false;
  private quandTermine: Promise<void> = Promise.resolve();
  /** L'arrêt en cours (le même pour tous les appelants : on n'envoie « quitter » qu'une fois). */
  private arret: Promise<void> | null = null;

  async demarrer(recevoir: (ev: Evenement) => void, fin: (f: FinTransport) => void): Promise<void> {
    const cmd = Command.sidecar(NOM_SIDECAR, []);

    // stdout = UNIQUEMENT le protocole (le moteur y veille, voir engine/README.md).
    const decoupeur = new DecoupeurLignes(
      (obj) => {
        if (estEvenement(obj)) recevoir(obj);
      },
      (ligne) => console.warn("[sidecar] ligne illisible :", ligne.slice(0, 200)),
    );
    cmd.stdout.on("data", (morceau) => decoupeur.pousser(String(morceau)));

    // stderr = les plantages « durs » (trace Python). On les montre dans le journal, sans id.
    cmd.stderr.on("data", (ligne) => {
      const texte = String(ligne).replace(/\r?\n$/, "");
      if (texte) recevoir({ id: null, type: "log", flux: "stderr", niveau: "erreur", texte });
    });

    let signalerFin: () => void = () => {};
    this.quandTermine = new Promise<void>((r) => (signalerFin = r));
    cmd.on("close", ({ code }) => {
      this.termine = true;
      this.enfant = null;
      signalerFin();
      fin({ raison: `Le moteur s'est arrêté (code ${code ?? "?"}).` });
    });
    cmd.on("error", (e) => console.error("[sidecar] erreur :", e));

    try {
      this.enfant = await cmd.spawn();
    } catch (e) {
      throw new ErreurMoteur("NON_CONNECTE", `Impossible de lancer le moteur (${NOM_SIDECAR}) : ${String(e)}`);
    }
  }

  async envoyer(req: Requete): Promise<void> {
    if (!this.enfant || this.termine) throw new ErreurMoteur("MOTEUR_ARRETE", "Le moteur est arrêté.");
    // JSON.stringify échappe les caractères « bizarres » (surrogates isolées) : la ligne reste valide.
    await this.enfant.write(JSON.stringify(req) + "\n");
  }

  arreter(): Promise<void> {
    // Plusieurs appels (fermeture de fenêtre + nettoyage React…) : un seul « quitter ».
    this.arret ??= this.arreterUneFois();
    return this.arret;
  }

  private async arreterUneFois(): Promise<void> {
    const enfant = this.enfant;
    if (!enfant || this.termine) return;
    // 1) On demande poliment : le moteur annule la tâche en cours, arrête ffmpeg, supprime le
    //    fichier incomplet, répond, puis quitte. On attend l'événement « close » du processus :
    //    si on fermait l'app tout de suite, Tauri tuerait le moteur en plein ménage.
    try {
      await enfant.write(JSON.stringify({ id: "ui-quitter", cmd: "quitter", args: { delai_s: 5 } }) + "\n");
    } catch {
      /* tuyau déjà fermé */
    }
    // 2) S'il ne s'est pas arrêté à temps, on force (le « Job Windows » du moteur emporte aussi ses ffmpeg).
    const delai = new Promise<"delai">((r) => setTimeout(() => r("delai"), DELAI_FERMETURE_MS));
    if ((await Promise.race([this.quandTermine.then(() => "ok" as const), delai])) === "delai") {
      await enfant.kill().catch(() => {});
    }
  }
}
