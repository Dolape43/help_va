import { useId, useLayoutEffect, useRef, useState, type FormEvent, type KeyboardEvent, type ReactNode } from "react";
import {
  ArrowClockwise,
  CalendarX,
  Desktop,
  FileX,
  Info,
  Key,
  PauseCircle,
  Prohibit,
  TelegramLogo,
  WarningCircle,
} from "@phosphor-icons/react";
import { Bouton, Rouage } from "../../components/ui";
import { CartePortail, EntetePortail } from "./Portail";
import { ICONES_3D } from "../../icones3d";
import type { ResultatActivation, StatutLicence } from "../../engine/api";
import { blocage, formaterCode, lienVendeur, nbUtiles, normaliserCode, positionCurseur } from "../../licence";
import { messageErreur } from "../../erreurs";
import { fr } from "../../fr";

const ICONES: Record<string, ReactNode> = {
  expire: <CalendarX weight="duotone" className="h-6 w-6" />,
  revoquee: <Prohibit weight="duotone" className="h-6 w-6" />,
  suspendu: <PauseCircle weight="duotone" className="h-6 w-6" />,
  mauvais_pc: <Desktop weight="duotone" className="h-6 w-6" />,
  invalide: <FileX weight="duotone" className="h-6 w-6" />,
};

/** L'icône 3D de chaque situation. */
const IMAGES_3D: Record<string, string> = {
  pas_active: ICONES_3D.cle,
  expire: ICONES_3D.expire,
  revoquee: ICONES_3D.bloque,
  suspendu: ICONES_3D.bloque,
  mauvais_pc: ICONES_3D.ordinateur,
  invalide: ICONES_3D.alerte,
};

type Message = { texte: string; ton: "erreur" | "info" };

/**
 * Écran d'activation : premier lancement, ou licence bloquée (expirée, résiliée, suspendue,
 * autre PC, fichier abîmé). Même logique que app_ctk.py > _ecran_activation.
 * App.tsx lui donne une clé par raison : changer de raison repart d'un écran neuf.
 */
export default function Activation({
  statut,
  activer,
  verifier,
  ouvrirLien,
}: {
  statut: StatutLicence;
  activer: (code: string) => Promise<ResultatActivation>;
  verifier: () => Promise<StatutLicence | null>;
  ouvrirLien: (url: string) => void;
}) {
  const b = blocage(statut.raison, statut.type);
  const [code, setCode] = useState("");
  const [envoi, setEnvoi] = useState(false);
  const [reverif, setReverif] = useState(false);
  const [message, setMessage] = useState<Message | null>(null);
  const champ = useRef<HTMLInputElement>(null);
  const idChamp = useId();
  const idAide = useId();
  const idMessage = useId();
  const occupe = envoi || reverif;

  /* ---------- Saisie du code : tirets placés tout seuls (HELP-XXXX-XXXX-XXXX) ----------
     Après chaque frappe, on remet en forme, puis on replace le curseur au bon endroit
     (sinon, l'ajout d'un tiret l'enverrait à la fin du champ). */
  const curseur = useRef<number | null>(null);
  useLayoutEffect(() => {
    const el = champ.current;
    if (curseur.current === null || !el || document.activeElement !== el) return;
    el.setSelectionRange(curseur.current, curseur.current);
    curseur.current = null;
  }, [code]);

  const saisir = (el: HTMLInputElement) => {
    const brut = el.value;
    const curseurBrut = el.selectionStart ?? brut.length;
    const utilesAvant = nbUtiles(brut.slice(0, curseurBrut));
    const texte = formaterCode(brut);
    // On tapait à la fin : le curseur reste à la fin, donc APRÈS le tiret ajouté (« HELP-| »).
    const position = curseurBrut >= brut.length ? texte.length : positionCurseur(texte, utilesAvant);
    if (texte === code) {
      // Rien n'a changé une fois mis en forme (17e caractère, tiret tapé…) : React ne
      // redessinerait pas, on remet donc nous-mêmes le texte et le curseur.
      el.value = texte;
      el.setSelectionRange(position, position);
      return;
    }
    curseur.current = position;
    setCode(texte);
    if (message?.ton === "erreur") setMessage(null);
  };

  // Retour arrière juste APRÈS un tiret, ou Suppr juste AVANT : on saute le tiret pour effacer
  // le caractère d'à côté (sinon le tiret serait remis aussitôt, et rien ne s'effacerait).
  const touche = (e: KeyboardEvent<HTMLInputElement>) => {
    const el = e.currentTarget;
    const p = el.selectionStart ?? 0;
    if (p !== el.selectionEnd) return;
    if (e.key === "Backspace" && code[p - 1] === "-") el.setSelectionRange(p - 1, p - 1);
    else if (e.key === "Delete" && code[p] === "-") el.setSelectionRange(p + 1, p + 1);
  };

  const envoyer = async (e: FormEvent) => {
    e.preventDefault();
    if (occupe) return;
    const c = normaliserCode(code);
    if (!c) {
      setMessage({ texte: "Entrez votre code d'activation.", ton: "erreur" });
      champ.current?.focus();
      return;
    }
    setEnvoi(true);
    setMessage(null);
    try {
      const r = await activer(c);
      if (r.ok) return; // licence valide : le portail passe tout seul à l'écran suivant
      setMessage({ texte: r.message || "Code invalide ou déjà utilisé.", ton: "erreur" });
    } catch (err) {
      setMessage({ texte: messageErreur(err), ton: "erreur" });
    }
    setEnvoi(false);
    // Le code reste sélectionné : on peut le corriger ou le recoller directement.
    requestAnimationFrame(() => champ.current?.select());
  };

  // « Abonnement réactivé ? » : le vendeur a pu débloquer la licence, sans nouveau code.
  const reverifier = async () => {
    if (occupe) return;
    setReverif(true);
    setMessage(null);
    const st = await verifier();
    setReverif(false);
    if (!st) {
      setMessage({ texte: "La vérification n'a pas abouti. Vérifiez votre connexion, puis réessayez.", ton: "erreur" });
    } else if (!st.ok && st.raison === statut.raison) {
      setMessage({ texte: "Toujours bloquée pour le moment. Si le vendeur vient de la réactiver, réessayez dans une minute.", ton: "info" });
    }
    // Sinon : licence débloquée (ou autre situation) → le portail change d'écran.
  };

  return (
    <CartePortail>
      <EntetePortail
        icone={ICONES[statut.raison] ?? <Key weight="duotone" className="h-6 w-6" />}
        image={IMAGES_3D[statut.raison] ?? ICONES_3D.cle}
        ton={b.ton}
        titre={b.titre}
        texte={fr(b.texte)}
      />

      <form onSubmit={envoyer} noValidate className="mt-7">
        <label htmlFor={idChamp} className="text-13 font-medium">
          Code d'activation
        </label>
        <input
          id={idChamp}
          ref={champ}
          value={code}
          onChange={(e) => saisir(e.target)}
          onKeyDown={touche}
          // readOnly (et non disabled) : le champ garde le focus pendant l'envoi.
          readOnly={envoi}
          autoFocus
          autoComplete="off"
          autoCorrect="off"
          autoCapitalize="characters"
          spellCheck={false}
          maxLength={40}
          inputMode="text"
          placeholder="HELP-XXXX-XXXX-XXXX"
          aria-invalid={message?.ton === "erreur" || undefined}
          aria-describedby={message ? idMessage : idAide}
          className="selectable mt-2 h-12 w-full rounded-xl border border-line-2 bg-surface-2 px-4 text-center font-mono text-16 uppercase tracking-[0.08em] text-fg outline-none transition-[border-color,box-shadow] duration-150 placeholder:text-fg-3/60 focus:border-brand focus:shadow-[0_0_0_4px_var(--brand-soft)] aria-[invalid=true]:border-danger aria-[invalid=true]:focus:shadow-[0_0_0_4px_color-mix(in_oklab,var(--danger)_15%,transparent)] read-only:opacity-70"
        />
        {/* Toujours une ligne sous le champ : l'aide, ou le message (erreur près du champ). */}
        <div className="mt-2 min-h-[20px]">
          {message ? (
            <p
              id={idMessage}
              role={message.ton === "erreur" ? "alert" : "status"}
              className={`flex items-start gap-1.5 text-13 leading-snug ${message.ton === "erreur" ? "text-danger" : "text-fg-2"}`}
            >
              {message.ton === "erreur" ? (
                <WarningCircle weight="fill" className="mt-px h-4 w-4 shrink-0" aria-hidden="true" />
              ) : (
                <Info weight="fill" className="mt-px h-4 w-4 shrink-0 text-brand-text" aria-hidden="true" />
              )}
              {fr(message.texte)}
            </p>
          ) : (
            <p id={idAide} className="text-12 text-fg-3">
              Le code vous a été remis par le vendeur lors de votre achat.
            </p>
          )}
        </div>

        <Bouton type="submit" variante="primaire" taille="lg" className="mt-5 w-full" aria-disabled={occupe || undefined}>
          {envoi ? (
            <>
              <Rouage />
              Activation en cours…
            </>
          ) : (
            "Activer HelpVA"
          )}
        </Bouton>
        {b.reessayer && (
          <Bouton className="mt-2.5 w-full" onClick={reverifier} aria-disabled={occupe || undefined}>
            {reverif ? (
              <>
                <Rouage />
                Vérification…
              </>
            ) : (
              <>
                <ArrowClockwise className="h-4 w-4" aria-hidden="true" />
                {fr("Abonnement réactivé ? Réessayer")}
              </>
            )}
          </Bouton>
        )}
      </form>

      <div className="mt-6 border-t border-line pt-4 text-center">
        <button
          type="button"
          onClick={() => ouvrirLien(lienVendeur(b.message))}
          className="inline-flex items-center gap-1.5 rounded-md text-13 font-medium text-brand-text hover:underline"
        >
          <TelegramLogo weight="fill" className="h-4 w-4" aria-hidden="true" />
          {statut.raison === "pas_active" ? fr("Pas encore de code ? Contacter le vendeur") : "Contacter le vendeur"}
        </button>
      </div>
    </CartePortail>
  );
}
