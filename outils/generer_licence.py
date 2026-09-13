"""
OUTIL PRIVÉ DU VENDEUR — ne jamais distribuer avec l'app.

Fabrique une licence pour un client à partir de l'EMPREINTE de son PC.

Usage :
    python outils/generer_licence.py <EMPREINTE> [vie|mois|an]

Exemples :
    python outils/generer_licence.py ABCD-EFGH-IJKL-MNOP vie
    python outils/generer_licence.py ABCD-EFGH-IJKL-MNOP mois
    python outils/generer_licence.py ABCD-EFGH-IJKL-MNOP an

Le comptage (mois/an) démarre AUJOURD'HUI (jour de génération).
Nécessite cle_privee.pem (créé par generer_paire_cles.py) dans ce dossier.
"""

import os
import sys
from datetime import date
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

# Permet d'importer le paquet `agent` quand on lance ce script depuis outils/.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from cryptography.hazmat.primitives import serialization
from agent import licence as L

ICI = os.path.dirname(os.path.abspath(__file__))
CHEMIN_PRIVEE = os.path.join(ICI, "cle_privee.pem")


def charger_cle_privee():
    with open(CHEMIN_PRIVEE, "rb") as f:
        return serialization.load_pem_private_key(f.read(), password=None)


def generer(empreinte: str, type_licence: str = "vie") -> str:
    cle = charger_cle_privee()
    payload = L.construire_payload(empreinte, type_licence, date.today())
    return L.encoder_licence(payload, cle.sign)


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage : python outils/generer_licence.py <EMPREINTE> [vie|mois|an]")
        raise SystemExit(1)
    if not os.path.isfile(CHEMIN_PRIVEE):
        print("❌ cle_privee.pem introuvable. Lance d'abord generer_paire_cles.py.")
        raise SystemExit(1)

    empreinte = sys.argv[1]
    type_licence = sys.argv[2].lower() if len(sys.argv) > 2 else "vie"
    if type_licence not in ("vie", "mois", "an"):
        print("Type invalide. Choisis : vie | mois | an")
        raise SystemExit(1)

    lic = generer(empreinte, type_licence)
    payload = L.construire_payload(empreinte, type_licence, date.today())
    print("Empreinte :", empreinte.strip().upper())
    print("Type      :", type_licence, "| expire :", payload.get("exp", "jamais (à vie)"))
    print("LICENCE (à renvoyer au client) :")
    print(lic)
