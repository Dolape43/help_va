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
  const r = await fetch(
    `${SUPA_URL}/rest/v1/licences?select=id,empreinte,nom_client,type,exp,premium,statut,cree_le&order=cree_le.desc`,
    { headers: dbHeaders() });
  return await r.json();
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
      const licence_id = await dbInsertLicenceRet({
        empreinte: emp, cle_hash, nom_client: c.nom_client || null,
        type: c.type, exp: (payload as any).exp || null, premium: !!c.premium, statut: "actif",
      });
      await dbMarquerCode(code, emp, licence_id);
      return json({ ok: true, licence, exp: (payload as any).exp || null });
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
    if (body.action === "lister") return json({ ok: true, licences: await dbListe() });
    if (body.action === "statut") {
      if (!["actif", "resiliee", "suspendu"].includes(body.statut)) return json({ erreur: "statut" }, 400);
      await dbStatut(body.id, body.statut);
      return json({ ok: true });
    }
    if (body.action === "creer_codes") {
      const n = Math.min(Math.max(parseInt(body.n) || 1, 1), 100);
      const type = ["vie", "mois", "an", "essai"].includes(body.type) ? body.type : "vie";
      const codes = Array.from({ length: n }, () => genererCode());
      await dbInsertCodes(codes.map((code) => ({
        code, type, premium: !!body.premium, jours: body.jours || null,
        nom_client: (body.nom || "").trim() || null, statut: "libre",
      })));
      return json({ ok: true, codes });
    }
    if (body.action === "lister_codes") return json({ ok: true, codes: await dbListeCodes() });
    return json({ erreur: "action inconnue" }, 400);
  } catch (e) {
    return json({ erreur: String(e) }, 500);
  }
});
