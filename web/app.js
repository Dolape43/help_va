/* HelpVA — interface web. Rendu + navigation + pont Python (pywebview). */

const api = () => window.pywebview.api;
const $ = (sel, el = document) => el.querySelector(sel);
let S = {};                 // état courant (modèle, licence, abonnement…)
let PAGE = "home";

/* ---------- Icônes (SVG en ligne) ---------- */
const I = {
  grid: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><rect x="3" y="3" width="7" height="7" rx="1.5"/><rect x="14" y="3" width="7" height="7" rx="1.5"/><rect x="3" y="14" width="7" height="7" rx="1.5"/><rect x="14" y="14" width="7" height="7" rx="1.5"/></svg>',
  box: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M21 8l-9-5-9 5 9 5 9-5z"/><path d="M3 8v8l9 5 9-5V8"/><path d="M12 13v8"/></svg>',
  calendar: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><rect x="3" y="4" width="18" height="17" rx="2.5"/><path d="M3 9h18M8 2v4M16 2v4"/></svg>',
  gear: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.6 1.6 0 0 0 .3 1.8l.1.1a2 2 0 1 1-2.8 2.8l-.1-.1a1.6 1.6 0 0 0-1.8-.3 1.6 1.6 0 0 0-1 1.5V21a2 2 0 1 1-4 0v-.1a1.6 1.6 0 0 0-1-1.5 1.6 1.6 0 0 0-1.8.3l-.1.1a2 2 0 1 1-2.8-2.8l.1-.1a1.6 1.6 0 0 0 .3-1.8 1.6 1.6 0 0 0-1.5-1H3a2 2 0 1 1 0-4h.1a1.6 1.6 0 0 0 1.5-1 1.6 1.6 0 0 0-.3-1.8l-.1-.1a2 2 0 1 1 2.8-2.8l.1.1a1.6 1.6 0 0 0 1.8.3H9a1.6 1.6 0 0 0 1-1.5V3a2 2 0 1 1 4 0v.1a1.6 1.6 0 0 0 1 1.5 1.6 1.6 0 0 0 1.8-.3l.1-.1a2 2 0 1 1 2.8 2.8l-.1.1a1.6 1.6 0 0 0-.3 1.8V9a1.6 1.6 0 0 0 1.5 1H21a2 2 0 1 1 0 4h-.1a1.6 1.6 0 0 0-1.5 1z"/></svg>',
  folder: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M3 7a2 2 0 0 1 2-2h4l2 2.5h8a2 2 0 0 1 2 2V17a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"/></svg>',
  tag: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M20.6 13.4l-7.2 7.2a2 2 0 0 1-2.8 0l-7-7A2 2 0 0 1 3 12.2V5a2 2 0 0 1 2-2h7.2a2 2 0 0 1 1.4.6l7 7a2 2 0 0 1 0 2.8z"/><circle cx="7.5" cy="7.5" r="1.3"/></svg>',
  list: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M8 6h13M8 12h13M8 18h13"/><circle cx="3.5" cy="6" r="1"/><circle cx="3.5" cy="12" r="1"/><circle cx="3.5" cy="18" r="1"/></svg>',
  send: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M22 2L11 13"/><path d="M22 2l-7 20-4-9-9-4 20-7z"/></svg>',
  clock: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="9"/><path d="M12 7v5l3 2"/></svg>',
  bulb: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M9 18h6M10 22h4"/><path d="M12 2a6 6 0 0 0-4 10.5c.7.7 1 1.3 1 2.5h6c0-1.2.3-1.8 1-2.5A6 6 0 0 0 12 2z"/></svg>',
  swap: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M7 4L3 8l4 4"/><path d="M3 8h13a4 4 0 0 1 4 4M17 20l4-4-4-4"/><path d="M21 16H8a4 4 0 0 1-4-4"/></svg>',
  chevron: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M9 6l6 6-6 6"/></svg>',
  info: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="9"/><path d="M12 11v5M12 8h.01"/></svg>',
  user: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="8" r="4"/><path d="M4 21a8 8 0 0 1 16 0"/></svg>',
  copy: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><rect x="9" y="9" width="12" height="12" rx="2"/><path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"/></svg>',
};

/* ---------- Utilitaires ---------- */
function esc(s) { return (s || "").replace(/[&<>"]/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c])); }
function copier(txt) {
  try { navigator.clipboard.writeText(txt); return; } catch (e) {}
  const t = document.createElement("textarea"); t.value = txt; document.body.appendChild(t);
  t.select(); try { document.execCommand("copy"); } catch (e) {} t.remove();
}

/* ====================================================================
   Démarrage + routage licence
   ==================================================================== */
async function boot() {
  S = await api().demarrer();
  route();
}
function route() {
  const L = S.licence || {};
  if (L.ok) { renderApp("home"); return; }
  if (L.raison === "pas_internet") { renderInternet(); return; }
  renderActivation(L);
}

/* ---------- Écran : connexion requise ---------- */
function renderInternet() {
  document.getElementById("app").innerHTML = `
    <div class="center-screen"><div class="center-card fade">
      <img src="assets/logo.png" alt="">
      <h2>Connexion internet requise</h2>
      <p>HelpVA doit vérifier ton abonnement en ligne.<br>Connecte-toi à internet, puis réessaie.</p>
      <button class="btn btn-primary" id="retry">Réessayer</button>
    </div></div>`;
  $("#retry").onclick = async () => {
    const r = await api().reverifier_licence(); S.licence = r.licence; route();
  };
}

/* ---------- Écran : activation ---------- */
function renderActivation(L) {
  let titre = "Activation de HelpVA", sous =
    "Ce logiciel est lié à CE PC. Envoie l'empreinte ci-dessous au vendeur pour recevoir ta licence.";
  if (L.raison === "expire") { titre = "Abonnement expiré"; sous = "Ton abonnement a expiré. Renvoie ton empreinte au vendeur pour le renouveler."; }
  else if (L.raison === "mauvais_pc") { titre = "Licence non valable pour ce PC"; sous = "Cette licence a été faite pour un autre PC. Envoie l'empreinte ci-dessous."; }
  document.getElementById("app").innerHTML = `
    <div class="center-screen"><div class="center-card fade">
      <img src="assets/logo.png" alt="">
      <h2>${titre}</h2>
      <p>${sous}</p>
      <label class="field-label">1) Empreinte de ce PC (à envoyer)</label>
      <div class="mono-box">
        <input class="input" id="emp" value="${esc(S.empreinte)}" readonly>
        <button class="btn btn-soft" id="cp">${I.copy}</button>
      </div>
      <label class="field-label">2) Colle ta licence, puis Active</label>
      <textarea class="textarea" id="lic" placeholder="Colle ici la licence reçue…"></textarea>
      <div class="msg err" id="msg"></div>
      <button class="btn btn-primary mt" id="go">Activer HelpVA</button>
    </div></div>`;
  $("#cp").onclick = () => { copier(S.empreinte); $("#msg").className = "msg ok"; $("#msg").textContent = "Empreinte copiée."; };
  $("#go").onclick = async () => {
    const cle = $("#lic").value.trim();
    if (!cle) { $("#msg").className = "msg err"; $("#msg").textContent = "Colle d'abord ta licence."; return; }
    const r = await api().activer_licence(cle);
    if (r.licence.ok) { S.licence = r.licence; S.abonnement = r.abonnement; renderApp("home"); }
    else {
      $("#msg").className = "msg err";
      $("#msg").textContent = r.licence.raison === "expire" ? "Cette licence est déjà expirée."
        : r.licence.raison === "pas_internet" ? "Pas d'internet pour vérifier."
        : "Licence invalide pour ce PC.";
    }
  };
}

/* ====================================================================
   Application (sidebar + contenu)
   ==================================================================== */
function renderApp(page) {
  PAGE = page;
  const genre = S.genre === "masculin" ? "Masculin" : "Féminin";
  const modeleTxt = S.modele ? `${esc(S.modele)} (${genre})` : "Aucun modèle";
  document.getElementById("app").innerHTML = `
    <div class="layout">
      <aside class="sidebar">
        <div class="brand"><img src="assets/logo.png"><span>HelpVA</span></div>
        <nav class="nav">
          ${navItem("home", I.grid, "Accueil")}
          ${navItem("modeles", I.box, "Modèles")}
          ${navItem("publications", I.calendar, "Publications")}
          ${navItem("parametres", I.gear, "Paramètres")}
        </nav>
        <div class="sidebar-foot">
          <div class="user-card">
            <div class="avatar">${I.user}</div>
            <div><div class="u-name">${S.modele ? esc(S.modele) : "HelpVA"}</div>
            <div class="u-sub">${esc(S.abonnement || "")}</div></div>
          </div>
          <div class="ver">v${S.version}</div>
        </div>
      </aside>
      <main class="main" id="content"></main>
    </div>`;
  document.querySelectorAll(".nav-item").forEach(n => n.onclick = () => renderApp(n.dataset.p));
  const pages = { home: renderHome, modeles: () => placeholder("Modèles", I.box, "La gestion des modèles arrive ici."),
    publications: () => placeholder("Publications", I.calendar, "L'historique des publications arrivera ici."),
    parametres: () => placeholder("Paramètres", I.gear, "Les réglages arriveront ici.") };
  (pages[page] || renderHome)();
}
function navItem(p, icon, label) {
  return `<div class="nav-item ${p === PAGE ? "active" : ""}" data-p="${p}">${icon}<span>${label}</span></div>`;
}

/* ---------- Accueil ---------- */
function renderHome() {
  const genre = S.genre === "masculin" ? "Masculin" : "Féminin";
  const c = $("#content");
  c.innerHTML = `
    <div class="fade">
      <div class="page-head">
        <div><h1>Bonjour ! 👋</h1><div class="subtitle">Prépare, enrichis et publie ton modèle en quelques étapes.</div></div>
        <button class="btn-ghost" id="aide">${I.info} Aide</button>
      </div>

      <div class="row two">
        <div class="card info-card">
          <div><div class="label">Modèle actif</div>
            <div class="value">${S.modele ? esc(S.modele) + " (" + genre + ")" : "Aucun modèle"}</div></div>
          <button class="btn btn-soft" id="chg">${I.swap} ${S.modele ? "Changer" : "Choisir"}</button>
        </div>
        <div class="card tip-card">
          <div class="badge">${I.bulb}</div>
          <div><div class="tip-title">Conseil</div>
          <div class="tip-text">Commence par ranger les médias, puis enrichis les métadonnées pour améliorer la qualité de ton modèle.</div></div>
        </div>
      </div>

      <div class="section-title">Contenu du modèle</div>
      <div class="row three">
        ${feature("ranger", I.folder, "Ranger les médias", "Organise tes images et vidéos")}
        ${feature("metadonnees", I.tag, "Changer les métadonnées", "Uniquifie tes photos et vidéos")}
        ${feature("legendes", I.list, "Générer les légendes", "Crée des légendes automatiquement")}
      </div>

      <div class="section-title">Publication</div>
      <div class="row pair">
        ${feature("publier", I.send, "Publier le contenu", "Publie une photo, un carrousel ou un réel")}
        ${feature("automatiser", I.clock, "Automatiser les publications", "Planifie et publie tout seul")}
      </div>
    </div>`;

  $("#aide").onclick = () => alert("HelpVA — Prépare le contenu d'un modèle (Ranger, Métadonnées, Légendes), puis publie à la main ou en automatique.");
  $("#chg").onclick = ouvrirModele;
  const besoinModele = { ranger: 1, metadonnees: 1, legendes: 1 };
  document.querySelectorAll(".feature").forEach(f => f.onclick = () => {
    const k = f.dataset.k;
    if (besoinModele[k] && !S.modele) { ouvrirModele(); return; }
    ouvrirFonction(k);
  });
}
function feature(k, icon, title, sub) {
  return `<div class="card feature" data-k="${k}">
    <div class="badge">${icon}</div>
    <div class="f-body"><div class="f-title">${title}</div><div class="f-sub">${sub}</div></div>
    <div class="chevron">${I.chevron}</div></div>`;
}

/* ---------- Modal : nom + sexe du modèle ---------- */
function ouvrirModele() {
  const g = S.genre || "feminin";
  const ov = document.createElement("div");
  ov.className = "overlay";
  ov.innerHTML = `<div class="modal fade">
      <h3>Nom du modèle</h3>
      <p>Pour quel modèle (compte) travailles-tu ? Les médias seront rangés dans son dossier.</p>
      <input class="input" id="mnom" placeholder="Ex : Olivia" value="${esc(S.modele || "")}">
      <label class="field-label">Sexe</label>
      <div class="seg" id="seg">
        <button data-g="feminin" class="${g === "feminin" ? "on" : ""}">Féminin</button>
        <button data-g="masculin" class="${g === "masculin" ? "on" : ""}">Masculin</button>
      </div>
      <div class="actions">
        <button class="btn btn-soft" id="annul">Annuler</button>
        <button class="btn btn-primary" id="ok">Enregistrer</button>
      </div></div>`;
  document.body.appendChild(ov);
  let genre = g;
  ov.querySelectorAll("#seg button").forEach(b => b.onclick = () => {
    genre = b.dataset.g; ov.querySelectorAll("#seg button").forEach(x => x.classList.remove("on")); b.classList.add("on");
  });
  $("#annul", ov).onclick = () => ov.remove();
  $("#ok", ov).onclick = async () => {
    const nom = $("#mnom", ov).value.trim();
    if (!nom) { $("#mnom", ov).focus(); return; }
    const r = await api().definir_modele(nom, genre);
    S.modele = r.modele; S.genre = r.genre; ov.remove(); renderApp("home");
  };
  $("#mnom", ov).focus();
}

/* ---------- Fonctions (pages à migrer) ---------- */
function ouvrirFonction(k) {
  const titres = { ranger: "Ranger les médias", metadonnees: "Changer les métadonnées",
    legendes: "Générer les légendes", publier: "Publier le contenu", automatiser: "Automatiser les publications" };
  const icons = { ranger: I.folder, metadonnees: I.tag, legendes: I.list, publier: I.send, automatiser: I.clock };
  placeholder(titres[k], icons[k], "Cette page est en cours de migration vers le nouveau design. On la branche juste après.");
}

/* ---------- Placeholder générique ---------- */
function placeholder(titre, icon, texte) {
  $("#content").innerHTML = `<div class="fade">
    <div class="page-head"><div><h1>${titre}</h1></div></div>
    <div class="card placeholder"><div class="badge">${icon}</div><div>${texte}</div></div>
  </div>`;
}

/* ---------- Boot ---------- */
window.addEventListener("pywebviewready", boot);
