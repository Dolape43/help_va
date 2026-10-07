/**
 * api.ts — ce que les ÉCRANS ont le droit de demander au moteur, avec des types.
 *
 * Les écrans ne voient jamais de JSON ni d'id : ils appellent `moteur.convertirMp4(...)`.
 * Deux implémentations du même contrat `Moteur` :
 *   - MoteurReel    (ce fichier)     : le vrai moteur Python (pont de dev ou sidecar Tauri) ;
 *   - MoteurSimule  (simulation.ts)  : des minuteurs JavaScript, quand aucun moteur n'est joignable.
 */
import { DANS_TAURI } from "../plateforme";
import type { ClientMoteur, Ecouteurs } from "./client";
import type { EvLog, EvProgress } from "./protocole";

/* ---------- Types des réponses (voir engine/README.md, section 3) ---------- */

export type Source = { type: "dossier"; chemin: string } | { type: "fichiers"; chemins: string[] };

export type InfoMoteur = {
  nom: string;
  version: string;
  protocole: number;
  python: string;
  frozen: boolean;
  dossier_donnees: string;
  dossier_sortie: string;
  licence_contournee_dev?: boolean;
};

export type TypeLicence = "vie" | "mois" | "an";

export type StatutLicence = {
  ok: boolean;
  raison: "actif" | "pas_active" | "invalide" | "mauvais_pc" | "expire" | "pas_internet" | "revoquee" | "suspendu" | string;
  type: TypeLicence | null;
  /** "AAAA-MM-JJ" */
  expire_le: string | null;
  debut_le?: string | null;
  jours_restants: number | null;
  nom?: string | null;
  hors_ligne?: boolean;
};

export type VueParametres = {
  parametres: Record<string, unknown>;
  dossier_sortie: string;
  dossier_sortie_defaut: string;
  personnalise: boolean;
};

export type Preparation = {
  commande: string;
  sortie: string;
  existe: boolean;
  remplacement: boolean;
  nb_medias: number;
  /** conversion_mp4 : nombre de .mp4 déjà présents qui seront écrasés */
  deja_presents?: number;
};

export type Bilan = { titre: string; message: string; erreur: boolean };

export type ResultatConversion = {
  traites: number;
  echecs: string[];
  arrete: boolean;
  dossiers: number;
  sortie: string;
  duree_s: number;
  bilan: Bilan;
};

export type FiltreFichiers = "videos" | "images" | "medias" | "tous";

/** Une tâche longue lancée : son résultat, et de quoi l'annuler. */
export type TacheEnCours<T> = { resultat: Promise<T>; annuler: () => Promise<void> };

export type EcouteursTache = {
  onProgress: (ev: EvProgress) => void;
  onLog: (ev: EvLog) => void;
};

/** Le contrat commun (vrai moteur ET simulation). */
export interface Moteur {
  /** "reel" = vrai moteur Python ; "simule" = démonstration (dev seulement) ;
   *  "indisponible" = app livrée dont le moteur n'a pas démarré (toutes les actions échouent). */
  readonly mode: "reel" | "simule" | "indisponible";
  /** « pont de dev », « sidecar » ou « simulation » */
  readonly transport: string;
  info(): Promise<InfoMoteur>;
  licenceStatut(): Promise<StatutLicence>;
  parametresLire(): Promise<VueParametres>;
  parametresEcrire(valeurs: Record<string, unknown>): Promise<VueParametres>;
  /** Le dossier de sortie effectif (créé s'il n'existe pas, comme l'ancienne app). */
  dossierSortie(): Promise<{ chemin: string; defaut: string; personnalise: boolean }>;
  ouvrirDossier(chemin: string): Promise<void>;
  choisirDossier(titre?: string): Promise<string | null>;
  choisirFichiers(titre?: string, filtre?: FiltreFichiers): Promise<string[]>;
  preparer(commande: "conversion_mp4", args: { source: Source }): Promise<Preparation>;
  convertirMp4(source: Source, ev: EcouteursTache): TacheEnCours<ResultatConversion>;
  /** Journal sans propriétaire (plantage dur du moteur…). */
  surLogLibre(f: ((ev: EvLog) => void) | null): void;
  /** Appelé si le moteur se déconnecte. */
  surDeconnexion(f: ((raison: string) => void) | null): void;
  fermer(): Promise<void>;
}

/* ---------- Extensions vidéo (même liste que agent/conversion.py, pour le sélecteur Tauri) ---------- */
const EXT_VIDEOS = ["mov", "mp4", "m4v", "avi", "mkv", "webm", "mpg", "mpeg", "wmv", "flv"];
const FILTRES_TAURI: Record<FiltreFichiers, { name: string; extensions: string[] }[]> = {
  videos: [{ name: "Vidéos", extensions: EXT_VIDEOS }],
  images: [{ name: "Images", extensions: ["jpg", "jpeg", "png", "webp", "heic", "heif", "bmp", "tif", "tiff"] }],
  medias: [{ name: "Médias", extensions: ["jpg", "jpeg", "png", "webp", "heic", "heif", ...EXT_VIDEOS] }],
  tous: [],
};

/* ---------- Le vrai moteur ---------- */

export class MoteurReel implements Moteur {
  readonly mode = "reel" as const;
  readonly transport: string;

  constructor(private readonly client: ClientMoteur) {
    this.transport = client.transport.nom;
  }

  info() {
    return this.client.appeler<InfoMoteur>("info");
  }
  licenceStatut() {
    return this.client.appeler<StatutLicence>("licence_statut");
  }
  parametresLire() {
    return this.client.appeler<VueParametres>("parametres_lire");
  }
  parametresEcrire(valeurs: Record<string, unknown>) {
    return this.client.appeler<VueParametres>("parametres_ecrire", { valeurs });
  }
  dossierSortie() {
    return this.client.appeler<{ chemin: string; defaut: string; personnalise: boolean }>("dossier_sortie");
  }
  async ouvrirDossier(chemin: string) {
    // C'est le MOTEUR qui ouvre l'Explorateur : il vérifie que c'est bien un dossier existant
    // (jamais un .exe). Ça marche pareil avec le pont de dev et dans Tauri, sans donner à
    // l'interface la permission d'ouvrir n'importe quel chemin.
    await this.client.appeler("ouvrir_dans_explorateur", { chemin });
  }

  async choisirDossier(titre = "Choisir un dossier") {
    if (DANS_TAURI) {
      const { open } = await import("@tauri-apps/plugin-dialog");
      const choix = await open({ directory: true, multiple: false, title: titre });
      return typeof choix === "string" ? choix : null;
    }
    // Navigateur : le pont de dev ouvre une fenêtre de choix Windows (tkinter). Pas de délai :
    // l'utilisateur peut prendre son temps.
    const r = await this.client.appeler<{ chemin: string | null }>("choisir_dossier", { titre }, {}, 0);
    return r.chemin;
  }

  async choisirFichiers(titre = "Choisir des fichiers", filtre: FiltreFichiers = "tous") {
    if (DANS_TAURI) {
      const { open } = await import("@tauri-apps/plugin-dialog");
      const choix = await open({ directory: false, multiple: true, title: titre, filters: FILTRES_TAURI[filtre] });
      return Array.isArray(choix) ? choix : choix ? [choix] : [];
    }
    const r = await this.client.appeler<{ chemins: string[] }>("choisir_fichiers", { titre, filtre }, {}, 0);
    return r.chemins;
  }

  preparer(commande: "conversion_mp4", args: { source: Source }) {
    return this.client.appeler<Preparation>("preparer", { commande, args });
  }

  convertirMp4(source: Source, ev: EcouteursTache): TacheEnCours<ResultatConversion> {
    const ecouteurs: Ecouteurs = { onProgress: ev.onProgress, onLog: ev.onLog };
    // Tâche longue : pas de délai (une conversion peut durer des heures), mais un garde-fou
    // (« surveiller ») qui vérifie par « etat » que le moteur y travaille encore.
    const { id, resultat } = this.client.requete<ResultatConversion>("conversion_mp4", { source }, ecouteurs, 0, true);
    return {
      resultat,
      annuler: async () => {
        await this.client.annuler(id);
      },
    };
  }

  surLogLibre(f: ((ev: EvLog) => void) | null) {
    this.client.onLogLibre = f;
  }
  surDeconnexion(f: ((raison: string) => void) | null) {
    this.client.onDeconnexion = f;
  }
  fermer() {
    return this.client.fermer();
  }
}
