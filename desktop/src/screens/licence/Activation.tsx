import { useId, useRef, useState, type FormEvent, type ReactNode } from "react";
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
import type { ResultatActivation, StatutLicence } from "../../engine/api";
import { blocage, lienVendeur, normaliserCode } from "../../licence";
import { messageErreur } from "../../erreurs";
import { fr } from "../../fr";

const ICONES: Record<string, ReactNode> = {
  expire: <CalendarX weight="duotone" className="h-6 w-6" />,
  revoquee: <Prohibit weight="duotone" className="h-6 w-6" />,
  suspendu: <PauseCircle weight="duotone" className="h-6 w-6" />,
  mauvais_pc: <Desktop weight="duotone" className="h-6 w-6" />,
  invalide: <FileX weight="duotone" className="h-6 w-6" />,
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
          onChange={(e) => {
            setCode(e.target.value);
            if (message?.ton === "erreur") setMessage(null);
          }}
          // readOnly (et non disabled) : le champ garde le focus pendant l'envoi.
          readOnly={envoi}
          autoFocus
          autoComplete="off"
          autoCorrect="off"
          autoCapitalize="characters"
          spellCheck={false}
          maxLength={40}
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
