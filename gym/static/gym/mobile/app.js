/* =====================================================================
   WELLNESS GYM — application mobile du personnel (Android / iPhone)
   Une seule base de code : installable depuis le navigateur (PWA) ou
   compilée en application native avec Capacitor (dossier mobile/).
   ===================================================================== */
(function () {
  "use strict";
  const VERSION = "1.0.0";
  const $ = (s, el) => (el || document).querySelector(s);
  const app = $("#app");

  /* ---------- Stockage local (protégé) ---------- */
  const stock = {
    get(k) { try { return JSON.parse(localStorage.getItem("wgm_" + k)); } catch (e) { return null; } },
    set(k, v) { try { localStorage.setItem("wgm_" + k, JSON.stringify(v)); } catch (e) { /* mode privé */ } },
    del(k) { try { localStorage.removeItem("wgm_" + k); } catch (e) { } },
  };
  // Servi par le logiciel lui-même (/m/) : même adresse. Sinon (application native) : adresse à saisir.
  const MEME_ORIGINE = /^https?:$/.test(location.protocol) && location.pathname.indexOf("/m") === 0;
  const S = { serveur: MEME_ORIGINE ? location.origin : stock.get("serveur"), jeton: stock.get("jeton"),
    user: stock.get("user"), etab: stock.get("etab") || { nom: "WELLNESS HOTEL", service: "Salle de sport", devise: "FCFA" } };

  /* ---------- Utilitaires ---------- */
  const esc = s => String(s == null ? "" : s).replace(/[&<>"']/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  const argent = n => (n == null ? "—" : Number(n).toLocaleString("fr-FR").replace(/ | /g, " ") + " " + (S.etab.devise || "FCFA"));
  const initiales = nom => esc((nom || "?").split(" ").map(x => x[0]).join("").slice(0, 2).toUpperCase());
  const dateFr = iso => iso ? iso.split("-").reverse().slice(0, 2).join("/") : "";
  const ico = n => `<svg class="i"><use href="#i-${n}"/></svg>`;
  const badgeEtat = e => ({ ACTIF: "ok", EXPIRE: "danger", A_VENIR: "info", CONSOMME: "neutre", ANNULE: "neutre" }[e] || "neutre");
  function vibrer(ms) { try { navigator.vibrate && navigator.vibrate(ms); } catch (e) { } }

  let minuterieToast;
  function toast(texte, type) {
    const t = $("#toast");
    t.className = "toast " + (type || "ok");
    t.textContent = texte;
    requestAnimationFrame(() => t.classList.add("visible"));
    clearTimeout(minuterieToast);
    minuterieToast = setTimeout(() => t.classList.remove("visible"), type === "danger" ? 6000 : 3800);
  }
  function confirmer(titre, texte) {
    return new Promise(res => {
      const m = $("#modal");
      $("#modal-titre").textContent = titre;
      $("#modal-texte").textContent = texte;
      m.classList.add("ouvert");
      const fin = v => { m.classList.remove("ouvert"); $("#modal-oui").onclick = $("#modal-non").onclick = null; res(v); };
      $("#modal-oui").onclick = () => fin(true);
      $("#modal-non").onclick = () => fin(false);
    });
  }

  /* ---------- Appels au serveur ---------- */
  async function api(chemin, opts) {
    opts = opts || {};
    const h = { "Content-Type": "application/json" };
    if (S.jeton) h.Authorization = "Token " + S.jeton;
    let r;
    try {
      r = await fetch(S.serveur.replace(/\/$/, "") + "/api/v1" + chemin, {
        method: opts.methode || "GET", headers: h, body: opts.corps ? JSON.stringify(opts.corps) : undefined });
      document.body.classList.remove("offline");
    } catch (e) {
      document.body.classList.add("offline");
      throw new Error("Serveur injoignable. Vérifiez que le téléphone est sur le Wi-Fi de l'hôtel et que le logiciel est ouvert à la réception.");
    }
    if (opts.brut) { if (!r.ok) throw new Error("Document indisponible."); return r.blob(); }
    let d = {};
    try { d = await r.json(); } catch (e) { }
    if (r.status === 401 && chemin !== "/connexion") { deconnecter(true); throw new Error(d.erreur || "Session expirée."); }
    if (!r.ok) { const err = new Error(d.erreur || "Erreur " + r.status); err.data = d; throw err; }
    return d;
  }

  function deconnecter(expire) {
    S.jeton = null; S.user = null;
    stock.del("jeton"); stock.del("user");
    if (expire) toast("Session expirée : reconnectez-vous.", "alerte");
    location.hash = "#/connexion";
  }

  /* ---------- Gabarit ---------- */
  function cadre(titre, contenu, opts) {
    opts = opts || {};
    const onglet = opts.onglet || "";
    return `<header class="entete">${opts.retour ? `<button class="retour" onclick="history.back()" aria-label="Retour">‹</button>` : `<div class="embleme">W</div>`}
      <div class="t"><b>${esc(titre || S.etab.nom)}</b><span>${esc(opts.sous || S.etab.service)}</span></div>${opts.action || ""}</header>
      <main>${contenu}</main>
      <nav class="onglets">
        <a href="#/accueil" class="${onglet === "accueil" ? "actif" : ""}">${ico("home")}Accueil</a>
        <a href="#/clients" class="${onglet === "clients" ? "actif" : ""}">${ico("users")}Clients</a>
        <a href="#/scanner" class="scan"><span class="rond">${ico("qr")}</span>Scanner</a>
        <a href="#/presents" class="${onglet === "presents" ? "actif" : ""}">${ico("clock")}Présents</a>
        <a href="#/profil" class="${onglet === "profil" ? "actif" : ""}">${ico("user")}Profil</a>
      </nav>`;
  }
  const chargement = (t, o) => { app.innerHTML = cadre(t, '<div class="chargement">Chargement…</div>', o); };
  const echec = (t, e, o) => { app.innerHTML = cadre(t, `<div class="msg danger">${esc(e.message)}</div><button class="btn" onclick="location.reload()">Réessayer</button>`, o); };

  /* ---------- Routeur ---------- */
  let arret = null; // fonction de nettoyage de l'écran courant (caméra, rafraîchissement)
  const routes = [
    [/^#\/connexion$/, ecranConnexion], [/^#\/accueil$/, ecranAccueil], [/^#\/clients$/, ecranClients],
    [/^#\/client\/(\d+)$/, ecranClient], [/^#\/scanner$/, ecranScanner], [/^#\/presents$/, ecranPresents],
    [/^#\/vente\/(\d+)$/, ecranVente], [/^#\/nouveau$/, ecranNouveau], [/^#\/transaction\/(\d+)$/, ecranTransaction],
    [/^#\/profil$/, ecranProfil],
  ];
  function router() {
    if (arret) { try { arret(); } catch (e) { } arret = null; }
    const h = location.hash || "#/accueil";
    if (!S.jeton || !S.serveur) { if (h !== "#/connexion") { location.hash = "#/connexion"; return; } }
    for (const [re, f] of routes) { const m = h.match(re); if (m) { window.scrollTo(0, 0); f(...m.slice(1)); return; } }
    location.hash = "#/accueil";
  }
  window.addEventListener("hashchange", router);

  /* ---------- Connexion ---------- */
  function ecranConnexion() {
    app.innerHTML = `<div class="connexion"><div class="marque"><div class="embleme">W</div><b>${esc((S.etab.nom || "WELLNESS HOTEL").toUpperCase())}</b><span>Gym &amp; Fitness · personnel</span></div>
      <form class="boite" id="f">
        ${MEME_ORIGINE ? "" : `<label>Adresse du logiciel à la réception</label><input class="champ" name="serveur" inputmode="url" placeholder="ex. 192.168.1.20:8000" value="${esc(S.serveur || "")}" required>
          <div class="muted petit" style="margin-top:4px">Affichée dans la fenêtre noire du logiciel, sur l'ordinateur de la réception.</div>`}
        <label>Identifiant</label><input class="champ" name="identifiant" autocomplete="username" autocapitalize="none" required>
        <label>Mot de passe</label><input class="champ" type="password" name="mot_de_passe" autocomplete="current-password" required>
        <div id="err"></div>
        <button class="btn btn-primaire" style="margin-top:16px">Se connecter</button>
      </form><p class="petit" style="text-align:center;opacity:.7;margin-top:18px">Wellness Gym Manager · application mobile v${VERSION}</p></div>`;
    $("#f").onsubmit = async e => {
      e.preventDefault();
      const f = e.target, b = $("button", f);
      if (!MEME_ORIGINE) {
        let s = f.serveur.value.trim();
        if (!/^https?:\/\//.test(s)) s = "http://" + s;
        S.serveur = s.replace(/\/+$/, "");
      }
      b.disabled = true; b.textContent = "Connexion…";
      try {
        const d = await api("/connexion", { methode: "POST", corps: { identifiant: f.identifiant.value.trim(),
          mot_de_passe: f.mot_de_passe.value, appareil: (navigator.userAgent || "").slice(0, 110) } });
        Object.assign(S, { jeton: d.jeton, user: d.utilisateur, etab: d.etablissement });
        stock.set("jeton", d.jeton); stock.set("user", d.utilisateur); stock.set("etab", d.etablissement);
        if (!MEME_ORIGINE) stock.set("serveur", S.serveur);
        location.hash = "#/accueil";
      } catch (err) {
        $("#err").innerHTML = `<div class="msg danger" style="margin-top:12px">${esc(err.message)}</div>`;
        b.disabled = false; b.textContent = "Se connecter";
      }
    };
  }

  /* ---------- Accueil ---------- */
  async function ecranAccueil() {
    chargement(null, { onglet: "accueil" });
    try {
      const d = await api("/tableau");
      const u = S.user;
      const fin = u.voit_finances && d.encaisse_jour != null ? `
        <div class="kpis"><div class="kpi or"><div class="l">Encaissé aujourd'hui</div><div class="v argent">${argent(d.encaisse_jour)}</div></div>
          <div class="kpi"><div class="l">Ce mois</div><div class="v argent">${argent(d.encaisse_mois)}</div></div></div>` : "";
      const alertes = (d.alertes || []).filter(a => a.total).map(a => `
        <div class="alerte-bloc ${a.niveau}"><h3>${esc(a.titre)} <span class="badge ${a.niveau === "danger" ? "danger" : "alerte"}">${a.total}</span></h3>
          ${a.elements.map(x => `<a href="#/client/${x.client_id}">${esc(x.texte)}</a>`).join("")}</div>`).join("");
      app.innerHTML = cadre(null, `
        <h1>Bonjour ${esc((u.nom || "").split(" ")[0])}</h1>
        <div class="kpis">
          <a class="kpi or" href="#/presents" style="text-decoration:none;color:inherit"><div class="l">Présents</div><div class="v">${d.presents}</div></a>
          <div class="kpi"><div class="l">Entrées du jour</div><div class="v">${d.entrees}</div></div>
          <div class="kpi"><div class="l">Clients différents</div><div class="v">${d.frequentation}</div></div>
          <div class="kpi"><div class="l">${d.mes_clients != null ? "Mes clients" : "Sorties"}</div><div class="v">${d.mes_clients != null ? d.mes_clients : d.sorties}</div></div>
        </div>${fin}
        ${u.peut_pointer ? `<div class="pile" style="margin-bottom:14px"><a class="btn btn-or" href="#/scanner">${ico("qr")} Scanner une carte de membre</a>
          <a class="btn" href="#/nouveau">+ Nouveau client</a></div>` : ""}
        ${alertes ? `<h2>Alertes</h2>${alertes}` : (u.peut_pointer ? '<div class="msg ok">Aucune alerte en cours.</div>' : "")}`, { onglet: "accueil" });
    } catch (e) { echec(null, e, { onglet: "accueil" }); }
  }

  /* ---------- Clients ---------- */
  function ligneClient(c) {
    return `<a class="el" href="#/client/${c.id}"><div class="avatar ${c.present ? "present" : ""}">${initiales(c.nom)}</div>
      <div class="corps"><b>${esc(c.nom)}</b><span class="muted petit">${esc(c.identifiant)} · ${esc(c.telephone)}</span></div>
      <span class="badge ${c.present ? "info" : badgeEtat(c.etat)}">${c.present ? "Présent" : esc(c.etat_libelle)}</span></a>`;
  }
  function ecranClients() {
    app.innerHTML = cadre("Clients", `
      <input class="champ" id="q" type="search" placeholder="Nom, téléphone ou identifiant" autocomplete="off" style="margin-bottom:12px">
      <div id="res"><div class="chargement">Chargement…</div></div>`, { onglet: "clients",
      action: S.user.peut_pointer ? `<a class="action" href="#/nouveau" style="text-decoration:none">+ Nouveau</a>` : "" });
    let minuterie;
    const chercher = async () => {
      try {
        const d = await api("/clients?q=" + encodeURIComponent($("#q").value.trim()));
        $("#res").innerHTML = d.resultats.length ? `<div class="liste">${d.resultats.map(ligneClient).join("")}</div>` : '<div class="vide">Aucun client trouvé.</div>';
      } catch (e) { $("#res").innerHTML = `<div class="msg danger">${esc(e.message)}</div>`; }
    };
    $("#q").addEventListener("input", () => { clearTimeout(minuterie); minuterie = setTimeout(chercher, 250); });
    chercher();
  }

  /* ---------- Fiche client / pointage ---------- */
  async function ecranClient(id, donnees) {
    if (!donnees) chargement("Client", { retour: true, onglet: "clients" });
    let c;
    try { c = donnees || await api("/clients/" + id); } catch (e) { return echec("Client", e, { retour: true }); }
    const u = S.user, a = c.acces, ab = c.abonnement, dr = c.droits;
    let verdict;
    if (c.presence) verdict = `<div class="verdict present"><div class="ic">●</div><div><b>PRÉSENT EN SALLE</b>depuis ${c.presence.arrivee} · ${esc(c.presence.duree)}${c.presence.depassement_minutes ? `<br><strong>Dépassement : +${c.presence.depassement_minutes} min</strong>` : ""}</div></div>`;
    else if (a.autorise) verdict = `<div class="verdict ok"><div class="ic">✔</div><div><b>ACCÈS AUTORISÉ</b>${esc(ab ? ab.designation : "")}</div></div>`;
    else verdict = `<div class="verdict bloque"><div class="ic">✖</div><div><b>ACCÈS BLOQUÉ</b>${esc(a.message)}</div></div>`;
    let soldes = "";
    if (dr && ab) {
      if (dr.illimite) soldes = `<div class="soldes"><div class="solde"><div class="n">∞</div><div class="l">Illimité</div></div><div class="solde"><div class="n">${dr.total_utilisees}</div><div class="l">Consommées</div></div><div class="solde"><div class="n">${ab.jours_restants}</div><div class="l">Jours restants</div></div></div>`;
      else if (ab.type === "MENSUEL" && dr.semaine) soldes = `<div class="soldes"><div class="solde"><div class="n">${dr.semaine.autorisees}</div><div class="l">Autorisées semaine</div></div>
        <div class="solde"><div class="n">${dr.semaine.utilisees}</div><div class="l">Consommées</div></div>
        <div class="solde ${dr.semaine.restantes ? "" : "zero"}"><div class="n">${dr.semaine.restantes}</div><div class="l">Restantes</div></div></div>
        <div class="muted petit">Période : ${dr.total_utilisees} / ${dr.total_droits} consommées · <b>${dr.total_restantes} restante(s)</b></div>
        <div class="semaines" style="margin-top:8px">${dr.semaines.map(s => `<div class="semaine ${s.statut}"><b>S${s.numero}</b> ${dateFr(s.debut)}<br>${s.utilisees}/${s.autorisees}</div>`).join("")}</div>`;
      else soldes = `<div class="soldes"><div class="solde ${dr.total_restantes ? "" : "zero"}"><div class="n">${dr.total_restantes}</div><div class="l">Séance restante</div></div>${ab.duree_minutes ? `<div class="solde"><div class="n">${ab.duree_minutes}</div><div class="l">Minutes autorisées</div></div>` : ""}</div>`;
    }
    let actions = "";
    if (u.peut_pointer) {
      if (c.presence) actions = `<button class="btn btn-sortie" id="b-sortie">SORTIE ←</button>`;
      else if (a.autorise) actions = `<button class="btn btn-entree" id="b-entree">→ ENTRÉE</button>`;
      else {
        if (a.proposer_renouvellement || ["SEANCE_CONSOMMEE", "AUCUN_ABONNEMENT", "ABONNEMENT_EXPIRE"].includes(a.code))
          actions += `<a class="btn btn-or" href="#/vente/${c.id}">Renouveler / vendre une séance</a>`;
        if (a.peut_deroger) actions += `<details style="margin-top:10px"><summary>Autorisation exceptionnelle</summary>
          <form id="f-exc"><label>Justification (obligatoire)</label><textarea class="champ" name="justification" rows="2" required></textarea>
          ${u.est_admin ? "" : `<div class="responsable"><label>Identifiant du responsable</label><input class="champ" name="resp_identifiant" autocapitalize="none" required>
            <label>Mot de passe du responsable</label><input class="champ" type="password" name="resp_mot_de_passe" required></div>`}
          <button class="btn btn-danger" style="margin-top:12px">Autoriser et enregistrer l'entrée</button></form></details>`;
      }
      if ((a.autorise || c.presence) && a.proposer_renouvellement) actions += `<a class="btn" style="margin-top:10px" href="#/vente/${c.id}">Renouveler l'abonnement</a>`;
    }
    const factures = (c.factures || []).map(f => `<div class="el"><div class="corps"><b>${esc(f.numero)}</b><span class="muted petit">${f.date} · ${esc(f.designation)}</span></div>
      <div style="text-align:right">${argent(f.montant)}<br>${f.statut === "ANNULEE" ? '<span class="badge neutre">Annulée</span>' : f.reste ? `<a class="badge danger" href="#/transaction/${f.transaction_id}">Reste ${argent(f.reste)}</a>` : '<span class="badge ok">Payée</span>'}
      <br><button class="btn btn-petit" data-pdf="${f.id}" data-num="${esc(f.numero)}" style="margin-top:4px">PDF</button></div></div>`).join("");
    app.innerHTML = cadre(c.nom, `
      ${verdict}
      ${a.avertissements.map(x => `<div class="msg alerte">${esc(x)}</div>`).join("")}
      <div class="carte"><div class="muted petit">${esc(c.identifiant)} · ${esc(c.telephone)}${c.coach ? " · coach " + esc(c.coach) : ""}</div>
        ${ab ? `<div style="margin-top:6px"><b>${esc(ab.designation)}</b> <span class="badge ${badgeEtat(ab.etat)}">${esc(ab.etat_libelle)}</span><div class="muted petit">du ${dateFr(ab.debut)} au ${ab.fin.split("-").reverse().join("/")}</div></div>` : '<div class="muted">Aucun abonnement</div>'}
        ${soldes}
        ${u.voit_finances && c.reste_a_payer ? `<div class="msg danger" style="margin-top:10px">Reste à payer : <b>${argent(c.reste_a_payer)}</b></div>` : ""}</div>
      <div class="pile" style="margin-bottom:12px">${actions}</div>
      ${u.peut_pointer && !actions.includes("vente") ? `<a class="btn" style="margin-bottom:12px" href="#/vente/${c.id}">Vendre une formule</a>` : ""}
      <details><summary>Observation / incident</summary><form id="f-obs">
        <label>Type</label><select class="champ" name="type"><option value="OBSERVATION">Observation</option><option value="RECOMMANDATION">Recommandation</option><option value="INCIDENT">Incident</option></select>
        <label>Texte</label><textarea class="champ" name="texte" rows="3" required></textarea><button class="btn btn-primaire" style="margin-top:10px">Enregistrer</button></form>
        ${c.observations.map(o => `<div class="petit" style="margin-top:8px"><b>${o.date}</b> · ${esc(o.type)} : ${esc(o.texte)}</div>`).join("")}</details>
      <h2>Derniers passages</h2>
      <div class="liste">${c.passages.map(p => `<div class="el"><div class="corps"><b>${dateFr(p.date)} · ${p.arrivee} → ${p.depart || "en cours"}</b><span class="muted petit">${esc(p.duree)}${p.exception ? " · exception" : ""}</span></div><span class="badge ${p.statut === "EN_COURS" ? "info" : p.statut === "ANNULEE" ? "neutre" : "ok"}">${esc(p.statut_libelle)}</span></div>`).join("") || '<div class="vide">Aucun passage.</div>'}</div>
      ${factures ? `<h2>Factures</h2><div class="liste">${factures}</div>` : ""}`, { retour: true, onglet: "clients", sous: c.identifiant });

    const occupe = b => { b.disabled = true; };
    const bE = $("#b-entree");
    if (bE) bE.onclick = async () => {
      occupe(bE);
      try { const d = await api(`/clients/${c.id}/entree`, { methode: "POST", corps: {} }); vibrer(80);
        const p = d.presence; toast(`ENTRÉE enregistrée à ${p.arrivee}` + (p.solde_semaine != null ? ` — reste ${p.solde_semaine} séance(s) cette semaine` : ""));
        ecranClient(c.id, d.client);
      } catch (e) { toast(e.message, "danger"); bE.disabled = false; }
    };
    const bS = $("#b-sortie");
    if (bS) bS.onclick = async () => {
      if (!await confirmer("Sortie", `Enregistrer la sortie de ${c.nom} ?`)) return;
      occupe(bS);
      try { const d = await api(`/presences/${c.presence.id}/sortie`, { methode: "POST", corps: {} }); vibrer(80);
        if (d.supplement) { toast(`Dépassement : supplément de ${argent(d.supplement.montant)} à régler`, "alerte"); location.hash = "#/transaction/" + d.supplement.transaction_id; return; }
        toast(`SORTIE enregistrée — durée ${d.presence.duree}`); ecranClient(c.id);
      } catch (e) { toast(e.message, "danger"); bS.disabled = false; }
    };
    const fx = $("#f-exc");
    if (fx) fx.onsubmit = async e => {
      e.preventDefault();
      if (!await confirmer("Autorisation exceptionnelle", "L'entrée sera tracée avec la justification et le nom du responsable.")) return;
      const corps = Object.fromEntries(new FormData(fx)); corps.motif = a.code || "AUTRE";
      try { const d = await api(`/clients/${c.id}/entree-exceptionnelle`, { methode: "POST", corps }); vibrer(80);
        toast("Entrée exceptionnelle enregistrée", "alerte"); ecranClient(c.id, d.client);
      } catch (err) { toast(err.message, "danger"); }
    };
    const fo = $("#f-obs");
    fo.onsubmit = async e => {
      e.preventDefault();
      try { await api(`/clients/${c.id}/observation`, { methode: "POST", corps: Object.fromEntries(new FormData(fo)) });
        toast("Enregistré"); ecranClient(c.id); } catch (err) { toast(err.message, "danger"); }
    };
    app.querySelectorAll("[data-pdf]").forEach(b => b.onclick = () => ouvrirFacture(b.dataset.pdf, b.dataset.num));
  }

  async function ouvrirFacture(id, numero, partager) {
    try {
      const blob = await api(`/factures/${id}/pdf`, { brut: true });
      const nom = `Facture_${numero}.pdf`;
      if (partager && navigator.canShare) {
        const f = new File([blob], nom, { type: "application/pdf" });
        if (navigator.canShare({ files: [f] })) { await navigator.share({ files: [f], title: nom }); return; }
      }
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url; a.download = nom; a.target = "_blank";
      document.body.appendChild(a); a.click(); a.remove();
      setTimeout(() => URL.revokeObjectURL(url), 60000);
    } catch (e) { if (e.name !== "AbortError") toast(e.message, "danger"); }
  }

  /* ---------- Scanner de QR code ---------- */
  function ecranScanner() {
    const direct = !!(navigator.mediaDevices && navigator.mediaDevices.getUserMedia && window.isSecureContext);
    app.innerHTML = cadre("Scanner", `
      ${direct ? `<div class="camera"><video id="v" playsinline muted></video><div class="cadre"></div><div class="ligne-scan"></div><div class="info">Placez le QR code de la carte dans le cadre</div></div>`
        : `<div class="camera camera-off"><div style="font-size:42px">▣</div><p>Photographiez le QR code de la carte de membre.</p><p class="petit" style="opacity:.75">La caméra en direct n'est disponible qu'en connexion sécurisée ou dans l'application installée.</p></div>`}
      <label class="btn btn-or" for="photo">📷 Photographier le QR code</label>
      <input type="file" id="photo" accept="image/*" capture="environment" style="display:none">
      <form id="f-code" style="margin-top:12px"><label>Ou saisir l'identifiant du client</label>
        <div style="display:flex;gap:8px"><input class="champ" name="code" placeholder="WG00001" autocapitalize="characters"><button class="btn btn-primaire" style="width:auto">OK</button></div></form>
      <canvas id="c" style="display:none"></canvas>`, { onglet: "scan" });
    let flux = null, actif = true, detecteur = null;
    const trouve = async code => {
      if (!actif) return;
      actif = false; vibrer([60, 40, 60]);
      try { const d = await api("/scan?code=" + encodeURIComponent(code.trim())); arreter();
        history.replaceState(null, "", "#/client/" + d.id); ecranClient(d.id, d);
      } catch (e) { toast(e.message, "danger"); setTimeout(() => { actif = true; }, 1500); }
    };
    const decoder = (source, l, h) => {
      const cv = $("#c"); cv.width = l; cv.height = h;
      const ctx = cv.getContext("2d", { willReadFrequently: true });
      ctx.drawImage(source, 0, 0, l, h);
      const r = window.jsQR && jsQR(ctx.getImageData(0, 0, l, h).data, l, h, { inversionAttempts: "attemptBoth" });
      return r ? r.data : null;
    };
    function arreter() { actif = false; if (flux) flux.getTracks().forEach(t => t.stop()); flux = null; }
    arret = arreter;
    if (direct) {
      if ("BarcodeDetector" in window) { try { detecteur = new BarcodeDetector({ formats: ["qr_code"] }); } catch (e) { } }
      navigator.mediaDevices.getUserMedia({ video: { facingMode: "environment", width: { ideal: 1280 } }, audio: false }).then(s => {
        flux = s; const v = $("#v"); if (!v) return arreter();
        v.srcObject = s; v.play();
        const boucle = async () => {
          if (!flux || !actif) { if (flux) setTimeout(boucle, 400); return; }
          if (v.readyState >= 2) {
            try {
              if (detecteur) { const r = await detecteur.detect(v); if (r.length) return trouve(r[0].rawValue); }
              else { const lw = 480, lh = Math.round(480 * v.videoHeight / v.videoWidth) || 640; const code = decoder(v, lw, lh); if (code) return trouve(code); }
            } catch (e) { }
          }
          setTimeout(boucle, 180);
        };
        boucle();
      }).catch(() => { const cam = $(".camera"); if (cam) cam.outerHTML = `<div class="msg alerte">Accès à la caméra refusé. Autorisez la caméra dans les réglages, ou utilisez la photo.</div>`; });
    }
    $("#photo").onchange = e => {
      const f = e.target.files[0]; if (!f) return;
      const img = new Image();
      img.onload = () => {
        let code = null;
        for (const max of [1000, 1600, 700]) {
          const k = Math.min(1, max / Math.max(img.width, img.height));
          code = decoder(img, Math.round(img.width * k), Math.round(img.height * k));
          if (code) break;
        }
        URL.revokeObjectURL(img.src);
        if (code) { actif = true; trouve(code); } else toast("QR code non reconnu. Recommencez en cadrant bien le code, sans reflet.", "danger");
      };
      img.src = URL.createObjectURL(f);
      e.target.value = "";
    };
    $("#f-code").onsubmit = e => { e.preventDefault(); const v = e.target.code.value.trim(); if (v) { actif = true; trouve(v); } };
  }

  /* ---------- Présents ---------- */
  async function ecranPresents() {
    const charger = async premier => {
      if (premier) chargement("Présences du jour", { onglet: "presents" });
      try {
        const d = await api("/presences");
        const enCours = d.presences.filter(p => p.statut === "EN_COURS"), autres = d.presences.filter(p => p.statut !== "EN_COURS");
        const ligne = p => `<div class="el"><a href="#/client/${p.client_id}" class="avatar ${p.statut === "EN_COURS" ? "present" : ""}" style="text-decoration:none">${initiales(p.client)}</a>
          <a class="corps" href="#/client/${p.client_id}" style="text-decoration:none;color:inherit"><b>${esc(p.client)}</b><span class="muted petit">${p.arrivee} → ${p.depart || "…"} · ${esc(p.duree)}${p.depassement_minutes ? ` · <span style="color:var(--danger);font-weight:700">+${p.depassement_minutes} min</span>` : ""}</span></a>
          ${p.statut === "EN_COURS" && S.user.peut_pointer ? `<button class="btn btn-petit btn-danger" data-sortie="${p.id}" data-nom="${esc(p.client)}">SORTIE</button>` : `<span class="badge ${p.statut === "ANNULEE" ? "neutre" : "ok"}">${esc(p.statut_libelle)}</span>`}</div>`;
        app.innerHTML = cadre("Présences du jour", `
          <div class="kpis"><div class="kpi or"><div class="l">En salle</div><div class="v">${enCours.length}</div></div><div class="kpi"><div class="l">Sortis</div><div class="v">${autres.length}</div></div></div>
          <h2>En salle maintenant</h2><div class="liste">${enCours.map(ligne).join("") || '<div class="vide">Personne en salle.</div>'}</div>
          ${autres.length ? `<h2>Sortis aujourd'hui</h2><div class="liste">${autres.map(ligne).join("")}</div>` : ""}
          <p class="muted petit" style="text-align:center">Mise à jour automatique toutes les 30 secondes</p>`, { onglet: "presents" });
        app.querySelectorAll("[data-sortie]").forEach(b => b.onclick = async () => {
          if (!await confirmer("Sortie", `Enregistrer la sortie de ${b.dataset.nom} ?`)) return;
          b.disabled = true;
          try { const r = await api(`/presences/${b.dataset.sortie}/sortie`, { methode: "POST", corps: {} }); vibrer(80);
            if (r.supplement) { toast(`Dépassement : supplément de ${argent(r.supplement.montant)} à régler`, "alerte"); location.hash = "#/transaction/" + r.supplement.transaction_id; return; }
            toast(`SORTIE de ${b.dataset.nom} — ${r.presence.duree}`); charger(false);
          } catch (e) { toast(e.message, "danger"); b.disabled = false; }
        });
      } catch (e) { if (premier) echec("Présences du jour", e, { onglet: "presents" }); }
    };
    await charger(true);
    const t = setInterval(() => { if (!document.hidden) charger(false); }, 30000);
    arret = () => clearInterval(t);
  }

  /* ---------- Vente / renouvellement ---------- */
  async function ecranVente(id) {
    chargement("Vente", { retour: true });
    let c, cat;
    try { [c, cat] = await Promise.all([api("/clients/" + id), api("/catalogue")]); } catch (e) { return echec("Vente", e, { retour: true }); }
    app.innerHTML = cadre("Vente / renouvellement", `
      <div class="carte"><b>${esc(c.nom)}</b><div class="muted petit">${esc(c.identifiant)}${c.abonnement ? " · " + esc(c.abonnement.designation) + " (" + esc(c.abonnement.etat_libelle) + ")" : ""}</div></div>
      <form id="f" class="carte">
        <label>Formule</label><select class="champ" name="formule" required><option value="">— Choisir —</option>
          ${cat.formules.map(f => `<option value="${f.id}" data-prix="${f.prix}">${esc(f.nom)} — ${argent(f.prix)}</option>`).join("")}</select>
        <label>Montant payé maintenant</label><input class="champ" name="montant" inputmode="numeric" pattern="[0-9]*" required>
        <label>Mode de paiement</label><select class="champ" name="mode">${cat.modes.map(m => `<option value="${m.id}">${esc(m.nom)}</option>`).join("")}</select>
        <label>Référence (n° de transaction Mobile Money…)</label><input class="champ" name="reference">
        <label>Coach (facultatif)</label><select class="champ" name="coach"><option value="">—</option>${cat.coachs.map(m => `<option value="${m.id}">${esc(m.nom)}</option>`).join("")}</select>
        <p class="muted petit">Paiement partiel accepté : le reste sera signalé. Un renouvellement anticipé démarre le lendemain de la fin de l'abonnement en cours.</p>
        <button class="btn btn-primaire">Valider et générer la facture</button></form>`, { retour: true, sous: c.identifiant });
    const f = $("#f");
    f.formule.onchange = () => { const o = f.formule.selectedOptions[0]; if (o && o.dataset.prix) f.montant.value = o.dataset.prix; };
    f.onsubmit = async e => {
      e.preventDefault();
      const o = f.formule.selectedOptions[0];
      if (!await confirmer("Confirmer la vente", `${o.textContent}\nMontant payé : ${argent(f.montant.value || 0)}`)) return;
      $("button", f).disabled = true;
      try {
        const d = await api(`/clients/${id}/vente`, { methode: "POST", corps: Object.fromEntries(new FormData(f)) });
        vibrer(80); toast(`Vente enregistrée — facture ${d.transaction.facture}`);
        history.replaceState(null, "", "#/client/" + id);
        location.hash = "#/transaction/" + d.transaction.id;
      } catch (err) { toast(err.message, "danger"); $("button", f).disabled = false; }
    };
  }

  async function ecranTransaction(id) {
    chargement("Facture", { retour: true });
    let t, cat;
    try { [t, cat] = await Promise.all([api("/transactions/" + id), api("/catalogue")]); } catch (e) { return echec("Facture", e, { retour: true }); }
    app.innerHTML = cadre("Facture " + t.facture, `
      <div class="carte"><b>${esc(t.client)}</b><div class="muted petit">${esc(t.type)} · ${esc(t.numero)}</div><p>${esc(t.designation)}</p>
        <div class="soldes"><div class="solde"><div class="n" style="font-size:1.05rem">${argent(t.montant)}</div><div class="l">Total</div></div>
          <div class="solde"><div class="n" style="font-size:1.05rem">${argent(t.paye)}</div><div class="l">Payé</div></div>
          <div class="solde ${t.reste ? "zero" : ""}"><div class="n" style="font-size:1.05rem">${argent(t.reste)}</div><div class="l">Reste</div></div></div></div>
      <div class="pile" style="margin-bottom:12px"><button class="btn btn-primaire" id="pdf">Ouvrir la facture (PDF)</button>
        <button class="btn" id="partager">Partager (WhatsApp, e-mail…)</button><a class="btn" href="#/client/${t.client_id}">Retour à la fiche client</a></div>
      ${t.reste && t.statut !== "ANNULEE" ? `<form id="f" class="carte"><h2>Encaisser le reste</h2>
        <label>Montant</label><input class="champ" name="montant" inputmode="numeric" value="${t.reste}" required>
        <label>Mode</label><select class="champ" name="mode">${cat.modes.map(m => `<option value="${m.id}">${esc(m.nom)}</option>`).join("")}</select>
        <label>Référence</label><input class="champ" name="reference"><button class="btn btn-primaire" style="margin-top:12px">Enregistrer le paiement</button></form>` : ""}`,
      { retour: true, sous: t.statut === "ANNULEE" ? "ANNULÉE" : t.reste ? "Paiement en attente" : "Payée" });
    $("#pdf").onclick = () => ouvrirFacture(t.facture_id, t.facture);
    $("#partager").onclick = () => ouvrirFacture(t.facture_id, t.facture, true);
    const f = $("#f");
    if (f) f.onsubmit = async e => {
      e.preventDefault();
      if (!await confirmer("Encaissement", `Encaisser ${argent(f.montant.value)} ?`)) return;
      try { const d = await api(`/transactions/${id}/encaisser`, { methode: "POST", corps: Object.fromEntries(new FormData(f)) });
        vibrer(80); toast(`Paiement enregistré (reçu ${d.recu})`); ecranTransaction(id);
      } catch (err) { toast(err.message, "danger"); }
    };
  }

  /* ---------- Nouveau client ---------- */
  function ecranNouveau() {
    app.innerHTML = cadre("Nouveau client", `<form id="f" class="carte">
      <label>Nom</label><input class="champ" name="nom" required autocapitalize="characters">
      <label>Prénom</label><input class="champ" name="prenom" required autocapitalize="words">
      <label>Téléphone</label><input class="champ" name="telephone" type="tel" required>
      <label>Adresse électronique (facultatif)</label><input class="champ" name="email" type="email" autocapitalize="none">
      <label>Sexe (facultatif)</label><select class="champ" name="sexe"><option value="">—</option><option value="M">Masculin</option><option value="F">Féminin</option></select>
      <div id="doublon"></div>
      <button class="btn btn-primaire" style="margin-top:14px">Enregistrer puis choisir la formule</button></form>`, { retour: true });
    const f = $("#f");
    f.onsubmit = async e => {
      e.preventDefault();
      const corps = Object.fromEntries(new FormData(f));
      corps.confirmer_doublon = !!f.dataset.confirmer;
      try { const c = await api("/clients/creer", { methode: "POST", corps }); toast(`Client ${c.identifiant} enregistré`);
        history.replaceState(null, "", "#/client/" + c.id); location.hash = "#/vente/" + c.id;
      } catch (err) {
        if (err.data && err.data.doublon) { f.dataset.confirmer = "1"; $("#doublon").innerHTML = `<div class="msg alerte" style="margin-top:10px">${esc(err.message)} Appuyez à nouveau pour créer quand même, ou <a href="#/client/${err.data.doublon.id}">ouvrir sa fiche</a>.</div>`; }
        else toast(err.message, "danger");
      }
    };
  }

  /* ---------- Profil ---------- */
  function ecranProfil() {
    const u = S.user || {};
    app.innerHTML = cadre("Profil", `<div class="carte"><b>${esc(u.nom)}</b><div class="muted">${esc(u.role_libelle)} · ${esc(u.identifiant)}</div></div>
      <div class="carte petit"><div><b>Établissement :</b> ${esc(S.etab.nom)}</div><div><b>Serveur :</b> ${esc(S.serveur)}</div><div><b>Version :</b> ${VERSION}</div></div>
      <div class="carte petit"><b>Installer sur l'écran d'accueil</b><br>Android (Chrome) : menu ⋮ → « Installer l'application ».<br>iPhone (Safari) : bouton Partager → « Sur l'écran d'accueil ».</div>
      <button class="btn btn-danger" id="out">Se déconnecter</button>`, { onglet: "profil" });
    $("#out").onclick = async () => { try { await api("/deconnexion", { methode: "POST", corps: {} }); } catch (e) { } deconnecter(false); };
  }

  /* ---------- Démarrage ---------- */
  window.addEventListener("online", () => document.body.classList.remove("offline"));
  if ("serviceWorker" in navigator && MEME_ORIGINE) navigator.serviceWorker.register("sw.js").catch(() => { });
  if (S.jeton && S.serveur) api("/moi").then(d => { S.user = d.utilisateur; S.etab = d.etablissement; stock.set("user", d.utilisateur); stock.set("etab", d.etablissement); }).catch(() => { });
  router();
})();
