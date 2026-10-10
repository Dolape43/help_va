import { useState } from "react";
import { ArrowRight, SealCheck } from "@phosphor-icons/react";
import logo from "../../assets/logo.png";
import { Bouton, Rouage } from "../../components/ui";
import { MODULES } from "../../modules";
import type { StatutLicence } from "../../engine/api";
import { nomLicence, resumeLicence } from "../../licence";

/**
 * « Bienvenue sur HelpVA » : montré UNE seule fois, au tout premier lancement, juste après
 * l'activation (comme app_ctk.py > _ecran_bienvenue). « Commencer » le marque comme vu
 * (paramètre deja_demarre) : ensuite, l'app s'ouvre directement sur l'accueil.
 */
export default function Bienvenue({
  statut,
  commencer,
  resume,
}: {
  statut: StatutLicence;
  commencer: () => Promise<void>;
  /** texte de la pastille (sinon : la formule de la licence) */
  resume?: string;
}) {
  const [envoi, setEnvoi] = useState(false);
  const nom = nomLicence(statut);

  const go = async () => {
    if (envoi) return;
    setEnvoi(true);
    await commencer(); // ne lève jamais : App gère l'échec d'enregistrement
  };

  return (
    <div className="flex w-full max-w-[560px] flex-col items-center text-center">
      <div className="relative grid h-28 w-28 place-items-center">
        <span aria-hidden="true" className="aura-logo calme absolute inset-0 rounded-full" />
        <img src={logo} alt="" className="relative h-[84px] w-[84px] drop-shadow-[0_12px_28px_rgba(76,111,255,0.45)]" />
      </div>
      <h1 className="mt-5 text-28 font-semibold leading-tight">Bienvenue sur HelpVA</h1>
      <p className="mt-2 text-16 text-fg-2">Votre assistant pour préparer vos contenus Instagram.</p>

      <p className="mt-5 inline-flex max-w-full items-center gap-2 rounded-full border border-line bg-surface px-3.5 py-1.5 text-13 text-fg-2 shadow-card">
        <SealCheck weight="fill" className="h-4 w-4 shrink-0 text-success" aria-hidden="true" />
        <span className="truncate">
          <span className="font-medium text-fg">{resume ?? resumeLicence(statut)}</span>
          {nom && <> · {nom}</>}
        </span>
      </p>

      <ul aria-label="Les 4 modules" className="mt-9 grid w-full grid-cols-4 gap-3">
        {MODULES.map((m, i) => (
          <li
            key={m.cle}
            className="entree flex flex-col items-center gap-2.5 rounded-2xl border border-line bg-surface px-2 pb-3.5 pt-4 shadow-card"
            style={{ animationDelay: `${120 + i * 50}ms` }}
          >
            <img src={m.icone} alt="" className="h-11 w-11 object-contain" />
            <span className="text-12 font-medium leading-tight">{m.titre}</span>
          </li>
        ))}
      </ul>

      <Bouton variante="primaire" taille="lg" className="mt-9 min-w-[240px]" onClick={go} aria-disabled={envoi || undefined} autoFocus>
        {envoi ? <Rouage /> : null}
        Commencer
        {!envoi && <ArrowRight weight="bold" className="h-4 w-4" aria-hidden="true" />}
      </Bouton>
    </div>
  );
}
