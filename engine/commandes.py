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
import re
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


def _lister_medias(dossier, fichiers, extensions) -> list:
    """Les fichiers utiles d'une source, dans l'ordre du traitement (pour le compteur
    d'activité : empreintes des médias traités)."""
    if fichiers is not None:
        return [f for f in fichiers if _a_extension(f, extensions)]
    trouves = []
    for racine, _sous, noms in os.walk(dossier):
        trouves += [os.path.join(racine, f) for f in sorted(noms) if _a_extension(f, extensions)]
    return trouves


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


@commande("dossier_existe")
def dossier_existe(ctx, args):
    """Le dossier existe-t-il, et contient-il quelque chose ? L'interface grise « Ouvrir le dossier
    du résultat » tant qu'il est absent ou vide (rien n'a encore été produit)."""
    chemin = args.get("chemin")
    existe = bool(est_absolu(chemin) and os.path.isdir(chemin))
    plein = False
    if existe:
        try:
            with os.scandir(chemin) as it:
                plein = any(True for _ in it)
        except OSError:
            plein = False
    return {"existe": existe, "plein": plein}


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
        # Renommées 1, 2, 3… : numérotées à la suite des fichiers existants, rien n'est remplacé.
        renomme = _booleen(sous_args, "renommer", False)
        out["deja_presents"] = _mp4_deja_presents(plan) if existe and not renomme else 0
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


# Paramètres « oui / non » (choix par défaut des modules, fin de traitement, 1er démarrage).
_PARAMETRES_BOOLEENS = ("deja_demarre", "renommer_images", "renommer_mp4", "renommer_metadonnees",
                        "ranger_aleatoire", "fin_ouvrir_dossier", "fin_notification")


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
        elif cle == "format_images":
            if val not in ("jpg", "png"):
                raise _invalide("valeurs.format_images",
                                "« format_images » doit valoir « jpg » ou « png ».")
        elif cle in _PARAMETRES_BOOLEENS:
            if not isinstance(val, bool):
                raise _invalide(f"valeurs.{cle}", f"« {cle} » doit valoir true ou false.")
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
# Liste de la doc Microsoft : COM0 à COM9 et LPT0 à LPT9, AUSSI avec les chiffres en exposant
# (COM¹, LPT²… : Windows 10 les refuse), et CONIN$ / CONOUT$ (la console).
_RESERVES = ({"CON", "PRN", "AUX", "NUL", "CONIN$", "CONOUT$"}
             | {f"{p}{i}" for p in ("COM", "LPT") for i in "0123456789¹²³"})


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


def _compter(cal) -> dict:
    """rangement.compter(), sans planter sur un calendrier mal formé (fichier modifié à la
    main) : 0 créneau, et _calendrier_utilisable() dit pourquoi au moment de ranger."""
    from agent import ranger as rangement
    try:
        return rangement.compter(cal)
    except (AttributeError, TypeError):
        return {t: 0 for t in rangement.TYPES}


def _vue_calendrier(cal: dict) -> dict:
    n = _compter(cal)
    return {"calendrier": cal, "semaines": len(cal) if isinstance(cal, dict) else 0,
            "compte": n, "creneaux": sum(n.values())}


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
#  Comptes du module Ranger (chacun SES dossiers et SON calendrier)
# ═══════════════════════════════════════════════════════════════════════════
def _calendrier_origine() -> dict:
    from agent import calendrier
    return copy.deepcopy(calendrier.CALENDRIER)


def _libelle_min(t: str) -> str:
    """« Réels » -> « réels », « Stories CTA » -> « stories CTA » (dans une phrase)."""
    from agent.ranger import LIBELLES
    return LIBELLES[t][0].lower() + LIBELLES[t][1:]


def _invalide_compte(compte_id, message: str):
    """Refus qui NOMME le compte fautif dans le message (« Compte 2 : … »).
    details.compte = son id (null s'il n'en a pas encore) : l'interface le sélectionne."""
    e = _invalide("comptes", message)
    e.details["compte"] = compte_id
    return e


def _valider_comptes(liste, calendriers_stricts: bool = True, calendriers_connus=()) -> list:
    """Vérifie TOUTE la liste des comptes -> [{id, nom, sources, calendrier}].

    Les noms deviennent des NOMS DE DOSSIERS (ranger/<nom>/…) : mêmes règles que le
    calendrier (_nom_valide), et uniques SANS tenir compte de la casse (pour Windows,
    « Marie » et « marie » sont le même dossier).
    calendriers_stricts :
      - True (comptes_sauver) : un calendrier NOUVEAU ou MODIFIÉ invalide est refusé ; un
        calendrier identique à celui d'origine est enregistré null (= « Calendrier d'origine ») ;
      - False (ranger_*) : le calendrier est gardé tel quel, et _comptes_ranger le
        signale compte par compte (calendrier_erreur), comme le calendrier enregistré.
    calendriers_connus : les calendriers DÉJÀ enregistrés (comptes_ranger.json, ou celui repris
    de calendrier_utilisateur.json). Ils sont gardés tels quels, même invalides : un calendrier
    hérité de l'ancienne app (heure « 12h15 » suivie d'une espace…) ne doit pas bloquer un
    changement de nom ou de dossier, ni « + » (qui copie le calendrier du compte 1). Le
    rangement, lui, reste refusé (calendrier_erreur, CALENDRIER_INVALIDE) tant qu'il n'est pas
    corrigé dans l'éditeur."""
    from agent.comptes import MAX_COMPTES
    from agent.ranger import TYPES
    if not isinstance(liste, list) or not liste:
        raise _invalide("comptes", "Il faut au moins 1 compte.")
    if len(liste) > MAX_COMPTES:
        raise _invalide("comptes", f"{MAX_COMPTES} comptes au maximum ({len(liste)} reçus).")

    # 1er passage : les ids déjà choisis par l'interface (uniques), pour en créer
    # d'autres sans collision aux comptes qui n'en ont pas.
    ids = set()
    for i, c in enumerate(liste, start=1):
        if not isinstance(c, dict):
            raise _invalide_compte(None, f"Compte n°{i} : format invalide (objet attendu).")
        cid = c.get("id")
        if cid is None or cid == "":
            continue
        if not isinstance(cid, str) or len(cid) > 64 or cid.strip() != cid:
            raise _invalide_compte(None, f"Compte n°{i} : identifiant invalide : {cid!r}")
        if cid in ids:
            raise _invalide_compte(cid, f"Compte n°{i} : l'identifiant « {cid} » est déjà "
                                        "utilisé par un autre compte.")
        ids.add(cid)

    origine = _calendrier_origine() if calendriers_stricts else None
    propres, noms = [], {}
    for i, c in enumerate(liste, start=1):
        # L'id choisi par l'interface (None s'il n'en a pas) : c'est lui que nomment les refus
        # (details.compte), jamais un id inventé ici, que l'interface ne connaîtrait pas.
        cid = c.get("id") or None

        # Nom : tant qu'il n'est pas valide, on désigne le compte par sa POSITION.
        nom = c.get("nom")
        if not isinstance(nom, str) or not nom.strip():
            raise _invalide_compte(cid, f"Compte n°{i} : donnez un nom au compte.")
        nom = nom.strip()
        if len(nom) > 40:
            raise _invalide_compte(cid, f"Compte n°{i} : nom trop long ({len(nom)} caractères, "
                                        "40 au maximum).")
        if not _nom_valide(nom):
            raise _invalide_compte(cid, f"Compte n°{i} : « {nom} » ne peut pas servir de nom de "
                                        "dossier Windows. Évitez les caractères < > : \" / \\ | ? *, "
                                        "le point à la fin et les noms réservés (CON, NUL, COM1…).")
        # « COMPTE~1 » est le NOM COURT que Windows donne au dossier « Compte 1 » : deux comptes
        # rangeraient alors leurs médias dans le même dossier, sans aucune erreur.
        if re.search(r"~\d", nom):
            raise _invalide_compte(cid, f"Compte n°{i} : « {nom} » ressemble à un nom court de "
                                        "Windows (comme COMPTE~1), qui peut désigner le dossier "
                                        "d'un autre compte. Évitez le signe ~ suivi d'un chiffre.")
        cle = nom.casefold()
        if cle in noms:
            raise _invalide_compte(cid, f"Compte n°{i} : le nom « {nom} » est déjà utilisé par "
                                        f"« {noms[cle]} ». Chaque compte doit avoir un nom "
                                        "différent (majuscules et minuscules comptent pareil).")
        noms[cle] = nom

        # Dossiers sources : {type: chemin absolu}, vide = pas encore choisi.
        sources = c.get("sources")
        if sources is None:
            sources = {}
        if not isinstance(sources, dict):
            raise _invalide_compte(cid, f"{nom} : « sources » doit être {{type: dossier}}.")
        propres_src = {}
        for t, d in sources.items():
            if t not in TYPES:
                raise _invalide_compte(cid, f"{nom} : type inconnu : {t}")
            if d is None or d == "":
                continue
            if not isinstance(d, str) or not est_absolu(d):
                raise _invalide_compte(cid, f"{nom} : le dossier des {_libelle_min(t)} doit être "
                                            f"un chemin ABSOLU (avec le lecteur) : {d}")
            propres_src[t] = d

        # Calendrier : null = celui d'origine.
        cal = c.get("calendrier")
        if cal is not None and calendriers_stricts:
            if cal not in calendriers_connus:
                try:
                    cal = _valider_calendrier(cal)
                except ErreurCommande as e:
                    raise _invalide_compte(cid, f"{nom} : {e.message}")
            if cal == origine:
                cal = None

        # Compte vérifié : on lui crée un id s'il n'en a pas (c1, c2… sans collision).
        if cid is None:
            n = 1
            while f"c{n}" in ids:
                n += 1
            cid = f"c{n}"
            ids.add(cid)
        propres.append({"id": cid, "nom": nom, "sources": propres_src, "calendrier": cal})
    return propres


def _vue_compte(compte: dict) -> dict:
    """Un compte + le résumé de son calendrier EFFECTIF (celui d'origine s'il vaut null)."""
    cal = compte.get("calendrier")
    vue = _vue_calendrier(cal if cal is not None else _calendrier_origine())
    vue["personnalise"] = cal is not None
    out = dict(compte)
    out["vue"] = vue
    return out


def _vue_comptes(comptes: list, message: str = None) -> dict:
    from agent.comptes import MAX_COMPTES
    out = {"comptes": [_vue_compte(c) for c in comptes], "max": MAX_COMPTES}
    if message:
        out["message"] = message
    return out


@commande("comptes_lire")
def comptes_lire(ctx, args):
    """Les comptes enregistrés (1re fois : « Compte 1 », avec le calendrier déjà enregistré)."""
    from agent import comptes
    with VERROU_DONNEES:
        liste = comptes.charger_comptes()
    return _vue_comptes(liste)


@commande("comptes_sauver", critique=True)
def comptes_sauver(ctx, args):
    """args = {"comptes": [...]} : la liste COMPLÈTE, vérifiée en entier avant d'écrire
    (un seul compte fautif -> rien n'est enregistré)."""
    from agent import comptes
    with VERROU_DONNEES:
        # Lire -> vérifier -> écrire sous le même verrou : les calendriers « connus » sont bien
        # ceux du fichier qu'on remplace (voir _valider_comptes).
        connus = [c["calendrier"] for c in comptes.charger_comptes() if c["calendrier"] is not None]
        liste = _valider_comptes(args.get("comptes"), calendriers_connus=connus)
        # Écrit d'un coup (.tmp puis os.replace), comme _ecrire_json_atomique.
        comptes.sauver_comptes(liste)
    return _vue_comptes(liste, "Enregistré.")


# ═══════════════════════════════════════════════════════════════════════════
#  Ranger les médias
# ═══════════════════════════════════════════════════════════════════════════
def _types_coches(args: dict) -> list:
    """Types demandés : args["types"] si fourni, sinon ceux cochés dans les
    paramètres (comme _types_ranger_actifs). COMMUNS à tous les comptes."""
    from agent.ranger import TYPES
    demandes = args.get("types")
    if demandes is not None:
        if not isinstance(demandes, list) or any(t not in TYPES for t in demandes):
            raise _invalide("types", f"« types » doit être une liste parmi {list(TYPES)}.")
        return [t for t in TYPES if t in demandes]
    choix = _charger_parametres().get("ranger_types")
    if not isinstance(choix, dict):
        choix = {}
    return [t for t in TYPES if bool(choix.get(t, True))]


def _types_actifs(coches: list, n: dict) -> list:
    """Types à ranger pour UN compte : cochés ET présents dans SON calendrier."""
    return [t for t in coches if n[t] > 0]


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


def _comptes_ranger(args: dict) -> list:
    """Les comptes à ranger, chacun avec son calendrier EFFECTIF :
    [{id, nom, sources, calendrier, calendrier_erreur, n}] (n = créneaux par type).

    - args["comptes"] fourni -> mode multi-comptes : dossiers et calendriers pris DANS
      les args (ce que l'interface affiche), jamais dans comptes_ranger.json ;
    - sinon -> ancien mode : UN compte implicite, args["sources"] + le calendrier
      enregistré (calendrier_utilisateur.json), comme avant les comptes."""
    if args.get("comptes") is not None:
        comptes = _valider_comptes(args["comptes"], calendriers_stricts=False)
        for c in comptes:
            if c["calendrier"] is None:
                c["calendrier"] = _calendrier_origine()
    else:
        comptes = [{"id": "c1", "nom": "Compte 1", "sources": _sources_ranger(args),
                    "calendrier": _charger_calendrier()}]
    for c in comptes:
        c["calendrier_erreur"] = _calendrier_utilisable(c["calendrier"])
        c["n"] = _compter(c["calendrier"])
    return comptes


def _sortie_compte(sortie: str, compte: dict, plusieurs: bool) -> str:
    """1 seul compte : « ranger » (arborescence d'avant) ; sinon « ranger/<nom du compte> »."""
    return os.path.join(sortie, compte["nom"]) if plusieurs else sortie


def _prefixe(compte: dict, plusieurs: bool) -> str:
    """« @marie : » devant un message, seulement quand il y a plusieurs comptes."""
    return f"{compte['nom']} : " if plusieurs else ""


def _analyser_compte(compte: dict, coches: list, sortie: str, sortie_compte: str) -> dict:
    """L'analyse d'UN compte (le calcul de l'ancienne app avant « Confirmer le rangement »).

    `sortie` = le dossier « ranger » ENTIER : c'est lui qui sera remplacé, une source
    placée dedans (même dans le sous-dossier d'un autre compte) serait détruite."""
    from agent import ranger as rangement
    n, sources = compte["n"], compte["sources"]
    actifs = _types_actifs(coches, n)
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
        groupes = a.get("groupes")
        # Carrousels déjà préparés (un sous-dossier = un carrousel) : ce qui manque se compte en
        # carrousels, même si l'utilisateur a mis 2 ou 4 images dans l'un d'eux.
        manque = (max(0, n[t] - len(groupes)) * rangement.medias_par_creneau(t)
                  if groupes is not None else max(0, requis - k))
        # Dossier vide : souvent, l'utilisateur a choisi le dossier PARENT (ex. « Vidéos » au lieu
        # de « Vidéos\US »). On cherche les sous-dossiers qui contiennent des médias pour le lui dire.
        sous = []
        if valide and k == 0:
            try:
                for nom in sorted(os.listdir(d)):
                    p = os.path.join(d, nom)
                    if os.path.isdir(p) and rangement.analyser_dossier(p, t)["fichiers"]:
                        sous.append(nom)
            except OSError:
                pass
        types[t] = {"libelle": rangement.LIBELLES[t], "est_video": video, "unite": unite,
                    "creneaux": n[t], "medias_par_creneau": rangement.medias_par_creneau(t),
                    "requis": requis, "actif": t in actifs, "dossier": d,
                    "dossier_valide": valide, "trouves": k, "ignores": a["ignores"],
                    "manque": manque, "sous_dossiers": sous[:6],
                    "carrousels": len(groupes) if groupes is not None else None}
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
        if groupes is not None:
            txt = f"• {rangement.LIBELLES[t]} : {len(groupes)} carrousel(s) préparé(s) pour {n[t]} requis"
        else:
            txt = f"• {rangement.LIBELLES[t]} : {k} {unite} pour {requis} requise(s)"
        if manque:
            txt += f"  ⚠️ il en manque {manque if groupes is None else n[t] - len(groupes)}"
            incomplet = True
        lignes.append(txt)
    return {"id": compte["id"], "nom": compte["nom"], "sortie": sortie_compte, "types": types,
            "actifs": actifs, "manquants": manquants, "source_dans_sortie": dans_sortie,
            "doublons": doublons, "incomplet": incomplet,
            "calendrier_erreur": compte["calendrier_erreur"],
            "creneaux": sum(n[t] for t in actifs), "lignes": lignes}


def _partages(comptes: list, analyses: list) -> list:
    """Dossiers utilisés par AU MOINS 2 comptes : les mêmes médias seront rangés plusieurs
    fois (avertissement, pas un refus). On regroupe par dossier ET par sorte de média :
    le même dossier pour les réels d'un compte (vidéos) et les stories d'un autre
    (images) ne range jamais deux fois le même fichier."""
    from agent import ranger as rangement
    groupes = {}
    for c, a in zip(comptes, analyses):
        for t in a["actifs"]:
            if not a["types"][t]["dossier_valide"]:
                continue
            d = c["sources"][t]
            g = groupes.setdefault((_norm(d), rangement.est_video(t)), {"dossier": d, "comptes": []})
            g["comptes"].append({"id": c["id"], "nom": c["nom"], "type": t})
    return [g for g in groupes.values() if len({u["id"] for u in g["comptes"]}) > 1]


def _total_types(analyses: list) -> dict:
    """Champ de tête « types » : la somme sur tous les comptes (même forme qu'avant)."""
    from agent import ranger as rangement
    if len(analyses) == 1:
        return analyses[0]["types"]
    total = {}
    for t in rangement.TYPES:
        parts = [a["types"][t] for a in analyses]
        concernes = [a["types"][t] for a in analyses if t in a["actifs"]] or parts
        tt = dict(parts[0])
        for cle in ("creneaux", "requis", "trouves", "ignores", "manque"):
            # Seulement les comptes qui ont besoin de ce type : le dossier d'un compte qui ne
            # s'en sert pas ne doit pas faire croire qu'il y a assez de médias (trouves ≥ requis).
            tt[cle] = sum(p[cle] for p in concernes)
        # Un dossier PAR compte : pas de dossier commun à afficher (voir « comptes »).
        tt.update({"actif": any(p["actif"] for p in parts), "dossier": None,
                   "dossier_valide": all(p["dossier_valide"] for p in concernes)})
        total[t] = tt
    return total


@commande("ranger_analyser")
def ranger_analyser(ctx, args):
    """Tout ce que l'ancienne app calculait AVANT sa fenêtre « Confirmer le rangement »,
    compte par compte (champ « comptes »), et le total dans les champs d'avant."""
    from agent import ranger as rangement
    comptes = _comptes_ranger(args)
    coches = _types_coches(args)
    # EXACTEMENT le même calcul que ranger_lancer (avec le repli sur le Bureau si le
    # dossier perso est inaccessible) : le chemin annoncé dans « Remplacer ? » est
    # celui qui sera vraiment remplacé.
    sortie = os.path.join(dossier_sortie(), "ranger")
    plusieurs = len(comptes) > 1
    analyses = [_analyser_compte(c, coches, sortie, _sortie_compte(sortie, c, plusieurs))
                for c in comptes]
    partages = _partages(comptes, analyses)

    def union(cle):
        return [t for t in rangement.TYPES if any(t in a[cle] for a in analyses)]

    actifs, manquants, dans_sortie = union("actifs"), union("manquants"), union("source_dans_sortie")
    doublons = []
    for a in analyses:
        doublons += [p for p in a["doublons"] if p not in doublons]
    incomplet = any(a["incomplet"] for a in analyses)
    erreurs = [_prefixe(c, plusieurs) + c["calendrier_erreur"]
               for c in comptes if c["calendrier_erreur"]]
    existe = os.path.exists(sortie)

    if plusieurs:
        blocs = []
        for a in analyses:
            if a["actifs"]:
                blocs.append("\n".join([f"{a['nom']} → {os.path.join('ranger', a['nom'])}"]
                                       + a["lignes"]))
            else:
                blocs.append(f"{a['nom']} : aucun type coché dans son calendrier (ignoré).")
        msg = "À ranger :\n\n" + "\n\n".join(blocs) + "\n"
        if partages:
            msg += ("\n⚠️ Même dossier pour plusieurs comptes (mêmes médias rangés plusieurs "
                    "fois) :\n" + "\n".join(
                        f"• {g['dossier']} : " + ", ".join(
                            f"{u['nom']} ({rangement.LIBELLES[u['type']]})" for u in g["comptes"])
                        for g in partages) + "\n")
        msg += f"\nDestination :\n{sortie}\n"
    else:
        msg = "À ranger :\n" + "\n".join(analyses[0]["lignes"]) + f"\n\nDestination :\n{sortie}\n"
    if incomplet:
        msg += "\n⚠️ Certains créneaux resteront incomplets.\n"
    if existe:
        msg += "\n⚠️ Ce dossier existe déjà et sera REMPLACÉ.\n"
    for a in analyses:
        del a["lignes"]
    return {"types": _total_types(analyses), "actifs": actifs, "sortie": sortie, "existe": existe,
            "manquants": manquants, "source_dans_sortie": dans_sortie,
            "doublons": doublons, "incomplet": incomplet,
            "calendrier_erreur": erreurs[0] if erreurs else None,
            "pret": bool(actifs) and not manquants and not dans_sortie and not erreurs,
            "message_confirmation": msg + "\nContinuer ?",
            "comptes": analyses, "partages": partages}


def _lignes_bilan(res: dict):
    """Lignes « • Réels : 8/10 vidéo(s)  ⚠️ il en manque 2 » d'un résultat de ranger()
    (copie de App._controle("fini_ranger")) -> (lignes, alerte)."""
    from agent import ranger as rangement
    lignes, alerte = [], False
    for t in res.get("types", []):
        unite = "vidéo(s)" if rangement.est_video(t) else "image(s)"
        requis = res["besoins"][t] * rangement.medias_par_creneau(t)
        ligne = f"• {rangement.LIBELLES[t]} : {res['places'][t]}/{requis} {unite}"
        if res["manques"].get(t):
            ligne += f"  ⚠️ il en manque {res['manques'][t]}"
            alerte = True
        lignes.append(ligne)
    return lignes, alerte


def _progression_compte(ctx, i: int, n: int, compte: dict, avant: int, creneaux: int,
                        total: int):
    """progress() d'UN compte quand il y en a plusieurs : 1re ligne « Compte 2/3 — @marie »,
    puis les lignes d'agent/ (Semaine/Jour/Créneau). La fraction devient GLOBALE (sur les
    créneaux de TOUS les comptes) : la barre ne repart pas à 0 à chaque compte.
    details.compte porte le nom COMPLET (c'est l'interface qui raccourcit)."""
    from agent import progression

    def progress(texte, fraction=None):
        t = TexteProgression(f"Compte {i}/{n} — {progression.court(compte['nom'], 26)}\n{texte}")
        details = getattr(texte, "details", None)
        t.details = dict(details) if isinstance(details, dict) else {"groupe": None, "element": None}
        t.details["compte"] = {"index": i, "total": n, "id": compte["id"], "nom": compte["nom"]}
        if fraction is not None:
            fraction = (avant + fraction * creneaux) / max(1, total)
        ctx.progress(t, fraction)
    return progress


def _somme_par_type(resultats: list, cle: str) -> dict:
    """{type: n} additionnés sur tous les comptes (besoins, places, surplus…)."""
    from agent import ranger as rangement
    total = {}
    for r in resultats:
        for t, v in (r.get(cle) or {}).items():
            total[t] = total.get(t, 0) + v
    return {t: total[t] for t in rangement.TYPES if t in total}


@commande("carrousels_preparer")
def carrousels_preparer(ctx, args):
    """Range les images d'un dossier en carrousel-1, carrousel-2… (3 images chacun, dans l'ordre),
    dans un NOUVEAU dossier « carrousels » du dossier de sortie (jamais un dossier remplacé :
    l'utilisateur va les retoucher). Ce dossier sert ensuite de source « Carrousels » au Ranger.
    Hors de « ranger » : ranger_lancer remplace ce dossier-là en entier."""
    from agent import ranger as rangement
    source = _chemin_absolu(args.get("source"), "source")
    if not os.path.isdir(source):
        raise ErreurCommande("SOURCE_INTROUVABLE", "Ce dossier est introuvable.", {"chemins": [source]})
    images = rangement.analyser_dossier(source, "image")["fichiers"]
    par = rangement.medias_par_creneau("carousel")
    if len(images) < par:
        raise ErreurCommande("SOURCE_VIDE",
                             f"Il faut au moins {par} images dans ce dossier "
                             f"({len(images)} trouvée(s)), posées directement dedans.",
                             {"chemins": [source], "images": len(images)})
    base = os.path.join(dossier_sortie(), "carrousels")
    sortie, i = base, 2
    while os.path.exists(sortie):          # « carrousels (2) »… : on n'écrase jamais
        sortie, i = f"{base} ({i})", i + 1
    if est_dans(source, sortie):
        raise _invalide("source", "Le dossier source est dans le dossier des carrousels.")
    try:
        res = rangement.preparer_carrousels(source, sortie)
    except Exception as e:
        raise _echec("Préparer les carrousels", e)
    return res


@commande("ranger_lancer", LONGUE)
def ranger_lancer(ctx, args):
    """Copie de App._lancer_ranger + message « fini_ranger », compte par compte."""
    from agent import ranger as rangement
    comptes = _comptes_ranger(args)
    aleatoire = _booleen(args, "aleatoire", True)
    completer = _booleen(args, "completer", False)   # médias manquants : réutiliser ceux qui sont là
    confirme = _confirmation(args)
    plusieurs = len(comptes) > 1
    # Tout est vérifié AVANT de toucher à l'ancienne sortie, pour TOUS les comptes
    # (sinon : sortie supprimée, puis plantage au 2e compte).
    for c in comptes:
        if c["calendrier_erreur"]:
            raise ErreurCommande("CALENDRIER_INVALIDE",
                                 _prefixe(c, plusieurs) + c["calendrier_erreur"],
                                 {"compte": c["id"]})
    coches = _types_coches(args)
    for c in comptes:
        c["actifs"] = _types_actifs(coches, c["n"])
    if not any(c["actifs"] for c in comptes):
        raise _invalide("types", "Cochez au moins un type de post (étape 1)." if not plusieurs
                        else "Aucun compte n'a de créneau pour les types cochés : cochez au moins "
                             "un type présent dans le calendrier d'un compte (étape 1).")
    for c in comptes:
        src = c["sources"]
        manquants = [t for t in c["actifs"] if not (src.get(t) and os.path.isdir(src[t]))]
        if manquants:
            titre = (f"Choisissez les dossiers de « {c['nom']} » pour :" if plusieurs
                     else "Choisissez un dossier pour :")
            raise ErreurCommande("SOURCE_INTROUVABLE", titre + "\n\n" + "\n".join(
                f"• {rangement.LIBELLES[t]}" for t in manquants),
                {"types": manquants, "chemins": [src.get(t) for t in manquants],
                 "compte": c["id"]})
    sortie = os.path.join(dossier_sortie(), "ranger")
    for c in comptes:
        for t in c["actifs"]:
            if est_dans(c["sources"][t], sortie):
                raise ErreurCommande("SOURCE_DANS_SORTIE",
                                     f"{_prefixe(c, plusieurs)}Le dossier des {_libelle_min(t)} "
                                     "est dans le dossier de sortie, qui va être remplacé. "
                                     "Choisissez un autre dossier.",
                                     {"sortie": sortie, "chemins": [c["sources"][t]], "types": [t],
                                      "compte": c["id"]})
    if ctx.doit_arreter():
        # Annulé juste après le clic : on ne supprime RIEN.
        return {"arrete": True, "creneaux": 0, "types": [], "sortie": sortie, "duree_s": 0.0,
                "comptes": [],
                "bilan": {"titre": "Ranger", "erreur": True,
                          "message": "Rangement arrêté.\n\nRien n'a été modifié."}}
    _remplacer_sortie(sortie, confirme)      # UNE fois, le dossier « ranger » entier
    debut = time.monotonic()

    a_ranger = [c for c in comptes if c["actifs"]]
    creneaux = {c["id"]: sum(c["n"][t] for t in c["actifs"]) for c in a_ranger}
    total = sum(creneaux.values())
    resultats, avant, k, arrete = [], 0, 0, False
    for c in comptes:
        base = {"id": c["id"], "nom": c["nom"], "sortie": _sortie_compte(sortie, c, plusieurs)}
        vide = dict(base, types=[], besoins={}, fournis={}, places={}, manques={},
                    incomplets={}, surplus={}, ignores={}, reutilises={}, creneaux=0)
        if not c["actifs"]:
            print(f"⏭ {c['nom']} : ignoré (aucun type coché dans son calendrier).", flush=True)
            resultats.append(dict(vide, arrete=False, aucun_type=True))
            continue
        if arrete or ctx.doit_arreter():
            # Annulé ENTRE deux comptes : les suivants ne sont pas commencés.
            arrete = True
            resultats.append(dict(vide, arrete=True, aucun_type=False))
            continue
        k += 1
        progress = ctx.progress            # 1 seul compte : progression identique à avant
        if plusieurs:
            print(f"\nCompte {k}/{len(a_ranger)} — {c['nom']}", flush=True)
            progress = _progression_compte(ctx, k, len(a_ranger), c, avant, creneaux[c["id"]],
                                           total)
        try:
            res = rangement.ranger({t: c["sources"][t] for t in c["actifs"]}, base["sortie"],
                                   c["actifs"], aleatoire=aleatoire, progress=progress,
                                   doit_arreter=ctx.doit_arreter, calendrier=c["calendrier"],
                                   completer=completer)
        except Exception as e:
            raise _echec("Ranger", e)
        avant += creneaux[c["id"]]
        arrete = bool(res.get("arrete"))
        r = dict(base)
        r.update(res)
        r["aucun_type"] = False
        resultats.append(r)

    # Champs de tête : même forme qu'avant (1 compte : le résultat de ranger() tel quel).
    if plusieurs:
        out = {"types": [t for t in rangement.TYPES if any(t in r["types"] for r in resultats)]}
        for cle in ("besoins", "fournis", "places", "manques", "incomplets", "surplus", "ignores",
                    "reutilises"):
            out[cle] = _somme_par_type(resultats, cle)
        out.update({"creneaux": sum(r["creneaux"] for r in resultats), "arrete": arrete})
    else:
        out = {cle: v for cle, v in resultats[0].items()
               if cle not in ("id", "nom", "sortie", "aucun_type")}

    # Message de fin : copie de App._controle("fini_ranger"), un bloc par compte s'il y en a 2+.
    if out["arrete"]:
        txt = f"Rangement arrêté.\n\n{out['creneaux']} créneau(x) déjà rangé(s) dans :\n{sortie}"
        if plusieurs:
            txt += "\n\n" + "\n".join(f"• {r['nom']} : {r['creneaux']} créneau(x)"
                                      for r in resultats if not r["aucun_type"])
        bilan = {"titre": "Ranger", "erreur": True, "message": txt}
    else:
        blocs, alerte = [], False
        for r in resultats:
            if r["aucun_type"]:
                blocs.append(f"{r['nom']} : ignoré (aucun type coché dans son calendrier).")
                continue
            lignes, manque = _lignes_bilan(r)
            alerte = alerte or manque
            blocs.append("\n".join(([f"{r['nom']} :"] if plusieurs else []) + lignes))
        txt = "Médias rangés !\n\n" + "\n\n".join(blocs) + f"\n\nDossier :\n{sortie}"
        en_trop = sum(out.get("surplus", {}).values())
        if en_trop:
            txt += (f"\n\n📦 {en_trop} média(s) en trop → dossiers « surplus » des comptes."
                    if plusieurs else f"\n\n📦 {en_trop} média(s) en trop → dossier « surplus ».")
        reutil = sum(out.get("reutilises", {}).values())
        if reutil:
            txt += f"\n\n♻️ {reutil} média(s) réutilisé(s) pour remplir tous les créneaux."
        bilan = {"titre": "Ranger", "message": txt, "erreur": alerte}
    out.update({"sortie": sortie, "duree_s": round(time.monotonic() - debut, 1),
                "bilan": bilan, "comptes": resultats})
    return out


# ═══════════════════════════════════════════════════════════════════════════
#  Compteur d'activité (agent/activite.py)
# ═══════════════════════════════════════════════════════════════════════════
def lancer_envoi_activite(delai_s: float = 0.0) -> None:
    """Envoie les compteurs au serveur des licences, dans un fil d'arrière-plan.

    Pourquoi un fil ? Hors-ligne, l'envoi peut attendre ~8 s : il ne doit jamais retarder
    la réponse d'une commande. Fil « daemon » : il ne bloque pas l'arrêt du moteur.
    Sans licence enregistrée (mode dev, tests), activite.envoyer() ne fait RIEN : aucun
    appel réseau. Deux envois ne tournent jamais en même temps (verrou dans activite.py)."""
    def envoyer():
        if delai_s > 0:
            time.sleep(delai_s)
        try:
            from agent import activite
            activite.envoyer()
        except Exception:
            pass        # jamais d'erreur visible : on réessaiera au prochain traitement
    try:
        threading.Thread(target=envoyer, name="activite", daemon=True).start()
    except Exception:
        pass


def _compter_activite(categorie: str, sources: list, n) -> None:
    """Ajoute ce qui a VRAIMENT été traité (même après un arrêt), SANS recompter un média
    déjà compté (empreinte), puis envoie au serveur. Ne fait JAMAIS échouer le traitement
    (voir activite.ajouter_medias)."""
    try:
        from agent import activite
        activite.ajouter_medias(categorie, sources, n)
    except Exception as e:
        print(f"⚠️ Compteur d'activité non mis à jour : {e}")
    lancer_envoi_activite()


@commande("activite_lire")
def activite_lire(ctx, args):
    """Activité de ce PC (carte « Votre activité » de l'Accueil) + partage : true si les
    compteurs sont envoyés à l'agence (une licence est enregistrée)."""
    from agent import activite
    out = activite.resume()
    out["partage"] = activite.partage()
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
    renommer = _booleen(args, "renommer", False)
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
            res = conversion.convertir_fichiers(fichiers, sortie, ctx.progress, ctx.doit_arreter,
                                                renommer=renommer)
        else:
            res = conversion.convertir_dossier(dossier, sortie, ctx.progress, ctx.doit_arreter,
                                               renommer=renommer)
    except Exception as e:
        raise _echec("Convertir en MP4", e)
    res["arrete"] = res.get("arrete") or ctx.doit_arreter()
    _compter_activite("videos", _lister_medias(dossier, fichiers, conversion.EXT_VIDEOS),
                      res.get("medias", 0))
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
    renommer = _booleen(args, "renommer", False)
    if ctx.doit_arreter():
        return _interrompu_avant("Images converties", sortie, f"image(s) en .{fmt}", {"format": fmt})
    _remplacer_sortie(sortie, confirme)
    debut = time.monotonic()
    try:
        if fichiers:
            res = unicite.convertir_images_fichiers(fichiers, sortie, fmt, progress=ctx.progress,
                                                    doit_arreter=ctx.doit_arreter, renommer=renommer)
        else:
            res = unicite.convertir_images_dossier(dossier, sortie, fmt, progress=ctx.progress,
                                                   doit_arreter=ctx.doit_arreter, renommer=renommer)
    except Exception as e:
        raise _echec("Convertir les images", e)
    res["arrete"] = ctx.doit_arreter()
    _compter_activite("images", _lister_medias(dossier, fichiers, unicite.EXT_IMAGES),
                      res.get("images", 0))
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
    _compter_activite("metadonnees",
                      _lister_medias(dossier, fichiers, unicite.EXT_IMAGES | unicite.EXT_VIDEOS),
                      res.get("medias", 0))
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
