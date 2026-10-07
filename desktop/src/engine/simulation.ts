/**
 * simulation.ts — moteur de DÉMONSTRATION (l'ancien engine.ts de la maquette).
 *
 * Utilisé seulement quand aucun vrai moteur n'est joignable (pont de dev non lancé, sidecar absent).
 * L'interface affiche alors clairement « Moteur non connecté — démonstration ».
 *
 * Il imite le VRAI moteur : mêmes événements (progress avec `details`, log avec `niveau`),
 * mêmes textes que agent/progression.py et agent/conversion.py. Les écrans n'ont donc qu'un
 * seul chemin de code, qu'il s'agisse du vrai moteur ou de la démo.
 */
import type {
  EcouteursTache,
  InfoMoteur,
  Moteur,
  Preparation,
  ResultatConversion,
  Source,
  StatutLicence,
  TacheEnCours,
  VueParametres,
} from "./api";
import { ErreurMoteur, type EvProgress, type NiveauLog } from "./protocole";

export const DOSSIER_SORTIE_DEMO = "C:\\Users\\Agence\\Desktop\\HelpVA";
const SORTIE_MP4_DEMO = `${DOSSIER_SORTIE_DEMO}\\media (mp4)`;
const SOURCE_DEMO = "C:\\Users\\Agence\\Videos\\Shooting juin";

const ARBO: { nom: string; videos: string[] }[] = [
  { nom: "Backstage", videos: ["IMG_2041.MOV", "IMG_2042.MOV", "teaser.mkv"] },
  { nom: "Modèle A", videos: ["clip_07.mov", "clip_08.mov", "reel_final_v3.mov", "story_02.avi"] },
  { nom: "Modèle B", videos: ["IMG_3310.MOV", "IMG_3311.MOV", "clip_studio.avi", "interview.mkv"] },
];
const DUREES = [700, 580, 1000, 800, 640, 1150, 540, 760, 660, 950, 850];
const attendre = (ms: number) => new Promise((r) => setTimeout(r, ms));

/** Copie de agent/progression.py > court() : raccourcit avec « … » au milieu. */
function court(nom: string, n: number) {
  if (nom.length <= n) return nom;
  const garde = n - 1;
  return nom.slice(0, garde - Math.floor(garde / 3)) + "…" + nom.slice(nom.length - Math.floor(garde / 3));
}

/** Copie de agent/progression.py > texte(), avec les détails que le moteur ajoute. */
function progression(i: number, n: number, di: number, dn: number, nomDossier: string, fichier: string, pct: number, fraction: number): EvProgress {
  const lignes: string[] = [];
  if (dn > 1) lignes.push(`Dossier ${di}/${dn} — ${court(nomDossier, 26)}`);
  lignes.push(`Vidéo ${i}/${n} · ${court(fichier, 24)} — ${pct} %`);
  return {
    id: null,
    type: "progress",
    fraction: Math.round(fraction * 10000) / 10000,
    texte: lignes.join("\n"),
    details: {
      groupe: dn > 1 ? { mot: "Dossier", index: di, total: dn, nom: nomDossier } : null,
      element: { mot: "Vidéo", index: i, total: n, nom: fichier, pct },
    },
  };
}

export class MoteurSimule implements Moteur {
  readonly mode = "simule" as const;
  readonly transport = "simulation";

  async info(): Promise<InfoMoteur> {
    return {
      nom: "HelpVA",
      version: __APP_VERSION__,
      protocole: 1,
      python: "—",
      frozen: false,
      dossier_donnees: "—",
      dossier_sortie: DOSSIER_SORTIE_DEMO,
    };
  }
  async licenceStatut(): Promise<StatutLicence> {
    return { ok: true, raison: "actif", type: "mois", expire_le: null, jours_restants: null, nom: "Agence Démo" };
  }
  async parametresLire(): Promise<VueParametres> {
    return { parametres: {}, dossier_sortie: DOSSIER_SORTIE_DEMO, dossier_sortie_defaut: DOSSIER_SORTIE_DEMO, personnalise: false };
  }
  async parametresEcrire(): Promise<VueParametres> {
    throw new ErreurMoteur("NON_CONNECTE", "Moteur non connecté : les paramètres ne peuvent pas être enregistrés.");
  }
  async dossierSortie() {
    return { chemin: DOSSIER_SORTIE_DEMO, defaut: DOSSIER_SORTIE_DEMO, personnalise: false };
  }
  async ouvrirDossier(): Promise<void> {
    throw new ErreurMoteur("NON_CONNECTE", "Moteur non connecté : ouverture impossible (démonstration).");
  }
  async choisirDossier() {
    return SOURCE_DEMO;
  }
  async choisirFichiers() {
    return ARBO[1].videos.map((v) => `${SOURCE_DEMO}\\${ARBO[1].nom}\\${v}`);
  }
  async preparer(_commande: "conversion_mp4", args: { source: Source }): Promise<Preparation> {
    const nb = args.source.type === "dossier" ? ARBO.reduce((s, d) => s + d.videos.length, 0) : args.source.chemins.length;
    return { commande: "conversion_mp4", sortie: SORTIE_MP4_DEMO, existe: false, remplacement: false, nb_medias: nb };
  }

  convertirMp4(source: Source, ev: EcouteursTache): TacheEnCours<ResultatConversion> {
    let annule = false;
    const log = (texte: string, niveau: NiveauLog = "info") => ev.onLog({ id: null, type: "log", flux: "stdout", niveau, texte });
    const groupes =
      source.type === "dossier"
        ? ARBO
        : [{ nom: "", videos: source.chemins.map((c) => c.split(/[\\/]/).pop() || c) }];
    const total = groupes.reduce((s, g) => s + g.videos.length, 0);

    const resultat = (async (): Promise<ResultatConversion> => {
      const debut = performance.now();
      let fait = 0;
      let k = 0;
      for (let di = 0; di < groupes.length; di++) {
        const g = groupes[di];
        for (let i = 0; i < g.videos.length; i++) {
          const nom = g.videos[i];
          const duree = DUREES[k++ % DUREES.length];
          // Même ordre que agent/conversion.py : progression à 0 %, PUIS la ligne du journal.
          ev.onProgress(progression(i + 1, g.videos.length, di + 1, groupes.length, g.nom, nom, 0, fait / total));
          log(`[convert] (${i + 1}/${g.videos.length}) ${nom}…`);
          for (let t = 0; t < duree; t += 60) {
            const pct = Math.round((t / duree) * 100);
            ev.onProgress(progression(i + 1, g.videos.length, di + 1, groupes.length, g.nom, nom, pct, (fait + pct / 100) / total));
            await attendre(60);
            if (annule) {
              log(`[convert] ⛔ arrêté pendant : ${nom}`, "arret");
              await attendre(400);
              log(`⛔ Arrêté. ${fait} vidéo(s) en .mp4 déjà traité(s) → ${SORTIE_MP4_DEMO}`, "arret");
              return fin(fait, true, di + 1);
            }
          }
          fait++;
        }
      }
      log(`✅ ${fait} vidéo(s) en .mp4 → ${SORTIE_MP4_DEMO}`, "succes");
      return fin(fait, false, groupes.length);

      function fin(n: number, arrete: boolean, dossiers: number): ResultatConversion {
        return {
          traites: n,
          echecs: [],
          arrete,
          dossiers,
          sortie: SORTIE_MP4_DEMO,
          duree_s: Math.round((performance.now() - debut) / 100) / 10,
          bilan: { titre: arrete ? "Interrompu" : "Conversion terminée", message: "", erreur: false },
        };
      }
    })();

    return {
      resultat,
      annuler: async () => {
        annule = true;
      },
    };
  }

  surLogLibre() {}
  surDeconnexion() {}
  async fermer() {}
}
