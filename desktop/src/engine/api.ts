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
import { ErreurMoteur, type EvLog, type EvProgress } from "./protocole";

/**
 * Événement de la fenêtre, à la fin de chaque traitement. useLicence l'écoute :
 *   - detail.refus = vrai : le moteur a refusé le traitement à cause de la licence (résiliée,
 *     expirée, hors-ligne depuis plus de 6 h, essai gratuit épuisé) -> on revérifie tout de suite,
 *     l'écran de licence remplace alors l'app ;
 *   - offre gratuite : on revérifie aussi, pour mettre à jour les médias restants.
 */
export const EV_TRAITEMENT_FINI = "helpva:traitement-fini";
const CODES_REFUS = ["LICENCE_REFUSEE", "ESSAI_INSUFFISANT", "ESSAI_HORS_LIGNE"];

function signalerFin(refus: boolean) {
  window.dispatchEvent(new CustomEvent(EV_TRAITEMENT_FINI, { detail: { refus } }));
}

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

/** "gratuit" = offre gratuite (pas de licence, un nombre de médias offerts) ; "essai" = licence d'essai par code. */
export type TypeLicence = "vie" | "mois" | "an" | "essai" | "gratuit";

/** Offre gratuite : compté par le serveur, par PC. */
export type EssaiGratuit = { quota: number; utilises: number; restant: number };

export type StatutLicence = {
  ok: boolean;
  raison: "actif" | "pas_active" | "invalide" | "mauvais_pc" | "expire" | "pas_internet" | "revoquee" | "suspendu" | "essai_gratuit" | "essai_fini" | string;
  type: TypeLicence | null;
  /** "AAAA-MM-JJ" */
  expire_le: string | null;
  debut_le?: string | null;
  jours_restants: number | null;
  nom?: string | null;
  /** vrai = le serveur n'a pas pu être joint, mais on tolère (moins de 6 heures sans confirmation) */
  hors_ligne?: boolean;
  /** identifiant de ce PC (« XXXX-XXXX-XXXX-XXXX »), renvoyé par licence_statut */
  empreinte?: string;
  /** offre gratuite (type "gratuit") : médias restants ; null = serveur injoignable */
  essai?: EssaiGratuit | null;
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

/**
 * Les réglages « Choix par défaut » et « Fin de traitement » (clés de parametres.json,
 * vérifiées par parametres_ecrire). Absents du fichier = valeurs de PREFERENCES_DEFAUT.
 */
export type Preferences = {
  format_images: "jpg" | "png";
  renommer_images: boolean;
  renommer_mp4: boolean;
  renommer_metadonnees: boolean;
  ranger_aleatoire: boolean;
  fin_ouvrir_dossier: boolean;
  fin_notification: boolean;
};

/** Mêmes défauts que le moteur (agent/parametres.py). */
export const PREFERENCES_DEFAUT: Preferences = {
  format_images: "jpg",
  renommer_images: false,
  renommer_mp4: false,
  renommer_metadonnees: true,
  ranger_aleatoire: true,
  fin_ouvrir_dossier: false,
  fin_notification: true,
};

/** Lit les préférences dans les paramètres bruts ; une valeur absente ou d'un mauvais type → défaut. */
export function preferencesDepuis(p: Record<string, unknown> | null): Preferences {
  const d = PREFERENCES_DEFAUT;
  const bool = (cle: keyof Preferences, defaut: boolean) => (typeof p?.[cle] === "boolean" ? (p[cle] as boolean) : defaut);
  return {
    format_images: p?.format_images === "png" ? "png" : p?.format_images === "jpg" ? "jpg" : d.format_images,
    renommer_images: bool("renommer_images", d.renommer_images),
    renommer_mp4: bool("renommer_mp4", d.renommer_mp4),
    renommer_metadonnees: bool("renommer_metadonnees", d.renommer_metadonnees),
    ranger_aleatoire: bool("ranger_aleatoire", d.ranger_aleatoire),
    fin_ouvrir_dossier: bool("fin_ouvrir_dossier", d.fin_ouvrir_dossier),
    fin_notification: bool("fin_notification", d.fin_notification),
  };
}

/* ---------- Activité (compteur des médias traités sur ce PC) ---------- */

/** images = converties ; videos = converties en MP4 ; metadonnees = passées dans Métadonnées (chaque média compté une fois). */
export type Compteurs = { images: number; videos: number; metadonnees: number; total: number };

/** Réponse de activite_lire. */
export type ResumeActivite = {
  aujourd_hui: Compteurs;
  /** 7 derniers jours, aujourd'hui compris */
  semaine: Compteurs;
  /** 30 derniers jours */
  mois: Compteurs;
  total: Compteurs;
  /** premier jour compté (« AAAA-MM-JJ »), null si rien encore */
  depuis: string | null;
  /** vrai = une licence existe : les compteurs sont envoyés à l'agence */
  partage: boolean;
};

/* ---------- Traitements : MP4, images, métadonnées ---------- */

export type CommandeTraitement = "conversion_mp4" | "conversion_images" | "metadonnees";

export type ArgsTraitement = {
  source: Source;
  /** conversion_images : "jpg" (défaut) ou "png" */
  format?: "jpg" | "png";
  /** renommer 1, 2, 3… (metadonnees : défaut true, « recommandé » ; conversions : défaut false) */
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

/** Nombre maximal de comptes (agent/comptes.py > MAX_COMPTES ; le moteur le renvoie aussi dans `max`). */
export const MAX_COMPTES = 50;

/**
 * Un compte (réseau social) du Ranger : SES dossiers sources et SON calendrier (comptes_ranger.json).
 * Les types cochés (paramètre ranger_types) restent communs à tous les comptes.
 */
export type CompteRanger = {
  /** stable, créé par l'interface (« c1 », « c7 ») ; le moteur en crée un s'il est absent ou vide */
  id: string;
  /** « Compte 1 », « @marie »… : devient le nom du sous-dossier du compte dans « ranger » */
  nom: string;
  /** {type: dossier absolu} */
  sources: SourcesRanger;
  /** null = le calendrier d'origine */
  calendrier: Calendrier | null;
};

/** Un compte tel que le moteur le renvoie : avec le résumé de son calendrier EFFECTIF. */
export type VueCompte = CompteRanger & { vue: VueCalendrier };

/** Réponse de comptes_lire et comptes_sauver. */
export type VueComptes = { comptes: VueCompte[]; max: number; message?: string };

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
  /** dossier vide : ses sous-dossiers qui contiennent des médias (le bon dossier est sans doute l'un d'eux) */
  sous_dossiers?: string[];
  /** Carrousels : nombre de carrousels déjà préparés (un sous-dossier = un carrousel), sinon null */
  carrousels?: number | null;
};

/** Le résultat de « Préparer les carrousels » (carrousels_preparer). */
export type CarrouselsPrepares = {
  sortie: string;
  carrousels: number;
  images: number;
  /** images restées hors carrousel (moins de 3 à la fin), non copiées */
  en_trop: number;
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
  /** le détail de chaque compte (un seul en ancien mode) */
  comptes: AnalyseCompteRanger[];
  /** dossiers utilisés par au moins 2 comptes : mêmes médias rangés plusieurs fois (avertissement) */
  partages: PartageRanger[];
};

/** L'analyse d'UN compte (mêmes champs que la tête de AnalyseRanger, pour ce compte seulement). */
export type AnalyseCompteRanger = {
  id: string;
  nom: string;
  /** …\ranger\<nom>, ou …\ranger s'il n'y a qu'un seul compte */
  sortie: string;
  types: Record<TypePost, AnalyseTypeRanger>;
  actifs: TypePost[];
  manquants: TypePost[];
  source_dans_sortie: TypePost[];
  /** paires de types d'images de CE compte qui utilisent le même dossier */
  doublons: [TypePost, TypePost][];
  incomplet: boolean;
  calendrier_erreur: string | null;
  /** créneaux à remplir (types actifs de ce compte) */
  creneaux: number;
};

export type PartageRanger = { dossier: string; comptes: { id: string; nom: string; type: TypePost }[] };

export type ArgsRanger = {
  /** mode multi-comptes : sources et calendriers pris ICI (pas dans le fichier) */
  comptes?: CompteRanger[];
  /** ancien mode (un seul compte implicite, calendrier global) */
  sources?: SourcesRanger;
  /** types à ranger (sinon : ceux cochés dans les paramètres) */
  types?: TypePost[];
  aleatoire?: boolean;
  /** médias manquants : réutiliser ceux qui sont là pour remplir TOUS les créneaux (choix de l'utilisateur) */
  completer?: boolean;
  remplacer?: string;
};

/** Le bilan d'UN compte après ranger_lancer. */
export type ResultatCompteRanger = {
  id: string;
  nom: string;
  sortie: string;
  types: TypePost[];
  besoins?: Partial<Record<TypePost, number>>;
  fournis?: Partial<Record<TypePost, number>>;
  places?: Partial<Record<TypePost, number>>;
  manques?: Partial<Record<TypePost, number>>;
  incomplets?: Partial<Record<TypePost, number>>;
  surplus?: Partial<Record<TypePost, number>>;
  creneaux: number;
  arrete: boolean;
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
  /** médias placés une 2e fois (ou plus) pour compléter */
  reutilises?: Partial<Record<TypePost, number>>;
  sortie: string;
  duree_s: number;
  bilan: Bilan;
  /** mode multi-comptes : le bilan de chaque compte (les champs de tête sont les sommes) */
  comptes?: ResultatCompteRanger[];
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
  /** le dossier existe-t-il ET contient-il quelque chose ? (sinon « Ouvrir le dossier du résultat » est grisé) */
  dossierExiste(chemin: string): Promise<boolean>;
  choisirDossier(titre?: string): Promise<string | null>;
  choisirFichiers(titre?: string, filtre?: FiltreFichiers): Promise<string[]>;

  /** Les compteurs d'activité de ce PC (aujourd'hui, 7 jours, 30 jours, total). */
  activiteLire(): Promise<ResumeActivite>;

  /** AVANT un traitement : où ira le résultat, combien de médias, faut-il demander « Remplacer ? ». */
  preparer(commande: CommandeTraitement, args: ArgsTraitement): Promise<Preparation>;
  /** Lance un traitement (tâche longue, annulable). */
  traiter(commande: CommandeTraitement, args: ArgsTraitement, ev: EcouteursTache): TacheEnCours<ResultatTraitement>;

  calendrierLire(): Promise<VueCalendrier>;
  calendrierDefaut(): Promise<VueCalendrier>;
  calendrierSauver(calendrier: Calendrier): Promise<VueCalendrier>;

  /** Les comptes du Ranger (dossiers et calendrier de chacun). */
  comptesLire(): Promise<VueComptes>;
  /** Enregistre la liste COMPLÈTE des comptes (tout est vérifié avant d'écrire). */
  comptesSauver(comptes: CompteRanger[]): Promise<VueComptes>;

  /** Tout ce qu'il faut savoir avant de ranger (dossiers trouvés, manques, « Remplacer ? »). */
  rangerAnalyser(args: Omit<ArgsRanger, "aleatoire" | "remplacer">): Promise<AnalyseRanger>;
  rangerLancer(args: ArgsRanger, ev: EcouteursTache): TacheEnCours<ResultatRanger>;
  /** Range les images d'un dossier en carrousel-1, carrousel-2… dans un nouveau dossier. */
  carrouselsPreparer(source: string): Promise<CarrouselsPrepares>;

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
    // Dans Tauri, c'est la fenêtre HelpVA qui ouvre (commande Rust « ouvrir_dossier », qui ne prend
    // elle aussi qu'un dossier existant) : ouvert par le moteur, en arrière-plan, l'Explorateur
    // apparaissait DERRIÈRE HelpVA (voir src-tauri/src/lib.rs).
    if (DANS_TAURI) {
      const { invoke } = await import("@tauri-apps/api/core");
      await invoke("ouvrir_dossier", { chemin });
      return;
    }
    await this.client.appeler("ouvrir_dans_explorateur", { chemin });
  }
  async dossierExiste(chemin: string) {
    const r = await this.client.appeler<{ existe: boolean; plein?: boolean }>("dossier_existe", { chemin });
    return r.existe && r.plein === true;
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

  activiteLire() {
    return this.client.appeler<ResumeActivite>("activite_lire");
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

  comptesLire() {
    return this.client.appeler<VueComptes>("comptes_lire");
  }
  comptesSauver(comptes: CompteRanger[]) {
    return this.client.appeler<VueComptes>("comptes_sauver", { comptes });
  }

  rangerAnalyser(args: Omit<ArgsRanger, "aleatoire" | "remplacer">) {
    // Compte les fichiers de chaque dossier : peut prendre un moment sur un disque lent.
    return this.client.appeler<AnalyseRanger>("ranger_analyser", args, {}, 120_000);
  }
  rangerLancer(args: ArgsRanger, ev: EcouteursTache) {
    return this.longue<ResultatRanger>("ranger_lancer", args, ev);
  }
  carrouselsPreparer(source: string) {
    // Copie des images : jusqu'à quelques minutes pour des milliers de photos sur un disque lent.
    return this.client.appeler<CarrouselsPrepares>("carrousels_preparer", { source }, {}, 600_000);
  }

  /**
   * Tâche longue : pas de délai (une conversion peut durer des heures), mais un garde-fou
   * (« surveiller ») qui vérifie par « etat » que le moteur y travaille encore.
   */
  private longue<T>(cmd: string, args: object, ev: EcouteursTache): TacheEnCours<T> {
    const ecouteurs: Ecouteurs = { onProgress: ev.onProgress, onLog: ev.onLog };
    const { id, resultat } = this.client.requete<T>(cmd, args as Record<string, unknown>, ecouteurs, 0, true);
    return {
      resultat: resultat.then(
        (r) => {
          signalerFin(false);
          return r;
        },
        (e: unknown) => {
          signalerFin(e instanceof ErreurMoteur && CODES_REFUS.includes(e.code));
          throw e;
        },
      ),
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
