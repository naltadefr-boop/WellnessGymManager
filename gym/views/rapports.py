from datetime import timedelta

from django.http import HttpResponse
from django.shortcuts import render
from django.utils import timezone
from django.http import Http404

from .. import services as S
from ..forms import FiltreRapportForm
from ..pdf import rapport_pdf
from ..permissions import admin_requis
from ..rapports import RAPPORTS, generer, rapport_excel


def _periode(code_periode, jour):
    if code_periode == "semaine":
        return jour - timedelta(days=jour.weekday()), jour
    if code_periode == "mois":
        return jour.replace(day=1), jour
    if code_periode == "mois_precedent":
        fin = jour.replace(day=1) - timedelta(days=1)
        return fin.replace(day=1), fin
    return jour, jour


@admin_requis
def index(request):
    return render(request, "gym/rapports/index.html", {"rapports": RAPPORTS})


@admin_requis
def rapport(request, code):
    if code not in RAPPORTS:
        raise Http404
    jour = timezone.localdate()
    defaut = "mois" if code in ("synthese", "paiements", "renouvellements", "seances_consommees", "receptionnistes",
                                "coachs", "abonnements_expires") else "jour"
    d1, d2 = _periode(request.GET.get("periode", defaut), jour)
    donnees = request.GET.copy()
    donnees.setdefault("debut", d1.isoformat())
    donnees.setdefault("fin", d2.isoformat())
    if request.GET.get("periode"):
        donnees["debut"], donnees["fin"] = d1.isoformat(), d2.isoformat()
    form = FiltreRapportForm(donnees)
    form.is_valid()
    f = {k: v for k, v in form.cleaned_data.items() if v}
    f.setdefault("debut", d1)
    f.setdefault("fin", d2)
    if f["fin"] < f["debut"]:
        f["debut"], f["fin"] = f["fin"], f["debut"]
    res = generer(code, f)
    fmt = request.GET.get("format")
    nom = f"{code}_{f['debut']:%Y%m%d}_{f['fin']:%Y%m%d}"
    if fmt in ("pdf", "xlsx"):
        S.journaliser(request.user, "RAPPORT", res["titre"], f"Export {fmt.upper()} : {res['titre']} "
                      f"({res['sous_titre']})", request=request)
    if fmt == "pdf":
        r = HttpResponse(rapport_pdf(res["titre"], res["sous_titre"], res["colonnes"], res["lignes"],
                                     res.get("totaux"), request.user.nom_complet), content_type="application/pdf")
        r["Content-Disposition"] = f'inline; filename="{nom}.pdf"'
        return r
    if fmt == "xlsx":
        r = HttpResponse(rapport_excel(res),
                         content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
        r["Content-Disposition"] = f'attachment; filename="{nom}.xlsx"'
        return r
    qs = request.GET.copy()
    qs.pop("format", None)
    qs.pop("periode", None)
    qs["debut"], qs["fin"] = f["debut"].isoformat(), f["fin"].isoformat()
    return render(request, "gym/rapports/resultat.html", {
        "code": code, "nom": RAPPORTS[code][0], "res": res, "form": form, "query": qs.urlencode()})
