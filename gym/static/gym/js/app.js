/* WELLNESS GYM MANAGER — comportements de l'interface (sans dépendance externe) */
(function () {
  "use strict";
  const $ = (s, el) => (el || document).querySelector(s);
  const $$ = (s, el) => Array.from((el || document).querySelectorAll(s));

  /* ---- Horloge ---- */
  const horloge = $("#horloge");
  if (horloge) {
    const maj = () => {
      const d = new Date();
      horloge.textContent = d.toLocaleDateString("fr-FR", { weekday: "long", day: "numeric", month: "long" }) +
        " · " + d.toLocaleTimeString("fr-FR", { hour: "2-digit", minute: "2-digit" });
    };
    maj(); setInterval(maj, 15000);
  }

  /* ---- Menu mobile ---- */
  const burger = $("#burger");
  if (burger) burger.addEventListener("click", () => document.body.classList.toggle("menu-ouvert"));

  /* ---- Déconnexion automatique après inactivité ---- */
  const minutes = parseInt(document.body.dataset.inactivite || "0", 10);
  if (minutes > 0 && document.body.dataset.connecte === "1") {
    let dernier = Date.now();
    ["click", "keydown", "mousemove", "touchstart", "scroll"].forEach(e =>
      document.addEventListener(e, () => { dernier = Date.now(); }, { passive: true }));
    setInterval(() => {
      if (Date.now() - dernier > minutes * 60000) window.location.href = "/deconnexion/?inactivite=1";
    }, 20000);
  }

  /* ---- Recherche rapide avec suggestions (et lecteur QR / code-barres) ---- */
  const champ = $("#recherche-q"), boite = $("#suggestions");
  if (champ && boite) {
    let minuterie, sel = -1;
    champ.addEventListener("input", () => {
      clearTimeout(minuterie);
      const q = champ.value.trim();
      if (q.length < 2) { boite.style.display = "none"; return; }
      minuterie = setTimeout(async () => {
        const r = await fetch("/recherche/?format=json&q=" + encodeURIComponent(q));
        const d = await r.json();
        sel = -1;
        boite.innerHTML = d.resultats.map(c =>
          `<a href="${c.url}"><span><b>${esc(c.nom)}</b> <span class="muted petit">${esc(c.identifiant)} · ${esc(c.telephone)}</span></span>` +
          `<span class="badge ${c.etat === "Actif" ? "ok" : c.etat === "Expiré" ? "danger" : "neutre"}">${esc(c.etat)}</span></a>`
        ).join("") || '<div class="vide">Aucun client trouvé</div>';
        boite.style.display = "block";
      }, 180);
    });
    champ.addEventListener("keydown", e => {
      const liens = $$("a", boite);
      if (e.key === "ArrowDown" || e.key === "ArrowUp") {
        e.preventDefault();
        sel = Math.max(0, Math.min(liens.length - 1, sel + (e.key === "ArrowDown" ? 1 : -1)));
        liens.forEach((l, i) => l.classList.toggle("sel", i === sel));
      } else if (e.key === "Enter" && sel >= 0 && liens[sel]) {
        e.preventDefault(); window.location.href = liens[sel].href;
      }
    });
    document.addEventListener("click", e => { if (!boite.contains(e.target) && e.target !== champ) boite.style.display = "none"; });
  }
  function esc(s) { return String(s || "").replace(/[&<>"']/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c])); }

  /* ---- Fenêtres de confirmation : <form data-confirm="Texte"> ---- */
  const fond = $("#modal-confirm");
  let formEnAttente = null;
  $$("form[data-confirm]").forEach(f => f.addEventListener("submit", e => {
    if (f.dataset.confirme === "1") return;
    e.preventDefault();
    formEnAttente = f;
    $("#modal-texte").textContent = f.dataset.confirm;
    $("#modal-titre").textContent = f.dataset.confirmTitre || "Confirmation";
    fond.classList.add("ouvert");
    $("#modal-ok").focus();
  }));
  if (fond) {
    $("#modal-annuler").addEventListener("click", () => fond.classList.remove("ouvert"));
    $("#modal-ok").addEventListener("click", () => {
      fond.classList.remove("ouvert");
      if (formEnAttente) { formEnAttente.dataset.confirme = "1"; formEnAttente.requestSubmit ? formEnAttente.requestSubmit() : formEnAttente.submit(); }
    });
    document.addEventListener("keydown", e => { if (e.key === "Escape") fond.classList.remove("ouvert"); });
  }

  /* ---- Anti double-clic sur les formulaires ---- */
  $$("form").forEach(f => f.addEventListener("submit", () => {
    if (f.dataset.confirm && f.dataset.confirme !== "1") return;
    setTimeout(() => $$("button[type=submit]", f).forEach(b => { b.disabled = true; }), 0);
  }));

  /* ---- Formulaire de vente : prix de la formule pré-rempli ---- */
  const formules = window.FORMULES || {};
  $$("select[data-formule-select]").forEach(sel => {
    const form = sel.closest("form");
    const montant = form && $("input[data-montant]", form);
    const info = form && $("#info-formule");
    const maj = (forcer) => {
      const f = formules[sel.value];
      if (!f) { if (info) info.innerHTML = ""; return; }
      if (montant && (forcer || !montant.value)) montant.value = f.prix;
      if (info) {
        const debut = (window.PROPOSITIONS || {})[sel.value];
        info.innerHTML = `Prix : <b>${f.prix.toLocaleString("fr-FR")} ${window.DEVISE || "FCFA"}</b>` +
          (debut ? ` · début proposé : <b>${debut}</b>` : "");
      }
    };
    sel.addEventListener("change", () => maj(true));
    maj(false);
  });

  /* ---- Tableau des présences en temps réel ---- */
  const tableau = $("#tableau-presences");
  if (tableau) {
    const rafraichir = async () => {
      if (document.hidden) return;
      try {
        const r = await fetch(tableau.dataset.url, { headers: { "X-Requested-With": "fetch" } });
        if (r.redirected || !r.ok) return;
        tableau.innerHTML = await r.text();
        lierConfirmations(tableau);
      } catch (e) { /* réseau momentanément indisponible */ }
    };
    setInterval(rafraichir, 20000);
  }
  function lierConfirmations(racine) {
    $$("form[data-confirm]", racine).forEach(f => f.addEventListener("submit", e => {
      if (f.dataset.confirme === "1") return;
      e.preventDefault(); formEnAttente = f;
      $("#modal-texte").textContent = f.dataset.confirm;
      $("#modal-titre").textContent = f.dataset.confirmTitre || "Confirmation";
      fond.classList.add("ouvert");
    }));
  }

  /* ---- Champ de scan : garde le focus pour la douchette / lecteur QR ---- */
  const scan = $(".scan-input");
  if (scan && !document.querySelector("#panneau-client")) scan.focus();

  /* ---- Messages de succès : disparition progressive ---- */
  $$(".msg.success").forEach(m => setTimeout(() => { m.style.transition = "opacity .6s"; m.style.opacity = ".55"; }, 8000));
})();
