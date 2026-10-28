"""
Range les médias dans une arborescence de dossiers selon le calendrier.

Chaque TYPE de post a son propre dossier source :
  - Réels        -> uniquement des vidéos (1 par créneau)
  - Stories      -> uniquement des images (1 par créneau)
  - Stories CTA  -> uniquement des images (1 par créneau)
  - Carrousels   -> images nommées 1, 2, 3… prises DANS L'ORDRE par groupes
                    de IMAGES_PAR_CAROUSEL, OU un dossier de carrousels déjà
                    préparés (preparer_carrousels) : un sous-dossier = un carrousel

Résultat :
  <sortie>/semaine-XX/jour-Y/<ordre>_<heure>_<type>/  + les médias (rien d'autre)

L'utilisateur choisit quels types ranger : les créneaux des types décochés
ne sont pas créés. Les originaux ne sont jamais modifiés (copie).
"""

import os
import random
import re
import shutil

from . import progression
from .calendrier import charger_calendrier
from .config import IMAGES_PAR_CAROUSEL

EXT_IMAGES = {".jpg", ".jpeg", ".png", ".webp"}
EXT_VIDEOS = {".mp4", ".mov", ".m4v", ".avi", ".mkv"}

# Types de posts, dans l'ordre d'affichage.
TYPES = ("reel", "story", "story_cta", "carousel")
LIBELLES = {"reel": "Réels", "story": "Stories", "story_cta": "Stories CTA",
            "carousel": "Carrousels"}
# Libellé d'UN créneau (éditeur de calendrier).
LIBELLE_CRENEAU = {"reel": "Réel", "story": "Story", "story_cta": "Story CTA",
                   "carousel": "Carrousel"}
# Nom du type dans le dossier du créneau (ex. 3_21h00_story-cta).
NOM_DOSSIER = {"reel": "reel", "story": "story", "story_cta": "story-cta",
               "carousel": "carousel"}


def est_video(typ: str) -> bool:
    return typ == "reel"


def medias_par_creneau(typ: str) -> int:
    return IMAGES_PAR_CAROUSEL if typ == "carousel" else 1


def compter(calendrier: dict = None) -> dict:
    """Nombre de créneaux de chaque type dans le calendrier."""
    cal = charger_calendrier() if calendrier is None else calendrier
    n = {t: 0 for t in TYPES}
    for jours in cal.values():
        for creneaux in jours.values():
            for cr in creneaux:
                if cr.get("type") in n:
                    n[cr["type"]] += 1
    return n


def _cle_numerique(chemin: str):
    """Tri NUMÉRIQUE : 1, 2, …, 9, 10, 11 (et non 1, 10, 11, 2…)."""
    nom = os.path.splitext(os.path.basename(chemin))[0]
    m = re.match(r"\s*(\d+)", nom)
    return (0, int(m.group(1)), nom.lower()) if m else (1, 0, nom.lower())


def analyser_dossier(dossier: str, typ: str) -> dict:
    """Fichiers utilisables pour ce type + nombre de fichiers ignorés
    (ex. une image posée dans le dossier des réels)."""
    ext_ok = EXT_VIDEOS if est_video(typ) else EXT_IMAGES
    valides, ignores = [], 0
    if dossier and os.path.isdir(dossier):
        for f in os.listdir(dossier):
            p = os.path.join(dossier, f)
            if not os.path.isfile(p) or f.startswith("."):
                continue
            if os.path.splitext(f)[1].lower() in ext_ok:
                valides.append(p)
            else:
                ignores += 1
    valides.sort(key=_cle_numerique)
    groupes = None
    if typ == "carousel" and not valides:
        groupes = _groupes_carrousels(dossier)
        valides = [f for g in groupes for f in g]
    return {"fichiers": valides, "ignores": ignores, "groupes": groupes}


def _cle_groupe(chemin: str):
    """« carrousel-10 » après « carrousel-9 » : tri sur le DERNIER nombre du nom."""
    nom = os.path.basename(chemin)
    m = re.search(r"(\d+)\D*$", nom)
    return (0, int(m.group(1)), nom.lower()) if m else (1, 0, nom.lower())


def _groupes_carrousels(dossier: str) -> list:
    """Un dossier de carrousels déjà préparés : chaque sous-dossier qui contient des images est
    UN carrousel, rangé tel quel (l'utilisateur a pu en retoucher). Liste de listes de chemins."""
    groupes = []
    if not (dossier and os.path.isdir(dossier)):
        return groupes
    for nom in os.listdir(dossier):
        p = os.path.join(dossier, nom)
        if not os.path.isdir(p) or nom.startswith("."):
            continue
        images = [os.path.join(p, f) for f in os.listdir(p)
                  if os.path.isfile(os.path.join(p, f))
                  and os.path.splitext(f)[1].lower() in EXT_IMAGES]
        if images:
            images.sort(key=_cle_numerique)
            groupes.append((p, images))
    groupes.sort(key=lambda g: _cle_groupe(g[0]))
    return [images for _, images in groupes]


def preparer_carrousels(source: str, dossier_sortie: str, progress=None, doit_arreter=None) -> dict:
    """Répartit les images de `source` (dans l'ordre 1, 2, 3…) en sous-dossiers carrousel-1,
    carrousel-2… de IMAGES_PAR_CAROUSEL images, dans `dossier_sortie` (créé, jamais remplacé).
    Les images en trop (moins d'un carrousel complet) ne sont pas copiées. Originaux intacts."""
    images = analyser_dossier(source, "image")["fichiers"]
    n = len(images) // IMAGES_PAR_CAROUSEL
    os.makedirs(dossier_sortie, exist_ok=True)
    faits, arrete = 0, False
    for i in range(n):
        if doit_arreter and doit_arreter():
            arrete = True
            break
        if progress:
            try:
                progress(progression.texte("Carrousel", i + 1, n), i / max(1, n))
            except Exception:
                pass
        d = os.path.join(dossier_sortie, f"carrousel-{i + 1}")
        for f in images[i * IMAGES_PAR_CAROUSEL:(i + 1) * IMAGES_PAR_CAROUSEL]:
            _copier(f, d)
        faits += 1
    return {"sortie": dossier_sortie, "carrousels": faits, "images": len(images),
            "en_trop": len(images) - n * IMAGES_PAR_CAROUSEL, "arrete": arrete}


def _copier(source: str, dossier_dest: str):
    os.makedirs(dossier_dest, exist_ok=True)
    shutil.copy2(source, os.path.join(dossier_dest, os.path.basename(source)))


class _Distributeur:
    """Donne les médias d'UN type, créneau après créneau.

    completer=True : quand tout a été donné, on recommence au début (re-mélangé si `melanger`)
    pour que AUCUN créneau ne reste vide — c'est l'utilisateur qui l'a choisi.
    Un élément = un fichier, ou un groupe (liste) pour les carrousels préparés."""

    def __init__(self, elements: list, completer: bool, melanger: bool):
        self.elements = list(elements)
        self.completer, self.melanger = completer, melanger
        self.pos = 0
        self.utilises = set()
        self.reutilises = 0

    @staticmethod
    def _cle(x):
        return tuple(x) if isinstance(x, list) else x

    def _nouveau_tour(self):
        self.pos = 0
        if self.melanger:
            random.shuffle(self.elements)

    def prendre(self, k: int = 1, suivis: bool = False, eviter: set = None) -> list:
        """k éléments (moins s'il n'y en a plus). suivis=True (carrousel en vrac) : les k doivent se
        suivre ; s'il en reste moins de k, on repart du début plutôt que de mélanger la fin du
        dossier avec son début (les restes non utilisés iront dans « surplus »).
        eviter : ce qui a déjà servi CE jour-là (complété au passage) ; on prend plutôt le suivant
        qui n'y est pas. S'il n'y en a aucun autre (trop peu de médias), on prend quand même."""
        n = len(self.elements)
        if (suivis and self.completer and n >= k and 0 < n - self.pos < k):
            self._nouveau_tour()
        pris = []
        while len(pris) < k:
            if self.pos >= n:
                if not (self.completer and n):
                    break
                self._nouveau_tour()
            if eviter and not suivis and self._cle(self.elements[self.pos]) in eviter:
                for j in range(self.pos + 1, n):
                    if self._cle(self.elements[j]) not in eviter:
                        self.elements[self.pos], self.elements[j] = self.elements[j], self.elements[self.pos]
                        break
            x = self.elements[self.pos]
            self.pos += 1
            cle = self._cle(x)
            if cle in self.utilises:
                self.reutilises += 1
            self.utilises.add(cle)
            if eviter is not None:
                eviter.add(cle)
            pris.append(x)
        return pris

    def restes(self) -> list:
        """Les éléments jamais donnés (-> « surplus »)."""
        return [x for x in self.elements if self._cle(x) not in self.utilises]


def ranger(sources: dict, dossier_sortie: str, types_actifs=None,
           aleatoire: bool = True, progress=None, doit_arreter=None,
           calendrier: dict = None, completer: bool = False) -> dict:
    """Range les médias selon le calendrier, type par type.

    sources      : {type: dossier} — un dossier source par type de post.
    types_actifs : types à ranger (les autres créneaux ne sont pas créés).
    aleatoire    : mélange les réels / stories / stories CTA ; les carrousels
                   gardent TOUJOURS l'ordre 1, 2, 3… (photos qui se suivent).
    progress(texte, fraction): avancement, ex. « Semaine 1/3 — Jour 2 » +
                   « Créneau 5/87 · 1_10h00_reel », et la fraction 0 → 1.
    calendrier   : le calendrier à suivre (celui d'UN compte, module multi-comptes) ;
                   None -> le calendrier enregistré, comme avant (ancienne app).
    completer    : pas assez de médias -> réutiliser ceux qui sont là pour remplir TOUS les
                   créneaux (sinon, comme avant, les derniers restent vides).
    """
    choisis = TYPES if types_actifs is None else types_actifs
    actifs = [t for t in TYPES if t in choisis]
    if calendrier is None:
        calendrier = charger_calendrier()
    besoins = compter(calendrier)

    # medias[t] : les fichiers à distribuer, un par un. Carrousels déjà préparés : la liste des
    # GROUPES (un sous-dossier = un créneau entier), et fournis[t] compte quand même les images.
    medias, ignores, fournis, groupes = {}, {}, {}, set()
    for t in actifs:
        a = analyser_dossier(sources.get(t), t)
        fichiers = a["fichiers"]
        fournis[t] = len(fichiers)
        if a.get("groupes") is not None:
            # Carrousels préparés : l'ORDRE DES CARROUSELS est mélangé (chacun garde ses images
            # dans l'ordre) ; en vrac, on ne peut pas, les images 1-2-3 doivent rester ensemble.
            groupes.add(t)
            fichiers = list(a["groupes"])
            if aleatoire:
                random.shuffle(fichiers)
        elif aleatoire and t != "carousel":
            random.shuffle(fichiers)
        medias[t], ignores[t] = fichiers, a["ignores"]

    print("=== Rangement des médias ===", flush=True)
    print(f"Sortie : {os.path.abspath(dossier_sortie)}", flush=True)
    for t in actifs:
        unite = "vidéo(s)" if est_video(t) else "image(s)"
        requis = besoins[t] * medias_par_creneau(t)
        if t in groupes:
            print(f"{LIBELLES[t]} : {len(medias[t])} carrousel(s) préparé(s) | requis : "
                  f"{besoins[t]}", flush=True)
        else:
            print(f"{LIBELLES[t]} : {fournis[t]} {unite} fournie(s) | requises : {requis}",
                  flush=True)
    print("-" * 50, flush=True)

    total = sum(besoins[t] for t in actifs)
    distrib = {t: _Distributeur(medias[t], completer, aleatoire and (t != "carousel" or t in groupes))
               for t in actifs}
    places = {t: 0 for t in actifs}
    incomplets = {t: 0 for t in actifs}
    fait = 0
    arrete = False
    n_semaines = len(calendrier)

    def dire(txt, frac):
        if progress:
            try:
                progress(txt, max(0.0, min(1.0, frac)))
            except Exception:
                pass

    for i_sem, (nom_semaine, jours) in enumerate(calendrier.items(), start=1):
        for nom_jour, creneaux in jours.items():
            du_jour = [cr for cr in creneaux if cr.get("type") in actifs]
            # « jour-2 » -> « Jour 2 » pour l'affichage
            jour_aff = nom_jour.replace("jour-", "Jour ").replace("jour_", "Jour ")
            # Ce qui a déjà été posté CE jour-là : jamais le même média (ou carrousel) deux fois
            # le même jour, même quand on complète en réutilisant.
            du_jour_vus = {t: set() for t in actifs}
            for ordre, cr in enumerate(du_jour, start=1):
                if doit_arreter and doit_arreter():
                    arrete = True
                    break
                t = cr["type"]
                slot = f"{ordre}_{cr.get('heure', '')}_{NOM_DOSSIER[t]}"
                dire(progression.texte("Créneau", fait + 1, total, i_sem, n_semaines, jour_aff, slot,
                                       groupe="Semaine", toujours=True), fait / max(1, total))
                dossier_slot = os.path.join(dossier_sortie, nom_semaine, nom_jour, slot)
                os.makedirs(dossier_slot, exist_ok=True)

                if t in groupes:
                    g = (distrib[t].prendre(1, eviter=du_jour_vus[t]) or [[]])[0]
                    for f in g:
                        _copier(f, dossier_slot)
                    places[t] += len(g)
                    if not g:
                        incomplets[t] += 1
                else:
                    pris = distrib[t].prendre(medias_par_creneau(t), suivis=t == "carousel",
                                              eviter=du_jour_vus[t])
                    for f in pris:
                        _copier(f, dossier_slot)
                    places[t] += len(pris)
                    if len(pris) < medias_par_creneau(t):
                        incomplets[t] += 1

                fait += 1
            if arrete:
                break
        if arrete:
            break

    # Surplus : médias non utilisés -> surplus/<type>
    surplus = {}
    if not arrete:
        restes = {t: distrib[t].restes() for t in actifs}
        n_reste = sum(len(r) for r in restes.values())
        k = 0
        for t in actifs:
            if restes[t]:
                d = os.path.join(dossier_sortie, "surplus", LIBELLES[t])
                for f in restes[t]:
                    if doit_arreter and doit_arreter():
                        arrete = True
                        break
                    k += 1
                    if t in groupes:   # un carrousel préparé en trop : son sous-dossier entier
                        nom = os.path.basename(os.path.dirname(f[0]))
                        dire(progression.texte("Carrousel en trop", k, n_reste, fichier=nom), 1.0)
                        for img in f:
                            _copier(img, os.path.join(d, nom))
                    else:
                        dire(progression.texte("Média en trop", k, n_reste, fichier=os.path.basename(f)), 1.0)
                        _copier(f, d)
            surplus[t] = len(restes[t])
            if arrete:
                break

    manques = {t: (0 if completer and medias[t]
                   else max(0, besoins[t] - len(medias[t])) * medias_par_creneau(t) if t in groupes
                   else max(0, besoins[t] * medias_par_creneau(t) - len(medias[t])))
               for t in actifs}
    reutilises = {t: distrib[t].reutilises for t in actifs}
    if any(reutilises.values()) and not arrete:
        print("\n♻️  Médias réutilisés pour compléter :", flush=True)
        for t in actifs:
            if reutilises[t]:
                print(f"   - {LIBELLES[t]} : {reutilises[t]}", flush=True)
    if arrete:
        print("\n⛔ Rangement arrêté.", flush=True)
    elif any(incomplets.values()):
        print("\n⚠️  Créneaux incomplets (pas assez de médias) :", flush=True)
        for t in actifs:
            if incomplets[t]:
                print(f"   - {LIBELLES[t]} : {incomplets[t]} créneau(x)", flush=True)
    else:
        print("\n✅ Tous les créneaux ont reçu leurs médias.", flush=True)

    return {"types": actifs, "besoins": {t: besoins[t] for t in actifs},
            "fournis": fournis, "places": places,
            "manques": manques, "incomplets": incomplets, "surplus": surplus,
            "ignores": ignores, "creneaux": fait, "arrete": arrete, "reutilises": reutilises}
