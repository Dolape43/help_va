"""
À LANCER UNE SEULE FOIS (par toi, le vendeur).

Crée la paire de clés Ed25519 :
  - cle_privee.pem   -> TON secret. Ne le partage JAMAIS, ne le mets pas dans l'exe.
  - cle_publique.txt -> à coller dans agent/licence.py (constante CLE_PUBLIQUE_B64).

Avec la clé PRIVÉE tu fabriques les licences (outils/generer_licence.py).
L'app, elle, ne connaît que la clé PUBLIQUE et se contente de VÉRIFIER.
"""

import os
import sys
import base64
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives import serialization

ICI = os.path.dirname(os.path.abspath(__file__))
CHEMIN_PRIVEE = os.path.join(ICI, "cle_privee.pem")
CHEMIN_PUBLIQUE = os.path.join(ICI, "cle_publique.txt")

if os.path.exists(CHEMIN_PRIVEE):
    print("⚠️  cle_privee.pem existe déjà. Supprime-le d'abord si tu veux régénérer.")
    raise SystemExit(1)

privee = Ed25519PrivateKey.generate()

# Sauvegarde de la clé privée (format PEM, sur ton PC uniquement).
pem = privee.private_bytes(
    encoding=serialization.Encoding.PEM,
    format=serialization.PrivateFormat.PKCS8,
    encryption_algorithm=serialization.NoEncryption(),
)
with open(CHEMIN_PRIVEE, "wb") as f:
    f.write(pem)

# Clé publique : 32 octets bruts -> base64 (à embarquer dans l'app).
pub_brut = privee.public_key().public_bytes(
    encoding=serialization.Encoding.Raw,
    format=serialization.PublicFormat.Raw,
)
pub_b64 = base64.b64encode(pub_brut).decode()
with open(CHEMIN_PUBLIQUE, "w", encoding="utf-8") as f:
    f.write(pub_b64)

print("✅ Clés générées.")
print(f"   Privée  : {CHEMIN_PRIVEE}   (GARDE-LA SECRÈTE)")
print(f"   Publique: {CHEMIN_PUBLIQUE}")
print()
print("Clé publique à coller dans agent/licence.py :")
print(f'   CLE_PUBLIQUE_B64 = "{pub_b64}"')
