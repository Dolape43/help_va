"""
Licence liée à la machine (Ed25519) avec abonnement.

Une licence contient des DONNÉES signées (l'app ne peut que les vérifier) :
    { "emp": "<empreinte du PC>", "type": "vie"|"mois"|"an", "exp": "2026-09-07" }
  - "vie"  : pas de date de fin (marche même hors-ligne).
  - "mois"/"an" : date de fin "exp" -> vérifiée avec la VRAIE date (internet).

Format de la licence (texte) :  <donnees_base64url>.<signature_base64url>
Comme "emp" et "exp" sont DANS les données signées, l'utilisateur ne peut
ni les changer ni prolonger l'abonnement (sinon la signature casse).

L'app n'a que la clé PUBLIQUE : elle vérifie, elle ne fabrique pas.
Fichier d'activation : licence.key, à côté de l'exe.
"""

import os
import sys
import json
import base64
import hashlib
from datetime import date, datetime, timedelta, timezone

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
from cryptography.exceptions import InvalidSignature

# Clé PUBLIQUE du vendeur (générée par outils/generer_paire_cles.py).
CLE_PUBLIQUE_B64 = "6VLUlwjlGm+4OChalCm/fpdX/fJKSnjPyVldqWZp4No="

NOM_FICHIER_LICENCE = "licence.key"


# ----------------------------------------------------------- emplacements

from . import emplacement


def chemin_licence() -> str:
    """licence.key dans %APPDATA%\\HelpVA (migration auto depuis l'ancien lieu)."""
    return emplacement.chemin(NOM_FICHIER_LICENCE)


def supprimer_licence() -> bool:
    """Supprime la licence de ce PC (résiliation -> retour à l'activation).

    On efface la licence dans %APPDATA% ET l'éventuelle ancienne à côté de
    l'exe, sinon elle serait re-migrée au prochain démarrage.
    """
    ok = True
    cibles = (os.path.join(emplacement.dossier_donnees(), NOM_FICHIER_LICENCE),
              emplacement.chemin_ancien(NOM_FICHIER_LICENCE))
    for c in cibles:
        try:
            if os.path.isfile(c):
                os.remove(c)
        except Exception:
            ok = False
    return ok


# ------------------------------------------- licences résiliées (blocage local)
NOM_FICHIER_REVOQUEES = "licences_revoquees.txt"


def _fichier_revoquees() -> str:
    return os.path.join(emplacement.dossier_donnees(), NOM_FICHIER_REVOQUEES)


def _hash_licence(licence_txt: str) -> str:
    """Empreinte courte et stable d'une licence (pour la liste des résiliées)."""
    return hashlib.sha256(licence_txt.strip().encode("utf-8")).hexdigest()


def _charger_revoquees() -> set:
    try:
        with open(_fichier_revoquees(), encoding="utf-8") as f:
            return {ligne.strip() for ligne in f if ligne.strip()}
    except Exception:
        return set()


def revoquer_licence(licence_txt: str) -> None:
    """Marque une licence comme résiliée : elle ne pourra plus être recollée
    sur ce PC (blocage local, stocké dans les données utilisateur)."""
    if not licence_txt or not licence_txt.strip():
        return
    h = _hash_licence(licence_txt)
    if h in _charger_revoquees():
        return
    try:
        with open(_fichier_revoquees(), "a", encoding="utf-8") as f:
            f.write(h + "\n")
    except Exception:
        pass


def est_revoquee(licence_txt: str) -> bool:
    """True si cette licence a déjà été résiliée sur ce PC."""
    return _hash_licence(licence_txt) in _charger_revoquees()


# -------------------------------------- tolérance hors-ligne (contrôle serveur)
# L'app confirme l'accès auprès du serveur régulièrement. Si elle ne peut PAS
# joindre le serveur (hors-ligne), elle tolère quelques heures grâce à la
# dernière confirmation, puis se bloque tant qu'une connexion n'est pas revenue.
GRACE_HORS_LIGNE_H = float(os.environ.get("HELPVA_GRACE_H", "72"))  # 3 jours
NOM_FICHIER_CONFIRM = "derniere_verif.txt"


def _fichier_confirmation() -> str:
    return os.path.join(emplacement.dossier_donnees(), NOM_FICHIER_CONFIRM)


def _marquer_confirmation() -> None:
    """Mémorise l'instant de la dernière confirmation serveur (accès autorisé)."""
    try:
        with open(_fichier_confirmation(), "w", encoding="utf-8") as f:
            f.write(datetime.now(timezone.utc).isoformat())
    except Exception:
        pass


def _confirmation_recente() -> bool:
    """Vrai si le serveur a confirmé l'accès il y a moins de GRACE_HORS_LIGNE_H h."""
    try:
        with open(_fichier_confirmation(), encoding="utf-8") as f:
            t = datetime.fromisoformat(f.read().strip())
        if t.tzinfo is None:
            t = t.replace(tzinfo=timezone.utc)
        ecoule = (datetime.now(timezone.utc) - t).total_seconds()
        return 0 <= ecoule < GRACE_HORS_LIGNE_H * 3600
    except Exception:
        return False


def _statut_serveur(empreinte: str, cle_hash: str):
    """Interroge Supabase pour le statut d'une licence (révocation à distance).

    Renvoie un couple (joignable, statut) :
      - joignable : True si le serveur a répondu, False si hors-ligne.
      - statut : 'actif' | 'resiliee' | 'suspendu' | None (licence introuvable).
    """
    try:
        import requests
        from . import config
        r = requests.post(
            f"{config.SUPABASE_URL}/rest/v1/rpc/verifier_licence",
            headers={"apikey": config.SUPABASE_ANON,
                     "Authorization": f"Bearer {config.SUPABASE_ANON}",
                     "Content-Type": "application/json"},
            json={"p_empreinte": empreinte, "p_cle_hash": cle_hash},
            timeout=6)
        if r.status_code == 200:
            data = r.json()
            return True, (data[0].get("statut") if data else None)
    except Exception:
        pass
    return False, None


def _blocage_serveur(licence_txt: str, empreinte: str):
    """Contrôle d'accès auprès du serveur, avec tolérance hors-ligne.

    Renvoie un couple (bloc, hors_ligne) :
      - bloc : dict BLOQUANT, ou None si l'accès peut continuer.
      - hors_ligne : True si on tolère faute d'avoir pu joindre le serveur.

    - Serveur joignable :
        * 'resiliee'/'suspendu' -> bloque (réversible : réactiver côté serveur
          débloque au prochain contrôle) ;
        * sinon -> on mémorise la confirmation et on autorise.
    - Serveur injoignable (hors-ligne) :
        * on tolère (sans bloquer) tant que la dernière confirmation date de
          moins de GRACE_HORS_LIGNE_H heures ; au-delà -> bloque
          (raison 'pas_internet') pour forcer une reconnexion.
    """
    joignable, srv = _statut_serveur(empreinte, _hash_licence(licence_txt))
    if joignable:
        if srv == "resiliee":
            return ({"ok": False, "raison": "revoquee", "type": None,
                     "expire_le": None, "jours_restants": None}, False)
        if srv == "suspendu":
            return ({"ok": False, "raison": "suspendu", "type": None,
                     "expire_le": None, "jours_restants": None}, False)
        _marquer_confirmation()
        return (None, False)
    if _confirmation_recente():
        return (None, True)
    return ({"ok": False, "raison": "pas_internet", "type": None,
             "expire_le": None, "jours_restants": None}, True)


def activer_par_code(code: str):
    """Demande une licence au serveur avec un CODE d'activation.

    L'app envoie automatiquement son empreinte + le code ; le serveur génère
    la licence et la renvoie. Renvoie (licence_str | None, message).
    """
    try:
        import requests
        from . import config
        r = requests.post(
            f"{config.SUPABASE_URL}/functions/v1/admin",
            headers={"apikey": config.SUPABASE_ANON,
                     "Authorization": f"Bearer {config.SUPABASE_ANON}",
                     "Content-Type": "application/json"},
            json={"action": "activer", "code": code.strip().upper(),
                  "empreinte": empreinte_machine()},
            timeout=15)
        try:
            data = r.json()
        except Exception:
            return None, "Réponse du serveur invalide."
        if data.get("ok") and data.get("licence"):
            return data["licence"], "ok"
        return None, data.get("erreur", "Code invalide ou déjà utilisé.")
    except Exception:
        return None, "Pas de connexion au serveur."


# ----------------------------------------------------------- empreinte machine

def _machine_guid_windows() -> str:
    try:
        import winreg
        cle = winreg.OpenKey(
            winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Microsoft\Cryptography",
            0, winreg.KEY_READ | winreg.KEY_WOW64_64KEY)
        val, _ = winreg.QueryValueEx(cle, "MachineGuid")
        winreg.CloseKey(cle)
        return str(val)
    except Exception:
        return ""


def _machine_id_mac() -> str:
    """UUID matériel Apple (stable, propre à chaque Mac)."""
    try:
        import subprocess
        out = subprocess.run(
            ["ioreg", "-rd1", "-c", "IOPlatformExpertDevice"],
            capture_output=True, text=True, timeout=5).stdout
        for ligne in out.splitlines():
            if "IOPlatformUUID" in ligne:
                return ligne.split('"')[-2]
    except Exception:
        pass
    return ""


def _machine_id_linux() -> str:
    """Identifiant machine stable sous Linux."""
    for chemin in ("/etc/machine-id", "/var/lib/dbus/machine-id"):
        try:
            with open(chemin) as f:
                val = f.read().strip()
                if val:
                    return val
        except Exception:
            pass
    return ""


def _machine_id_reseau() -> str:
    """Repli universel : adresse matérielle (MAC) de la carte réseau."""
    try:
        import uuid
        return format(uuid.getnode(), "012x")
    except Exception:
        return ""


def empreinte_machine() -> str:
    """Empreinte lisible et stable de la machine : ABCD-EFGH-IJKL-MNOP.

    Source d'identifiant selon l'OS (Windows: MachineGuid, macOS:
    IOPlatformUUID, Linux: machine-id), avec repli sur l'adresse réseau.
    Le format de sortie et le hachage restent identiques sur tous les OS.
    """
    if sys.platform == "win32":
        base = _machine_guid_windows()
        if not base:
            base = (os.environ.get("COMPUTERNAME", "")
                    + "|" + os.environ.get("PROCESSOR_IDENTIFIER", ""))
    elif sys.platform == "darwin":
        base = _machine_id_mac() or _machine_id_reseau()
    else:
        base = _machine_id_linux() or _machine_id_reseau()
    digest = hashlib.sha256(("HelpVA::" + base).encode("utf-8")).digest()
    code = base64.b32encode(digest).decode("ascii").replace("=", "")[:16]
    return "-".join(code[i:i + 4] for i in range(0, 16, 4))


# ----------------------------------------------------------- encodage / décodage

def _b64url(donnees: bytes) -> str:
    return base64.urlsafe_b64encode(donnees).rstrip(b"=").decode("ascii")


def _de_b64url(txt: str) -> bytes:
    pad = "=" * (-len(txt) % 4)
    return base64.urlsafe_b64decode(txt + pad)


def _payload_bytes(payload: dict) -> bytes:
    """Représentation canonique (stable) des données à signer."""
    return json.dumps(payload, separators=(",", ":"), sort_keys=True,
                      ensure_ascii=False).encode("utf-8")


ESSAI_JOURS = 3   # durée par défaut d'une licence d'essai


def construire_payload(empreinte: str, type_licence: str, aujourd_hui: date,
                       jours: int = None, nom: str = None,
                       premium: bool = False) -> dict:
    """Prépare les données d'une licence (utilisé par le générateur).

    type_licence : "vie" | "mois" | "an" | "essai". Le comptage démarre
    AUJOURD'HUI (jour de génération). "essai" = licence courte (3 jours
    par défaut, ou `jours` si fourni).
    nom : nom du détenteur, GRAVÉ dans la licence signée (affiché chez le client).
    premium : True -> débloque l'automatisation des publications.
    """
    payload = {"emp": empreinte.strip().upper(), "type": type_licence}
    if nom and nom.strip():
        payload["nom"] = nom.strip()
    if premium:
        payload["premium"] = True
    if type_licence == "mois":
        payload["exp"] = _ajouter_mois(aujourd_hui, 1).isoformat()
    elif type_licence == "an":
        payload["exp"] = _ajouter_mois(aujourd_hui, 12).isoformat()
    elif type_licence == "essai":
        payload["exp"] = (aujourd_hui + timedelta(days=jours or ESSAI_JOURS)).isoformat()
    # "vie" -> pas de "exp"
    return payload


def _ajouter_mois(d: date, n: int) -> date:
    """Ajoute n mois à une date (gère les fins de mois)."""
    mois_total = d.month - 1 + n
    annee = d.year + mois_total // 12
    mois = mois_total % 12 + 1
    # jour valide pour le mois cible (28-31)
    jours_mois = [31, 29 if (annee % 4 == 0 and (annee % 100 != 0 or annee % 400 == 0)) else 28,
                  31, 30, 31, 30, 31, 31, 30, 31, 30, 31][mois - 1]
    return date(annee, mois, min(d.day, jours_mois))


def encoder_licence(payload: dict, signer) -> str:
    """Fabrique la licence texte. `signer(bytes)->bytes` = clé privée du vendeur."""
    pb = _payload_bytes(payload)
    partie_donnees = _b64url(pb)
    signature = signer(partie_donnees.encode("ascii"))
    return partie_donnees + "." + _b64url(signature)


def decoder_licence(licence: str):
    """Vérifie la signature et renvoie les données (dict), ou None si invalide."""
    try:
        partie_donnees, partie_sig = licence.strip().split(".", 1)
        signature = _de_b64url(partie_sig)
        cle = Ed25519PublicKey.from_public_bytes(base64.b64decode(CLE_PUBLIQUE_B64))
        cle.verify(signature, partie_donnees.encode("ascii"))
        return json.loads(_de_b64url(partie_donnees).decode("utf-8"))
    except (InvalidSignature, ValueError, Exception):
        return None


# ----------------------------------------------------------- statut / vérification

def verifier() -> dict:
    """Évalue la licence présente. Renvoie un statut :

    {
      "ok": bool,
      "raison": "actif"|"pas_active"|"invalide"|"mauvais_pc"|"expire"|"pas_internet",
      "type": "vie"|"mois"|"an"|None,
      "expire_le": date|None,
      "jours_restants": int|None,
    }
    """
    chemin = chemin_licence()
    if not os.path.isfile(chemin):
        return {"ok": False, "raison": "pas_active", "type": None,
                "expire_le": None, "jours_restants": None}
    try:
        with open(chemin, encoding="utf-8") as f:
            licence = f.read().strip()
    except Exception:
        return {"ok": False, "raison": "invalide", "type": None,
                "expire_le": None, "jours_restants": None}

    payload = decoder_licence(licence)
    if payload is None:
        return {"ok": False, "raison": "invalide", "type": None,
                "expire_le": None, "jours_restants": None}
    nom = payload.get("nom")
    premium = bool(payload.get("premium"))
    if payload.get("emp") != empreinte_machine():
        return {"ok": False, "raison": "mauvais_pc", "type": payload.get("type"),
                "expire_le": None, "jours_restants": None, "nom": nom, "premium": premium}
    bloc, hors_ligne = _blocage_serveur(licence, payload.get("emp"))
    if bloc:
        bloc["type"] = payload.get("type")
        return bloc

    type_l = payload.get("type", "vie")
    exp = payload.get("exp")

    # À vie : rien à vérifier en ligne (marche hors-ligne).
    if type_l == "vie" or not exp:
        return {"ok": True, "raison": "actif", "type": "vie",
                "expire_le": None, "jours_restants": None, "nom": nom,
                "premium": premium, "hors_ligne": hors_ligne}

    # Mois / an : il FAUT la vraie date (internet).
    # "exp" peut être une DATE (produit) ou un DATETIME ISO (tests à la minute).
    precis = "T" in exp
    try:
        if precis:
            exp_dt = datetime.fromisoformat(exp)
            if exp_dt.tzinfo is None:
                exp_dt = exp_dt.replace(tzinfo=timezone.utc)
        else:
            exp_date = date.fromisoformat(exp)
    except Exception:
        return {"ok": False, "raison": "invalide", "type": type_l,
                "expire_le": None, "jours_restants": None}

    from . import horloge
    maintenant = horloge.date_reelle()   # datetime aware UTC, ou None
    if maintenant is None:
        # Hors-ligne mais dans la tolérance (sinon _blocage_serveur aurait déjà
        # bloqué) : on laisse travailler ; l'expiration sera revérifiée dès le
        # retour de la connexion.
        return {"ok": True, "raison": "actif", "type": type_l,
                "expire_le": (exp_dt.date() if precis else exp_date),
                "jours_restants": None, "nom": nom, "premium": premium,
                "hors_ligne": True}

    # Expiration EXACTE : aucune tolérance après la date de fin.
    if precis:
        actif = maintenant <= exp_dt
        jours = (exp_dt - maintenant).days
        expire_le = exp_dt.date()
    else:
        actif = maintenant.date() <= exp_date
        jours = (exp_date - maintenant.date()).days
        expire_le = exp_date

    return {"ok": actif, "raison": "actif" if actif else "expire",
            "type": type_l, "expire_le": expire_le, "jours_restants": jours,
            "nom": nom, "premium": premium, "hors_ligne": False}


def enregistrer_licence(licence: str) -> dict:
    """Vérifie (signature + PC) puis enregistre. Renvoie le statut verifier()."""
    payload = decoder_licence(licence)
    if payload is None:
        return {"ok": False, "raison": "invalide", "type": None,
                "expire_le": None, "jours_restants": None}
    if payload.get("emp") != empreinte_machine():
        return {"ok": False, "raison": "mauvais_pc", "type": payload.get("type"),
                "expire_le": None, "jours_restants": None}
    bloc, _ = _blocage_serveur(licence, payload.get("emp"))
    if bloc:
        bloc["type"] = payload.get("type")
        return bloc
    try:
        with open(chemin_licence(), "w", encoding="utf-8") as f:
            f.write(licence.strip())
    except Exception:
        return {"ok": False, "raison": "invalide", "type": None,
                "expire_le": None, "jours_restants": None}
    return verifier()
