import { useCallback, useEffect, useId, useMemo, useRef, useState, type KeyboardEvent } from "react";
import { ArrowCounterClockwise, Copy, FloppyDisk, Plus, Trash, Warning, X } from "@phosphor-icons/react";
import { Bouton, Icone3D, Rouage } from "../ui";
import { ICONES_3D } from "../../icones3d";
import Dialogue from "../Dialogue";
import { TYPES_POST, type Calendrier, type Moteur, type TypePost, type VueCalendrier } from "../../engine/api";
import { fr, pluriel } from "../../fr";

/** Libellé d'UN créneau (agent/ranger.py > LIBELLE_CRENEAU). */
const LIBELLE_CRENEAU: Record<TypePost, string> = { reel: "Réel", story: "Story", story_cta: "Story CTA", carousel: "Carrousel" };

/* Même règle que le moteur (engine/commandes.py > _nom_valide) : ces textes deviennent des NOMS DE
   DOSSIERS (semaine-01/jour-1/1_12h15_reel). On prévient ici, avant d'enregistrer. */
const INTERDITS = /[<>:"/\\|?*\u0000-\u001f]/;
const RESERVES = new Set(["CON", "PRN", "AUX", "NUL", ...Array.from({ length: 9 }, (_, i) => `COM${i + 1}`), ...Array.from({ length: 9 }, (_, i) => `LPT${i + 1}`)]);
export function heureValide(h: string): boolean {
  return (
    h.length > 0 &&
    h.length <= 40 &&
    h.trim() === h &&
    h !== "." &&
    h !== ".." &&
    !h.endsWith(".") &&
    !RESERVES.has(h.split(".")[0].trim().toUpperCase()) &&
    !INTERDITS.test(h)
  );
}

const copie = (c: Calendrier): Calendrier => JSON.parse(JSON.stringify(c)) as Calendrier;
const libelleSemaine = (nom: string) => {
  const num = nom.replace("semaine-", "");
  return `Semaine ${/^\d+$/.test(num) ? Number(num) : num}`;
};
const libelleJour = (nom: string) => {
  const num = nom.replace("jour-", "");
  return /^\d+$/.test(num) ? `Jour ${Number(num)}` : nom.charAt(0).toUpperCase() + nom.slice(1);
};
/** Les semaines renumérotées 01, 02… dans l'ordre (après une duplication ou une suppression). */
function renumeroter(semaines: Calendrier[string][]): Calendrier {
  return Object.fromEntries(semaines.map((j, i) => [`semaine-${String(i + 1).padStart(2, "0")}`, j]));
}
function compter(cal: Calendrier): Record<TypePost, number> {
  const n: Record<TypePost, number> = { reel: 0, story: 0, story_cta: 0, carousel: 0 };
  for (const jours of Object.values(cal)) for (const creneaux of Object.values(jours)) for (const c of creneaux) n[c.type] = (n[c.type] ?? 0) + 1;
  return n;
}
const toutReels = (cal: Calendrier) => Object.values(cal).every((j) => Object.values(j).every((cs) => cs.every((c) => c.type === "reel")));

type Confirmation = { titre: string; texte: string; action: string; danger?: boolean; faire: () => void } | null;

/**
 * Éditeur du calendrier de posts (copie de app_ctk.py > ouvrir_editeur_calendrier) :
 * semaines (dupliquer, supprimer), créneaux de chaque jour (heure + type), « Vidéos uniquement »,
 * Réinitialiser, Enregistrer. Rien n'est enregistré avant « Enregistrer » ; fermer avec des
 * modifications en cours demande quoi faire.
 */
export default function EditeurCalendrier({
  ouvert,
  fermer,
  moteur,
  imagesParCarrousel,
  surEnregistre,
  erreur,
}: {
  ouvert: boolean;
  fermer: () => void;
  moteur: Moteur;
  imagesParCarrousel: number;
  /** le calendrier enregistré (pour mettre la page Ranger à jour) et le message du moteur */
  surEnregistre: (vue: VueCalendrier) => void;
  erreur: (titre: string, e: unknown) => void;
}) {
  const ref = useRef<HTMLDialogElement>(null);
  const idTitre = useId();
  const [cal, setCal] = useState<Calendrier | null>(null);
  const [instantane, setInstantane] = useState("");
  const [courant, setCourant] = useState<string | null>(null);
  const [enregistrement, setEnregistrement] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [confirmation, setConfirmation] = useState<Confirmation>(null);
  const [quitter, setQuitter] = useState(false);

  // Ouverture : on (re)lit le calendrier enregistré.
  useEffect(() => {
    const d = ref.current;
    if (!d) return;
    if (ouvert && !d.open) {
      d.showModal();
      setCal(null);
      setMessage(null);
      moteur
        .calendrierLire()
        .then((v) => {
          setCal(copie(v.calendrier));
          setInstantane(JSON.stringify(v.calendrier));
          setCourant(Object.keys(v.calendrier)[0] ?? null);
        })
        .catch((e) => {
          erreur("Calendrier", e);
          fermer();
        });
    } else if (!ouvert && d.open) {
      d.close();
    }
  }, [ouvert, moteur, erreur, fermer]);

  const modifie = cal !== null && JSON.stringify(cal) !== instantane;
  const n = useMemo(() => (cal ? compter(cal) : null), [cal]);
  const heuresInvalides = useMemo(() => {
    if (!cal) return 0;
    let k = 0;
    for (const j of Object.values(cal)) for (const cs of Object.values(j)) for (const c of cs) if (!heureValide(c.heure)) k++;
    return k;
  }, [cal]);

  const demanderFermeture = useCallback(() => {
    if (enregistrement) return;
    if (modifie) setQuitter(true);
    else fermer();
  }, [enregistrement, modifie, fermer]);

  /* ---------- Modifications (toujours sur une copie : React voit le changement) ---------- */
  const changer = (f: (c: Calendrier) => void) => {
    setMessage(null);
    setCal((c) => {
      if (!c) return c;
      const nouveau = copie(c);
      f(nouveau);
      return nouveau;
    });
  };

  const dupliquer = (nom: string) => {
    if (!cal) return;
    const noms = Object.keys(cal);
    const i = noms.indexOf(nom);
    const semaines = Object.values(cal);
    semaines.splice(i + 1, 0, JSON.parse(JSON.stringify(cal[nom])));
    const nouveau = renumeroter(semaines);
    setCal(nouveau);
    setCourant(Object.keys(nouveau)[i + 1]);
    setMessage(null);
  };

  const supprimer = (nom: string) => {
    if (!cal) return;
    if (Object.keys(cal).length <= 1) {
      setMessage("Il faut au moins 1 semaine.");
      return;
    }
    setConfirmation({
      titre: `Supprimer la ${libelleSemaine(nom).toLowerCase()} ?`,
      texte: "Ses créneaux seront retirés du calendrier (rien n'est enregistré avant « Enregistrer »).",
      action: "Supprimer",
      danger: true,
      faire: () => {
        const noms = Object.keys(cal);
        const i = noms.indexOf(nom);
        const semaines = noms.filter((x) => x !== nom).map((x) => cal[x]);
        const nouveau = renumeroter(semaines);
        setCal(nouveau);
        const restants = Object.keys(nouveau);
        setCourant(restants[Math.min(i, restants.length - 1)]);
      },
    });
  };

  const choisirMode = (mode: "mixte" | "reels") => {
    if (!cal) return;
    if (mode === "reels") {
      setConfirmation({
        titre: "Vidéos uniquement ?",
        texte: "Mettre TOUT le calendrier en réels (vidéos) ? Les stories, stories CTA et carrousels deviendront des réels.",
        action: "Tout mettre en réels",
        faire: () =>
          changer((c) => {
            for (const j of Object.values(c)) for (const cs of Object.values(j)) for (const cr of cs) cr.type = "reel";
          }),
      });
    } else {
      setConfirmation({
        titre: "Images + Vidéos ?",
        texte: "Revenir au calendrier mixte par défaut (images + vidéos) ? Cela REMPLACE le calendrier actuel.",
        action: "Revenir au calendrier par défaut",
        faire: () => void reinitialiser(),
      });
    }
  };

  const reinitialiser = async () => {
    try {
      const v = await moteur.calendrierDefaut();
      setCal(copie(v.calendrier));
      setCourant(Object.keys(v.calendrier)[0] ?? null);
      setMessage(null);
    } catch (e) {
      erreur("Calendrier", e);
    }
  };

  const enregistrer = async (puisFermer = true) => {
    if (!cal || enregistrement) return;
    if (heuresInvalides) {
      setMessage(
        `${pluriel(heuresInvalides, "heure")} à corriger (en rouge) : heure vide ou invalide. Format conseillé : 12h00, sans \\ / : * ? " < > | ni point final.`,
      );
      return;
    }
    setEnregistrement(true);
    try {
      const v = await moteur.calendrierSauver(cal);
      setInstantane(JSON.stringify(v.calendrier));
      surEnregistre(v);
      if (puisFermer) fermer();
    } catch (e) {
      erreur("Calendrier non enregistré", e);
    } finally {
      setEnregistrement(false);
    }
  };

  const semaines = cal ? Object.keys(cal) : [];
  const semaine = cal && courant ? cal[courant] : null;
  const images = n ? n.story + n.story_cta + n.carousel * imagesParCarrousel : 0;

  // Barre des semaines = des onglets : les flèches passent d'une semaine à l'autre.
  const onglets = useRef<Record<string, HTMLButtonElement | null>>({});
  const flecheSemaine = (e: KeyboardEvent, nom: string) => {
    const i = semaines.indexOf(nom);
    const cible =
      e.key === "ArrowRight" ? semaines[i + 1] : e.key === "ArrowLeft" ? semaines[i - 1] : e.key === "Home" ? semaines[0] : e.key === "End" ? semaines[semaines.length - 1] : null;
    if (!cible) return;
    e.preventDefault();
    setCourant(cible);
    onglets.current[cible]?.focus();
  };

  return (
    <dialog
      ref={ref}
      aria-labelledby={idTitre}
      className="dialogue"
      onCancel={(e) => {
        e.preventDefault();
        if (e.target === e.currentTarget) demanderFermeture();
      }}
      // Fermée par le navigateur lui-même (Échap appuyé plusieurs fois) : on remet l'état à jour.
      // `target` : le « close » des confirmations ci-dessous remonte aussi jusqu'ici dans React.
      onClose={(e) => {
        if (e.target !== e.currentTarget || ref.current?.open || !ouvert) return;
        setQuitter(false);
        setConfirmation(null);
        fermer();
      }}
    >
      <div className="flex h-[min(86vh,820px)] w-[min(820px,calc(100vw-48px))] flex-col overflow-hidden rounded-[20px] border border-line bg-surface shadow-pop">
        {/* En-tête */}
        <div className="flex items-start gap-4 border-b border-line px-6 pb-4 pt-5">
          <Icone3D src={ICONES_3D.calendrier} taille={48} />
          <div className="min-w-0 flex-1">
            <h2 id={idTitre} className="text-20 font-semibold">
              Ajuster le calendrier
            </h2>
            <p className="text-13 text-fg-2">{fr("Autant de semaines que vous voulez : dupliquez ou supprimez-les.")}</p>
            {n && (
              <p className="tabular mt-1.5 text-13 font-medium text-brand-text">
                {fr(
                  `Besoins : ${pluriel(n.reel, "vidéo")} · ${pluriel(images, "image")} (${n.story} stories + ${n.story_cta} CTA + ${n.carousel} carrousels)`,
                )}
              </p>
            )}
          </div>
          <button
            type="button"
            onClick={demanderFermeture}
            aria-label="Fermer l'éditeur"
            className="grid h-8 w-8 shrink-0 place-items-center rounded-lg text-fg-3 transition-colors duration-150 hover:bg-fg/[0.06] hover:text-fg"
          >
            <X className="h-4 w-4" />
          </button>
        </div>

        {!cal ? (
          <div className="flex flex-1 items-center justify-center gap-2 text-13 text-fg-2" role="status">
            <Rouage /> Chargement du calendrier…
          </div>
        ) : (
          <>
            {/* Contenu + semaines */}
            <div className="flex flex-col gap-3 border-b border-line px-6 py-3.5">
              <div className="flex flex-wrap items-center gap-3">
                <span id="libelle-contenu" className="text-13 font-medium">
                  Contenu :
                </span>
                {/* Deux boutons « enfoncés / pas enfoncés » plutôt qu'un groupe radio : chaque choix
                    ouvre une confirmation, qui ne doit pas partir sur une simple flèche du clavier. */}
                <div role="group" aria-labelledby="libelle-contenu" className="inline-flex rounded-[10px] border border-line bg-fg/[0.04] p-0.5">
                  {(
                    [
                      ["mixte", "Images + Vidéos"],
                      ["reels", "Vidéos uniquement"],
                    ] as const
                  ).map(([mode, texte]) => {
                    const actif = (toutReels(cal) ? "reels" : "mixte") === mode;
                    return (
                      <button
                        key={mode}
                        type="button"
                        aria-pressed={actif}
                        onClick={() => !actif && choisirMode(mode)}
                        className={`flex h-8 items-center rounded-lg px-3.5 text-13 font-medium transition-[background-color,color,box-shadow] duration-150 ${
                          actif ? "bg-surface text-fg shadow-[0_0_0_1px_var(--line),0_1px_2px_rgba(0,0,0,0.08)]" : "text-fg-2 hover:text-fg"
                        }`}
                      >
                        {texte}
                      </button>
                    );
                  })}
                </div>
              </div>
              <div role="tablist" aria-label="Semaines" className="scroll-fin -mx-1 flex gap-1.5 overflow-x-auto px-1 pb-1">
                {semaines.map((nom) => {
                  const actif = nom === courant;
                  return (
                    <button
                      key={nom}
                      ref={(el) => {
                        onglets.current[nom] = el;
                      }}
                      type="button"
                      role="tab"
                      aria-selected={actif}
                      tabIndex={actif ? 0 : -1}
                      onClick={() => setCourant(nom)}
                      onKeyDown={(e) => flecheSemaine(e, nom)}
                      className={`h-8 shrink-0 rounded-lg px-3 text-13 font-medium transition-colors duration-150 ${
                        actif ? "bg-brand-btn text-white" : "bg-fg/[0.05] text-fg-2 hover:bg-fg/[0.09] hover:text-fg"
                      }`}
                    >
                      {libelleSemaine(nom)}
                    </button>
                  );
                })}
              </div>
            </div>

            {/* La semaine choisie */}
            <div role="tabpanel" aria-label={courant ? libelleSemaine(courant) : undefined} className="scroll-fin min-h-0 flex-1 overflow-y-auto bg-surface-2 px-6 py-4">
              {semaine && courant && (
                <>
                  <div className="flex flex-wrap gap-2">
                    <Bouton taille="sm" onClick={() => dupliquer(courant)}>
                      <Copy className="h-4 w-4 text-fg-2" aria-hidden="true" />
                      Dupliquer cette semaine
                    </Bouton>
                    <Bouton taille="sm" variante="danger" onClick={() => supprimer(courant)}>
                      <Trash className="h-4 w-4" aria-hidden="true" />
                      Supprimer cette semaine
                    </Bouton>
                  </div>
                  <div className="mt-4 flex flex-col gap-3">
                    {Object.entries(semaine).map(([jour, creneaux]) => (
                      <section key={jour} aria-label={libelleJour(jour)} className="rounded-xl border border-line bg-surface p-3.5">
                        <div className="flex items-center gap-3">
                          <h3 className="text-14 font-semibold">{libelleJour(jour)}</h3>
                          <span className="text-12 text-fg-3">{`${creneaux.length} créneau${creneaux.length > 1 ? "x" : ""}`}</span>
                          <Bouton
                            id={`ajouter-${jour}`}
                            taille="sm"
                            variante="fantome"
                            className="ml-auto"
                            onClick={() => changer((c) => c[courant][jour].push({ heure: "12h00", type: "reel" }))}
                          >
                            <Plus weight="bold" className="h-3.5 w-3.5" aria-hidden="true" />
                            Ajouter un créneau
                          </Bouton>
                        </div>
                        {creneaux.length > 0 && (
                          <ul className="mt-2.5 flex flex-col gap-2">
                            {creneaux.map((cr, k) => {
                              const invalide = !heureValide(cr.heure);
                              return (
                                <li key={k} className="flex items-center gap-2">
                                  <input
                                    value={cr.heure}
                                    onChange={(e) => {
                                      const v = e.target.value;
                                      changer((c) => {
                                        c[courant][jour][k].heure = v;
                                      });
                                    }}
                                    aria-label={`Heure du créneau ${k + 1}, ${libelleJour(jour)}`}
                                    aria-invalid={invalide || undefined}
                                    aria-describedby={invalide ? `erreur-${jour}-${k}` : undefined}
                                    placeholder="12h00"
                                    maxLength={40}
                                    spellCheck={false}
                                    className="selectable h-9 w-24 rounded-lg border border-line-2 bg-surface-2 px-2.5 font-mono text-13 outline-none transition-[border-color,box-shadow] duration-150 focus:border-brand focus:shadow-[0_0_0_3px_var(--brand-soft)] focus-visible:outline-2 focus-visible:outline-offset-1 focus-visible:outline-brand aria-[invalid=true]:border-danger"
                                  />
                                  <select
                                    value={cr.type}
                                    onChange={(e) => {
                                      const v = e.target.value as TypePost;
                                      changer((c) => {
                                        c[courant][jour][k].type = v;
                                      });
                                    }}
                                    aria-label={`Type du créneau ${k + 1}, ${libelleJour(jour)}`}
                                    className="h-9 rounded-lg border border-line-2 bg-surface px-2.5 text-13 outline-none focus:border-brand"
                                  >
                                    {TYPES_POST.map((t) => (
                                      <option key={t} value={t}>
                                        {LIBELLE_CRENEAU[t]}
                                      </option>
                                    ))}
                                  </select>
                                  <button
                                    type="button"
                                    onClick={() => {
                                      changer((c) => c[courant][jour].splice(k, 1));
                                      requestAnimationFrame(() => document.getElementById(`ajouter-${jour}`)?.focus());
                                    }}
                                    aria-label={`Supprimer le créneau ${k + 1} (${cr.heure}), ${libelleJour(jour)}`}
                                    className="grid h-9 w-9 place-items-center rounded-lg text-danger transition-colors duration-150 hover:bg-danger/10"
                                  >
                                    <X weight="bold" className="h-3.5 w-3.5" aria-hidden="true" />
                                  </button>
                                  {invalide && (
                                    <span id={`erreur-${jour}-${k}`} className="text-12 text-danger">
                                      Heure invalide
                                    </span>
                                  )}
                                </li>
                              );
                            })}
                          </ul>
                        )}
                      </section>
                    ))}
                  </div>
                </>
              )}
            </div>
          </>
        )}

        {/* Pied : Réinitialiser · message · Annuler / Enregistrer */}
        <div className="flex flex-wrap items-center gap-3 border-t border-line px-6 py-3.5">
          <Bouton taille="sm" variante="fantome" onClick={() => void reinitialiser()} disabled={!cal || enregistrement}>
            <ArrowCounterClockwise className="h-4 w-4" aria-hidden="true" />
            Réinitialiser
          </Bouton>
          <p role="status" className="min-w-0 flex-1 text-12 text-fg-3">
            {message ? (
              <span className="flex items-start gap-1.5 text-danger">
                <Warning weight="fill" className="mt-[2px] h-3.5 w-3.5 shrink-0" aria-hidden="true" />
                {fr(message)}
              </span>
            ) : modifie ? (
              "Modifications non enregistrées."
            ) : (
              ""
            )}
          </p>
          <Bouton taille="sm" onClick={demanderFermeture} disabled={enregistrement}>
            Annuler
          </Bouton>
          <Bouton taille="sm" variante="primaire" onClick={() => void enregistrer()} disabled={!cal} aria-busy={enregistrement || undefined}>
            {enregistrement ? <Rouage /> : <FloppyDisk className="h-4 w-4" aria-hidden="true" />}
            Enregistrer
          </Bouton>
        </div>
      </div>

      {/* Confirmations (supprimer une semaine, changer le contenu) */}
      <Dialogue
        ouvert={!!confirmation}
        fermer={() => setConfirmation(null)}
        ton={confirmation?.danger ? "danger" : "warning"}
        icone={<Warning weight="duotone" className="h-6 w-6" />}
        image={ICONES_3D.alerte}
        titre={confirmation?.titre ?? ""}
        actions={
          <>
            <Bouton data-autofocus onClick={() => setConfirmation(null)}>
              Annuler
            </Bouton>
            <Bouton
              variante={confirmation?.danger ? "alerte" : "primaire"}
              onClick={() => {
                confirmation?.faire();
                setConfirmation(null);
              }}
            >
              {confirmation?.action}
            </Bouton>
          </>
        }
      >
        <p>{confirmation ? fr(confirmation.texte) : ""}</p>
      </Dialogue>

      {/* Fermer avec des modifications : enregistrer, abandonner ou rester */}
      <Dialogue
        ouvert={quitter}
        fermer={() => setQuitter(false)}
        ton="warning"
        icone={<FloppyDisk weight="duotone" className="h-6 w-6" />}
        titre="Enregistrer les modifications du calendrier ?"
        actions={
          <>
            <Bouton data-autofocus onClick={() => setQuitter(false)}>
              Continuer à modifier
            </Bouton>
            <Bouton
              onClick={() => {
                setQuitter(false);
                fermer();
              }}
            >
              Ne pas enregistrer
            </Bouton>
            <Bouton
              variante="primaire"
              onClick={() => {
                setQuitter(false);
                void enregistrer();
              }}
            >
              Enregistrer
            </Bouton>
          </>
        }
      >
        <p>Vos changements ne sont pas encore enregistrés. Ils servent au prochain rangement une fois enregistrés.</p>
      </Dialogue>
    </dialog>
  );
}
