import { useEffect, useRef, useState } from "react";
import { CheckCircle, FolderOpen, Info, StopCircle, WarningCircle, X } from "@phosphor-icons/react";

export type Toast = {
  id: number;
  type: "succes" | "arret" | "info" | "erreur";
  titre: string;
  texte: string;
  action?: { libelle: string; onClick: () => void };
  duree?: number; // ms avant fermeture automatique
};

function UnToast({ t, fermer }: { t: Toast; fermer: (id: number) => void }) {
  const [sortie, setSortie] = useState(false);
  const [pause, setPause] = useState(false);
  const duree = t.duree ?? 6000;
  const fermerRef = useRef(fermer);
  fermerRef.current = fermer;
  const restant = useRef(duree);

  // Fermeture : on joue l'animation de sortie (200 ms), puis on retire le toast.
  const partir = () => setSortie(true);
  useEffect(() => {
    if (!sortie) return;
    const id = setTimeout(() => fermerRef.current(t.id), 200);
    return () => clearTimeout(id);
  }, [sortie, t.id]);

  // Décompte mis en PAUSE tant que la souris est dessus ou que le focus est dedans :
  // on ne ferme pas une notification pendant qu'on est en train de la lire ou de cliquer.
  useEffect(() => {
    if (pause || sortie) return;
    const debut = performance.now();
    const id = setTimeout(() => setSortie(true), restant.current);
    return () => {
      clearTimeout(id);
      restant.current = Math.max(restant.current - (performance.now() - debut), 0);
    };
  }, [pause, sortie]);

  const icone = {
    succes: <CheckCircle weight="fill" className="h-5 w-5 text-brand" />,
    arret: <StopCircle weight="fill" className="h-5 w-5 text-fg-3" />,
    info: <Info weight="fill" className="h-5 w-5 text-brand" />,
    erreur: <WarningCircle weight="fill" className="h-5 w-5 text-danger" />,
  }[t.type];

  return (
    <div
      role="status"
      onMouseEnter={() => setPause(true)}
      onMouseLeave={() => setPause(false)}
      onFocus={() => setPause(true)}
      onBlur={(e) => {
        if (!e.currentTarget.contains(e.relatedTarget as Node | null)) setPause(false);
      }}
      className={`toast relative w-[360px] overflow-hidden rounded-2xl border border-line bg-surface shadow-pop ${sortie ? "sortie" : ""}`}
    >
      <div className="flex gap-3 p-4 pr-10">
        <span className="mt-px shrink-0">{icone}</span>
        <div className="min-w-0">
          <p className="text-14 font-semibold">{t.titre}</p>
          <p className="mt-0.5 whitespace-pre-line text-13 leading-snug text-fg-2 [overflow-wrap:anywhere]">{t.texte}</p>
          {t.action && (
            <button
              type="button"
              onClick={() => {
                t.action!.onClick();
                partir();
              }}
              className="mt-2.5 inline-flex items-center gap-1.5 rounded-md text-13 font-medium text-brand-text hover:underline"
            >
              <FolderOpen weight="duotone" className="h-4 w-4" />
              {t.action.libelle}
            </button>
          )}
        </div>
      </div>
      <button
        type="button"
        onClick={partir}
        aria-label="Fermer"
        className="absolute right-2.5 top-2.5 grid h-7 w-7 place-items-center rounded-lg text-fg-3 transition-colors duration-150 hover:bg-fg/[0.06] hover:text-fg"
      >
        <X className="h-3.5 w-3.5" />
      </button>
      <span
        aria-hidden="true"
        className="toast-decompte absolute inset-x-0 bottom-0 h-0.5 bg-brand/40"
        style={{ animationDuration: `${duree}ms`, animationPlayState: pause ? "paused" : "running" }}
      />
    </div>
  );
}

export default function Toasts({ toasts, fermer }: { toasts: Toast[]; fermer: (id: number) => void }) {
  return (
    <div className="pointer-events-none fixed bottom-5 right-5 z-50 flex flex-col items-end gap-2.5">
      {toasts.map((t) => (
        <div key={t.id} className="pointer-events-auto">
          <UnToast t={t} fermer={fermer} />
        </div>
      ))}
    </div>
  );
}
