"""
Rapports : chaque rapport renvoie un titre, des colonnes, des lignes et des
totaux éventuels. Le même résultat sert à l'affichage, au PDF et à Excel.
"""
from collections import defaultdict
from datetime import timedelta
from decimal import Decimal
from io import BytesIO

from django.db.models import Count, Q, Sum
from django.utils import timezone

from .models import (
    Abonnement, Client, Coach, Formule, JournalAudit, Observation, Presence, Reglement, Remboursement,
    Transaction, Utilisateur,
)
from .services import duree_lisible, etat_droits, fcfa


def _h(d):
    return timezone.localtime(d).strftime("%H:%M") if d else "—"


def _dh(d):
    return timezone.localtime(d).strftime("%d/%m/%Y %H:%M") if d else "—"


def _filtre_client(qs, f, champ="client"):
    texte = (f.get("client") or "").strip()
    if texte:
        qs = qs.filter(Q(**{f"{champ}__nom__icontains": texte}) | Q(**{f"{champ}__prenom__icontains": texte})
                       | Q(**{f"{champ}__telephone__icontains": texte})
                       | Q(**{f"{champ}__identifiant__iexact": texte}))
    return qs


# ---------------------------------------------------------------------------
def r_presences(f):
    qs = Presence.objects.filter(date__gte=f["debut"], date__lte=f["fin"]).select_related(
        "client", "abonnement", "entree_par", "sortie_par", "coach").order_by("heure_entree")
    qs = _filtre_client(qs, f)
    if f.get("receptionniste"):
        qs = qs.filter(Q(entree_par=f["receptionniste"]) | Q(sortie_par=f["receptionniste"]))
    if f.get("coach"):
        qs = qs.filter(coach=f["coach"])
    if f.get("formule"):
        qs = qs.filter(abonnement__formule=f["formule"])
    lignes, total_min = [], 0
    for p in qs:
        total_min += p.duree_minutes or 0
        lignes.append([f"{p.date:%d/%m/%Y}", p.client.nom_complet, p.client.identifiant, p.type_abonnement,
                       _h(p.heure_entree), _h(p.heure_sortie), duree_lisible(p.duree_minutes),
                       p.get_statut_display() + (" (autorisation)" if p.autorisation_id else ""),
                       p.seances_restantes_semaine if p.seances_restantes_semaine is not None else "—",
                       str(p.entree_par or "—"), str(p.coach or "—")])
    return dict(titre="Rapport des présences",
                colonnes=["Date", "Client", "ID", "Formule", "Arrivée", "Départ", "Durée", "Statut",
                          "Solde sem.", "Réceptionniste", "Coach"],
                lignes=lignes,
                totaux=[f"{len(lignes)} passage(s)", "", "", "", "", "", duree_lisible(total_min), "", "", "", ""])


def r_synthese(f):
    jours = []
    d = f["debut"]
    while d <= f["fin"]:
        jours.append(d)
        d += timedelta(days=1)
    pres = Presence.objects.filter(date__gte=f["debut"], date__lte=f["fin"]).exclude(statut=Presence.Statut.ANNULEE)
    tx = Transaction.objects.filter(cree_le__date__gte=f["debut"], cree_le__date__lte=f["fin"],
                                    statut=Transaction.Statut.VALIDEE)
    reg = Reglement.objects.filter(annule=False, date__date__gte=f["debut"], date__date__lte=f["fin"])
    rmb = Remboursement.objects.filter(date__date__gte=f["debut"], date__date__lte=f["fin"])
    if f.get("receptionniste"):
        pres = pres.filter(entree_par=f["receptionniste"])
        tx = tx.filter(cree_par=f["receptionniste"])
        reg = reg.filter(recu_par=f["receptionniste"])
        rmb = rmb.filter(effectue_par=f["receptionniste"])
    if f.get("formule"):
        pres = pres.filter(abonnement__formule=f["formule"])
        tx = tx.filter(abonnement__formule=f["formule"])
        reg = reg.filter(transaction__abonnement__formule=f["formule"])
    e = defaultdict(lambda: defaultdict(Decimal))
    for p in pres.values("date", "client_id", "statut"):
        e[p["date"]]["entrees"] += 1
        e[p["date"]]["sorties"] += p["statut"] == Presence.Statut.TERMINEE
        e[p["date"]].setdefault("clients", set()).add(p["client_id"])
    for t in tx.values("cree_le", "type"):
        j = timezone.localtime(t["cree_le"]).date()
        if t["type"] in (Transaction.Type.ABONNEMENT, Transaction.Type.RENOUVELLEMENT):
            e[j]["abos"] += 1
        if t["type"] == Transaction.Type.RENOUVELLEMENT:
            e[j]["renouv"] += 1
        if t["type"] in (Transaction.Type.SEANCE, Transaction.Type.HORAIRE):
            e[j]["seances"] += 1
    for r in reg.values("date", "montant"):
        e[timezone.localtime(r["date"]).date()]["encaisse"] += r["montant"]
    for r in rmb.values("date", "montant"):
        e[timezone.localtime(r["date"]).date()]["rembourse"] += r["montant"]
    lignes, tot = [], defaultdict(Decimal)
    noms = ["lun.", "mar.", "mer.", "jeu.", "ven.", "sam.", "dim."]
    for j in jours:
        x = e[j]
        net = x["encaisse"] - x["rembourse"]
        nb_clients = len(x.get("clients", ()))
        for k in ("entrees", "sorties", "abos", "renouv", "seances", "encaisse", "rembourse"):
            tot[k] += x[k] if k != "clients" else 0
        tot["clients"] += nb_clients
        lignes.append([f"{noms[j.weekday()]} {j:%d/%m/%Y}", nb_clients, int(x["entrees"]), int(x["sorties"]),
                       int(x["abos"]), int(x["renouv"]), int(x["seances"]), fcfa(x["encaisse"]),
                       fcfa(x["rembourse"]), fcfa(net)])
    return dict(titre="Synthèse d'activité",
                colonnes=["Jour", "Clients", "Entrées", "Sorties", "Abonnements vendus", "dont renouvellements",
                          "Séances/horaires vendues", "Encaissé", "Remboursé", "Net"],
                lignes=lignes,
                totaux=["TOTAL", int(tot["clients"]), int(tot["entrees"]), int(tot["sorties"]), int(tot["abos"]),
                        int(tot["renouv"]), int(tot["seances"]), fcfa(tot["encaisse"]), fcfa(tot["rembourse"]),
                        fcfa(tot["encaisse"] - tot["rembourse"])])


def _abos_filtres(f):
    qs = Abonnement.objects.filter(statut=Abonnement.Statut.ACTIF).select_related("client", "formule", "coach")
    qs = _filtre_client(qs, f)
    if f.get("formule"):
        qs = qs.filter(formule=f["formule"])
    if f.get("coach"):
        qs = qs.filter(coach=f["coach"])
    if f.get("receptionniste"):
        qs = qs.filter(cree_par=f["receptionniste"])
    return qs


def r_abonnements_actifs(f):
    jour = timezone.localdate()
    lignes = []
    for a in _abos_filtres(f).filter(type=Formule.Type.MENSUEL, date_debut__lte=jour, date_fin__gte=jour
                                     ).order_by("date_fin"):
        d = etat_droits(a, jour)
        reste = sum((t.reste for t in a.transactions.filter(statut=Transaction.Statut.VALIDEE)), Decimal(0))
        lignes.append([a.client.nom_complet, a.client.identifiant, a.client.telephone, a.designation,
                       f"{a.date_debut:%d/%m/%Y}", f"{a.date_fin:%d/%m/%Y}", a.jours_restants,
                       "Illimité" if d["illimite"] else (d["courante"]["restantes"] if d["courante"] else 0),
                       "Illimité" if d["illimite"] else d["total_restantes"], fcfa(reste)])
    return dict(titre="Abonnements actifs",
                colonnes=["Client", "ID", "Téléphone", "Formule", "Début", "Fin", "Jours restants",
                          "Séances restantes (semaine)", "Séances restantes (total)", "Reste à payer"],
                lignes=lignes, totaux=[f"{len(lignes)} abonnement(s) actif(s)"] + [""] * 9)


def r_abonnements_expires(f):
    jour = timezone.localdate()
    derniers = {}
    for a in _abos_filtres(f).filter(type=Formule.Type.MENSUEL).order_by("client_id", "date_fin"):
        derniers[a.client_id] = a
    lignes = []
    for a in sorted(derniers.values(), key=lambda x: x.date_fin, reverse=True):
        if a.date_fin < jour and f["debut"] <= a.date_fin <= f["fin"]:
            lignes.append([a.client.nom_complet, a.client.identifiant, a.client.telephone, a.designation,
                           f"{a.date_fin:%d/%m/%Y}", (jour - a.date_fin).days])
    return dict(titre="Abonnements expirés (non renouvelés)",
                colonnes=["Client", "ID", "Téléphone", "Dernière formule", "Expiré le", "Depuis (jours)"],
                lignes=lignes, totaux=[f"{len(lignes)} client(s) à relancer", "", "", "", "", ""])


def _tx_filtres(f, types=None):
    qs = Transaction.objects.filter(cree_le__date__gte=f["debut"], cree_le__date__lte=f["fin"]
                                    ).select_related("client", "cree_par", "abonnement")
    if types:
        qs = qs.filter(type__in=types)
    qs = _filtre_client(qs, f)
    if f.get("receptionniste"):
        qs = qs.filter(cree_par=f["receptionniste"])
    if f.get("formule"):
        qs = qs.filter(abonnement__formule=f["formule"])
    if f.get("coach"):
        qs = qs.filter(coach=f["coach"])
    return qs.order_by("cree_le")


def r_renouvellements(f):
    lignes, total = [], Decimal(0)
    for t in _tx_filtres(f, [Transaction.Type.RENOUVELLEMENT]):
        if t.statut == Transaction.Statut.VALIDEE:
            total += t.montant_du
        lignes.append([_dh(t.cree_le), t.numero, t.client.nom_complet, t.client.identifiant,
                       t.abonnement.designation if t.abonnement else "—",
                       f"{t.abonnement.date_debut:%d/%m/%Y} → {t.abonnement.date_fin:%d/%m/%Y}" if t.abonnement else "—",
                       fcfa(t.montant_du), t.get_statut_display(), str(t.cree_par or "—")])
    return dict(titre="Renouvellements", colonnes=["Date", "Transaction", "Client", "ID", "Formule", "Période",
                                                   "Montant", "Statut", "Réceptionniste"],
                lignes=lignes, totaux=[f"{len(lignes)} renouvellement(s)", "", "", "", "", "", fcfa(total), "", ""])


def r_paiements(f):
    regs = Reglement.objects.filter(date__date__gte=f["debut"], date__date__lte=f["fin"]).select_related(
        "transaction__client", "mode", "recu_par", "transaction__abonnement")
    regs = _filtre_client(regs, f, "transaction__client")
    if f.get("receptionniste"):
        regs = regs.filter(recu_par=f["receptionniste"])
    if f.get("formule"):
        regs = regs.filter(transaction__abonnement__formule=f["formule"])
    lignes, total, par_mode = [], Decimal(0), defaultdict(Decimal)
    for r in regs.order_by("date"):
        if not r.annule:
            total += r.montant
            par_mode[r.mode.nom] += r.montant
        lignes.append([_dh(r.date), r.numero, r.transaction.numero, r.transaction.client.nom_complet,
                       r.transaction.get_type_display(), r.mode.nom, r.reference or "",
                       fcfa(r.montant) + (" (ANNULÉ)" if r.annule else ""), str(r.recu_par or "—")])
    rmb = Remboursement.objects.filter(date__date__gte=f["debut"], date__date__lte=f["fin"]).select_related(
        "transaction__client", "mode", "autorise_par")
    rmb = _filtre_client(rmb, f, "transaction__client")
    total_rmb = Decimal(0)
    for r in rmb:
        total_rmb += r.montant
        lignes.append([_dh(r.date), r.numero, r.transaction.numero, r.transaction.client.nom_complet,
                       "REMBOURSEMENT", r.mode.nom, r.motif, "– " + fcfa(r.montant),
                       f"autorisé par {r.autorise_par}"])
    detail = " · ".join(f"{k} : {fcfa(v)}" for k, v in sorted(par_mode.items()))
    return dict(titre="Paiements encaissés",
                colonnes=["Date", "Reçu", "Transaction", "Client", "Objet", "Mode", "Référence / motif",
                          "Montant", "Réceptionniste"],
                lignes=lignes, resume=detail,
                totaux=["NET ENCAISSÉ", "", "", "", "", "", f"Remboursements : {fcfa(total_rmb)}",
                        fcfa(total - total_rmb), ""])


def r_impayes(f):
    from .services import transactions_impayees_qs
    qs = _filtre_client(transactions_impayees_qs(), f)
    lignes, total = [], Decimal(0)
    for t in qs:
        total += t.reste
        lignes.append([_dh(t.cree_le), t.numero, t.client.nom_complet, t.client.telephone, t.designation,
                       fcfa(t.montant_du), fcfa(t.montant_paye), fcfa(t.reste)])
    return dict(titre="Paiements en attente", colonnes=["Date", "Transaction", "Client", "Téléphone", "Objet",
                                                        "Montant dû", "Payé", "Reste"],
                lignes=lignes, totaux=[f"{len(lignes)} dossier(s)", "", "", "", "", "", "", fcfa(total)])


def r_seances_consommees(f):
    qs = Presence.objects.filter(date__gte=f["debut"], date__lte=f["fin"]).exclude(
        statut=Presence.Statut.ANNULEE).select_related("client")
    qs = _filtre_client(qs, f)
    if f.get("formule"):
        qs = qs.filter(abonnement__formule=f["formule"])
    if f.get("coach"):
        qs = qs.filter(coach=f["coach"])
    agg = qs.values("client__nom", "client__prenom", "client__identifiant").annotate(
        nb=Count("id"), minutes=Sum("duree_minutes"), exceptions=Count("autorisation")).order_by("-nb")
    lignes = [[f"{a['client__prenom']} {a['client__nom']}", a["client__identifiant"], a["nb"],
               duree_lisible(a["minutes"] or 0), a["exceptions"]] for a in agg]
    return dict(titre="Séances consommées", colonnes=["Client", "ID", "Séances", "Durée cumulée",
                                                      "dont autorisations exceptionnelles"],
                lignes=lignes, totaux=["TOTAL", "", sum(a["nb"] for a in agg), "", ""])


def r_seances_restantes(f):
    jour = timezone.localdate()
    lignes = []
    for a in _abos_filtres(f).filter(type=Formule.Type.MENSUEL, date_debut__lte=jour, date_fin__gte=jour):
        d = etat_droits(a, jour)
        c = d["courante"]
        if d["illimite"]:
            lignes.append([a.client.nom_complet, a.client.identifiant, a.designation, "Illimité", "—", "—", "—",
                           f"{a.date_fin:%d/%m/%Y}"])
        else:
            lignes.append([a.client.nom_complet, a.client.identifiant, a.designation,
                           f"S{c['numero']} ({c['debut']:%d/%m} → {c['fin']:%d/%m})" if c else "—",
                           c["autorisees"] if c else 0, c["utilisees"] if c else 0, c["restantes"] if c else 0,
                           f"{d['total_restantes']} / {d['total_droits']} · fin {a.date_fin:%d/%m/%Y}"])
    lignes.sort(key=lambda l: (l[6] if isinstance(l[6], int) else 99))
    return dict(titre="Séances restantes (abonnements en cours)",
                colonnes=["Client", "ID", "Formule", "Semaine en cours", "Autorisées", "Consommées",
                          "Restantes (semaine)", "Restantes (période) · fin"],
                lignes=lignes, totaux=None)


def r_receptionnistes(f):
    users = Utilisateur.objects.exclude(role=Utilisateur.Role.COACH)
    if f.get("receptionniste"):
        users = users.filter(pk=f["receptionniste"].pk)
    d1, d2 = f["debut"], f["fin"]
    lignes = []
    for u in users:
        clients = Client.objects.filter(cree_par=u, cree_le__date__gte=d1, cree_le__date__lte=d2).count()
        entrees = Presence.objects.filter(entree_par=u, date__gte=d1, date__lte=d2).count()
        sorties = Presence.objects.filter(sortie_par=u, date__gte=d1, date__lte=d2).count()
        txs = Transaction.objects.filter(cree_par=u, cree_le__date__gte=d1, cree_le__date__lte=d2).count()
        enc = Reglement.objects.filter(recu_par=u, annule=False, date__date__gte=d1, date__date__lte=d2
                                       ).aggregate(s=Sum("montant"))["s"] or 0
        ops = JournalAudit.objects.filter(utilisateur=u, date__date__gte=d1, date__date__lte=d2).count()
        if clients or entrees or sorties or txs or enc or ops or f.get("receptionniste"):
            lignes.append([u.nom_complet, u.get_role_display(), clients, entrees, sorties, txs, fcfa(enc), ops])
    return dict(titre="Activités des réceptionnistes",
                colonnes=["Utilisateur", "Rôle", "Clients enregistrés", "Entrées", "Sorties", "Transactions",
                          "Montant encaissé", "Opérations journalisées"], lignes=lignes, totaux=None)


def r_coachs(f):
    coachs = Coach.objects.all()
    if f.get("coach"):
        coachs = coachs.filter(pk=f["coach"].pk)
    d1, d2 = f["debut"], f["fin"]
    lignes = []
    for c in coachs:
        pres = Presence.objects.filter(coach=c, date__gte=d1, date__lte=d2).exclude(statut=Presence.Statut.ANNULEE)
        obs = Observation.objects.filter(coach=c, date__date__gte=d1, date__date__lte=d2)
        lignes.append([str(c), c.fonction, c.get_statut_display(), c.clients.filter(actif=True).count(),
                       pres.count(), pres.values("client").distinct().count(),
                       obs.filter(type=Observation.Type.OBSERVATION).count(),
                       obs.filter(type=Observation.Type.RECOMMANDATION).count(),
                       obs.filter(type=Observation.Type.INCIDENT).count()])
    return dict(titre="Activités des coachs",
                colonnes=["Coach", "Fonction", "Statut", "Clients attitrés", "Séances encadrées",
                          "Clients suivis", "Observations", "Recommandations", "Incidents"],
                lignes=lignes, totaux=None)


RAPPORTS = {
    "presences": ("Présences (journalier / période)", r_presences, "Liste détaillée des entrées et sorties."),
    "synthese": ("Synthèse hebdomadaire / mensuelle", r_synthese, "Activité et recettes jour par jour."),
    "abonnements_actifs": ("Abonnements actifs", r_abonnements_actifs, "Abonnements mensuels en cours."),
    "abonnements_expires": ("Abonnements expirés", r_abonnements_expires, "Clients à relancer (fin dans la période)."),
    "renouvellements": ("Renouvellements", r_renouvellements, "Réabonnements de la période."),
    "paiements": ("Paiements", r_paiements, "Encaissements et remboursements, par mode."),
    "impayes": ("Paiements en attente", r_impayes, "Restes à payer à ce jour."),
    "seances_consommees": ("Séances consommées", r_seances_consommees, "Par client, sur la période."),
    "seances_restantes": ("Séances restantes", r_seances_restantes, "Solde de la semaine et de la période."),
    "receptionnistes": ("Activités des réceptionnistes", r_receptionnistes, "Opérations par utilisateur."),
    "coachs": ("Activités des coachs", r_coachs, "Séances encadrées et observations."),
}


def generer(code, filtres):
    titre, fn, _ = RAPPORTS[code]
    res = fn(filtres)
    res.setdefault("resume", "")
    morceaux = [f"Du {filtres['debut']:%d/%m/%Y} au {filtres['fin']:%d/%m/%Y}"]
    for k, lib in (("client", "Client"), ("receptionniste", "Réceptionniste"), ("coach", "Coach"),
                   ("formule", "Formule")):
        if filtres.get(k):
            morceaux.append(f"{lib} : {filtres[k]}")
    res["sous_titre"] = " · ".join(morceaux)
    return res


def rapport_excel(res) -> bytes:
    from openpyxl import Workbook
    from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
    from openpyxl.utils import get_column_letter
    from .models import Parametres
    params = Parametres.get()
    wb = Workbook()
    ws = wb.active
    ws.title = res["titre"][:31]
    n = len(res["colonnes"])
    ws.append([f"{params.nom_etablissement} — {params.service}"])
    ws.append([res["titre"]])
    ws.append([res["sous_titre"]])
    ws.append([])
    ws["A1"].font = Font(bold=True, size=14, color="0F3D36")
    ws["A2"].font = Font(bold=True, size=12, color="B8913A")
    ws["A3"].font = Font(italic=True, color="5B6B67")
    ws.append(res["colonnes"])
    fill = PatternFill("solid", fgColor="0F3D36")
    fin = Side(style="thin", color="D5DEDB")
    for i in range(1, n + 1):
        c = ws.cell(row=5, column=i)
        c.font, c.fill = Font(bold=True, color="FFFFFF"), fill
        c.alignment = Alignment(wrap_text=True, vertical="center")
    for l in res["lignes"]:
        ws.append([_nombre(v) for v in l])
    if res.get("totaux"):
        ws.append([_nombre(v) for v in res["totaux"]])
        for i in range(1, n + 1):
            ws.cell(row=ws.max_row, column=i).font = Font(bold=True)
            ws.cell(row=ws.max_row, column=i).fill = PatternFill("solid", fgColor="E8F1EE")
    if res.get("resume"):
        ws.append([])
        ws.append([res["resume"]])
    for row in ws.iter_rows(min_row=5, max_row=ws.max_row, max_col=n):
        for c in row:
            c.border = Border(top=fin, bottom=fin, left=fin, right=fin)
    for i in range(1, n + 1):
        largeur = max(len(str(ws.cell(row=r, column=i).value or "")) for r in range(5, ws.max_row + 1))
        ws.column_dimensions[get_column_letter(i)].width = min(45, max(10, largeur + 2))
    ws.freeze_panes = "A6"
    buf = BytesIO()
    wb.save(buf)
    return buf.getvalue()


def _nombre(v):
    """Convertit « 25 000 FCFA » en nombre pour Excel."""
    if isinstance(v, str) and v.endswith(" FCFA") and not v.startswith("–"):
        brut = v[:-5].replace(" ", "")
        if brut.lstrip("-").isdigit():
            return int(brut)
    return v
