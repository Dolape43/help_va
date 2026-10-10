import { ErreurMoteur } from "./engine/protocole";

/** La commande concernée par une erreur, quand le client l'a notée (délai dépassé…). */
function commandeDe(e: ErreurMoteur): string {
  const d = e.details as { cmd?: unknown } | null;
  return typeof d?.cmd === "string" ? d.cmd : "";
}

/** Texte d'une erreur du moteur, avec une phrase plus claire pour les cas fréquents. */
export function messageErreur(e: unknown): string {
  if (!(e instanceof ErreurMoteur)) return e instanceof Error ? e.message : String(e);
  switch (e.code) {
    case "LICENCE_REQUISE":
      // Juste après une reconnexion, le moteur attend la fin de la vérification de licence.
      return import.meta.env.DEV
        ? "Licence non vérifiée par le moteur : patientez, ou lancez le pont avec --sans-licence."
        : "Votre licence est en cours de vérification. Réessayez dans un instant.";
    case "DELAI_DEPASSE":
      // Seules les commandes de licence passent par internet : ailleurs, ce n'est pas le réseau.
      return commandeDe(e).startsWith("licence_")
        ? "Le serveur ne répond pas. Vérifiez votre connexion internet, puis réessayez."
        : "HelpVA n'a pas répondu à temps. Réessayez ; si cela continue, fermez puis rouvrez HelpVA.";
    default:
      return e.message;
  }
}

/** Le chemin à confirmer dans une erreur SORTIE_EXISTE (la sortie a changé depuis « preparer »). */
export function sortieAConfirmer(e: unknown): string | null {
  if (!(e instanceof ErreurMoteur) || e.code !== "SORTIE_EXISTE") return null;
  const d = e.details as { sortie?: unknown } | null;
  return typeof d?.sortie === "string" ? d.sortie : null;
}
