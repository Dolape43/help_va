"""
Offre gratuite : un PC sans licence peut traiter QUOTA médias (50 par défaut) avant de
devoir entrer un code d'activation.

Le compte est tenu par le SERVEUR (table `essais`, voir
supabase/migrations/20261028_essai_gratuit.sql), par PC (empreinte_machine) :
réinstaller HelpVA ne remet pas le compteur à zéro. L'essai demande donc internet.

Un média est reconnu par son empreinte (activite.empreinte : taille + début + fin du
fichier) : retraiter le même média, même renommé, ne recompte pas.

Avant chaque traitement, le moteur RÉSERVE les médias du traitement (reserver()) : si les
nouveaux dépassent ce qui reste, le traitement ne démarre pas (choix de Christ : on refuse
plutôt que de traiter à moitié).
"""

QUOTA = 50          # seulement pour les messages : le vrai quota est côté serveur
DELAI_RESEAU_S = 8


def _rpc(fonction: str, corps: dict):
    """Appel d'une fonction SQL de Supabase. Renvoie le JSON, ou None (hors-ligne, refus…).
    Tests automatiques (jamais dans l'exe) : aucun appel au vrai serveur, comme hors-ligne."""
    import os
    import sys
    if not getattr(sys, "frozen", False) and os.environ.get("HELPVA_MOTEUR_TESTS") == "1":
        return None
    try:
        import requests
        from . import config
        r = requests.post(
            f"{config.SUPABASE_URL}/rest/v1/rpc/{fonction}",
            headers={"apikey": config.SUPABASE_ANON,
                     "Authorization": f"Bearer {config.SUPABASE_ANON}",
                     "Content-Type": "application/json"},
            json=corps, timeout=DELAI_RESEAU_S)
        if r.status_code == 200:
            data = r.json()
            return data if isinstance(data, dict) else None
    except Exception:
        pass
    return None


def _propre(data) -> dict:
    """Réponse du serveur -> {quota, utilises, restant} en entiers (+ ok, nouveaux si présents)."""
    out = {}
    for cle in ("quota", "utilises", "restant", "nouveaux"):
        v = data.get(cle)
        if isinstance(v, (int, float)) and not isinstance(v, bool):
            out[cle] = max(0, int(v))
    if "ok" in data:
        out["ok"] = data.get("ok") is True
    out.setdefault("quota", QUOTA)
    out.setdefault("utilises", 0)
    out.setdefault("restant", max(0, out["quota"] - out["utilises"]))
    return out


def statut():
    """{quota, utilises, restant} de ce PC, ou None si le serveur n'a pas pu être joint."""
    from .licence import empreinte_machine
    data = _rpc("essai_statut", {"p_empreinte": empreinte_machine()})
    return _propre(data) if data is not None else None


def empreintes(chemins) -> list:
    """Empreintes distinctes des médias lisibles (un fichier illisible échouera de toute
    façon au traitement : il ne compte pas)."""
    from .activite import empreinte
    vues = []
    for c in chemins:
        e = empreinte(c)
        if e and e not in vues:
            vues.append(e)
    return vues


def reserver(chemins):
    """Réserve les médias d'un traitement. Renvoie {ok, quota, utilises, restant, nouveaux},
    ou None si le serveur n'a pas pu être joint.

    Plus de médias que le quota entier : refusé sans rien lire ni rien envoyer (même si
    certains étaient déjà comptés, les nouveaux dépassent forcément ce qui reste)."""
    from .licence import empreinte_machine
    chemins = list(chemins)
    if len(chemins) > QUOTA:
        st = statut()
        if st is None:
            return None
        if len(chemins) > st["quota"]:
            return {**st, "ok": False, "nouveaux": max(0, len(chemins) - st["utilises"])}
    data = _rpc("essai_reserver", {"p_empreinte": empreinte_machine(),
                                   "p_medias": empreintes(chemins)})
    return _propre(data) if data is not None else None
