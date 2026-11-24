from datetime import timedelta
from decimal import Decimal

from django.db.models import Count, Sum
from django.db.models.functions import TruncDate
from django.http import JsonResponse
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils import timezone

from ..models import Abonnement, Client, Formule, Presence, Reglement, Remboursement, Transaction
from ..permissions import tout_personnel
from ..services import abonnement_courant, alertes, total_encaisse, transactions_impayees
from .commun import chercher_clients, clients_visibles


@tout_personnel
def tableau_de_bord(request):
    jour = timezone.localdate()
    debut_semaine = jour - timedelta(days=jour.weekday())
    debut_mois = jour.replace(day=1)
    u = request.user
    ctx = {"jour": jour}

    if u.est_coach:
        mes_clients = clients_visibles(u)
        ctx.update(
            mes_clients=mes_clients.count(),
            presents=Presence.objects.filter(statut=Presence.Statut.EN_COURS, client__in=mes_clients)
            .select_related("client"),
            seances_jour=Presence.objects.filter(date=jour, client__in=mes_clients).exclude(
                statut=Presence.Statut.ANNULEE).count(),
        )
        return render(request, "gym/tableau_de_bord_coach.html", ctx)

    al = alertes(jour)
    valides = Abonnement.objects.filter(statut=Abonnement.Statut.ACTIF, date_debut__lte=jour, date_fin__gte=jour)
    pres_jour = Presence.objects.filter(date=jour).exclude(statut=Presence.Statut.ANNULEE)
    tx_mois = Transaction.objects.filter(statut=Transaction.Statut.VALIDEE, cree_le__date__gte=debut_mois)
    impayes = transactions_impayees()

    # Graphiques : 14 derniers jours
    d0 = jour - timedelta(days=13)
    entrees = dict(Presence.objects.filter(date__gte=d0).exclude(statut=Presence.Statut.ANNULEE)
                   .values_list("date").annotate(n=Count("id")))
    enc = {r["j"]: r["s"] for r in Reglement.objects.filter(annule=False, date__date__gte=d0)
           .annotate(j=TruncDate("date")).values("j").annotate(s=Sum("montant"))}
    rmb = {r["j"]: r["s"] for r in Remboursement.objects.filter(date__date__gte=d0)
           .annotate(j=TruncDate("date")).values("j").annotate(s=Sum("montant"))}
    graph = []
    for i in range(14):
        d = d0 + timedelta(days=i)
        graph.append({"jour": d, "entrees": entrees.get(d, 0),
                      "recette": (enc.get(d) or Decimal(0)) - (rmb.get(d) or Decimal(0))})
    max_e = max([g["entrees"] for g in graph] + [1])
    max_r = max([g["recette"] for g in graph] + [1])
    for g in graph:
        g["h_e"] = round(100 * g["entrees"] / max_e)
        g["h_r"] = round(100 * float(g["recette"]) / float(max_r)) if g["recette"] > 0 else 0

    ctx.update(
        nb_clients=Client.objects.filter(actif=True).count(),
        nb_actifs=valides.values("client").distinct().count(),
        nb_nouveaux=Client.objects.filter(date_inscription__gte=debut_mois).count(),
        nb_expires=len(al["expires"]),
        nb_presents=len(al["presents"]),
        nb_frequentation=pres_jour.values("client").distinct().count(),
        nb_entrees=pres_jour.count(),
        nb_sorties=pres_jour.filter(statut=Presence.Statut.TERMINEE).count(),
        enc_jour=total_encaisse(jour, jour),
        enc_semaine=total_encaisse(debut_semaine, jour),
        enc_mois=total_encaisse(debut_mois, jour),
        abos_vendus=tx_mois.filter(type__in=[Transaction.Type.ABONNEMENT, Transaction.Type.RENOUVELLEMENT]).count(),
        seances_vendues=tx_mois.filter(type__in=[Transaction.Type.SEANCE, Transaction.Type.HORAIRE]).count(),
        nb_impayes=len(impayes), total_impayes=sum((t.reste for t in impayes), Decimal(0)),
        al=al, graph=graph, max_e=max_e, max_r=max_r,
        nb_alertes=sum(len(al[k]) for k in ("a_renouveler", "expires", "quota_epuise", "depassements",
                                             "paiements_attente")),
    )
    return render(request, "gym/tableau_de_bord.html", ctx)


@tout_personnel
def recherche(request):
    """Recherche rapide (barre du haut) ; un identifiant exact (ex. QR code scanné)
    ouvre directement le pointage du client."""
    q = request.GET.get("q", "").strip()
    qs = clients_visibles(request.user)
    exact = qs.filter(identifiant__iexact=q).first()
    if request.GET.get("format") == "json":
        res = []
        for c in chercher_clients(q, qs)[:8] if len(q) >= 2 else []:
            abo = abonnement_courant(c)
            res.append({"id": c.pk, "nom": c.nom_complet, "identifiant": c.identifiant, "telephone": c.telephone,
                        "etat": abo.etat_libelle if abo else "Sans abonnement",
                        "url": reverse("client_detail", args=[c.pk]),
                        "pointage": reverse("presences") + f"?client={c.pk}"})
        return JsonResponse({"resultats": res})
    if exact:
        if request.user.est_coach:
            return redirect("client_detail", exact.pk)
        return redirect(reverse("presences") + f"?client={exact.pk}")
    resultats = chercher_clients(q, qs)
    if resultats.count() == 1:
        return redirect("client_detail", resultats.first().pk)
    return redirect(reverse("clients") + f"?q={q}")
