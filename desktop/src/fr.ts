/**
 * Typographie française.
 *
 * En français on met une espace avant « : ; ! ? % » et à l'intérieur des guillemets « ».
 * Si c'est une espace NORMALE, le navigateur peut couper la ligne juste là : on se retrouve
 * avec un « % » ou un « » » tout seul en début de ligne. L'espace insécable (U+00A0)
 * interdit cette coupure.
 *
 *   fr("Dossier : 43 %")  →  "Dossier : 43 %"
 */
const INSECABLE = " ";

export function fr(texte: string): string {
  return texte.replace(/ ([:;!?»%])/g, `${INSECABLE}$1`).replace(/« /g, `«${INSECABLE}`);
}

/** « 1 vidéo », « 11 vidéos » (au lieu de « vidéo(s) ») pour les textes de l'interface. */
export function pluriel(n: number, mot: string): string {
  return `${n}${INSECABLE}${n > 1 ? `${mot}s` : mot}`;
}
