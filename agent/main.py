"""
Point d'entrée de l'agent.

Utilisation (depuis le dossier du projet) :

  # Lister tes profils AdsPower (retrouver les user_id)
  python -m agent.main list

  # Vérifier la connexion à un profil (ouvre le navigateur, lit la page)
  python -m agent.main check k1fgl1fu

  # Poster (ajoute --essai pour tout faire SAUF publier)
  python -m agent.main post k1fgl1fu publication image.jpg      --legende "Coucou" --essai
  python -m agent.main post k1fgl1fu carrousel   img1.jpg img2.jpg --legende "Slides"
  python -m agent.main post k1fgl1fu reel        video.mp4       --legende "Mon reel"
"""

import sys
import argparse
from contextlib import contextmanager

from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options

from . import adspower
from . import instagram

# La console Windows est en cp1252 par défaut et plante sur les emojis.
# On force l'UTF-8 pour pouvoir afficher ✅ ❌ etc.
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass


@contextmanager
def navigateur_du_profil(user_id: str):
    """Démarre le profil AdsPower, s'y branche avec Selenium, et fournit
    un `driver` prêt à l'emploi.

    On NE ferme PAS le profil à la fin : on laisse AdsPower ouvert pour
    pouvoir vérifier le résultat à l'œil. (Le driver, lui, se détache.)
    """
    debugger_address, driver_path = adspower.demarrer_profil(user_id)
    print(f"[AdsPower] profil {user_id} démarré ({debugger_address}).", flush=True)

    options = Options()
    # On s'ATTACHE au navigateur déjà ouvert par AdsPower.
    options.add_experimental_option("debuggerAddress", debugger_address)
    # "eager" : on n'attend pas TOUTES les ressources (images, pubs...),
    # juste le DOM. Plus rapide et évite les blocages sur IP lente.
    options.page_load_strategy = "eager"
    # Accepte automatiquement les pop-ups natifs du navigateur
    # (ex: "Quitter le site ?") qui sinon bloquent tout le JavaScript.
    options.set_capability("unhandledPromptBehavior", "accept")
    driver = webdriver.Chrome(service=Service(executable_path=driver_path), options=options)
    # Un script JS ne doit jamais bloquer plus de 15s (sinon on abandonne).
    driver.set_script_timeout(15)
    print("[Selenium] attaché au navigateur.", flush=True)

    try:
        yield driver
    finally:
        # quit() détacherait/fermerait ; on préfère laisser le navigateur
        # ouvert. On ne fait donc rien ici volontairement.
        pass


def cmd_list():
    for profil in adspower.lister_profils():
        print(f"- {profil['name']:<20} user_id={profil['user_id']}  serial={profil['serial_number']}")


def cmd_check(user_id: str):
    with navigateur_du_profil(user_id) as driver:
        # Réessai simple si le réseau flanche au 1er chargement.
        for tentative in range(3):
            driver.get("https://www.instagram.com/")
            if "Instagram" in driver.title and "Impossible" not in driver.title:
                break
            print(f"[check] page pas chargée (essai {tentative + 1}/3), on retente...", flush=True)
            driver.implicitly_wait(3)
        print(f"URL actuelle : {driver.current_url}", flush=True)
        print(f"Titre page   : {driver.title}", flush=True)
        connecte = "/accounts/login" not in driver.current_url
        print("Connecté à Instagram :", "✅ oui" if connecte else "❌ non (login)", flush=True)


def cmd_post(user_id, type_post, fichiers, legende, essai):
    with navigateur_du_profil(user_id) as driver:
        if type_post == "publication":
            instagram.poster_publication(driver, fichiers[0], legende, essai)
        elif type_post == "carrousel":
            instagram.poster_carrousel(driver, fichiers, legende, essai)
        elif type_post == "reel":
            instagram.poster_reel(driver, fichiers[0], legende, essai)
        print("✅ Terminé.", flush=True)


def main():
    parser = argparse.ArgumentParser(description="Agent Insta via AdsPower")
    sous = parser.add_subparsers(dest="commande", required=True)

    sous.add_parser("list", help="Lister les profils AdsPower")

    p_check = sous.add_parser("check", help="Vérifier la connexion à un profil")
    p_check.add_argument("user_id")

    p_post = sous.add_parser("post", help="Publier un contenu")
    p_post.add_argument("user_id")
    p_post.add_argument("type", choices=["publication", "carrousel", "reel"])
    p_post.add_argument("fichiers", nargs="+")
    p_post.add_argument("--legende", default="")
    p_post.add_argument("--essai", action="store_true",
                        help="Fait tout le parcours SAUF le clic final Partager")

    p_ranger = sous.add_parser("ranger",
                               help="Range les médias (sources/) dans planning/ selon le calendrier")
    p_ranger.add_argument("--simuler", action="store_true",
                          help="Montre le rangement sans rien écrire")

    p_uniq = sous.add_parser("uniquiser",
                             help="Rend uniques (anti-détection) toutes les images d'un dossier")
    p_uniq.add_argument("dossier", help="Dossier à traiter (ex: planning ou sources/images)")

    args = parser.parse_args()

    if args.commande == "list":
        cmd_list()
    elif args.commande == "check":
        cmd_check(args.user_id)
    elif args.commande == "post":
        cmd_post(args.user_id, args.type, args.fichiers, args.legende, args.essai)
    elif args.commande == "ranger":
        from . import ranger as rangement
        rangement.ranger(simuler=args.simuler)
    elif args.commande == "uniquiser":
        from . import unicite
        n = unicite.uniquiser_dossier(args.dossier)
        print(f"✅ {n} image(s) uniquisée(s) dans {args.dossier}", flush=True)


if __name__ == "__main__":
    main()
