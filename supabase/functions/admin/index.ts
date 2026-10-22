// HelpVA — API licences (Edge Function). Génère des licences signées (Ed25519)
// + gère les statuts. La PAGE web est hébergée à part (Netlify) et appelle cette API.
// Secrets requis : PRIVEE_PEM (clé privée), ADMIN_MDP (mot de passe admin).
// SUPABASE_URL et SUPABASE_SERVICE_ROLE_KEY sont fournis automatiquement.
// ⚠️ Déployer avec "Verify JWT" DÉSACTIVÉ.

const PEM = Deno.env.get("PRIVEE_PEM") ?? "";
const MDP = Deno.env.get("ADMIN_MDP") ?? "";
const SUPA_URL = Deno.env.get("SUPABASE_URL")!;
const SERVICE = Deno.env.get("SUPABASE_SERVICE_ROLE_KEY")!;

const CORS = {
  "Access-Control-Allow-Origin": "*",
  "Access-Control-Allow-Methods": "POST, OPTIONS",
  "Access-Control-Allow-Headers": "authorization, apikey, content-type, x-client-info",
};

// ---------- crypto / encodage (miroir exact du format Python) ----------
function pemToDer(pem: string): Uint8Array {
  const b64 = pem.replace(/-----[^-]+-----/g, "").replace(/\s+/g, "");
  const bin = atob(b64);
  const der = new Uint8Array(bin.length);
  for (let i = 0; i < bin.length; i++) der[i] = bin.charCodeAt(i);
  return der;
}
function b64url(bytes: Uint8Array): string {
  let s = "";
  for (const b of bytes) s += String.fromCharCode(b);
  return btoa(s).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");
}
function canonical(obj: Record<string, unknown>): string {
  const keys = Object.keys(obj).sort();
  return "{" + keys.map((k) => JSON.stringify(k) + ":" + JSON.stringify(obj[k])).join(",") + "}";
}
async function sha256hex(txt: string): Promise<string> {
  const h = await crypto.subtle.digest("SHA-256", new TextEncoder().encode(txt));
  return [...new Uint8Array(h)].map((b) => b.toString(16).padStart(2, "0")).join("");
}
function addMonths(d: Date, n: number): Date {
  const total = d.getUTCMonth() + n;
  const year = d.getUTCFullYear() + Math.floor(total / 12);
  const month = ((total % 12) + 12) % 12;
  const leap = (year % 4 === 0 && (year % 100 !== 0 || year % 400 === 0));
  const dim = [31, leap ? 29 : 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31][month];
  const day = Math.min(d.getUTCDate(), dim);
  return new Date(Date.UTC(year, month, day));
}
const isoDate = (d: Date) => d.toISOString().slice(0, 10);

let cleSignature: CryptoKey | null = null;
async function getCle(): Promise<CryptoKey> {
  if (!cleSignature) {
    cleSignature = await crypto.subtle.importKey(
      "pkcs8", pemToDer(PEM), { name: "Ed25519" }, false, ["sign"]);
  }
  return cleSignature;
}
function construirePayload(emp: string, type: string, nom: string, premium: boolean, jours: number) {
  const p: Record<string, unknown> = { emp: emp.trim().toUpperCase(), type };
  if (nom && nom.trim()) p.nom = nom.trim();
  if (premium) p.premium = true;
  const today = new Date();
  if (type === "mois") p.exp = isoDate(addMonths(today, 1));
  else if (type === "an") p.exp = isoDate(addMonths(today, 12));
  else if (type === "essai") p.exp = isoDate(new Date(today.getTime() + (jours || 3) * 86400000));
  return p;
}
async function genererLicence(payload: Record<string, unknown>): Promise<string> {
  const pb = new TextEncoder().encode(canonical(payload));
  const partie = b64url(pb);
  const sig = new Uint8Array(await crypto.subtle.sign(
    { name: "Ed25519" }, await getCle(), new TextEncoder().encode(partie)));
  return partie + "." + b64url(sig);
}

// ---------- accès base (service role, contourne RLS) ----------
function dbHeaders(extra: Record<string, string> = {}) {
  return { apikey: SERVICE, Authorization: `Bearer ${SERVICE}`, ...extra };
}
async function dbInsert(row: unknown) {
  const r = await fetch(`${SUPA_URL}/rest/v1/licences`, {
    method: "POST",
    headers: dbHeaders({ "Content-Type": "application/json", Prefer: "return=minimal" }),
    body: JSON.stringify(row),
  });
  if (!r.ok) throw new Error("db insert " + r.status + " " + (await r.text()));
}
async function dbListe() {
  // Les VA supprimés (supprime_le renseigné) ne sont plus listés ; chaque licence vient avec
  // son agence_id. Si une colonne n'existe pas encore (SQL 20261023_suppression_va.sql ou
  // 20261023_agences.sql pas appliqué), on liste sans elle plutôt que de casser la console.
  const champs = "id,empreinte,nom_client,type,exp,premium,statut,cree_le";
  const essais = [
    `select=${champs},agence_id&supprime_le=is.null`,
    `select=${champs}&supprime_le=is.null`,
    `select=${champs},agence_id`,
    `select=${champs}`,
  ];
  let derniere = "";
  for (const q of essais) {
    const r = await fetch(`${SUPA_URL}/rest/v1/licences?${q}&order=cree_le.desc`, { headers: dbHeaders() });
    if (r.ok) return await r.json();
    derniere = r.status + " " + (await r.text());
  }
  throw new Error("db licences " + derniere);
}
async function dbSupprimer(id: string) {
  // « Supprimer » = résilier + masquer (voir supabase/migrations/20261023_suppression_va.sql).
  const r = await fetch(`${SUPA_URL}/rest/v1/licences?id=eq.${id}`, {
    method: "PATCH",
    headers: dbHeaders({ "Content-Type": "application/json", Prefer: "return=minimal" }),
    body: JSON.stringify({ statut: "resiliee", supprime_le: new Date().toISOString() }),
  });
  if (!r.ok) throw new Error("Suppression impossible (" + r.status + "). Le SQL 20261023_suppression_va.sql est-il appliqué ?");
}
async function dbStatut(id: string, statut: string) {
  const r = await fetch(`${SUPA_URL}/rest/v1/licences?id=eq.${id}`, {
    method: "PATCH",
    headers: dbHeaders({ "Content-Type": "application/json", Prefer: "return=minimal" }),
    body: JSON.stringify({ statut }),
  });
  if (!r.ok) throw new Error("db patch " + r.status);
}

// ---------- codes d'activation (semi-auto) ----------
async function dbCode(code: string) {
  const r = await fetch(
    `${SUPA_URL}/rest/v1/codes?code=eq.${encodeURIComponent(code)}&select=*`,
    { headers: dbHeaders() });
  const rows = await r.json();
  return rows[0] || null;
}
async function dbInsertLicenceRet(row: unknown): Promise<string> {
  const r = await fetch(`${SUPA_URL}/rest/v1/licences`, {
    method: "POST",
    headers: dbHeaders({ "Content-Type": "application/json", Prefer: "return=representation" }),
    body: JSON.stringify(row),
  });
  if (!r.ok) throw new Error("db insert lic " + r.status + " " + (await r.text()));
  return (await r.json())[0].id;
}
async function dbMarquerCode(code: string, empreinte: string, licence_id: string) {
  await fetch(`${SUPA_URL}/rest/v1/codes?code=eq.${encodeURIComponent(code)}&statut=eq.libre`, {
    method: "PATCH",
    headers: dbHeaders({ "Content-Type": "application/json", Prefer: "return=minimal" }),
    body: JSON.stringify({ statut: "utilise", empreinte, licence_id, utilise_le: new Date().toISOString() }),
  });
}
async function dbInsertCodes(rows: unknown[]) {
  const r = await fetch(`${SUPA_URL}/rest/v1/codes`, {
    method: "POST",
    headers: dbHeaders({ "Content-Type": "application/json", Prefer: "return=minimal" }),
    body: JSON.stringify(rows),
  });
  if (!r.ok) throw new Error("db insert codes " + r.status + " " + (await r.text()));
}
async function dbListeCodes() {
  const r = await fetch(
    `${SUPA_URL}/rest/v1/codes?select=code,type,premium,statut,nom_client,empreinte,cree_le,utilise_le&order=cree_le.desc`,
    { headers: dbHeaders() });
  return await r.json();
}
function genererCode(): string {
  const alpha = "ABCDEFGHJKMNPQRSTUVWXYZ23456789"; // sans I O 0 1 L (ambigus)
  const rnd = crypto.getRandomValues(new Uint8Array(12));
  let s = "";
  for (let i = 0; i < 12; i++) s += alpha[rnd[i] % alpha.length];
  return "HELP-" + s.slice(0, 4) + "-" + s.slice(4, 8) + "-" + s.slice(8, 12);
}

// ---------- compteur d'activité des VA (table activite, voir supabase/migrations) ----------
const CATEGORIES = ["images", "videos", "metadonnees"] as const;
const MAX_COMPTEUR = 1_000_000;
const MAX_JOURS = 31;

async function dbLicenceParHash(cle_hash: string) {
  const r = await fetch(
    `${SUPA_URL}/rest/v1/licences?cle_hash=eq.${cle_hash}&select=id,statut`,
    { headers: dbHeaders() });
  if (!r.ok) throw new Error("db licence " + r.status);
  const rows = await r.json();
  return rows[0] || null;
}
async function dbUpsertActivite(rows: unknown[]) {
  // UPSERT : une ligne par (licence, jour). L'app envoie des valeurs ABSOLUES :
  // renvoyer le même jour remplace la ligne, il ne s'ajoute jamais en double.
  const r = await fetch(`${SUPA_URL}/rest/v1/activite?on_conflict=licence_id,jour`, {
    method: "POST",
    headers: dbHeaders({ "Content-Type": "application/json",
                         Prefer: "resolution=merge-duplicates,return=minimal" }),
    body: JSON.stringify(rows),
  });
  if (!r.ok) throw new Error("db upsert activite " + r.status + " " + (await r.text()));
}
async function dbToutesActivites() {
  // PostgREST renvoie 1 000 lignes au plus par requête : on lit page par page.
  const lignes: any[] = [];
  for (let debut = 0; ; debut += 1000) {
    const r = await fetch(
      `${SUPA_URL}/rest/v1/activite?select=licence_id,jour,images,videos,metadonnees` +
      `&order=jour.asc,licence_id.asc&limit=1000&offset=${debut}`,
      { headers: dbHeaders() });
    if (!r.ok) throw new Error("db activite " + r.status);
    const page = await r.json();
    lignes.push(...page);
    if (page.length < 1000) return lignes;
  }
}
// "AAAA-MM-JJ" valide (le 31 février est refusé) -> la date (UTC, minuit), sinon null.
function dateValide(j: unknown): Date | null {
  if (typeof j !== "string" || !/^\d{4}-\d{2}-\d{2}$/.test(j)) return null;
  const d = new Date(j + "T00:00:00Z");
  return isNaN(d.getTime()) || isoDate(d) !== j ? null : d;
}
const compteurValide = (v: unknown) =>
  typeof v === "number" && Number.isInteger(v) && v >= 0 && v <= MAX_COMPTEUR;
const plusJours = (d: Date, n: number) => new Date(d.getTime() + n * 86400000);

// Jours envoyés par l'app -> lignes à enregistrer, ou un message d'erreur (texte).
function validerJours(jours: unknown, licence_id: string): unknown[] | string {
  if (!Array.isArray(jours)) return "« jours » doit être une liste.";
  if (jours.length > MAX_JOURS) return `${MAX_JOURS} jours au maximum par envoi.`;
  // Le PC du VA peut avoir un fuseau en avance sur UTC : on tolère 1 jour dans le futur.
  const limite = plusJours(new Date(isoDate(new Date()) + "T00:00:00Z"), 1);
  const parJour = new Map<string, Record<string, unknown>>();
  for (const j of jours) {
    if (!j || typeof j !== "object") return "Jour invalide.";
    const d = dateValide((j as any).jour);
    if (!d) return "Date invalide (format AAAA-MM-JJ attendu).";
    if (d > limite) return "Date dans le futur : " + (j as any).jour;
    const ligne: Record<string, unknown> = { licence_id, jour: (j as any).jour,
                                             maj_le: new Date().toISOString() };
    for (const c of CATEGORIES) {
      const v = (j as any)[c] ?? 0;
      if (!compteurValide(v)) return `Compteur « ${c} » invalide (entier de 0 à ${MAX_COMPTEUR}).`;
      ligne[c] = v;
    }
    // Deux fois le même jour dans un envoi : Postgres refuserait l'UPSERT -> on garde le dernier.
    parJour.set(ligne.jour as string, ligne);
  }
  return [...parJour.values()];
}

// Totaux par licence pour la console : aujourd'hui / 7 jours / 30 jours / total + dernier jour actif.
// « aujourd'hui » = la date du NAVIGATEUR de l'admin (son fuseau), sinon celle d'UTC.
function resumerActivite(licences: any[], lignes: any[], aujourdhui: Date) {
  const vide = () => ({ images: 0, videos: 0, metadonnees: 0, total: 0 });
  const auj = isoDate(aujourdhui);
  const debut7 = isoDate(plusJours(aujourdhui, -6));
  const debut30 = isoDate(plusJours(aujourdhui, -29));
  const parLicence = new Map<string, any>();
  for (const l of licences) {
    parLicence.set(l.id, {
      id: l.id, nom_client: l.nom_client, empreinte: l.empreinte, type: l.type, statut: l.statut,
      agence_id: l.agence_id ?? null, agence_nom: l.agence_nom ?? null,
      aujourd_hui: vide(), semaine: vide(), mois: vide(), total: vide(), dernier_jour: null,
    });
  }
  for (const r of lignes) {
    const a = parLicence.get(r.licence_id);
    if (!a) continue;
    const blocs = [a.total];
    if (r.jour >= debut30 && r.jour <= auj) blocs.push(a.mois);
    if (r.jour >= debut7 && r.jour <= auj) blocs.push(a.semaine);
    if (r.jour === auj) blocs.push(a.aujourd_hui);
    let somme = 0;
    for (const c of CATEGORIES) somme += r[c] || 0;
    for (const b of blocs) {
      for (const c of CATEGORIES) b[c] += r[c] || 0;
      b.total += somme;
    }
    if (somme > 0 && (!a.dernier_jour || r.jour > a.dernier_jour)) a.dernier_jour = r.jour;
  }
  return [...parLicence.values()];
}

// ---------- fiche profil d'un VA + « nouveau code pour ce VA » ----------
const TYPES = ["vie", "mois", "an", "essai"];
const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;
const EMPREINTE = /^[A-Z0-9]{4}-[A-Z0-9]{4}-[A-Z0-9]{4}-[A-Z0-9]{4}$/;
const COLS_LICENCE = "id,empreinte,nom_client,type,exp,premium,statut,cree_le";
const COLS_CODE = "code,type,premium,jours,statut,nom_client,empreinte,licence_id,cree_le,utilise_le";

async function dbLire(table: string, filtre: string, cols: string) {
  const r = await fetch(`${SUPA_URL}/rest/v1/${table}?select=${cols}&${filtre}`, { headers: dbHeaders() });
  if (!r.ok) throw new Error("db " + table + " " + r.status + " " + (await r.text()));
  return await r.json();
}
async function dbLicence(id: string) {
  // Avec agence_id si la colonne existe (SQL 20261023_agences.sql), sinon sans.
  try {
    const rows = await dbLire("licences", `id=eq.${id}`, COLS_LICENCE + ",agence_id");
    return rows[0] || null;
  } catch {
    const rows = await dbLire("licences", `id=eq.${id}`, COLS_LICENCE);
    return rows[0] || null;
  }
}
async function dbActiviteLicence(licence_id: string) {
  // Même lecture page par page que dbToutesActivites, limitée à une licence.
  const lignes: any[] = [];
  for (let debut = 0; ; debut += 1000) {
    const page = await dbLire("activite",
      `licence_id=eq.${licence_id}&order=jour.asc&limit=1000&offset=${debut}`,
      "licence_id,jour,images,videos,metadonnees");
    lignes.push(...page);
    if (page.length < 1000) return lignes;
  }
}
// Fusionne plusieurs listes en retirant les doublons (même valeur de « cle »).
function fusionner(listes: any[][], cle: string) {
  const vus = new Map<string, any>();
  for (const l of listes) for (const x of l) vus.set(x[cle], x);
  return [...vus.values()];
}

// Licences et codes du même VA : même nom_client (s'il existe), même empreinte,
// ou code lié par licence_id. Sans nom : la licence et son empreinte seulement.
async function profilVA(lic: any, aujourdhui: Date) {
  const nom = (lic.nom_client || "").trim();
  const parEmp = EMPREINTE.test(lic.empreinte || "")
    ? dbLire("licences", `empreinte=eq.${lic.empreinte}`, COLS_LICENCE) : Promise.resolve([]);
  const parNom = nom
    ? dbLire("licences", `nom_client=eq.${encodeURIComponent(nom)}`, COLS_LICENCE) : Promise.resolve([]);
  const licences = fusionner([[lic], await parEmp, await parNom], "id");

  const ids = licences.map((l) => l.id).filter((id) => UUID.test(id));
  const emps = [...new Set(licences.map((l) => l.empreinte).filter((e) => EMPREINTE.test(e || "")))];
  const requetes: Promise<any[]>[] = [];
  if (ids.length) requetes.push(dbLire("codes", `licence_id=in.(${ids.join(",")})`, COLS_CODE));
  if (emps.length) requetes.push(dbLire("codes", `empreinte=in.(${emps.join(",")})`, COLS_CODE));
  if (nom) requetes.push(dbLire("codes", `nom_client=eq.${encodeURIComponent(nom)}`, COLS_CODE));
  const codes = fusionner(await Promise.all(requetes), "code");

  const parDate = (a: any, b: any) => String(b.cree_le || "").localeCompare(String(a.cree_le || ""));
  licences.sort(parDate);
  codes.sort(parDate);

  // Activité de CETTE licence : totaux (mêmes calculs que l'onglet Activité)
  // + jours actifs des 90 derniers jours, du plus récent au plus ancien.
  const lignes = await dbActiviteLicence(lic.id);
  const r = resumerActivite([lic], lignes, aujourdhui)[0];
  const debut90 = isoDate(plusJours(aujourdhui, -89));
  const auj = isoDate(aujourdhui);
  const jours = lignes
    .filter((l) => l.jour >= debut90 && l.jour <= auj)
    .map((l) => ({ jour: l.jour, images: l.images || 0, videos: l.videos || 0, metadonnees: l.metadonnees || 0,
                   total: (l.images || 0) + (l.videos || 0) + (l.metadonnees || 0) }))
    .filter((l) => l.total > 0)
    .reverse();
  return {
    licence: lic,
    licences_liees: licences.filter((l) => l.id !== lic.id),
    codes,
    activite: {
      totaux: { aujourd_hui: r.aujourd_hui, semaine: r.semaine, mois: r.mois, total: r.total, dernier_jour: r.dernier_jour },
      jours,
    },
  };
}

// Nouveau code d'activation pour un VA existant : mêmes nom, formule, premium (et jours d'essai),
// même agence (si le VA en a une).
// Le code garde licence_id = l'ancienne licence tant qu'il est libre (lien visible dans la fiche) ;
// à l'activation, dbMarquerCode le remplace par la nouvelle licence.
async function nouveauCodePour(lic: any, typeDemande: unknown) {
  const type = TYPES.includes(typeDemande as string) ? typeDemande as string
    : (TYPES.includes(lic.type) ? lic.type : "vie");
  let jours: number | null = null;
  if (type === "essai") {
    const anciens = await dbLire("codes", `licence_id=eq.${lic.id}&jours=not.is.null&limit=1`, "jours");
    jours = anciens[0]?.jours || null; // null -> 3 jours par défaut à l'activation
  }
  const code = genererCode();
  await dbInsertCodes([{
    code, type, premium: !!lic.premium, jours,
    nom_client: (lic.nom_client || "").trim() || null, statut: "libre", licence_id: lic.id,
    ...(lic.agence_id ? { agence_id: lic.agence_id } : {}),
  }]);
  return code;
}

// ---------- agences (ranger les VA par agence, voir supabase/migrations/20261023_agences.sql) ----------
const MSG_AGENCES_ABSENTES =
  "Les agences ne sont pas encore installées : exécute d'abord le SQL 20261023_agences.sql dans Supabase.";
const MAX_NOM_AGENCE = 60;

// Erreur « normale » (saisie invalide, doublon…) : renvoyée telle quelle à la console.
class ErreurClient extends Error {
  status: number;
  constructor(message: string, status = 400) { super(message); this.status = status; }
}
// Table ou colonne absente (SQL pas encore appliqué) : PostgREST répond 404 (table) ou 400 (colonne).
const sqlAbsent = (status: number, texte: string) =>
  status === 404 || /42P01|42703|PGRST20[045]/.test(texte);

function nomAgence(v: unknown): string {
  const nom = typeof v === "string" ? v.trim().replace(/\s+/g, " ") : "";
  if (!nom || nom.length > MAX_NOM_AGENCE)
    throw new ErreurClient(`Nom d'agence invalide (1 à ${MAX_NOM_AGENCE} caractères).`);
  return nom;
}
// UUID facultatif : null / "" -> null ; sinon un UUID valide, ou une erreur claire.
function uuidOuNull(v: unknown, quoi: string): string | null {
  if (v == null || v === "") return null;
  const id = typeof v === "string" ? v.trim() : "";
  if (!UUID.test(id)) throw new ErreurClient(`Identifiant ${quoi} invalide.`);
  return id;
}

// Liste des agences. strict = false : null si la table n'existe pas encore (la console
// fonctionne alors sans agences) ; strict = true : erreur claire à la place.
async function dbAgences(strict = false): Promise<any[] | null> {
  const r = await fetch(`${SUPA_URL}/rest/v1/agences?select=id,nom,cree_le&order=nom.asc`, { headers: dbHeaders() });
  if (r.ok) return await r.json();
  if (!strict) return null;
  const texte = await r.text();
  if (sqlAbsent(r.status, texte)) throw new ErreurClient(MSG_AGENCES_ABSENTES);
  throw new Error("db agences " + r.status + " " + texte);
}
async function agenceExiste(id: string) {
  return ((await dbAgences(true)) || []).some((a) => a.id === id);
}
// Écriture dans la table agences (création, renommage, suppression) -> lignes touchées.
async function dbEcrireAgences(methode: string, filtre: string, corps?: unknown): Promise<any[]> {
  const r = await fetch(`${SUPA_URL}/rest/v1/agences?select=id,nom${filtre}`, {
    method: methode,
    headers: dbHeaders({ "Content-Type": "application/json", Prefer: "return=representation" }),
    body: corps === undefined ? undefined : JSON.stringify(corps),
  });
  const texte = await r.text();
  if (r.ok) return texte ? JSON.parse(texte) : [];
  // Index unique sur lower(nom) : « Erika » et « erika » sont la même agence.
  if (r.status === 409 || texte.includes("23505")) throw new ErreurClient("Cette agence existe déjà.", 409);
  if (sqlAbsent(r.status, texte)) throw new ErreurClient(MSG_AGENCES_ABSENTES);
  throw new Error("db agences " + r.status + " " + texte);
}
// Ajoute agence_nom à chaque licence (agence_id absent = SQL pas appliqué -> null).
function nommerAgences(licences: any[], agences: any[] | null) {
  const noms = new Map((agences || []).map((a) => [a.id, a.nom]));
  for (const l of licences) {
    l.agence_id = l.agence_id ?? null;
    l.agence_nom = l.agence_id ? noms.get(l.agence_id) ?? null : null;
  }
  return licences;
}
// Agences + nombre de VA (licences non supprimées) dans chacune. null reste null.
function compterVA(agences: any[] | null, licences: any[]) {
  if (!agences) return null;
  const nb = new Map<string, number>();
  for (const l of licences) if (l.agence_id) nb.set(l.agence_id, (nb.get(l.agence_id) || 0) + 1);
  return agences.map((a) => ({ id: a.id, nom: a.nom, cree_le: a.cree_le, nb_va: nb.get(a.id) || 0 }));
}
async function dbLicenceAgence(licence_id: string, agence_id: string | null) {
  const r = await fetch(`${SUPA_URL}/rest/v1/licences?id=eq.${licence_id}&select=id`, {
    method: "PATCH",
    headers: dbHeaders({ "Content-Type": "application/json", Prefer: "return=representation" }),
    body: JSON.stringify({ agence_id }),
  });
  const texte = await r.text();
  if (!r.ok) {
    if (sqlAbsent(r.status, texte)) throw new ErreurClient(MSG_AGENCES_ABSENTES);
    if (r.status === 409 || texte.includes("23503")) throw new ErreurClient("Agence introuvable.", 404);
    throw new Error("db licence agence " + r.status + " " + texte);
  }
  return (texte ? JSON.parse(texte) : []).length > 0;
}

const json = (o: unknown, s = 200) =>
  new Response(JSON.stringify(o), { status: s, headers: { "Content-Type": "application/json", ...CORS } });

Deno.serve(async (req) => {
  if (req.method === "OPTIONS") return new Response("ok", { headers: CORS });
  if (req.method === "GET") return json({ ok: true, service: "HelpVA licences API" });
  if (req.method !== "POST") return json({ erreur: "methode" }, 405);

  let body: any;
  try { body = await req.json(); } catch { return json({ erreur: "json" }, 400); }

  try {
    // --- Action PUBLIQUE (app du client) : activer par code ---
    if (body.action === "activer") {
      const emp = (body.empreinte || "").trim().toUpperCase();
      if (!/^[A-Z0-9]{4}-[A-Z0-9]{4}-[A-Z0-9]{4}-[A-Z0-9]{4}$/.test(emp))
        return json({ erreur: "Empreinte invalide." }, 400);
      const code = (body.code || "").trim().toUpperCase();
      const c = await dbCode(code);
      if (!c) return json({ erreur: "Code inconnu." }, 404);
      if (c.statut !== "libre") return json({ erreur: "Code déjà utilisé." }, 409);
      const payload = construirePayload(emp, c.type, c.nom_client || "", !!c.premium, c.jours || 0);
      const licence = await genererLicence(payload);
      const cle_hash = await sha256hex(licence);
      const ligne = {
        empreinte: emp, cle_hash, nom_client: c.nom_client || null,
        type: c.type, exp: (payload as any).exp || null, premium: !!c.premium, statut: "actif",
      };
      // L'agence du code passe à la licence. Si ça échoue (SQL des agences incomplet…),
      // on active SANS agence : l'activation d'un VA ne doit jamais échouer à cause des agences.
      let licence_id: string;
      if (c.agence_id) {
        try { licence_id = await dbInsertLicenceRet({ ...ligne, agence_id: c.agence_id }); }
        catch { licence_id = await dbInsertLicenceRet(ligne); }
      } else {
        licence_id = await dbInsertLicenceRet(ligne);
      }
      await dbMarquerCode(code, emp, licence_id);
      return json({ ok: true, licence, exp: (payload as any).exp || null });
    }

    // --- Action PUBLIQUE (app du client) : compteurs d'activité du VA ---
    // L'app envoie le texte de SA licence : on le retrouve par son empreinte SHA-256
    // (cle_hash, comme pour verifier_licence). Seule une licence ACTIVE peut écrire.
    if (body.action === "activite") {
      const licence = typeof body.licence === "string" ? body.licence.trim() : "";
      if (!licence || licence.length > 4096) return json({ erreur: "Licence absente." }, 400);
      const lic = await dbLicenceParHash(await sha256hex(licence));
      if (!lic || lic.statut !== "actif") return json({ erreur: "Licence inconnue ou inactive." }, 403);
      const lignes = validerJours(body.jours, lic.id);
      if (typeof lignes === "string") return json({ erreur: lignes }, 400);
      if (lignes.length) await dbUpsertActivite(lignes);
      return json({ ok: true });
    }

    // --- Actions ADMIN (mot de passe requis) ---
    if (!MDP || body.mdp !== MDP) return json({ erreur: "mauvais mot de passe" }, 401);

    if (body.action === "generer") {
      const emp = (body.empreinte || "").trim().toUpperCase();
      if (!/^[A-Z0-9]{4}-[A-Z0-9]{4}-[A-Z0-9]{4}-[A-Z0-9]{4}$/.test(emp))
        return json({ erreur: "empreinte invalide (format ABCD-EFGH-IJKL-MNOP)" }, 400);
      const type = ["vie", "mois", "an", "essai"].includes(body.type) ? body.type : "vie";
      const payload = construirePayload(emp, type, body.nom || "", !!body.premium, body.jours || 0);
      const licence = await genererLicence(payload);
      const cle_hash = await sha256hex(licence);
      await dbInsert({
        empreinte: emp, cle_hash, nom_client: (body.nom || "").trim() || null,
        type, exp: (payload as any).exp || null, premium: !!body.premium, statut: "actif",
      });
      return json({ ok: true, licence, exp: (payload as any).exp || null });
    }
    if (body.action === "lister") {
      // agences = null tant que le SQL des agences n'est pas appliqué (la console les masque).
      const [licences, agences] = await Promise.all([dbListe(), dbAgences()]);
      return json({ ok: true, licences: nommerAgences(licences, agences), agences: compterVA(agences, licences) });
    }
    if (body.action === "supprimer") {
      const id = typeof body.id === "string" ? body.id.trim() : "";
      if (!UUID.test(id)) return json({ erreur: "Identifiant de licence invalide." }, 400);
      await dbSupprimer(id);
      return json({ ok: true });
    }
    if (body.action === "statut") {
      if (!["actif", "resiliee", "suspendu"].includes(body.statut)) return json({ erreur: "statut" }, 400);
      await dbStatut(body.id, body.statut);
      return json({ ok: true });
    }
    if (body.action === "creer_codes") {
      const n = Math.min(Math.max(parseInt(body.n) || 1, 1), 100);
      const type = ["vie", "mois", "an", "essai"].includes(body.type) ? body.type : "vie";
      // Agence facultative : sans elle, les codes sont créés comme avant (même sans le SQL des agences).
      const agence_id = uuidOuNull(body.agence_id, "d'agence");
      if (agence_id && !(await agenceExiste(agence_id))) return json({ erreur: "Agence introuvable." }, 404);
      const codes = Array.from({ length: n }, () => genererCode());
      await dbInsertCodes(codes.map((code) => ({
        code, type, premium: !!body.premium, jours: body.jours || null,
        nom_client: (body.nom || "").trim() || null, statut: "libre",
        ...(agence_id ? { agence_id } : {}),
      })));
      return json({ ok: true, codes });
    }
    if (body.action === "lister_codes") return json({ ok: true, codes: await dbListeCodes() });
    if (body.action === "agences_lister") {
      const agences = await dbAgences(true);
      return json({ ok: true, agences: compterVA(agences, await dbListe()) });
    }
    if (body.action === "agence_creer") {
      const rows = await dbEcrireAgences("POST", "", { nom: nomAgence(body.nom) });
      return json({ ok: true, agence: rows[0] || null });
    }
    if (body.action === "agence_renommer") {
      const id = uuidOuNull(body.id, "d'agence");
      if (!id) return json({ erreur: "Identifiant d'agence invalide." }, 400);
      const rows = await dbEcrireAgences("PATCH", `&id=eq.${id}`, { nom: nomAgence(body.nom) });
      if (!rows.length) return json({ erreur: "Agence introuvable." }, 404);
      return json({ ok: true, agence: rows[0] });
    }
    if (body.action === "agence_supprimer") {
      // « on delete set null » (voir le SQL) : ses licences et codes passent « sans agence ».
      const id = uuidOuNull(body.id, "d'agence");
      if (!id) return json({ erreur: "Identifiant d'agence invalide." }, 400);
      const rows = await dbEcrireAgences("DELETE", `&id=eq.${id}`);
      if (!rows.length) return json({ erreur: "Agence introuvable." }, 404);
      return json({ ok: true });
    }
    if (body.action === "licence_agence") {
      const licence_id = uuidOuNull(body.licence_id, "de licence");
      if (!licence_id) return json({ erreur: "Identifiant de licence invalide." }, 400);
      const agence_id = uuidOuNull(body.agence_id, "d'agence"); // null = « sans agence »
      if (agence_id && !(await agenceExiste(agence_id))) return json({ erreur: "Agence introuvable." }, 404);
      if (!(await dbLicenceAgence(licence_id, agence_id))) return json({ erreur: "Licence introuvable." }, 404);
      return json({ ok: true });
    }
    if (body.action === "activite_lister") {
      // Calcul en JS à partir de toutes les lignes (quelques milliers au plus : reste simple).
      const aujourdhui = dateValide(body.aujourdhui) ?? new Date(isoDate(new Date()) + "T00:00:00Z");
      const [licences, lignes, agences] = await Promise.all([dbListe(), dbToutesActivites(), dbAgences()]);
      nommerAgences(licences, agences);
      return json({ ok: true, activite: resumerActivite(licences, lignes, aujourdhui),
                    agences: compterVA(agences, licences) });
    }
    if (body.action === "profil" || body.action === "nouveau_code") {
      const id = typeof body.licence_id === "string" ? body.licence_id.trim() : "";
      if (!UUID.test(id)) return json({ erreur: "Identifiant de licence invalide." }, 400);
      const lic = await dbLicence(id);
      if (!lic) return json({ erreur: "Licence introuvable." }, 404);
      if (body.action === "profil") {
        const aujourdhui = dateValide(body.aujourd_hui ?? body.aujourdhui)
          ?? new Date(isoDate(new Date()) + "T00:00:00Z");
        const agences = await dbAgences();
        nommerAgences([lic], agences);
        return json({ ok: true, ...(await profilVA(lic, aujourdhui)), agences });
      }
      if (body.type != null && !TYPES.includes(body.type))
        return json({ erreur: "Formule invalide (vie, mois, an ou essai)." }, 400);
      const code = await nouveauCodePour(lic, body.type);
      // Le code est créé AVANT la résiliation : en cas d'erreur, le VA n'est jamais bloqué sans code.
      if (body.resilier_ancienne === true && lic.statut !== "resiliee") await dbStatut(lic.id, "resiliee");
      return json({ ok: true, code });
    }
    return json({ erreur: "action inconnue" }, 400);
  } catch (e) {
    if (e instanceof ErreurClient) return json({ erreur: e.message }, e.status);
    return json({ erreur: String(e) }, 500);
  }
});
