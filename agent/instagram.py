"""
Actions Instagram via l'interface web, pilotées par Selenium.

⚠️ Instagram change souvent son interface. Les "repères" (textes/labels
des boutons) peuvent casser. Si un clic ne marche plus, ajuste les listes
de textes ci-dessous.

Points clés appris à l'usage :
- On CLIQUE en JavaScript (el.click()), car le clic Selenium classique
  bloque sur certains éléments d'Instagram.
- On avance en cliquant "Suivant" JUSQU'À voir "Partager" (le nombre
  d'écrans intermédiaires peut varier).

`essai=True` fait tout SAUF le clic final "Partager".
"""

import json
import os
import random
import subprocess
import sys
import time

from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import WebDriverException

from .config import DELAI_ACTIONS


# --- Journal de diagnostic Inssist écrit dans un FICHIER (pour debug fiable) ---
_DEBUG_FICHIER = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "inssist_debug.log")


def _log(msg: str, reset: bool = False):
    """Affiche dans le journal ET écrit dans inssist_debug.log (debug fiable)."""
    print(msg, flush=True)
    try:
        with open(_DEBUG_FICHIER, "w" if reset else "a", encoding="utf-8") as f:
            f.write(msg + "\n")
    except Exception:
        pass


# --- Arrêt propre : l'app pose un « faut-il arrêter ? » pour interrompre vite
#     les boucles de réessai (accueil, composer, partager) quand on clique Arrêter.
_doit_arreter = None


def definir_arret(fn):
    """fn() -> bool. Quand fn() renvoie True, la publication en cours s'arrête."""
    global _doit_arreter
    _doit_arreter = fn


def _stop():
    if _doit_arreter and _doit_arreter():
        raise RuntimeError("Automatisation arrêtée par l'utilisateur.")


def _copier_presse_papier(texte: str) -> bool:
    """Met le texte dans le presse-papier Windows (gère les emojis).

    Utilise PowerShell (aucune dépendance externe). Retourne True si OK.
    """
    try:
        ps = ("[Console]::InputEncoding=[System.Text.Encoding]::UTF8; "
              "$t=[Console]::In.ReadToEnd(); Set-Clipboard -Value $t")
        flags = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
        subprocess.run(
            ["powershell", "-NoProfile", "-STA", "-Command", ps],
            input=texte.encode("utf-8"),
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            creationflags=flags, timeout=15,
        )
        return True
    except Exception as e:
        print(f"[legende] presse-papier échoué : {e}", flush=True)
        return False


def _js(driver, script, *args):
    """Exécute un script JS sans jamais faire planter l'agent.

    Si le navigateur est momentanément bloqué (pop-up natif, page occupée),
    on renvoie None au lieu de lever une exception : la boucle appelante
    réessaiera d'elle-même.
    """
    try:
        return driver.execute_script(script, *args)
    except WebDriverException:
        return None

# Textes des boutons (français + anglais, selon la langue du compte).
TXT_SUIVANT = ["Suivant", "Next"]
TXT_PARTAGER = ["Partager", "Share"]
TXT_OK = ["OK", "Ok"]
LBL_CREER = ["Nouvelle publication", "New post", "Créer", "Create"]


def _pause():
    time.sleep(random.uniform(*DELAI_ACTIONS))


# --- Petites briques JavaScript, robustes ---

def _texte_present(driver, textes: list[str]) -> bool:
    """Vrai si un bouton portant l'un de ces textes est visible."""
    return bool(_js(
        driver,
        """
        const wanted = arguments[0];
        const els = document.querySelectorAll('button, [role=button]');
        for (const el of els) {
            const t = (el.innerText || '').trim();
            if (wanted.includes(t) && el.offsetParent !== null) return true;
        }
        return false;
        """,
        textes,
    ))


def _cliquer_texte(driver, textes: list[str]) -> bool:
    """Clique (en JS) le premier bouton portant l'un de ces textes."""
    return bool(_js(
        driver,
        """
        const wanted = arguments[0];
        const els = document.querySelectorAll('button, [role=button]');
        for (const el of els) {
            const t = (el.innerText || '').trim();
            if (wanted.includes(t) && el.offsetParent !== null) { el.click(); return true; }
        }
        return false;
        """,
        textes,
    ))


def _attendre_texte(driver, textes: list[str], delai=30) -> bool:
    """Attend qu'un bouton portant l'un de ces textes apparaisse."""
    fin = time.time() + delai
    while time.time() < fin:
        if _texte_present(driver, textes):
            return True
        time.sleep(1)
    return False


def _file_input_present(driver) -> bool:
    return bool(_js(
        driver,
        "return !!document.querySelector('input[type=file]');",
    ))


def _attendre_file_input(driver, delai: int) -> bool:
    fin = time.time() + delai
    while time.time() < fin:
        if _file_input_present(driver):
            return True
        time.sleep(0.5)
    return False


def _clic_icone_creer(driver) -> bool:
    """Clique le bouton « Créer / Nouvelle publication » d'Instagram.

    Robuste : d'abord par aria-label (svg OU élément), puis repli par le
    TEXTE visible du lien de navigation (« Créer » / « Create »).
    """
    return bool(_js(
        driver,
        """
        const labels = arguments[0];
        // 1) aria-label sur un svg
        for (const lab of labels) {
            const svg = document.querySelector(`svg[aria-label="${lab}"]`);
            if (svg) {
                const el = svg.closest('a,[role=link],[role=button],div[role=button]');
                if (el) { el.click(); return true; }
            }
        }
        // 2) aria-label sur n'importe quel élément
        for (const lab of labels) {
            const el = document.querySelector(`[aria-label="${lab}"]`);
            if (el) {
                const cible = el.closest('a,[role=link],[role=button],div[role=button]') || el;
                cible.click(); return true;
            }
        }
        // 3) repli : texte visible du lien de nav
        const norm = s => (s||'').replace(/\\s+/g,' ').trim().toLowerCase();
        const want = labels.map(norm);
        for (const a of document.querySelectorAll('a[role=link], a, [role=button], div[role=button], span')) {
            if (want.includes(norm(a.innerText)) && a.offsetParent !== null) {
                a.click(); return true;
            }
        }
        return false;
        """,
        LBL_CREER,
    ))


def _dump_aria_creer(driver):
    """Écrit dans le journal-fichier les aria-labels de la barre latérale
    (aide si « Créer » n'est pas trouvé)."""
    labels = _js(
        driver,
        """
        const acc = [];
        for (const e of document.querySelectorAll('[aria-label]')) {
            const l = e.getAttribute('aria-label');
            if (l && e.getClientRects().length) acc.push(l);
        }
        return [...new Set(acc)].slice(0, 40).join(' | ');
        """,
    )
    _log(f"[post/inssist] aria-labels visibles : {labels}")


def _fermer_popups(driver):
    """Ferme les pop-ups Instagram qui gênent (Plus tard, Not Now…)."""
    _cliquer_texte(driver, ["Plus tard", "Not Now", "Pas maintenant"])


def _ouvrir_composer(driver):
    """Ouvre le composer et s'assure que le champ fichier est présent.

    Robuste : ferme les pop-ups, cherche l'icône 'Créer', et si ça échoue
    RECHARGE la page d'accueil et réessaie (au lieu d'abandonner).
    """
    for tentative in range(3):
        _stop()
        _fermer_popups(driver)

        # Cherche/clique l'icône "Créer" (attente jusqu'à 12s).
        clique = False
        fin = time.time() + 12
        while time.time() < fin:
            _stop()
            if _clic_icone_creer(driver):
                clique = True
                break
            time.sleep(1)

        if clique:
            if _attendre_file_input(driver, 12):
                return
            # Certaines versions affichent d'abord un menu : on clique 'Publication'.
            _cliquer_texte(driver, ["Publication", "Post"])
            if _attendre_file_input(driver, 8):
                return

        # Échec de cette tentative : on recharge l'accueil et on réessaie.
        print(f"[post] composer non ouvert (essai {tentative + 1}/3), rechargement…", flush=True)
        try:
            _aller_accueil(driver)
        except Exception:
            pass
        time.sleep(2)

    raise RuntimeError(
        "Impossible d'ouvrir le composer. Vérifie dans le profil AdsPower "
        "qu'Instagram est bien CONNECTÉ (pas déconnecté, pas de vérification "
        "de sécurité en cours).")


def _charger_fichiers(driver, fichiers: list[str]):
    """Envoie les chemins au champ fichier (caché) du dialogue."""
    chemins = "\n".join(os.path.abspath(f) for f in fichiers)
    champ = WebDriverWait(driver, 30).until(
        EC.presence_of_element_located((By.XPATH, "//input[@type='file']"))
    )
    champ.send_keys(chemins)


def _lire_legende(driver) -> str:
    """Relit le texte actuellement présent dans le champ légende."""
    return _js(
        driver,
        "const el=document.querySelector('div[role=dialog] [contenteditable=\"true\"]');"
        "return el ? el.innerText : '';",
    ) or ""


def _ecrire_legende(driver, legende: str):
    """Écrit la légende dans le champ (éditeur Lexical d'Instagram).

    Point CLÉ : l'éditeur Lexical garde son propre état interne. Insérer du
    texte dans le DOM ne suffit pas (il apparaît mais n'est pas "enregistré"
    -> publication sans légende). La méthode FIABLE = un vrai COLLER :
      1. localiser le champ, le rendre visible, lire ses coordonnées ;
      2. VRAI clic souris (CDP) -> curseur posé dans l'éditeur ;
      3. mettre la légende dans le presse-papier (pyperclip) ;
      4. Ctrl+V -> événement "paste" authentique que Lexical gère nativement
         (et qui gère les emojis) ;
      5. si le collage échoue, repli sur CDP Input.insertText ;
      6. relecture de contrôle.
    """
    if not legende:
        return
    time.sleep(1)   # laisse le champ se stabiliser

    SEL = 'div[role=dialog] [contenteditable="true"]'

    # 1) Focus FIABLE via JS (sans coordonnées — le clic par coordonnées
    #    tombait parfois à côté et rien ne s'insérait).
    focus_ok = _js(
        driver,
        f"""
        const el = document.querySelector('{SEL}');
        if (!el) return false;
        el.scrollIntoView({{block: 'center'}});
        el.focus();
        return document.activeElement === el;
        """,
    )
    if not focus_ok:
        print("[avertissement] champ légende introuvable/non focalisable.")
        return
    time.sleep(0.2)

    cible = legende.strip()

    def _ok():
        # Comparaison EXACTE : détecte aussi les doublons ("textetexte").
        return _lire_legende(driver).strip() == cible

    def _vider():
        """Vide le champ via de vrais événements clavier (Lexical les honore)."""
        try:
            (ActionChains(driver)
                .key_down(Keys.CONTROL).send_keys("a").key_up(Keys.CONTROL)
                .send_keys(Keys.DELETE).perform())
            time.sleep(0.3)
        except Exception:
            pass

    # On part TOUJOURS d'un champ vide (évite la concaténation/doublons).
    _vider()

    # 2) Presse-papier + Ctrl+V (paste authentique, Lexical l'enregistre).
    if _mettre_presse_papier(legende):
        try:
            ActionChains(driver).key_down(Keys.CONTROL).send_keys("v").key_up(Keys.CONTROL).perform()
            time.sleep(0.8)
        except Exception as e:
            print(f"[legende] Ctrl+V échoué : {e}", flush=True)

    # 3) Repli : on VIDE d'abord, puis CDP Input.insertText.
    if not _ok():
        _vider()
        try:
            driver.execute_cdp_cmd("Input.insertText", {"text": legende})
            time.sleep(0.5)
        except Exception as e:
            print(f"[legende] insertText échoué : {e}", flush=True)

    # 5) NUDGE clavier : taper un espace puis l'effacer (vrais événements
    #    clavier) force Lexical à propager le texte à l'état de soumission
    #    (sinon le collage seul reste "visuel" et Partager envoie du vide).
    try:
        driver.execute_cdp_cmd("Input.dispatchKeyEvent", {"type": "char", "text": " "})
        time.sleep(0.15)
        for t in ("rawKeyDown", "keyUp"):
            driver.execute_cdp_cmd("Input.dispatchKeyEvent",
                                   {"type": t, "key": "Backspace",
                                    "windowsVirtualKeyCode": 8, "nativeVirtualKeyCode": 8})
        time.sleep(0.25)
    except Exception:
        pass

    # Vérification finale.
    if not _ok():
        print(f"[AVERTISSEMENT] la légende ne s'est PAS insérée (lu: {_lire_legende(driver)!r}).", flush=True)
    else:
        print("[post] légende insérée. ✅", flush=True)


def _mettre_presse_papier(texte: str) -> bool:
    """Met le texte dans le presse-papier (pyperclip, repli PowerShell)."""
    try:
        import pyperclip
        pyperclip.copy(texte)
        return True
    except Exception:
        return _copier_presse_papier(texte)


def _page_contient(driver, textes: list[str]) -> bool:
    """Vrai si le texte de la page contient l'un de ces fragments."""
    return bool(_js(
        driver,
        "const w=arguments[0];const t=(document.body?document.body.innerText:'');"
        "return w.some(x=>t.includes(x));",
        textes,
    ))


# Textes affichés une fois la publication réellement partie.
TXT_CONFIRME = [
    "Votre publication a été partagée", "Your post has been shared",
    "a été partagé", "has been shared", "Publication partagée", "Post shared",
]


def _clic_partager_brut(driver) -> bool:
    """Un seul clic sur 'Partager' : vrai clic souris (CDP), repli clic JS."""
    coords = _js(
        driver,
        """
        const W = arguments[0];
        for (const b of document.querySelectorAll('div[role=dialog] button, [role=button]')) {
            if (W.includes((b.innerText || '').trim()) && b.offsetParent !== null) {
                const r = b.getBoundingClientRect();
                return {x: r.x + r.width / 2, y: r.y + r.height / 2};
            }
        }
        return null;
        """,
        TXT_PARTAGER,
    )
    if not coords:
        return _cliquer_texte(driver, TXT_PARTAGER)
    for ev in ("mouseMoved", "mousePressed", "mouseReleased"):
        p = {"type": ev, "x": coords["x"], "y": coords["y"]}
        if ev != "mouseMoved":
            p.update({"button": "left", "clickCount": 1, "buttons": 1})
        driver.execute_cdp_cmd("Input.dispatchMouseEvent", p)
    return True


def _partager_et_verifier(driver) -> bool:
    """Clique 'Partager' PUIS vérifie que la publication est bien partie.

    On ne se fie plus au simple clic : on attend une preuve réelle
    (message de confirmation, ou disparition durable du bouton Partager).
    Jusqu'à 3 tentatives, en alternant clic souris (CDP) et clic JS.
    Retourne True seulement si la publication est confirmée.
    """
    for essai in range(3):
        _stop()
        if essai == 0:
            _clic_partager_brut(driver)      # vrai clic souris
        else:
            _cliquer_texte(driver, TXT_PARTAGER)  # clic JS direct

        # Attente d'une preuve de publication (max 45 s : une vidéo est lente).
        fin = time.time() + 45
        while time.time() < fin:
            _stop()
            if _page_contient(driver, TXT_CONFIRME):
                print("[post] publication confirmée. ✅", flush=True)
                return True
            # Le bouton Partager a disparu ET aucun champ légende visible
            # => l'écran de création s'est fermé = publié.
            if not _texte_present(driver, TXT_PARTAGER):
                time.sleep(3)
                if not _texte_present(driver, TXT_PARTAGER):
                    print("[post] écran de création fermé = publié. ✅", flush=True)
                    return True
            time.sleep(1)

        print(f"[post] 'Partager' sans effet (essai {essai + 1}/3), on réessaie…", flush=True)

    return False


def _aller_accueil(driver):
    """Charge la page d'accueil Instagram, avec réessais.

    L'IP peut flancher ("Impossible de charger la page") : on retente
    jusqu'à ce que l'icône 'Créer' soit présente (signe que c'est chargé).
    """
    for tentative in range(4):
        _stop()
        driver.get("https://www.instagram.com/")
        # On attend que l'icône Créer apparaisse (page réellement chargée).
        fin = time.time() + 15
        while time.time() < fin:
            _stop()
            present = _js(
                driver,
                "return !!document.querySelector('svg[aria-label=\"Nouvelle publication\"],"
                "svg[aria-label=\"New post\"]');",
            )
            if present:
                return
            time.sleep(1)
        print(f"[post] accueil pas chargé (essai {tentative + 1}/4), on retente...", flush=True)
    raise RuntimeError("Impossible de charger la page d'accueil Instagram.")


def _choisir_format_original(driver):
    """Sur l'écran de recadrage, sélectionne le format 'Original' (pas 1:1).

    Non bloquant : si le bouton n'est pas trouvé, on ignore simplement.
    """
    fin = time.time() + 20
    present = False
    while time.time() < fin:
        # Le bandeau Reel (OK) peut masquer le bouton : on le ferme d'abord.
        if _texte_present(driver, TXT_OK):
            _cliquer_texte(driver, TXT_OK)
            time.sleep(1)
        if _js(driver,
               "return !!document.querySelector('div[role=dialog] "
               "svg[aria-label=\"Sélectionner un format\"]');"):
            present = True
            break
        time.sleep(1)
    if not present:
        return

    ouvert = _js(
        driver,
        """
        const s = document.querySelector('div[role=dialog] svg[aria-label="Sélectionner un format"]');
        if (!s) return false;
        const e = s.closest('button,[role=button]') || s.parentElement;
        if (e) { e.click(); return true; }
        return false;
        """,
    )
    if not ouvert:
        return
    time.sleep(0.8)
    if _cliquer_texte(driver, ["Original"]):
        print("[post] format 'Original' sélectionné.", flush=True)
    time.sleep(0.5)


def _publier(driver, fichiers: list[str], legende: str, essai: bool):
    """Parcours complet : ouvrir, charger, avancer, légender, publier."""
    _aller_accueil(driver)
    _pause()

    print("[post] ouverture du dialogue de création...", flush=True)
    _ouvrir_composer(driver)
    _pause()

    print("[post] envoi du/des fichier(s)...", flush=True)
    _charger_fichiers(driver, fichiers)
    _pause()

    # Écran de recadrage : choisir "Original" (sinon recadré en 1:1).
    print("[post] sélection du format Original...", flush=True)
    _choisir_format_original(driver)
    _pause()

    # On avance écran par écran jusqu'à atteindre "Partager".
    # À chaque étape : si "Partager" est là -> fini ; sinon si un "OK"
    # est présent (bandeau Reels) -> on le clique ; sinon on clique
    # "Suivant". Délai large (60s) car une vidéo met du temps à traiter.
    # (Photo = 2x Suivant ; Réel = OK puis 2x Suivant.)
    print("[post] progression vers l'écran de légende...", flush=True)
    for etape in range(8):
        if _texte_present(driver, TXT_PARTAGER):
            break
        if _texte_present(driver, TXT_OK):
            print("[post] bandeau Réel, clic OK...", flush=True)
            _cliquer_texte(driver, TXT_OK)
            _pause()
            continue
        if _attendre_texte(driver, TXT_SUIVANT, delai=60):
            _cliquer_texte(driver, TXT_SUIVANT)
            _pause()
            continue
        break

    if not _texte_present(driver, TXT_PARTAGER):
        raise RuntimeError("Écran de publication ('Partager') non atteint.")

    if legende:
        print("[post] écriture de la légende...", flush=True)
        _ecrire_legende(driver, legende)
        _pause()

    if essai:
        print("[ESSAI] Tout est prêt — clic 'Partager' NON effectué. ✅", flush=True)
        return

    print("[post] publication...", flush=True)
    if not _partager_et_verifier(driver):
        raise RuntimeError(
            "Le clic 'Partager' n'a pas abouti : la publication n'a PAS été "
            "confirmée par Instagram. Rien n'a été publié — réessaie.")
    time.sleep(5)


def poster_publication(driver, image: str, legende: str = "", essai: bool = False,
                       methode: str = "web"):
    """Publie une photo simple dans le feed (Instagram web ou Inssist)."""
    if methode == "inssist":
        _publier_inssist(driver, [image], legende, essai, typ="post")
    else:
        _publier(driver, [image], legende, essai)


def poster_carrousel(driver, images: list[str], legende: str = "", essai: bool = False,
                     methode: str = "web"):
    """Publie plusieurs images (slides / carrousel), via web ou Inssist."""
    if methode == "inssist":
        _publier_inssist(driver, images, legende, essai, typ="post")
    else:
        _publier(driver, images, legende, essai)


def poster_reel(driver, video: str, legende: str = "", essai: bool = False,
                methode: str = "web"):
    """Publie une vidéo en tant que Réel, via web ou Inssist."""
    if methode == "inssist":
        _publier_inssist(driver, [video], legende, essai, typ="reel")
    else:
        _publier(driver, [video], legende, essai)


# ======================================================================
#  STORIES via l'extension Inssist (le web Instagram ne les gère pas)
# ======================================================================

def _cliquer_ci(driver, textes: list[str]) -> bool:
    """Clique (JS) un élément dont le texte == l'un des textes.

    Insensible à la casse ET aux espaces (Inssist utilise des espaces
    insécables \\xa0 -> on normalise tout en espace simple).
    """
    return bool(_js(
        driver,
        """
        const norm = s => (s || '').replace(/\\s+/g, ' ').trim().toLowerCase();
        const W = arguments[0].map(norm);
        for (const b of document.querySelectorAll('button,[role=button],a,div,span')) {
            if (W.includes(norm(b.innerText)) && b.offsetParent !== null) {
                b.click(); return true;
            }
        }
        return false;
        """,
        textes,
    ))


def _present_ci(driver, textes: list[str]) -> bool:
    """Vrai si un élément cliquable au texte donné est visible (insensible casse/espaces)."""
    return bool(_js(
        driver,
        """
        const norm = s => (s || '').replace(/\\s+/g, ' ').trim().toLowerCase();
        const W = arguments[0].map(norm);
        for (const b of document.querySelectorAll('button,[role=button],a,div,span')) {
            if (W.includes(norm(b.innerText)) && b.offsetParent !== null) return true;
        }
        return false;
        """,
        textes,
    ))


def _ouvrir_inssist(driver):
    """Ouvre le menu de l'extension Inssist puis le composer (Assistant)."""
    ouvert = _js(
        driver,
        "const b=document.querySelector('.EmbedInssistMenuButton');"
        "if(!b) return false; (b.querySelector('*')||b).click(); return true;",
    )
    if not ouvert:
        raise RuntimeError(
            "Bouton Inssist introuvable. Vérifie que l'extension Inssist est "
            "installée et active dans le profil AdsPower.")
    _pause()
    if not _cliquer_ci(driver, ["Assistant +", "Assistant", "Create & schedule"]):
        # parfois le composer s'ouvre direct
        pass
    time.sleep(3)


def _ajouter_lien_story(driver, lien: str, texte_lien: str):
    """Ajoute un sticker LIEN à la story (best-effort, à affiner au test)."""
    if not _cliquer_ci(driver, ["Link", "Lien", "Add link", "Ajouter un lien"]):
        print("[story] option 'Lien' non trouvée (à ajuster).", flush=True)
        return
    time.sleep(1)
    # Remplit l'URL puis (si présent) le texte du lien.
    ok = _js(
        driver,
        """
        const url = arguments[0], txt = arguments[1];
        const champs = [...document.querySelectorAll('input[type=text],input[type=url],input:not([type]),textarea')]
            .filter(e => e.offsetParent !== null);
        if (champs.length === 0) return false;
        champs[0].focus(); champs[0].value = url;
        champs[0].dispatchEvent(new Event('input', {bubbles: true}));
        if (champs.length > 1 && txt) {
            champs[1].focus(); champs[1].value = txt;
            champs[1].dispatchEvent(new Event('input', {bubbles: true}));
        }
        return true;
        """,
        lien, texte_lien or "",
    )
    if ok:
        print("[story] lien renseigné.", flush=True)
        time.sleep(0.6)
        _cliquer_ci(driver, ["Add", "Ajouter", "Done", "OK", "Apply", "Appliquer", "Terminé"])
        time.sleep(0.6)


def poster_story(driver, media: str, lien: str = "", texte_lien: str = "",
                 essai: bool = False):
    """Publie une STORY via Inssist, avec un lien optionnel."""
    _aller_accueil(driver)
    _pause()

    print("[story] ouverture d'Inssist...", flush=True)
    _ouvrir_inssist(driver)

    print("[story] onglet Story...", flush=True)
    _cliquer_ci(driver, ["Story"])
    time.sleep(2)

    print("[story] envoi du média...", flush=True)
    champ = WebDriverWait(driver, 30).until(
        EC.presence_of_element_located((By.XPATH, "//input[@type='file']")))
    champ.send_keys(os.path.abspath(media))
    time.sleep(5)

    if lien:
        print("[story] ajout du lien...", flush=True)
        _ajouter_lien_story(driver, lien, texte_lien)
        _pause()

    if essai:
        print("[ESSAI] Story prête — publication NON effectuée. ✅", flush=True)
        return

    print("[story] publication...", flush=True)
    if not _cliquer_ci(driver, ["PUBLISH STORY", "Publish story", "Publier la story",
                                 "Publish", "Publier"]):
        raise RuntimeError("Bouton de publication de story introuvable.")
    time.sleep(10)


# ======================================================================
#  POSTS (carrousels + reels) via l'extension Inssist
# ======================================================================
#  Le client veut que les posts feed passent AUSSI par Inssist (interface
#  "mobile" -> plus naturel pour Instagram). On réutilise l'ouverture de
#  l'extension déjà écrite pour les stories.
#  ⚠️ Les repères (onglets, boutons) sont à AFFINER au 1er test réel :
#     Inssist peut nommer/afficher ses écrans autrement.
# ======================================================================

# Repères RÉELS du composer Inssist (relevés sur captures d'écran).
# Chemin : « Créer » (Instagram) -> « Post Assistant » -> ADD FILES -> composer.
LBL_POST_ASSISTANT = ["Post Assistant"]
# Onglets du composer (POST / REEL / STORY).
TXT_INSSIST_TAB_POST = ["POST", "Post"]
TXT_INSSIST_TAB_REEL = ["REEL", "Reel"]
# Zone d'import.
TXT_INSSIST_ADD = ["ADD FILES", "Add files", "Click to add photos and videos"]
# Quand on envoie PLUSIEURS médias, Inssist demande le mode -> on veut carrousel.
TXT_INSSIST_CAROUSEL = ["CAROUSEL POST", "Carousel post", "CAROUSEL", "Carousel"]
# Bouton de publication finale (varie selon le type : PHOTO / REEL / CAROUSEL).
TXT_INSSIST_PUBLIER = ["PUBLISH PHOTO", "PUBLISH REEL", "PUBLISH CAROUSEL", "PUBLISH POST",
                       "PUBLISH", "Publish photo", "Publish reel", "Publish", "Publier"]


# JS réutilisable : collecte TOUS les éléments en traversant les shadow DOM
# OUVERTS (le composer Inssist vit dans un shadow root ouvert).
_JS_TOUS = """
function _tous(racine, acc){
  const els = racine.querySelectorAll ? racine.querySelectorAll('*') : [];
  for (const e of els){ acc.push(e); if (e.shadowRoot) _tous(e.shadowRoot, acc); }
  return acc;
}
function _visible(e){ const r = e.getClientRects && e.getClientRects(); return !!(r && r.length); }
"""


def _cliquer_inssist(driver, textes: list[str]) -> bool:
    """Clique un élément par son texte, EN TRAVERSANT le shadow DOM.

    2 passes : d'abord une correspondance EXACTE du texte, sinon l'élément
    visible le plus court qui CONTIENT le texte (utile pour « ADD FILES » dont
    le conteneur inclut aussi « Click to add photos and videos »).
    """
    return bool(_js(
        driver,
        _JS_TOUS + """
        const norm = s => (s||'').replace(/\\s+/g,' ').trim().toLowerCase();
        const W = arguments[0].map(norm);
        const all = _tous(document, []).filter(_visible);
        for (const e of all){ if (W.includes(norm(e.innerText))){ e.click(); return true; } }
        let best=null, bl=1e9;
        for (const e of all){ const t=norm(e.innerText); if(!t) continue;
          if (W.some(w=>t.includes(w)) && t.length<bl){ best=e; bl=t.length; } }
        if (best){ best.click(); return true; }
        return false;
        """,
        textes,
    ))


def _present_inssist(driver, textes: list[str]) -> bool:
    """Vrai si un texte est présent (shadow DOM ouvert compris)."""
    return bool(_js(
        driver,
        _JS_TOUS + """
        const norm = s => (s||'').replace(/\\s+/g,' ').trim().toLowerCase();
        const W = arguments[0].map(norm);
        for (const e of _tous(document, []).filter(_visible)){
          const t = norm(e.innerText);
          if (t && (W.includes(t) || W.some(w=>t.includes(w)))) return true;
        }
        return false;
        """,
        textes,
    ))


def _scan_composer_inssist(driver, etape: str = ""):
    """Écrit dans le JOURNAL la liste des boutons/champs visibles du composer
    Inssist (shadow DOM compris). Sert à relever les VRAIS libellés pour
    fiabiliser les clics. Purement informatif (ne clique rien)."""
    infos = _js(
        driver,
        _JS_TOUS + """
        const vis = e => { const r = e.getClientRects(); return !!(r && r.length); };
        const all = _tous(document, []);
        const btns = [...new Set(all
            .filter(e => vis(e) && (e.tagName==='BUTTON' || e.getAttribute('role')==='button' || e.tagName==='A'))
            .map(e => e.tagName + ' » ' + (e.innerText||'').replace(/\\s+/g,' ').trim().slice(0,45)))]
            .filter(s => s.length > 6);
        const champs = all
            .filter(e => e.tagName==='TEXTAREA' || e.tagName==='INPUT' || e.getAttribute('contenteditable')==='true')
            .map(e => e.tagName + ' type=' + (e.getAttribute('type')||'-')
                     + ' placeholder="' + (e.getAttribute('placeholder')||'') + '"');
        return JSON.stringify({btns: btns, champs: champs});
        """,
    )
    try:
        data = json.loads(infos) if infos else {}
    except Exception:
        data = {}
    btns = data.get("btns", [])
    champs = data.get("champs", [])
    _log(f"[inssist-scan] ===== {etape} =====")
    _log(f"[inssist-scan] BOUTONS ({len(btns)}) :")
    for b in btns:
        _log(f"[inssist-scan]   • {b}")
    _log(f"[inssist-scan] CHAMPS ({len(champs)}) :")
    for c in champs:
        _log(f"[inssist-scan]   • {c}")


def _input_fichier_partout(driver):
    """Retourne le <input type=file> d'Inssist visible en shadow DOM OUVERT.

    (Repli JS. Ne voit PAS les shadow DOM fermés ni les iframes -> on préfère
    la méthode CDP `_envoyer_fichiers_cdp` qui, elle, traverse tout.)
    """
    return _js(
        driver,
        """
        function chercher(racine) {
            const direct = racine.querySelector && racine.querySelector('input[type=file]');
            if (direct) return direct;
            const hotes = racine.querySelectorAll ? racine.querySelectorAll('*') : [];
            for (const h of hotes) {
                if (h.shadowRoot) {
                    const t = chercher(h.shadowRoot);
                    if (t) return t;
                }
            }
            return null;
        }
        return chercher(document);
        """,
    )


def _envoyer_fichiers_cdp(driver, fichiers: list[str]) -> bool:
    """Pose les fichiers sur l'input[type=file] d'Inssist via CDP (pierce=true).

    CDP `DOM.getDocument(pierce=true)` traverse TOUT : shadow DOM ouverts ET
    FERMÉS, et iframes. On trouve le node input file, puis
    `DOM.setFileInputFiles` y dépose les chemins (fonctionne sur input caché).
    Retourne True si un input a été trouvé et rempli.
    """
    chemins = [os.path.abspath(f) for f in fichiers]

    def _est_input_file(node) -> bool:
        if (node.get("nodeName") or "").upper() != "INPUT":
            return False
        attrs = node.get("attributes") or []
        for i in range(0, len(attrs) - 1, 2):
            if attrs[i] == "type" and (attrs[i + 1] or "").lower() == "file":
                return True
        return False

    def _chercher(node):
        if _est_input_file(node):
            return node.get("backendNodeId")
        for enfant in node.get("children", []) or []:
            r = _chercher(enfant)
            if r:
                return r
        cd = node.get("contentDocument")
        if cd:
            r = _chercher(cd)
            if r:
                return r
        for sr in node.get("shadowRoots", []) or []:
            r = _chercher(sr)
            if r:
                return r
        return None

    try:
        doc = driver.execute_cdp_cmd("DOM.getDocument", {"depth": -1, "pierce": True})
    except WebDriverException as e:
        print(f"[post/inssist] CDP getDocument échoué : {e}", flush=True)
        return False

    backend_id = _chercher(doc.get("root", {}))
    if not backend_id:
        return False

    try:
        driver.execute_cdp_cmd(
            "DOM.setFileInputFiles",
            {"files": chemins, "backendNodeId": backend_id},
        )
        return True
    except WebDriverException as e:
        print(f"[post/inssist] CDP setFileInputFiles échoué : {e}", flush=True)
        return False


def _backend_ids_inputs_file(driver) -> list:
    """Liste les backendNodeId de TOUS les input[type=file] via CDP.

    CDP `DOM.getDocument(pierce=true)` traverse TOUT : shadow DOM ouverts ET
    FERMÉS + iframes. Le backendNodeId est stable pour un même nœud -> on peut
    comparer AVANT/APRÈS le clic pour trouver le nouvel input d'Inssist.
    """
    try:
        doc = driver.execute_cdp_cmd("DOM.getDocument", {"depth": -1, "pierce": True})
    except WebDriverException:
        return []
    ids = []

    def walk(node):
        if (node.get("nodeName") or "").upper() == "INPUT":
            attrs = node.get("attributes") or []
            for i in range(0, len(attrs) - 1, 2):
                if attrs[i] == "type" and (attrs[i + 1] or "").lower() == "file":
                    ids.append(node.get("backendNodeId"))
        for c in node.get("children", []) or []:
            walk(c)
        cd = node.get("contentDocument")
        if cd:
            walk(cd)
        for sr in node.get("shadowRoots", []) or []:
            walk(sr)

    walk(doc.get("root", {}))
    return ids


def _marquer_inputs_fichier(driver) -> list:
    """Marque (data-insid) et liste TOUS les input[type=file] (light + shadow
    ouvert). Sert à repérer le NOUVEL input créé par Inssist au clic ADD FILES."""
    return _js(
        driver,
        _JS_TOUS + """
        const acc = [];
        for (const e of _tous(document, [])) {
            if (e.tagName === 'INPUT' && (e.getAttribute('type')||'').toLowerCase() === 'file') {
                if (!e.dataset.insid) e.dataset.insid = 'ins_' + Math.random().toString(36).slice(2);
                acc.push(e.dataset.insid);
            }
        }
        return acc;
        """,
    ) or []


def _element_par_insid(driver, insid: str):
    """Retourne le WebElement portant ce data-insid (light + shadow ouvert)."""
    return _js(
        driver,
        _JS_TOUS + """
        const id = arguments[0];
        for (const e of _tous(document, [])) {
            if (e.dataset && e.dataset.insid === id) return e;
        }
        return null;
        """,
        insid,
    )


def _envoyer_fichiers_add_files(driver, fichiers: list[str]) -> bool:
    """Cas « ADD FILES ouvre une fenêtre Windows » : on l'intercepte ET on
    cible le BON input.

    Inssist crée un <input type=file> NEUF au clic sur ADD FILES. Comme la page
    Instagram contient déjà son propre input file, on ne peut pas prendre
    « le premier trouvé » (faux succès). Méthode fiable :
      1) noter les inputs file existants AVANT (data-insid) ;
      2) activer l'interception de la fenêtre Windows (CDP) ;
      3) cliquer ADD FILES -> Inssist crée son input (fenêtre bloquée) ;
      4) repérer le NOUVEL input (celui qui n'existait pas avant) ;
      5) y déposer les fichiers (send_keys) -> Inssist reçoit le change.
    """
    chemins = [os.path.abspath(f) for f in fichiers]
    avant = set(_backend_ids_inputs_file(driver))
    _log(f"[post/inssist] inputs file avant ADD FILES : {len(avant)}")

    interception_ok = False
    try:
        driver.execute_cdp_cmd("Page.enable", {})
        driver.execute_cdp_cmd("Page.setInterceptFileChooserDialog", {"enabled": True})
        interception_ok = True
    except WebDriverException as e:
        _log(f"[post/inssist] interception NON disponible : {e}")
    _log(f"[post/inssist] interception activée : {interception_ok}")

    try:
        present = _present_inssist(driver, TXT_INSSIST_ADD)
        _log(f"[post/inssist] ADD FILES visible par le JS (shadow ouvert) : {present}")
        clique = _cliquer_inssist(driver, TXT_INSSIST_ADD)
        _log(f"[post/inssist] ADD FILES cliqué : {clique}. Attente du nouvel input...")

        # Repérer le NOUVEL input file (CDP, perce même les shadow fermés).
        cible_id = None
        apres = []
        fin = time.time() + 8
        while time.time() < fin:
            _stop()
            apres = _backend_ids_inputs_file(driver)
            diff = [i for i in apres if i not in avant]
            if diff:
                cible_id = diff[0]
                break
            time.sleep(0.4)

        if cible_id is None:
            _log(f"[post/inssist] aucun NOUVEL input après ADD FILES "
                 f"(inputs après = {len(apres)}).")
            return False

        driver.execute_cdp_cmd(
            "DOM.setFileInputFiles", {"files": chemins, "backendNodeId": cible_id})
        _log("[post/inssist] fichiers déposés sur le NOUVEL input Inssist (CDP). ✅")
        return True
    finally:
        try:
            driver.execute_cdp_cmd("Page.setInterceptFileChooserDialog", {"enabled": False})
        except WebDriverException:
            pass


def _envoyer_fichiers_iframes(driver, fichiers: list[str]) -> bool:
    """Entre dans l'iframe d'Inssist et y dépose les fichiers.

    IMPORTANT : si l'input est trouvé DANS un iframe, on y RESTE (on ne
    revient pas au contexte principal) car TOUT le composer (CAROUSEL POST,
    légende, PUBLISH) vit dans ce même iframe. L'appelant remettra le
    contexte principal à la fin via driver.switch_to.default_content().
    """
    chemins = "\n".join(os.path.abspath(f) for f in fichiers)
    iframes = driver.find_elements(By.TAG_NAME, "iframe")
    for fr in iframes:
        driver.switch_to.default_content()
        try:
            driver.switch_to.frame(fr)
        except WebDriverException:
            continue
        try:
            # a) input via JS (shadow DOM ouvert compris) dans l'iframe
            trouve = _input_fichier_partout(driver)
            # b) sinon recherche simple dans l'iframe
            if not trouve:
                els = driver.find_elements(By.XPATH, "//input[@type='file']")
                trouve = els[0] if els else None
            if trouve:
                trouve.send_keys(chemins)
                print("[post/inssist] fichiers envoyés dans l'iframe Inssist "
                      "(on reste dans l'iframe). ✅", flush=True)
                return True   # <-- on RESTE dans l'iframe volontairement
        except WebDriverException as e:
            print(f"[post/inssist] iframe : {e}", flush=True)
    driver.switch_to.default_content()
    return False


def _diagnostic_inssist(driver):
    """Affiche dans le journal un petit état de la page (aide au debug Inssist)."""
    driver.switch_to.default_content()
    infos = _js(
        driver,
        """
        const frames = [...document.querySelectorAll('iframe')];
        let inputsLight = document.querySelectorAll('input[type=file]').length;
        let shadowOuverts = 0;
        for (const el of document.querySelectorAll('*')) if (el.shadowRoot) shadowOuverts++;
        const srcs = frames.map(f => (f.src || '(sans src)').slice(0, 60)).join(' , ');
        return frames.length + '|' + inputsLight + '|' + shadowOuverts + '|' + srcs;
        """,
    )
    if infos:
        ifr, inp, sh, srcs = (infos.split("|", 3) + ["", "", "", ""])[:4]
        print(f"[post/inssist] diagnostic : iframes={ifr}, inputs(file) visibles={inp}, "
              f"shadowRoots ouverts={sh}", flush=True)
        print(f"[post/inssist] iframes src : {srcs}", flush=True)


def _ecrire_legende_inssist(driver, legende: str) -> bool:
    """Écrit la légende dans le champ « caption » du composer Inssist.

    Inssist utilise un simple <textarea> (placeholder « Write a caption… »),
    bien plus facile que l'éditeur Lexical d'Instagram. On vise d'abord ce
    champ précis, sinon on prend le plus grand champ visible.
    """
    ok = _js(
        driver,
        _JS_TOUS + """
        const txt = arguments[0];
        const all = _tous(document, []);
        // 1) Champ 'caption' explicite (placeholder / aria-label), shadow compris.
        let el = all.find(e => e.tagName === 'TEXTAREA' &&
            /caption|légende|legende/i.test(
                (e.getAttribute('placeholder')||'') + ' ' + (e.getAttribute('aria-label')||'')));
        // 2) Sinon : le plus grand champ éditable visible.
        if (!el) {
            const champs = all.filter(e =>
                (e.tagName === 'TEXTAREA' || e.getAttribute('contenteditable') === 'true')
                && _visible(e));
            if (!champs.length) return false;
            champs.sort((a, b) => (b.clientHeight * b.clientWidth) - (a.clientHeight * a.clientWidth));
            el = champs[0];
        }
        el.focus();
        if (el.tagName === 'TEXTAREA') {
            el.value = txt;
            el.dispatchEvent(new Event('input', {bubbles: true}));
            el.dispatchEvent(new Event('change', {bubbles: true}));
        } else {
            el.innerText = txt;
            el.dispatchEvent(new Event('input', {bubbles: true}));
        }
        return true;
        """,
        legende,
    )
    if ok:
        print("[post/inssist] légende insérée. ✅", flush=True)
    else:
        print("[post/inssist] champ légende introuvable (à ajuster).", flush=True)
    return bool(ok)


def _attendre_inssist_pret(driver, delai: int = 25) -> bool:
    """Attend que l'extension Inssist ait fini de s'injecter dans la page.

    L'extension met quelques secondes à charger après l'ouverture d'Instagram.
    Si on clique trop tôt, « Post Assistant » n'existe pas encore. On sonde
    des marqueurs Inssist (bouton flottant, classes/ids contenant 'inssist')
    jusqu'à les voir apparaître.
    """
    fin = time.time() + delai
    while time.time() < fin:
        _stop()
        pret = _js(
            driver,
            """
            if (document.querySelector('.EmbedInssistMenuButton')) return true;
            for (const e of document.querySelectorAll('*')) {
                let c = e.className;
                if (c && c.baseVal !== undefined) c = c.baseVal;      // SVG
                if (typeof c === 'string' && c.toLowerCase().includes('inssist')) return true;
                if ((e.id || '').toLowerCase().includes('inssist')) return true;
            }
            return false;
            """,
        )
        if pret:
            return True
        time.sleep(1)
    return False


def _publier_inssist(driver, fichiers: list[str], legende: str, essai: bool,
                     typ: str = "post"):
    """Publie un post (photo/carrousel/reel) via le composer Inssist.

    Chemin réel : « Créer » (Instagram) → « Post Assistant » → ADD FILES →
    composer (onglet POST/REEL) → légende → PUBLISH.
    """
    _log(f"=== NOUVELLE TENTATIVE INSSIST ({typ}, {len(fichiers)} média) ===", reset=True)
    _aller_accueil(driver)

    # Laisser l'extension Inssist finir de s'injecter AVANT de cliquer.
    print("[post/inssist] attente du chargement de l'extension Inssist...", flush=True)
    if _attendre_inssist_pret(driver, 25):
        print("[post/inssist] Inssist détecté dans la page. ✅", flush=True)
    else:
        print("[post/inssist] Inssist non détecté après 25s — tentative quand même.",
              flush=True)
    time.sleep(2)   # petite marge de sécurité
    _pause()

    # 1) Bouton « Créer » natif d'Instagram (rouvre le menu de création).
    _log("[post/inssist] clic sur « Créer »...")
    fin = time.time() + 15
    while time.time() < fin:
        _stop()
        if _clic_icone_creer(driver):
            break
        time.sleep(1)
    else:
        _dump_aria_creer(driver)   # note les aria-labels visibles pour debug
        raise RuntimeError("Bouton « Créer » d'Instagram introuvable.")
    _log("[post/inssist] « Créer » cliqué. ✅")
    _pause()

    # 2) Bouton « Post Assistant » injecté par Inssist dans ce menu.
    print("[post/inssist] ouverture de « Post Assistant »...", flush=True)
    fin = time.time() + 12
    while time.time() < fin:
        _stop()
        if _cliquer_inssist(driver, LBL_POST_ASSISTANT):
            break
        time.sleep(1)
    else:
        raise RuntimeError(
            "« Post Assistant » introuvable : l'extension Inssist n'est pas "
            "active dans ce profil AdsPower (ou pas connectée à Instagram).")
    time.sleep(2)

    # 3) Import des médias. Inssist crée son input AU CLIC sur ADD FILES et
    #    ouvre une fenêtre Windows -> on l'intercepte (méthode principale).
    #    Replis : CDP direct / shadow ouvert (si l'input existait déjà).
    print("[post/inssist] envoi du/des média(s)...", flush=True)
    envoye = _envoyer_fichiers_add_files(driver, fichiers)

    if not envoye:
        _diagnostic_inssist(driver)
        _scan_composer_inssist(driver, "échec import (état de la page)")
        raise RuntimeError(
            "Import Inssist impossible (nouvel input non trouvé après ADD FILES). "
            "Vérifie qu'Inssist est bien actif et connecté dans ce profil. "
            "Regarde les lignes 'diagnostic'/'inssist-scan' du journal.")
    time.sleep(4)
    _scan_composer_inssist(driver, "après import (choix carrousel ?)")

    # 4) Plusieurs médias -> Inssist demande « 2 POSTS / CAROUSEL POST » : on
    #    choisit CAROUSEL POST. Un seul média : pas de question, on continue.
    if len(fichiers) > 1:
        print("[post/inssist] choix « CAROUSEL POST »...", flush=True)
        clic = False
        fin = time.time() + 15
        while time.time() < fin:
            _stop()
            if _cliquer_inssist(driver, TXT_INSSIST_CAROUSEL):
                clic = True
                break
            time.sleep(1)
        if not clic:
            print("[post/inssist] bouton « CAROUSEL POST » non vu (à vérifier).", flush=True)
        time.sleep(2)
    elif typ == "reel":
        print("[post/inssist] onglet REEL...", flush=True)
        _cliquer_inssist(driver, TXT_INSSIST_TAB_REEL)
        time.sleep(1.5)

    # 5) Légende (champ « Write a caption… »).
    if legende:
        print("[post/inssist] écriture de la légende...", flush=True)
        _ecrire_legende_inssist(driver, legende)
        _pause()

    _scan_composer_inssist(driver, "composer final (avant PUBLISH)")

    if essai:
        print("[ESSAI] Post Inssist prêt — publication NON effectuée. ✅", flush=True)
        driver.switch_to.default_content()
        return

    # 6) Publication (PUBLISH PHOTO / REEL / CAROUSEL).
    print("[post/inssist] publication...", flush=True)
    _stop()
    if not _cliquer_inssist(driver, TXT_INSSIST_PUBLIER):
        raise RuntimeError(
            "Bouton PUBLISH d'Inssist introuvable "
            "(regarde le nom exact du bouton en bas du composer).")
    time.sleep(10)
    driver.switch_to.default_content()
    print("[post/inssist] publication envoyée. ✅", flush=True)
