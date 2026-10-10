import { useEffect, useState } from "react";
import logo from "../../assets/logo.png";

/** Au-delà de ce délai, on rassure : hors-ligne, la vérification peut durer jusqu'à ~40 s. */
const LENT_MS = 6000;

/** Premier écran au lancement, le temps que le moteur vérifie la licence. */
export default function Verification() {
  const [lent, setLent] = useState(false);
  useEffect(() => {
    const id = setTimeout(() => setLent(true), LENT_MS);
    return () => clearTimeout(id);
  }, []);

  return (
    <div role="status" className="flex flex-col items-center text-center">
      <div className="relative grid h-28 w-28 place-items-center">
        <span aria-hidden="true" className="aura-logo absolute inset-0 rounded-full" />
        <img src={logo} alt="" className="relative h-[72px] w-[72px] drop-shadow-[0_10px_24px_rgba(76,111,255,0.4)]" />
      </div>
      <p className="mt-5 text-16 font-semibold">Vérification de votre licence…</p>
      {/* Hauteur réservée : le texte « lent » apparaît sans faire bouger le reste. */}
      <p className="mt-1.5 min-h-5 text-13 text-fg-2">{lent ? "La connexion semble lente. Encore un instant…" : ""}</p>
      <div aria-hidden="true" className="barre-indeterminee mt-5 h-1 w-44 overflow-hidden rounded-full bg-fg/[0.07]">
        <span />
      </div>
    </div>
  );
}
