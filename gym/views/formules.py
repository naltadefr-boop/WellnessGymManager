from django.contrib import messages
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_POST

from .. import services as S
from ..forms import FormuleForm
from ..models import Abonnement, Formule
from ..permissions import admin_requis, personnel_requis
from .commun import chercher_clients, paginer

CHAMPS = ["nom", "type", "prix", "duree_mois", "seances_par_semaine", "report_seances", "duree_minutes",
          "tolerance_minutes", "tranche_depassement_minutes", "tarif_depassement", "actif"]


@personnel_requis
def liste(request):
    formules = Formule.objects.all()
    stats = {f.pk: f.abonnements.exclude(statut=Abonnement.Statut.ANNULE).count() for f in formules}
    return render(request, "gym/formules/liste.html", {"formules": formules, "stats": stats})


@admin_requis
def edition(request, pk=None):
    formule = get_object_or_404(Formule, pk=pk) if pk else None
    avant = {c: str(getattr(formule, c)) for c in CHAMPS} if formule else {}
    form = FormuleForm(request.POST or None, instance=formule)
    if request.method == "POST" and form.is_valid():
        f = form.save()
        if formule:
            changes = {c: [avant[c], str(getattr(f, c))] for c in CHAMPS if avant[c] != str(getattr(f, c))}
            if changes:
                S.journaliser(request.user, "TARIF_MODIFIE", f.nom, "Formule modifiée : " + "; ".join(
                    f"{Formule._meta.get_field(c).verbose_name} {v[0]} → {v[1]}" for c, v in changes.items()),
                    details=changes, request=request)
        else:
            S.journaliser(request.user, "TARIF_CREE", f.nom, f"Nouvelle formule : {f.nom} ({S.fcfa(f.prix)})",
                          request=request)
        messages.success(request, "Formule enregistrée. Les abonnements déjà vendus conservent leurs conditions.")
        return redirect("formules")
    return render(request, "gym/formules/edition.html", {"form": form, "formule": formule})


@admin_requis
@require_POST
def basculer(request, pk):
    f = get_object_or_404(Formule, pk=pk)
    f.actif = not f.actif
    f.save(update_fields=["actif"])
    S.journaliser(request.user, "TARIF_MODIFIE", f.nom, "Formule " + ("réactivée" if f.actif else "désactivée"),
                  request=request)
    messages.success(request, f"Formule « {f.nom} » {'réactivée' if f.actif else 'désactivée (historique conservé)'}.")
    return redirect("formules")


@personnel_requis
def abonnements(request):
    jour = timezone.localdate()
    etat = request.GET.get("etat", "actifs")
    q = request.GET.get("q", "")
    params = S.Parametres.get()
    qs = Abonnement.objects.select_related("client", "formule", "cree_par")
    if q:
        qs = qs.filter(client__in=chercher_clients(q))
    if request.GET.get("formule"):
        qs = qs.filter(formule_id=request.GET["formule"])
    if etat == "actifs":
        qs = qs.filter(statut=Abonnement.Statut.ACTIF, date_debut__lte=jour, date_fin__gte=jour)
    elif etat == "a_renouveler":
        ids = [a.pk for a in S.alertes(jour)["a_renouveler"]]
        qs = qs.filter(pk__in=ids)
    elif etat == "expires":
        ids = [a.pk for a in S.alertes(jour)["expires"]]
        qs = qs.filter(pk__in=ids)
    elif etat == "a_venir":
        qs = qs.filter(statut=Abonnement.Statut.ACTIF, date_debut__gt=jour)
    elif etat == "annules":
        qs = qs.filter(statut=Abonnement.Statut.ANNULE)
    page = paginer(request, qs.order_by("date_fin") if etat in ("actifs", "a_renouveler") else qs)
    lignes = [{"a": a, "d": S.etat_droits(a, jour, params)} for a in page]
    return render(request, "gym/formules/abonnements.html", {
        "page": page, "lignes": lignes, "etat": etat, "q": q, "formules": Formule.objects.all(),
        "formule_sel": request.GET.get("formule", "")})
