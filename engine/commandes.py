"""
Les commandes du moteur HelpVA.

Chaque commande est une fonction  `nom(ctx, args) -> dict`  enregistrée avec
@commande("nom", nature). Le dict renvoyé devient l'événement « result ».
Pour refuser proprement, on lève ErreurCommande(code, message, details) :
elle devient un événement « error » (voir README.md, codes d'erreur).

Règle d'or : LE MOTEUR VÉRIFIE TOUT. On ne fait jamais confiance aux
arguments reçus de l'interface (chemin absent, source dans la sortie…),
surtout avant un shutil.rmtree.

Les comportements reprennent EXACTEMENT ceux de l'ancienne app (app_ctk.py) :
mêmes dossiers de sortie, mêmes messages de fin, mêmes remplacements.

Les modules lourds d'agent/ (PIL, numpy, cryptography…) sont importés DANS
les fonctions : le moteur démarre vite et ne les charge qu'au premier besoin.
"""

import copy
import functools
import inspect
import json
import os
import shutil
import sys
import threading
import time
import traceback

LONGUE = "L"    # une seule à la fois, annulable, dans un fil dédié
RAPIDE = "R"    # en parallèle (4 max), même pendant une tâche longue
RESEAU = "N"    # comme RAPIDE, mais dans un AUTRE groupe de fils : une vérification de
                # licence hors-ligne (jusqu'à ~40 s) ne bloque jamais preparer, parametres…

COMMANDES = {}  # nom -> (fonction, nature)

# Commandes « critiques » : les couper en plein milieu ferait perdre quelque chose
# (code d'activation consommé sans licence.key écrit, paramètres à moitié enregistrés…).
# À l'arrêt, le moteur les attend plus longtemps que les autres (voir Moteur.arreter).
CRITIQUES = set()

# Lire -> modifier -> écrire parametres.json / calendrier_utilisateur.json :
# deux requêtes rapides en parallèle ne doivent pas s'écraser. Les LECTURES du moteur
# passent aussi par ce verrou. RLock (verrou « réentrant ») : un fil qui le tient déjà
# peut le reprendre sans se bloquer lui-même (ex. parametres_ecrire -> _sortie_perso).
VERROU_DONNEES = threading.RLock()


class ErreurCommande(Exception):
    """La commande n'a pas pu s'exécuter (devient un événement « error »)."""

    def __init__(self, code: str, message: str, details=None):
        super().__init__(message)
        self.code = code
        self.message = message
        self.details = details


def commande(nom: str, nature: str = RAPIDE, critique: bool = False):
    def enregistrer(fonction):
        COMMANDES[nom] = (fonction, nature)
        if critique:
            CRITIQUES.add(nom)
        return fonction
    return enregistrer


# ═══════════════════════════════════════════════════════════════════════════
#  Progression structurée (sans modifier agent/)
# ═══════════════════════════════════════════════════════════════════════════
class TexteProgression(str):
    """Un texte de progression (c'est une vraie str) qui porte aussi .details.

    agent/ construit ses textes avec progression.texte(...). On enveloppe cette
    fonction ICI, dans le moteur seulement : le texte reste identique (l'ancienne
    app n'est pas touchée), et l'interface reçoit en plus les infos structurées
    avec les noms COMPLETS (c'est elle qui raccourcit, en CSS). Ça évite de
    relire le texte avec une regex, qui casserait au moindre changement de libellé.
    """
    details = None


def _installer_details_progression():
    from agent import progression
    if getattr(progression.texte, "_helpva_details", False):
        return
    original = progression.texte
    signature = inspect.signature(original)

    # On transmet TOUS les arguments tels quels (*a, **kw) : si agent/ ajoute un jour un
    # paramètre à progression.texte, l'enveloppe ne casse pas (sinon TypeError, et dans
    # conversion.annoncer l'erreur est avalée : toute la progression disparaîtrait sans bruit).
    # Les champs sont ensuite relus PAR LEUR NOM grâce à la signature de l'original.
    @functools.wraps(original)
    def texte(*a, **kw):
        t = TexteProgression(original(*a, **kw))
        try:
            lies = signature.bind(*a, **kw)
            lies.apply_defaults()
            v = lies.arguments
            grp = None
            if v.get("dossier_n") and (v["dossier_n"] > 1 or v.get("toujours")):
                grp = {"mot": v.get("groupe"), "index": v.get("dossier_i"),
                       "total": v["dossier_n"], "nom": v.get("nom_dossier")}
            pct = v.get("pct")
            t.details = {"groupe": grp,
                         "element": {"mot": v.get("quoi"), "index": v.get("k"),
                                     "total": v.get("total"), "nom": v.get("fichier"),
                                     "pct": None if pct is None else int(pct)}}
        except Exception:
            t.details = None        # le texte reste juste : seuls les détails manquent
        return t

    texte._helpva_details = True
    texte._helpva_original = original
    progression.texte = texte


_installer_details_progression()


# ═══════════════════════════════════════════════════════════════════════════
#  Vérification des arguments
# ═══════════════════════════════════════════════════════════════════════════
def _invalide(champ: str, message: str):
    return ErreurCommande("ARGUMENTS_INVALIDES", message, {"champ": champ})


def _texte(args: dict, nom: str, obligatoire: bool = True, defaut: str = None) -> str:
    val = args.get(nom, defaut)
    if val is None and not obligatoire:
        return defaut
    if not isinstance(val, str) or (obligatoire and not val.strip()):
        raise _invalide(nom, f"« {nom} » doit être un texte non vide.")
    return val


def _booleen(args: dict, nom: str, defaut: bool = False) -> bool:
    val = args.get(nom, defaut)
    if not isinstance(val, bool):
        raise _invalide(nom, f"« {nom} » doit valoir true ou false.")
    return val


def est_absolu(chemin: str) -> bool:
    r"""Chemin COMPLET. Sous Windows : avec un lecteur (C:\…) ou un partage (\\serveur\…).

    Pourquoi pas juste os.path.isabs ? De Python 3.10 à 3.12, isabs("\Users\x") vaut
    True alors que ce chemin dépend du lecteur COURANT ; Python 3.13+ le refuse. On exige
    donc un lecteur : même comportement avant et après le passage à Python 3.14."""
    if not isinstance(chemin, str) or not os.path.isabs(chemin):
        return False
    return sys.platform != "win32" or bool(os.path.splitdrive(chemin)[0])


# Sans « LongPathsEnabled » (réglage Windows désactivé par défaut), Windows n'ouvre pas
# un dossier de 248 caractères ou plus, ni un fichier de 260 ou plus.
_LONGUEUR_MAX = {"dossier": 248, "fichier": 260}


def _trop_long(chemin: str, sorte: str) -> bool:
    return (sys.platform == "win32" and not chemin.startswith("\\\\?\\")
            and len(chemin) >= _LONGUEUR_MAX[sorte])


def _erreur_trop_long(chemins: list, sorte: str):
    return ErreurCommande(
        "CHEMIN_TROP_LONG",
        f"Chemin trop long pour Windows (plus de {_LONGUEUR_MAX[sorte] - 1} caractères) : "
        "raccourcissez les noms de dossiers, ou rapprochez le dossier de la racine du disque "
        "(par ex. C:\\Vidéos).\n" + chemins[0],
        {"chemins": chemins})


def _chemin_absolu(val, champ: str) -> str:
    if not isinstance(val, str) or not val.strip():
        raise _invalide(champ, f"« {champ} » doit être un chemin non vide.")
    if not est_absolu(val):
        raise _invalide(champ, f"« {champ} » doit être un chemin ABSOLU (avec le lecteur) : {val}")
    return val


def _source(args: dict):
    """Lit args["source"] -> (dossier, None) ou (None, [fichiers]).

    Source = {"type":"dossier","chemin":str} | {"type":"fichiers","chemins":[str]}"""
    src = args.get("source")
    if not isinstance(src, dict):
        raise _invalide("source", "« source » doit être un objet {type, chemin|chemins}.")
    typ = src.get("type")
    if typ == "dossier":
        dossier = _chemin_absolu(src.get("chemin"), "source.chemin")
        if not os.path.isdir(dossier):
            if _trop_long(dossier, "dossier"):
                raise _erreur_trop_long([dossier], "dossier")
            raise ErreurCommande("SOURCE_INTROUVABLE", f"Dossier introuvable : {dossier}",
                                 {"chemins": [dossier]})
        return dossier, None
    if typ == "fichiers":
        chemins = src.get("chemins")
        if not isinstance(chemins, list) or not chemins:
            raise _invalide("source.chemins", "« source.chemins » doit être une liste non vide.")
        fichiers = [_chemin_absolu(c, "source.chemins") for c in chemins]
        absents = [f for f in fichiers if not os.path.isfile(f)]
        longs = [f for f in absents if _trop_long(f, "fichier")]
        if longs:
            raise _erreur_trop_long(longs, "fichier")
        if absents:
            raise ErreurCommande("SOURCE_INTROUVABLE",
                                 f"{len(absents)} fichier(s) introuvable(s) : "
                                 + ", ".join(os.path.basename(a) for a in absents[:5]),
                                 {"chemins": absents})
        return None, fichiers
    raise _invalide("source.type", "« source.type » doit valoir « dossier » ou « fichiers ».")


def _a_extension(chemin: str, extensions) -> bool:
    return os.path.splitext(chemin)[1].lower() in extensions


def _compter_medias(dossier, fichiers, extensions) -> int:
    """Nombre de fichiers utiles (vérifié AVANT d'appeler agent/)."""
    if fichiers is not None:
        return sum(1 for f in fichiers if _a_extension(f, extensions))
    n = 0
    for _racine, _sous, noms in os.walk(dossier):
        n += sum(1 for f in noms if _a_extension(f, extensions))
    return n


def _norm(chemin: str) -> str:
    return os.path.normcase(os.path.realpath(os.path.abspath(chemin)))


def est_dans(chemin: str, parent: str) -> bool:
    """Vrai si `chemin` EST `parent` ou se trouve dedans (même via un raccourci de dossier)."""
    c, p = _norm(chemin), _norm(parent)
    return c == p or c.startswith(p.rstrip(os.sep) + os.sep)


def _verifier_pas_dans_sortie(dossier, fichiers, sortie, message: str):
    """Refuse une source située dans la sortie : le shutil.rmtree la détruirait,
    et ffmpeg écraserait la vidéo qu'il est en train de lire."""
    if dossier is not None:
        fautifs = [dossier] if est_dans(dossier, sortie) else []
    else:
        fautifs = [f for f in fichiers if est_dans(f, sortie)]
    if fautifs:
        raise ErreurCommande("SOURCE_DANS_SORTIE", message,
                             {"sortie": sortie, "chemins": fautifs})


# ═══════════════════════════════════════════════════════════════════════════
#  Dossier de sortie (même logique que App.dossier_sortie)
# ═══════════════════════════════════════════════════════════════════════════
def dossier_sortie_defaut() -> str:
    bureau = os.path.join(os.path.expanduser("~"), "Desktop")
    if not os.path.isdir(bureau):
        bureau = os.path.expanduser("~")
    return os.path.join(bureau, "HelpVA")


def _charger_parametres() -> dict:
    from agent import parametres
    with VERROU_DONNEES:
        return parametres.charger()


def _charger_calendrier() -> dict:
    from agent import calendrier
    with VERROU_DONNEES:
        return calendrier.charger_calendrier()


def _ecrire_json_atomique(chemin: str, donnees) -> None:
    """Écrit un fichier JSON SANS jamais laisser un fichier à moitié écrit.

    Pourquoi : open(…, "w") VIDE d'abord le fichier, puis le réécrit. Une lecture
    pendant ce court instant voit un JSON tronqué -> agent/ renvoie les valeurs par
    défaut -> le dossier de sortie (et le « Remplacer ») viserait un autre dossier.
    Ici on écrit dans un fichier .tmp, puis os.replace() l'échange d'un coup :
    un lecteur voit l'ancien OU le nouveau fichier, jamais un mélange.
    Même format que agent/ (indent=2, accents en clair) : l'ancienne app le relit."""
    tmp = f"{chemin}.{os.getpid()}.tmp"
    try:
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(donnees, f, indent=2, ensure_ascii=False)
            f.flush()
            os.fsync(f.fileno())
        for essai in range(10):
            try:
                os.replace(tmp, chemin)
                break
            except PermissionError:
                # Windows : le fichier est lu au même instant (ancienne app, antivirus) -> on réessaie.
                if essai == 9:
                    raise
                time.sleep(0.05)
    except BaseException:
        try:
            os.remove(tmp)
        except OSError:
            pass
        raise


def _sortie_perso() -> str:
    return str(_charger_parametres().get("dossier_sortie") or "").strip()


def dossier_sortie(creer: bool = True) -> str:
    """Dossier où les modules enregistrent. Personnalisable, par défaut Bureau\\HelpVA.

    Comme l'ancienne app : si le dossier personnalisé ne peut pas être créé
    (clé USB retirée…), on se rabat sur le dossier par défaut."""
    d = _sortie_perso() or dossier_sortie_defaut()
    if not creer:
        return d
    try:
        os.makedirs(d, exist_ok=True)
    except OSError:
        d = dossier_sortie_defaut()
        try:
            os.makedirs(d, exist_ok=True)
        except OSError as e:
            raise ErreurCommande("SORTIE_INACCESSIBLE",
                                 f"Impossible de créer le dossier de sortie : {d}\n{e}",
                                 {"sortie": d})
    return d


def _confirmation(args: dict):
    """args["remplacer"] = le chemin EXACT que l'utilisateur a vu dans « Remplacer ? ».

    Pourquoi un chemin et pas true ? Entre « preparer » et le lancement, la sortie peut
    changer (paramètre modifié, clé USB retirée -> repli sur le Bureau…). Avec un simple
    true, on supprimerait un AUTRE dossier que celui confirmé. Avec le chemin, le moteur
    ne supprime que si c'est exactement le même."""
    val = args.get("remplacer")
    if val is None or val is False:
        return None
    if isinstance(val, str) and val.strip():
        return val
    raise _invalide("remplacer", "« remplacer » doit être le chemin EXACT du dossier à remplacer "
                                 "(le champ « sortie » renvoyé par preparer), ou absent.")


def _remplacer_sortie(sortie: str, confirme) -> None:
    """La sortie existe déjà : on la supprime SEULEMENT si l'interface a confirmé CE chemin.

    (Dans l'ancienne app : messagebox « Remplacer ? » puis shutil.rmtree.)

    On RENOMME d'abord le dossier, puis on supprime la copie renommée. Pourquoi ?
    shutil.rmtree(…, ignore_errors=True) échoue EN SILENCE si un fichier est ouvert
    (visionneuse, aperçu de l'Explorateur, antivirus) : les anciens fichiers restaient
    mélangés aux nouveaux. Le renommage, lui, échoue d'un bloc SANS rien effacer :
    on prévient alors l'utilisateur avant de commencer."""
    if not os.path.exists(sortie):
        return
    if confirme is None:
        raise ErreurCommande("SORTIE_EXISTE",
                             f"Le dossier existe déjà et sera REMPLACÉ :\n{sortie}\n\nContinuer ?",
                             {"sortie": sortie})
    if _norm(confirme) != _norm(sortie):
        raise ErreurCommande("SORTIE_EXISTE",
                             "Le dossier de sortie a changé depuis votre confirmation. "
                             f"Ce dossier existe déjà et sera REMPLACÉ :\n{sortie}\n\nContinuer ?",
                             {"sortie": sortie, "confirme": confirme})
    horodatage = time.strftime("%Y%m%d-%H%M%S")
    ancien, n = f"{sortie}.ancien-{horodatage}", 1
    while os.path.exists(ancien):
        n += 1
        ancien = f"{sortie}.ancien-{horodatage}-{n}"
    try:
        os.replace(sortie, ancien)
    except OSError as e:
        raise ErreurCommande("SORTIE_VERROUILLEE",
                             "Impossible de remplacer ce dossier : un fichier y est encore ouvert "
                             "(visionneuse, Explorateur, antivirus…). Fermez-le puis réessayez.\n"
                             f"{sortie}\n\n{e}", {"sortie": sortie})
    if os.path.isdir(ancien):
        shutil.rmtree(ancien, ignore_errors=True)
    else:
        try:
            os.remove(ancien)
        except OSError:
            pass
    if os.path.exists(ancien):
        # Rare : un fichier s'est ouvert juste après le renommage. La NOUVELLE sortie reste
        # propre (l'ancien contenu est à côté, renommé) : on prévient seulement.
        print(f"⚠️ L'ancien dossier n'a pas pu être supprimé entièrement : {ancien}")


def _verifier_ffmpeg() -> None:
    try:
        import imageio_ffmpeg
        exe = imageio_ffmpeg.get_ffmpeg_exe()
        if not exe or not os.path.isfile(exe):
            raise FileNotFoundError(exe)
    except Exception as e:
        raise ErreurCommande("FFMPEG_INTROUVABLE",
                             f"ffmpeg est introuvable (imageio-ffmpeg absent ou cassé) : {e}")


def _echec(titre: str, e: Exception):
    """Exception d'agent/ : même trace que l'ancienne app, puis événement « error »."""
    print(f"\n[ERREUR] {e}")
    traceback.print_exc()
    return ErreurCommande("ERREUR_INTERNE", str(e) or e.__class__.__name__, {"titre": titre})


def bilan_fin(titre: str, res: dict, sortie: str, mot: str = "fichier(s)", nb_dossiers=None) -> dict:
    """Message de fin commun — copie fidèle de App._fin_traitement (app_ctk.py).

    Écrit les mêmes lignes dans le journal et renvoie le texte de la popup
    {titre, message, erreur} : l'interface l'affiche tel quel."""
    n = res.get("medias", res.get("images", 0))
    echecs = res.get("echecs") or []
    if res.get("arrete"):
        print(f"\n⛔ Arrêté. {n} {mot} déjà traité(s) → {sortie}")
        return {"titre": "Interrompu", "message": f"Opération arrêtée.\n{n} {mot} déjà traité(s).",
                "erreur": False}
    detail = f"\n\nRésultat :\n{sortie}"
    if nb_dossiers:
        detail = (f" dans {nb_dossiers} dossier(s) !\n\nMême arborescence que "
                  f"votre dossier, dans :\n{sortie}")
        msg = f"✅ {n} {mot} traité(s)" + detail
    else:
        msg = f"✅ {n} {mot} traité(s) !" + detail
    print(f"\n✅ {n} {mot} → {sortie}")
    if echecs:
        apercu = ", ".join(echecs[:5]) + ("…" if len(echecs) > 5 else "")
        print(f"⚠️ {len(echecs)} fichier(s) illisibles : {apercu}")
        msg += (f"\n\n⚠️ {len(echecs)} fichier(s) n'ont PAS pu être traités "
                f"(illisibles/corrompus) :\n{apercu}\n\nVoir le journal pour le détail.")
    return {"titre": titre, "message": msg, "erreur": bool(echecs)}


# ═══════════════════════════════════════════════════════════════════════════
#  Plans : ce qu'une tâche longue VA faire (partagé avec « preparer »)
# ═══════════════════════════════════════════════════════════════════════════
def _plan_conversion_mp4(args: dict) -> dict:
    from agent import conversion
    dossier, fichiers = _source(args)
    n = _compter_medias(dossier, fichiers, conversion.EXT_VIDEOS)
    if n == 0:
        raise ErreurCommande("SOURCE_VIDE", "Aucune vidéo trouvée dans ce dossier." if dossier
                             else "Aucune vidéo dans la sélection.")
    sortie = os.path.join(dossier_sortie(), "media (mp4)")
    _verifier_pas_dans_sortie(dossier, fichiers, sortie,
                              "Choisissez d'autres vidéos : la source ne peut pas être dans le "
                              "dossier de sortie « media (mp4) ».")
    # La conversion MP4 ne supprime RIEN (comme l'ancienne app) : les .mp4 sont
    # ajoutés / remplacés un par un dans « media (mp4) ».
    return {"dossier": dossier, "fichiers": fichiers, "nb_medias": n, "sortie": sortie,
            "supprime_sortie": False}


def _mp4_deja_presents(plan: dict) -> int:
    """Nombre de .mp4 qui existent DÉJÀ là où la conversion va écrire.

    ffmpeg les écrase sans prévenir (option -y) : « preparer » le signale à l'interface.
    Mêmes noms de sortie que agent/conversion.py : <sortie>/<sous-dossier>/<nom>.mp4."""
    from agent import conversion
    sortie, cibles = plan["sortie"], set()
    if plan["fichiers"] is not None:
        for f in plan["fichiers"]:
            if _a_extension(f, conversion.EXT_VIDEOS):
                cibles.add(os.path.join(sortie, os.path.splitext(os.path.basename(f))[0] + ".mp4"))
    else:
        dossier = plan["dossier"]
        for racine, _sous, noms in os.walk(dossier):
            rel = os.path.relpath(racine, dossier)
            cible = sortie if rel == "." else os.path.join(sortie, rel)
            for f in noms:
                if _a_extension(f, conversion.EXT_VIDEOS):
                    cibles.add(os.path.join(cible, os.path.splitext(f)[0] + ".mp4"))
    return sum(1 for c in cibles if os.path.isfile(c))


def _format_image(args: dict) -> str:
    fmt = args.get("format", "jpg")
    if not isinstance(fmt, str) or fmt.lower() not in ("jpg", "png"):
        raise _invalide("format", "« format » doit valoir « jpg » ou « png ».")
    return fmt.lower()


def _plan_conversion_images(args: dict) -> dict:
    from agent import unicite
    fmt = _format_image(args)
    dossier, fichiers = _source(args)
    n = _compter_medias(dossier, fichiers, unicite.EXT_IMAGES)
    if n == 0:
        raise ErreurCommande("SOURCE_VIDE", "Aucune image trouvée dans ce dossier." if dossier
                             else "Aucune image dans la sélection.")
    sortie = os.path.join(dossier_sortie(), f"images ({fmt})")
    _verifier_pas_dans_sortie(dossier, fichiers, sortie,
                              "Choisissez un autre dossier : la source ne peut pas être le "
                              "dossier de sortie.")
    return {"dossier": dossier, "fichiers": fichiers, "nb_medias": n, "sortie": sortie,
            "supprime_sortie": True, "format": fmt}


def _plan_metadonnees(args: dict) -> dict:
    from agent import unicite
    dossier, fichiers = _source(args)
    n = _compter_medias(dossier, fichiers, unicite.EXT_IMAGES | unicite.EXT_VIDEOS)
    if n == 0:
        raise ErreurCommande("SOURCE_VIDE", "Aucune image ni vidéo trouvée dans ce dossier."
                             if dossier else "Aucune image ni vidéo dans la sélection.")
    # Sortie nommée d'après le dossier importé : « OK » -> « OK (métadonnées changées) ».
    if dossier:
        nom_src = os.path.basename(os.path.normpath(dossier)) or "media"
        sortie = os.path.join(dossier_sortie(), f"{nom_src} (métadonnées changées)")
    else:
        sortie = os.path.join(dossier_sortie(), "media (métadonnées changées)")
    _verifier_pas_dans_sortie(dossier, fichiers, sortie,
                              "Choisissez un autre dossier : la source ne peut pas être le dossier "
                              "de sortie « media (métadonnées changées) » (ni un sous-dossier de "
                              "celui-ci).")
    return {"dossier": dossier, "fichiers": fichiers, "nb_medias": n, "sortie": sortie,
            "supprime_sortie": True}


# ═══════════════════════════════════════════════════════════════════════════
#  Système
# ═══════════════════════════════════════════════════════════════════════════
@commande("info")
def info(ctx, args):
    from agent import conversion, emplacement, unicite, version
    from agent import ranger as rangement
    from agent.config import IMAGES_PAR_CAROUSEL
    perso = _sortie_perso()
    return {
        "nom": version.NOM, "version": version.VERSION,
        "protocole": ctx.moteur.protocole,
        "python": sys.version.split()[0], "plateforme": sys.platform,
        "frozen": bool(getattr(sys, "frozen", False)), "pid": os.getpid(),
        "dossier_donnees": emplacement.dossier_donnees(),
        "dossier_sortie": perso or dossier_sortie_defaut(),
        "dossier_sortie_defaut": dossier_sortie_defaut(),
        "extensions": {
            "videos_mp4": sorted(conversion.EXT_VIDEOS),
            "images_conversion": sorted(unicite.EXT_IMAGES),
            "medias_metadonnees": sorted(unicite.EXT_IMAGES | unicite.EXT_VIDEOS),
            "ranger_images": sorted(rangement.EXT_IMAGES),
            "ranger_videos": sorted(rangement.EXT_VIDEOS),
        },
        "types_ranger": [{"type": t, "libelle": rangement.LIBELLES[t],
                          "libelle_creneau": rangement.LIBELLE_CRENEAU[t],
                          "nom_dossier": rangement.NOM_DOSSIER[t],
                          "est_video": rangement.est_video(t),
                          "medias_par_creneau": rangement.medias_par_creneau(t)}
                         for t in rangement.TYPES],
        "images_par_carrousel": IMAGES_PAR_CAROUSEL,
        "licence_contournee_dev": bool(ctx.moteur.sans_licence),
        "commandes": sorted(COMMANDES),
    }


@commande("ouvrir_dans_explorateur")
def ouvrir_dans_explorateur(ctx, args):
    chemin = args.get("chemin")
    if not est_absolu(chemin) or not os.path.isdir(chemin):
        # On n'ouvre QUE des dossiers : jamais un .exe ou un document qu'on
        # lancerait sans le vouloir.
        raise ErreurCommande("CHEMIN_REFUSE", "Seul un dossier existant peut être ouvert.",
                             {"chemin": chemin})
    if sys.platform == "win32":
        os.startfile(chemin)
    else:
        import subprocess
        subprocess.Popen(["open" if sys.platform == "darwin" else "xdg-open", chemin],
                         stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                         stderr=subprocess.DEVNULL)
    return {"ok": True}


@commande("preparer")
def preparer(ctx, args):
    """Avant une tâche longue : où ira le résultat ? Faudra-t-il REMPLACER un dossier ?

    L'interface pose alors la question « Remplacer ? » (l'ancienne messagebox),
    puis lance la vraie commande avec remplacer: "<le champ sortie renvoyé ici>".
    Le moteur ne supprime que CE chemin-là (voir _confirmation)."""
    cible = args.get("commande")
    sous_args = args.get("args") or {}
    if not isinstance(sous_args, dict):
        raise _invalide("args", "« args » doit être un objet.")
    plans = {"conversion_mp4": _plan_conversion_mp4,
             "conversion_images": _plan_conversion_images,
             "metadonnees": _plan_metadonnees}
    if cible == "ranger_lancer":
        a = ranger_analyser(ctx, sous_args)
        return {"commande": cible, "sortie": a["sortie"], "existe": a["existe"],
                "remplacement": a["existe"], "analyse": a}
    if cible not in plans:
        raise _invalide("commande", "« commande » doit être conversion_mp4, conversion_images, "
                                    "metadonnees ou ranger_lancer.")
    plan = plans[cible](sous_args)
    existe = os.path.exists(plan["sortie"])
    out = {"commande": cible, "sortie": plan["sortie"], "existe": existe,
           "remplacement": existe and plan["supprime_sortie"], "nb_medias": plan["nb_medias"]}
    if cible == "conversion_mp4":
        out["deja_presents"] = _mp4_deja_presents(plan) if existe else 0
    return out


# ═══════════════════════════════════════════════════════════════════════════
#  Licence
# ═══════════════════════════════════════════════════════════════════════════
def _statut_json(st: dict) -> dict:
    """Statut de licence -> JSON (les dates deviennent "AAAA-MM-JJ")."""
    from agent import licence
    out = dict(st)
    fin = st.get("expire_le")
    debut = None
    if fin is not None:
        if st.get("type") == "an":
            debut = licence._ajouter_mois(fin, -12)
        elif st.get("type") == "mois":
            debut = licence._ajouter_mois(fin, -1)
    out["expire_le"] = fin.isoformat() if fin is not None else None
    out["debut_le"] = debut.isoformat() if debut is not None else None
    return out


# Plusieurs licence_statut en même temps (« Réessayer » cliqué 3 fois) : UNE seule
# vérification tourne, les autres attendent son résultat au lieu d'en relancer une.
_VERROU_STATUT = threading.Lock()
_statut_en_cours = None     # {"fini": Event, "res", "exc", "generation"} pendant une vérification


def _verifier_licence_partage(moteur):
    """licence.verifier(), partagée entre les appels simultanés.

    Renvoie (statut, generation) : la « génération » de licence relevée AU DÉBUT de la
    vraie vérification (voir Moteur.licence_maj)."""
    global _statut_en_cours
    from agent import licence
    with _VERROU_STATUT:
        partage = _statut_en_cours
        chef = partage is None
        if chef:
            partage = _statut_en_cours = {"fini": threading.Event(), "res": None, "exc": None,
                                          "generation": moteur.generation_licence()}
    if chef:
        try:
            partage["res"] = licence.verifier()
        except BaseException as e:
            partage["exc"] = e
        finally:
            with _VERROU_STATUT:
                _statut_en_cours = None
            partage["fini"].set()
    else:
        partage["fini"].wait()
    if partage["exc"] is not None:
        raise partage["exc"]
    return partage["res"], partage["generation"]


@commande("licence_statut", RESEAU)
def licence_statut(ctx, args):
    """licence.verifier() — peut durer ~40 s hors-ligne (Supabase + lecture de la vraie date)."""
    from agent import licence
    st, generation = _verifier_licence_partage(ctx.moteur)
    ctx.moteur.licence_maj(bool(st.get("ok")), generation)
    out = _statut_json(st)
    out["empreinte"] = licence.empreinte_machine()
    return out


@commande("licence_activer", RESEAU, critique=True)
def licence_activer(ctx, args):
    """Code d'activation -> licence (même logique que l'écran d'activation).

    Un refus (code faux, pas de connexion) n'est PAS une erreur : result ok:false."""
    from agent import licence
    code = _texte(args, "code")
    generation = ctx.moteur.generation_licence()
    lic, message = licence.activer_par_code(code)
    if not lic:
        return {"ok": False, "message": message, "statut": None}
    st = licence.enregistrer_licence(lic)
    ctx.moteur.licence_maj(bool(st.get("ok")), generation, nouvelle_generation=True)
    if st.get("ok"):
        return {"ok": True, "message": "ok", "statut": _statut_json(st)}
    return {"ok": False, "message": "Code accepté mais activation refusée. Réessayez.",
            "statut": _statut_json(st)}


@commande("licence_resilier", critique=True)
def licence_resilier(ctx, args):
    from agent import licence
    # Nouvelle « génération » AVANT et APRÈS la suppression : un licence_statut lent,
    # lancé avant, ne pourra plus remettre licence_ok à vrai en finissant après nous.
    ctx.moteur.licence_reinitialiser()
    ok = licence.supprimer_licence()
    ctx.moteur.licence_reinitialiser()
    return {"ok": bool(ok)}


# ═══════════════════════════════════════════════════════════════════════════
#  Paramètres
# ═══════════════════════════════════════════════════════════════════════════
def _vue_parametres(params: dict) -> dict:
    perso = str(params.get("dossier_sortie") or "").strip()
    return {"parametres": params, "dossier_sortie": perso or dossier_sortie_defaut(),
            "dossier_sortie_defaut": dossier_sortie_defaut(), "personnalise": bool(perso)}


@commande("parametres_lire")
def parametres_lire(ctx, args):
    return _vue_parametres(_charger_parametres())


@commande("parametres_ecrire", critique=True)
def parametres_ecrire(ctx, args):
    """args = {"valeurs": {...}} — seules les clés connues sont acceptées."""
    from agent import parametres
    from agent.ranger import TYPES
    valeurs = args.get("valeurs")
    if not isinstance(valeurs, dict) or not valeurs:
        raise _invalide("valeurs", "« valeurs » doit être un objet non vide.")
    propres = {}
    for cle, val in valeurs.items():
        if cle == "theme":
            if val not in ("light", "dark"):
                raise _invalide("valeurs.theme", "« theme » doit valoir « light » ou « dark ».")
        elif cle == "dossier_sortie":
            if not isinstance(val, str):
                raise _invalide("valeurs.dossier_sortie", "« dossier_sortie » doit être un texte.")
            val = val.strip()
            if val:                      # vide = retour au dossier par défaut (Bureau)
                if not est_absolu(val):
                    raise _invalide("valeurs.dossier_sortie",
                                    "« dossier_sortie » doit être un chemin absolu (avec le lecteur).")
                try:
                    os.makedirs(val, exist_ok=True)
                except OSError as e:
                    raise ErreurCommande("SORTIE_INACCESSIBLE",
                                         f"Impossible d'utiliser ce dossier : {val}\n{e}",
                                         {"sortie": val})
        elif cle == "ranger_types":
            if not isinstance(val, dict) or any(k not in TYPES or not isinstance(v, bool)
                                                for k, v in val.items()):
                raise _invalide("valeurs.ranger_types",
                                "« ranger_types » doit être {type: true|false}.")
        elif cle == "deja_demarre":
            if not isinstance(val, bool):
                raise _invalide("valeurs.deja_demarre", "« deja_demarre » doit valoir true ou false.")
        else:
            raise _invalide(f"valeurs.{cle}", f"Paramètre inconnu : {cle}")
        propres[cle] = val
    with VERROU_DONNEES:
        params = parametres.charger()
        params.update(propres)
        # Même fichier que parametres.sauver(), mais écrit d'un coup (voir _ecrire_json_atomique).
        _ecrire_json_atomique(parametres._chemin(), params)
    return _vue_parametres(params)


@commande("dossier_sortie")
def commande_dossier_sortie(ctx, args):
    """Le dossier de sortie effectif (créé s'il n'existe pas, comme l'ancienne app)."""
    d = dossier_sortie(creer=True)
    perso = _sortie_perso()
    return {"chemin": d, "defaut": dossier_sortie_defaut(),
            "personnalise": bool(perso) and _norm(d) == _norm(perso)}


# ═══════════════════════════════════════════════════════════════════════════
#  Calendrier
# ═══════════════════════════════════════════════════════════════════════════
_INTERDITS = set('<>:"/\\|?*')
# Noms RÉSERVÉS par Windows (même suivis d'une extension : « CON.txt ») : impossible de
# créer un dossier qui porte ce nom. Accepté ici, le calendrier s'enregistrerait, puis
# chaque rangement planterait APRÈS avoir supprimé l'ancienne sortie.
_RESERVES = ({"CON", "PRN", "AUX", "NUL"} | {f"COM{i}" for i in range(1, 10)}
             | {f"LPT{i}" for i in range(1, 10)})


def _nom_valide(nom) -> bool:
    """Ces noms deviennent des NOMS DE DOSSIERS (semaine-01/jour-1/1_12h15_reel) :
    pas de « \\ », de « .. », d'espace au début/à la fin, de nom réservé (CON, NUL…),
    ni de caractère interdit par Windows."""
    return (isinstance(nom, str) and 0 < len(nom) <= 40 and nom.strip() == nom
            and nom not in (".", "..") and not nom.endswith(".")
            and nom.split(".")[0].strip().upper() not in _RESERVES
            and not any(c in _INTERDITS or ord(c) < 32 for c in nom))


def _valider_calendrier(cal) -> dict:
    from agent.ranger import TYPES
    if not isinstance(cal, dict) or not cal:
        raise _invalide("calendrier", "Il faut au moins 1 semaine.")
    propre = {}
    for sem, jours in cal.items():
        if not _nom_valide(sem) or not isinstance(jours, dict):
            raise _invalide("calendrier", f"Semaine invalide : {sem!r}")
        propre[sem] = {}
        for jour, creneaux in jours.items():
            if not _nom_valide(jour) or not isinstance(creneaux, list):
                raise _invalide("calendrier", f"Jour invalide : {sem} / {jour!r}")
            liste = []
            for cr in creneaux:
                if (not isinstance(cr, dict) or cr.get("type") not in TYPES
                        or not _nom_valide(cr.get("heure"))):
                    raise _invalide("calendrier", f"Créneau invalide : {sem} / {jour} / {cr!r}")
                liste.append({"heure": cr["heure"], "type": cr["type"]})
            propre[sem][jour] = liste
    return propre


def _vue_calendrier(cal: dict) -> dict:
    from agent import ranger as rangement
    n = rangement.compter(cal)
    return {"calendrier": cal, "semaines": len(cal), "compte": n,
            "creneaux": sum(n.values())}


def _calendrier_utilisable(cal) -> str:
    """Message d'erreur si le calendrier ENREGISTRÉ ne peut pas servir au rangement
    (par ex. écrit par l'ancienne app avec un nom réservé), sinon None."""
    try:
        _valider_calendrier(cal)
        return None
    except ErreurCommande as e:
        return (f"{e.message}\nCorrigez le calendrier (éditeur du module Ranger) "
                "avant de lancer le rangement.")


@commande("calendrier_lire")
def calendrier_lire(ctx, args):
    from agent import calendrier
    vue = _vue_calendrier(_charger_calendrier())
    vue["personnalise"] = os.path.exists(calendrier._chemin_utilisateur())
    return vue


@commande("calendrier_defaut")
def calendrier_defaut(ctx, args):
    """Le calendrier d'origine (bouton « Réinitialiser » de l'éditeur)."""
    from agent import calendrier
    return _vue_calendrier(copy.deepcopy(calendrier.CALENDRIER))


@commande("calendrier_sauver", critique=True)
def calendrier_sauver(ctx, args):
    from agent import calendrier
    cal = _valider_calendrier(args.get("calendrier"))
    with VERROU_DONNEES:
        # Même fichier que calendrier.sauver_calendrier(), mais écrit d'un coup.
        _ecrire_json_atomique(calendrier._chemin_utilisateur(), cal)
    vue = _vue_calendrier(cal)
    vue["message"] = f"Enregistré ({len(cal)} semaine(s)).\nAppliqué au prochain rangement."
    return vue


# ═══════════════════════════════════════════════════════════════════════════
#  Ranger les médias
# ═══════════════════════════════════════════════════════════════════════════
def _types_actifs(args: dict, n: dict) -> list:
    """Types à ranger : args["types"] si fourni, sinon ceux cochés dans les
    paramètres ET présents dans le calendrier (comme _types_ranger_actifs)."""
    from agent.ranger import TYPES
    demandes = args.get("types")
    if demandes is not None:
        if not isinstance(demandes, list) or any(t not in TYPES for t in demandes):
            raise _invalide("types", f"« types » doit être une liste parmi {list(TYPES)}.")
        return [t for t in TYPES if t in demandes and n[t] > 0]
    choix = _charger_parametres().get("ranger_types")
    if not isinstance(choix, dict):
        choix = {}
    return [t for t in TYPES if bool(choix.get(t, True)) and n[t] > 0]


def _sources_ranger(args: dict) -> dict:
    from agent.ranger import TYPES
    sources = args.get("sources", {})
    if not isinstance(sources, dict):
        raise _invalide("sources", "« sources » doit être {type: dossier}.")
    propres = {}
    for t, d in sources.items():
        if t not in TYPES:
            raise _invalide("sources", f"Type inconnu : {t}")
        if d is None or d == "":
            continue
        propres[t] = _chemin_absolu(d, f"sources.{t}")
    return propres


@commande("ranger_analyser")
def ranger_analyser(ctx, args):
    """Tout ce que l'ancienne app calculait AVANT sa fenêtre « Confirmer le rangement »."""
    from agent import ranger as rangement
    sources = _sources_ranger(args)
    cal = _charger_calendrier()
    erreur_calendrier = _calendrier_utilisable(cal)
    n = rangement.compter(cal)
    actifs = _types_actifs(args, n)
    # EXACTEMENT le même calcul que ranger_lancer (avec le repli sur le Bureau si le
    # dossier perso est inaccessible) : le chemin annoncé dans « Remplacer ? » est
    # celui qui sera vraiment remplacé.
    sortie = os.path.join(dossier_sortie(), "ranger")
    types, lignes, manquants, dans_sortie, vus, doublons = {}, [], [], [], {}, []
    incomplet = False
    for t in rangement.TYPES:
        video = rangement.est_video(t)
        unite = "vidéo(s)" if video else "image(s)"
        requis = n[t] * rangement.medias_par_creneau(t)
        d = sources.get(t)
        valide = bool(d and os.path.isdir(d))
        a = rangement.analyser_dossier(d, t) if valide else {"fichiers": [], "ignores": 0}
        k = len(a["fichiers"])
        types[t] = {"libelle": rangement.LIBELLES[t], "est_video": video, "unite": unite,
                    "creneaux": n[t], "medias_par_creneau": rangement.medias_par_creneau(t),
                    "requis": requis, "actif": t in actifs, "dossier": d,
                    "dossier_valide": valide, "trouves": k, "ignores": a["ignores"],
                    "manque": max(0, requis - k)}
        if t not in actifs:
            continue
        if not valide:
            manquants.append(t)
            continue
        if est_dans(d, sortie):
            dans_sortie.append(t)
        if not video:   # même dossier pour deux types d'IMAGES -> mêmes images rangées 2 fois
            cle = _norm(d)
            if cle in vus:
                doublons.append([vus[cle], t])
            else:
                vus[cle] = t
        txt = f"• {rangement.LIBELLES[t]} : {k} {unite} pour {requis} requise(s)"
        if k < requis:
            txt += f"  ⚠️ il en manque {requis - k}"
            incomplet = True
        lignes.append(txt)
    existe = os.path.exists(sortie)
    msg = "À ranger :\n" + "\n".join(lignes) + f"\n\nDestination :\n{sortie}\n"
    if incomplet:
        msg += "\n⚠️ Certains créneaux resteront incomplets.\n"
    if existe:
        msg += "\n⚠️ Ce dossier existe déjà et sera REMPLACÉ.\n"
    return {"types": types, "actifs": actifs, "sortie": sortie, "existe": existe,
            "manquants": manquants, "source_dans_sortie": dans_sortie,
            "doublons": doublons, "incomplet": incomplet,
            "calendrier_erreur": erreur_calendrier,
            "pret": (bool(actifs) and not manquants and not dans_sortie
                     and erreur_calendrier is None),
            "message_confirmation": msg + "\nContinuer ?"}


@commande("ranger_lancer", LONGUE)
def ranger_lancer(ctx, args):
    """Copie de App._lancer_ranger + message « fini_ranger »."""
    from agent import ranger as rangement
    sources = _sources_ranger(args)
    aleatoire = _booleen(args, "aleatoire", True)
    confirme = _confirmation(args)
    cal = _charger_calendrier()
    erreur_calendrier = _calendrier_utilisable(cal)
    if erreur_calendrier:
        # Vérifié AVANT de toucher à l'ancienne sortie (sinon : sortie supprimée, puis plantage).
        raise ErreurCommande("CALENDRIER_INVALIDE", erreur_calendrier)
    n = rangement.compter(cal)
    actifs = _types_actifs(args, n)
    if not actifs:
        raise _invalide("types", "Cochez au moins un type de post (étape 1).")
    manquants = [t for t in actifs if not (sources.get(t) and os.path.isdir(sources[t]))]
    if manquants:
        raise ErreurCommande("SOURCE_INTROUVABLE", "Choisissez un dossier pour :\n\n" + "\n".join(
            f"• {rangement.LIBELLES[t]}" for t in manquants),
            {"types": manquants, "chemins": [sources.get(t) for t in manquants]})
    sortie = os.path.join(dossier_sortie(), "ranger")
    for t in actifs:
        if est_dans(sources[t], sortie):
            nom = rangement.LIBELLES[t][0].lower() + rangement.LIBELLES[t][1:]
            raise ErreurCommande("SOURCE_DANS_SORTIE",
                                 f"Le dossier des {nom} est dans le dossier de sortie, qui va être "
                                 "remplacé. Choisissez un autre dossier.",
                                 {"sortie": sortie, "chemins": [sources[t]], "types": [t]})
    if ctx.doit_arreter():
        # Annulé juste après le clic : on ne supprime RIEN.
        return {"arrete": True, "creneaux": 0, "types": [], "sortie": sortie, "duree_s": 0.0,
                "bilan": {"titre": "Ranger", "erreur": True,
                          "message": "Rangement arrêté.\n\nRien n'a été modifié."}}
    _remplacer_sortie(sortie, confirme)
    debut = time.monotonic()
    try:
        res = rangement.ranger({t: sources[t] for t in actifs}, sortie, actifs,
                               aleatoire=aleatoire, progress=ctx.progress,
                               doit_arreter=ctx.doit_arreter)
    except Exception as e:
        raise _echec("Ranger", e)

    # Message de fin : copie de App._controle("fini_ranger").
    if res.get("arrete"):
        bilan = {"titre": "Ranger", "erreur": True,
                 "message": f"Rangement arrêté.\n\n{res.get('creneaux', 0)} "
                            f"créneau(x) déjà rangé(s) dans :\n{sortie}"}
    else:
        lignes, alerte = [], False
        for t in res.get("types", []):
            unite = "vidéo(s)" if rangement.est_video(t) else "image(s)"
            requis = res["besoins"][t] * rangement.medias_par_creneau(t)
            ligne = f"• {rangement.LIBELLES[t]} : {res['places'][t]}/{requis} {unite}"
            if res["manques"].get(t):
                ligne += f"  ⚠️ il en manque {res['manques'][t]}"
                alerte = True
            lignes.append(ligne)
        txt = "Médias rangés !\n\n" + "\n".join(lignes) + f"\n\nDossier :\n{sortie}"
        en_trop = sum(res.get("surplus", {}).values())
        if en_trop:
            txt += f"\n\n📦 {en_trop} média(s) en trop → dossier « surplus »."
        bilan = {"titre": "Ranger", "message": txt, "erreur": alerte}
    out = dict(res)
    out.update({"sortie": sortie, "duree_s": round(time.monotonic() - debut, 1),
                "bilan": bilan})
    return out


# ═══════════════════════════════════════════════════════════════════════════
#  Tâches longues : conversions et métadonnées
# ═══════════════════════════════════════════════════════════════════════════
def _interrompu_avant(titre: str, sortie: str, mot: str, extra: dict = None) -> dict:
    """Annulation reçue AVANT le début du travail : on s'arrête sans rien toucher
    (surtout sans supprimer l'ancienne sortie)."""
    out = {"traites": 0, "echecs": [], "arrete": True, "dossiers": 0, "sortie": sortie,
           "duree_s": 0.0, "bilan": bilan_fin(titre, {"arrete": True, "medias": 0}, sortie, mot)}
    out.update(extra or {})
    return out


@commande("conversion_mp4", LONGUE)
def conversion_mp4(ctx, args):
    """Copie de App._lancer_convert : sortie « <dossier de sortie>/media (mp4) »."""
    from agent import conversion
    plan = _plan_conversion_mp4(args)
    _verifier_ffmpeg()
    sortie, dossier, fichiers = plan["sortie"], plan["dossier"], plan["fichiers"]
    if ctx.doit_arreter():
        return _interrompu_avant("Conversion terminée", sortie, "vidéo(s) en .mp4")
    try:
        os.makedirs(sortie, exist_ok=True)
    except OSError as e:
        raise ErreurCommande("SORTIE_INACCESSIBLE", f"Impossible de créer : {sortie}\n{e}",
                             {"sortie": sortie})
    debut = time.monotonic()
    try:
        if fichiers:
            res = conversion.convertir_fichiers(fichiers, sortie, ctx.progress, ctx.doit_arreter)
        else:
            res = conversion.convertir_dossier(dossier, sortie, ctx.progress, ctx.doit_arreter)
    except Exception as e:
        raise _echec("Convertir en MP4", e)
    res["arrete"] = res.get("arrete") or ctx.doit_arreter()
    nb_d = res.get("dossiers") if (dossier and res.get("dossiers", 1) > 1) else None
    bilan = bilan_fin("Conversion terminée", res, sortie, "vidéo(s) en .mp4", nb_dossiers=nb_d)
    return {"traites": res.get("medias", 0), "echecs": res.get("echecs") or [],
            "arrete": bool(res["arrete"]), "dossiers": res.get("dossiers", 1),
            "sortie": sortie, "duree_s": round(time.monotonic() - debut, 1), "bilan": bilan}


@commande("conversion_images", LONGUE)
def conversion_images(ctx, args):
    """Copie de App._lancer_imgconv : sortie « images (jpg) » ou « images (png) »."""
    from agent import unicite
    plan = _plan_conversion_images(args)
    confirme = _confirmation(args)
    sortie, dossier, fichiers, fmt = plan["sortie"], plan["dossier"], plan["fichiers"], plan["format"]
    if ctx.doit_arreter():
        return _interrompu_avant("Images converties", sortie, f"image(s) en .{fmt}", {"format": fmt})
    _remplacer_sortie(sortie, confirme)
    debut = time.monotonic()
    try:
        if fichiers:
            res = unicite.convertir_images_fichiers(fichiers, sortie, fmt, progress=ctx.progress,
                                                    doit_arreter=ctx.doit_arreter)
        else:
            res = unicite.convertir_images_dossier(dossier, sortie, fmt, progress=ctx.progress,
                                                   doit_arreter=ctx.doit_arreter)
    except Exception as e:
        raise _echec("Convertir les images", e)
    res["arrete"] = ctx.doit_arreter()
    bilan = bilan_fin("Images converties", res, sortie, f"image(s) en .{fmt}")
    return {"traites": res.get("images", 0), "echecs": res.get("echecs") or [],
            "arrete": bool(res["arrete"]), "dossiers": res.get("dossiers", 1),
            "format": fmt, "sortie": sortie, "duree_s": round(time.monotonic() - debut, 1),
            "bilan": bilan}


@commande("metadonnees", LONGUE)
def metadonnees(ctx, args):
    """Copie de App._lancer_uniquiser : images ET vidéos rendues uniques."""
    from agent import unicite
    plan = _plan_metadonnees(args)
    # Par défaut true, comme la case « recommandé » cochée de l'ancienne app.
    renommer = _booleen(args, "renommer", True)
    confirme = _confirmation(args)
    filtre = False      # option de filtre retirée : uniquisation invisible uniquement
    sortie, dossier, fichiers = plan["sortie"], plan["dossier"], plan["fichiers"]
    if _compter_medias(dossier, fichiers, unicite.EXT_VIDEOS):
        _verifier_ffmpeg()          # ffmpeg n'est utile que s'il y a des vidéos
    if ctx.doit_arreter():
        return _interrompu_avant("Métadonnées changées", sortie, "média(s)")
    _remplacer_sortie(sortie, confirme)
    debut = time.monotonic()
    try:
        if fichiers:
            res = unicite.uniquiser_fichiers(fichiers, sortie, renommer=renommer, filtre=filtre,
                                             progress=ctx.progress, doit_arreter=ctx.doit_arreter)
            res["arrete"] = ctx.doit_arreter()
            res.setdefault("dossiers", 0)
        else:
            # Dossier : arborescence conservée + progression fichier par fichier.
            res = unicite.uniquiser_arbre(dossier, sortie, renommer=renommer, filtre=filtre,
                                          progress=ctx.progress, doit_arreter=ctx.doit_arreter)
    except Exception as e:
        raise _echec("Métadonnées", e)
    bilan = bilan_fin("Métadonnées changées", res, sortie, "média(s)", res.get("dossiers"))
    return {"traites": res.get("medias", 0), "echecs": res.get("echecs") or [],
            "arrete": bool(res.get("arrete")), "dossiers": res.get("dossiers", 0),
            "sortie": sortie, "duree_s": round(time.monotonic() - debut, 1), "bilan": bilan}


# ═══════════════════════════════════════════════════════════════════════════
#  Commande de TEST uniquement (jamais dans l'exe, jamais sans la variable)
# ═══════════════════════════════════════════════════════════════════════════
if not getattr(sys, "frozen", False) and os.environ.get("HELPVA_MOTEUR_TESTS") == "1":

    @commande("_diagnostic_bruit")
    def _diagnostic_bruit(ctx, args):
        """Fait volontairement du « bruit » pour vérifier que stdout reste propre :
        print(), stderr, écriture directe sur le fd 1, et un sous-processus qui
        écrit sur SA sortie et lit SON entrée (comme ffmpeg)."""
        import subprocess
        print("bruit print é ⛔ 漢字")
        sys.stdout.write("début de ligne… ")
        sys.stdout.write("fin de ligne\n")
        sys.stderr.write("bruit stderr ⚠️\n")
        os.write(1, b"BRUIT-FD1 pas du JSON\n")
        # Un enfant qui hérite de nos poignées standard (comme ffmpeg) :
        subprocess.run([sys.executable, "-c", "print('BRUIT-ENFANT-STDOUT')"], timeout=30)
        lu = subprocess.run([sys.executable, "-c",
                             "import sys; d = sys.stdin.buffer.read(); print(len(d))"],
                            stdout=subprocess.PIPE, timeout=30)
        return {"octets_lus_par_enfant": int(lu.stdout.strip() or b"-1")}
