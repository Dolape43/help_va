/**
 * api.ts — ce que les ÉCRANS ont le droit de demander au moteur, avec des types.
 *
 * Les écrans ne voient jamais de JSON ni d'id : ils appellent `moteur.traiter(...)`,
 * `moteur.rangerAnalyser(...)`… Deux implémentations du même contrat `Moteur` :
 *   - MoteurReel         (ce fichier)       : le vrai moteur Python (pont de dev ou sidecar Tauri) ;
 *   - MoteurIndisponible (indisponible.ts)  : aucun moteur joignable → chaque action échoue
 *                                              avec un message clair (jamais de faux résultat).
 * Les formes des réponses suivent engine/README.md, section 3 (et engine/commandes.py).
 */
import { DANS_TAURI } from "../plateforme";
import type { ClientMoteur, Ecouteurs } from "./client";
import type { EvLog, EvProgress } from "./protocole";

/* ---------- Types communs ---------- */

export type Source = { type: "dossier"; chemin: string } | { type: "fichiers"; chemins: string[] };

/** Les 4 types de posts, dans l'ordre d'affichage (agent/ranger.py > TYPES). */
export type TypePost = "reel" | "story" | "story_cta" | "carousel";
export const TYPES_POST: TypePost[] = ["reel", "story", "story_cta", "carousel"];

export type TypeRangerInfo = {
  type: TypePost;
  libelle: string; // « Réels »
  libelle_creneau: string; // « Réel »
  nom_dossier: string; // « reel »
  est_video: boolean;
  medias_par_creneau: number; // 3 pour un carrousel
};

export type InfoMoteur = {
  nom: string;
  version: string;
  protocole: number;
  python: string;
  frozen: boolean;
  dossier_donnees: string;
  dossier_sortie: string;
  types_ranger?: TypeRangerInfo[];
  images_par_carrousel?: number;
  /** pont de dev lancé avec --sans-licence : la licence n'est pas exigée (dev seulement) */
  licence_contournee_dev?: boolean;
};

/* ---------- Licence ---------- */

export type TypeLicence = "vie" | "mois" | "an" | "essai";

export type StatutLicence = {
  ok: boolean;
  raison: "actif" | "pas_active" | "invalide" | "mauvais_pc" | "expire" | "pas_internet" | "revoquee" | "suspendu" | string;
  type: TypeLicence | null;
  /** "AAAA-MM-JJ" */
  expire_le: string | null;
  debut_le?: string | null;
  jours_restants: number | null;
  nom?: string | null;
  /** vrai = le serveur n'a pas pu être joint, mais on tolère (moins de 3 jours sans confirmation) */
  hors_ligne?: boolean;
  /** identifiant de ce PC (« XXXX-XXXX-XXXX-XXXX »), renvoyé par licence_statut */
  empreinte?: string;
};

/** Réponse de licence_activer. Un refus (code faux, pas de réseau) n'est PAS une erreur : ok = false + message. */
export type ResultatActivation = { ok: boolean; message: string; statut: StatutLicence | null };

/* ---------- Paramètres ---------- */

export type VueParametres = {
  parametres: Record<string, unknown>;
  dossier_sortie: string;
  dossier_sortie_defaut: string;
  personnalise: boolean;
};

/* ---------- Traitements : MP4, images, métadonnées ---------- */

export type CommandeTraitement = "conversion_mp4" | "conversion_images" | "metadonnees";

export type ArgsTraitement = {
  source: Source;
  /** conversion_images : "jpg" (défaut) ou "png" */
  format?: "jpg" | "png";
  /** metadonnees : renommer 1, 2, 3… (défaut true, « recommandé ») */
  renommer?: boolean;
  /** le chemin EXACT confirmé dans « Remplacer ? » (champ `sortie` de preparer), jamais true */
  remplacer?: string;
};

export type Preparation = {
  commande: string;
  /** où ira le résultat */
  sortie: string;
  existe: boolean;
  /** vrai = ce dossier existe et sera SUPPRIMÉ puis recréé : il faut demander « Remplacer ? » */
  remplacement: boolean;
  nb_medias: number;
  /** conversion_mp4 : nombre de .mp4 déjà présents qui seront écrasés */
  deja_presents?: number;
};

/** Le texte de fin de l'ancienne app (même texte que la popup de _fin_traitement). */
export type Bilan = { titre: string; message: string; erreur: boolean };

export type ResultatTraitement = {
  traites: number;
  echecs: string[];
  arrete: boolean;
  dossiers: number;
  sortie: string;
  duree_s: number;
  bilan: Bilan;
  /** conversion_images */
  format?: "jpg" | "png";
};

/** Ancien nom, gardé pour le module MP4. */
export type ResultatConversion = ResultatTraitement;

/* ---------- Calendrier ---------- */

export type Creneau = { heure: string; type: TypePost };
/** semaine → jour → créneaux. Ex. { "semaine-01": { "jour-1": [{ heure: "12h15", type: "carousel" }] } } */
export type Calendrier = Record<string, Record<string, Creneau[]>>;

export type VueCalendrier = {
  calendrier: Calendrier;
  semaines: number;
  /** nombre de créneaux par type */
  compte: Record<TypePost, number>;
  creneaux: number;
  /** calendrier modifié par l'utilisateur (sinon : celui d'origine) */
  personnalise?: boolean;
  /** calendrier_sauver : « Enregistré (3 semaine(s)). Appliqué au prochain rangement. » */
  message?: string;
};

/* ---------- Ranger les médias ---------- */

export type SourcesRanger = Partial<Record<TypePost, string>>;

export type AnalyseTypeRanger = {
  libelle: string;
  est_video: boolean;
  unite: string; // « vidéo(s) » / « image(s) »
  creneaux: number;
  medias_par_creneau: number;
  requis: number;
  actif: boolean;
  dossier: string | null;
  dossier_valide: boolean;
  trouves: number;
  ignores: number;
  manque: number;
};

export type AnalyseRanger = {
  types: Record<TypePost, AnalyseTypeRanger>;
  actifs: TypePost[];
  sortie: string;
  existe: boolean;
  /** types cochés sans dossier valide */
  manquants: TypePost[];
  /** types dont le dossier est DANS la sortie (qui va être remplacée) */
  source_dans_sortie: TypePost[];
  /** paires de types d'images qui utilisent le même dossier */
  doublons: [TypePost, TypePost][];
  incomplet: boolean;
  calendrier_erreur: string | null;
  pret: boolean;
  message_confirmation: string;
};

export type ArgsRanger = {
  sources: SourcesRanger;
  /** types à ranger (sinon : ceux cochés dans les paramètres) */
  types?: TypePost[];
  aleatoire?: boolean;
  remplacer?: string;
};

export type ResultatRanger = {
  arrete: boolean;
  creneaux: number;
  types: TypePost[];
  besoins?: Partial<Record<TypePost, number>>;
  fournis?: Partial<Record<TypePost, number>>;
  places?: Partial<Record<TypePost, number>>;
  manques?: Partial<Record<TypePost, number>>;
  surplus?: Partial<Record<TypePost, number>>;
  sortie: string;
  duree_s: number;
  bilan: Bilan;
};

/* ---------- Fenêtres de choix ---------- */

export type FiltreFichiers = "videos" | "images" | "medias" | "tous";

/** Une tâche longue lancée : son résultat, et de quoi l'annuler. */
export type TacheEnCours<T> = { resultat: Promise<T>; annuler: () => Promise<void> };

export type EcouteursTache = {
  onProgress: (ev: EvProgress) => void;
  onLog: (ev: EvLog) => void;
};

/** Le contrat commun (vrai moteur ET moteur indisponible). */
export interface Moteur {
  /** "reel" = vrai moteur Python ; "indisponible" = aucun moteur (toutes les actions échouent). */
  readonly mode: "reel" | "indisponible";
  /** « pont de dev », « sidecar » ou « aucun » */
  readonly transport: string;
  info(): Promise<InfoMoteur>;

  licenceStatut(): Promise<StatutLicence>;
  /** Envoie le code d'activation au serveur ; la licence obtenue est enregistrée sur ce PC. */
  licenceActiver(code: string): Promise<ResultatActivation>;
  /** Supprime la licence de ce PC (retour à l'écran d'activation). */
  licenceResilier(): Promise<{ ok: boolean }>;

  parametresLire(): Promise<VueParametres>;
  parametresEcrire(valeurs: Record<string, unknown>): Promise<VueParametres>;
  /** Le dossier de sortie effectif (créé s'il n'existe pas, comme l'ancienne app). */
  dossierSortie(): Promise<{ chemin: string; defaut: string; personnalise: boolean }>;
  ouvrirDossier(chemin: string): Promise<void>;
  choisirDossier(titre?: string): Promise<string | null>;
  choisirFichiers(titre?: string, filtre?: FiltreFichiers): Promise<string[]>;

  /** AVANT un traitement : où ira le résultat, combien de médias, faut-il demander « Remplacer ? ». */
  preparer(commande: CommandeTraitement, args: ArgsTraitement): Promise<Preparation>;
  /** Lance un traitement (tâche longue, annulable). */
  traiter(commande: CommandeTraitement, args: ArgsTraitement, ev: EcouteursTache): TacheEnCours<ResultatTraitement>;

  calendrierLire(): Promise<VueCalendrier>;
  calendrierDefaut(): Promise<VueCalendrier>;
  calendrierSauver(calendrier: Calendrier): Promise<VueCalendrier>;

  /** Tout ce qu'il faut savoir avant de ranger (dossiers trouvés, manques, « Remplacer ? »). */
  rangerAnalyser(args: Omit<ArgsRanger, "aleatoire" | "remplacer">): Promise<AnalyseRanger>;
  rangerLancer(args: ArgsRanger, ev: EcouteursTache): TacheEnCours<ResultatRanger>;

  /** Journal sans propriétaire (plantage dur du moteur…). */
  surLogLibre(f: ((ev: EvLog) => void) | null): void;
  /** Appelé si le moteur se déconnecte. */
  surDeconnexion(f: ((raison: string) => void) | null): void;
  fermer(): Promise<void>;
}

/* ---------- Extensions des fenêtres de choix de Tauri ----------
   EXACTEMENT celles que le moteur traite (sinon un fichier choisi serait ignoré sans rien dire) :
   vidéos MP4 = agent/conversion.py > EXT_VIDEOS ; images et médias = agent/unicite.py > EXT_IMAGES / EXT_VIDEOS.
   Mêmes listes que les fenêtres du pont de dev (engine/dev_bridge.py). */
const EXT_VIDEOS_MP4 = ["mov", "mp4", "m4v", "avi", "mkv", "webm", "mpg", "mpeg", "wmv", "flv"];
const EXT_IMAGES = ["jpg", "jpeg", "png", "webp", "heic", "heif"];
const EXT_VIDEOS_UNICITE = ["mp4", "mov", "m4v", "avi", "mkv"];
const FILTRES_TAURI: Record<FiltreFichiers, { name: string; extensions: string[] }[]> = {
  videos: [{ name: "Vidéos", extensions: EXT_VIDEOS_MP4 }],
  images: [{ name: "Images", extensions: EXT_IMAGES }],
  medias: [{ name: "Images et vidéos", extensions: [...EXT_IMAGES, ...EXT_VIDEOS_UNICITE] }],
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
    // Hors-ligne, la vérification peut durer ~40 s (serveur + vraie date) : délai large.
    return this.client.appeler<StatutLicence>("licence_statut", {}, {}, 90_000);
  }
  licenceActiver(code: string) {
    return this.client.appeler<ResultatActivation>("licence_activer", { code }, {}, 60_000);
  }
  licenceResilier() {
    return this.client.appeler<{ ok: boolean }>("licence_resilier");
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

  preparer(commande: CommandeTraitement, args: ArgsTraitement) {
    // Un gros dossier sur un disque réseau peut être long à parcourir : délai généreux.
    return this.client.appeler<Preparation>("preparer", { commande, args }, {}, 120_000);
  }

  traiter(commande: CommandeTraitement, args: ArgsTraitement, ev: EcouteursTache) {
    return this.longue<ResultatTraitement>(commande, args, ev);
  }

  calendrierLire() {
    return this.client.appeler<VueCalendrier>("calendrier_lire");
  }
  calendrierDefaut() {
    return this.client.appeler<VueCalendrier>("calendrier_defaut");
  }
  calendrierSauver(calendrier: Calendrier) {
    return this.client.appeler<VueCalendrier>("calendrier_sauver", { calendrier });
  }

  rangerAnalyser(args: Omit<ArgsRanger, "aleatoire" | "remplacer">) {
    // Compte les fichiers de chaque dossier : peut prendre un moment sur un disque lent.
    return this.client.appeler<AnalyseRanger>("ranger_analyser", args, {}, 120_000);
  }
  rangerLancer(args: ArgsRanger, ev: EcouteursTache) {
    return this.longue<ResultatRanger>("ranger_lancer", args, ev);
  }

  /**
   * Tâche longue : pas de délai (une conversion peut durer des heures), mais un garde-fou
   * (« surveiller ») qui vérifie par « etat » que le moteur y travaille encore.
   */
  private longue<T>(cmd: string, args: object, ev: EcouteursTache): TacheEnCours<T> {
    const ecouteurs: Ecouteurs = { onProgress: ev.onProgress, onLog: ev.onLog };
    const { id, resultat } = this.client.requete<T>(cmd, args as Record<string, unknown>, ecouteurs, 0, true);
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
