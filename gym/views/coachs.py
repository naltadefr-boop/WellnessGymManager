from django.contrib import messages
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from .. import services as S
from ..forms import CoachForm
from ..models import Coach, Observation, Presence
from ..permissions import admin_requis, personnel_requis, tout_personnel


@personnel_requis
def liste(request):
    debut_mois = timezone.localdate().replace(day=1)
    lignes = []
    for c in Coach.objects.select_related("utilisateur"):
        pres = c.seances_encadrees.exclude(statut=Presence.Statut.ANNULEE)
        lignes.append({"c": c, "clients": c.clients.filter(actif=True).count(), "total": pres.count(),
                       "mois": pres.filter(date__gte=debut_mois).count(), "obs": c.observations.count()})
    return render(request, "gym/coachs/liste.html", {"lignes": lignes})


@admin_requis
def edition(request, pk=None):
    coach = get_object_or_404(Coach, pk=pk) if pk else None
    form = CoachForm(request.POST or None, instance=coach)
    if request.method == "POST" and form.is_valid():
        c = form.save()
        S.journaliser(request.user, "COACH", str(c), ("Modification" if coach else "Enregistrement")
                      + f" du coach {c}", request=request)
        messages.success(request, "Coach enregistré.")
        return redirect("coach_detail", c.pk)
    return render(request, "gym/form_page.html", {
        "form": form, "titre": f"Modifier — {coach}" if coach else "Nouveau coach", "bouton": "Enregistrer"})


@tout_personnel
def detail(request, pk):
    coach = get_object_or_404(Coach, pk=pk)
    if request.user.est_coach and getattr(request.user, "coach", None) != coach:
        raise Http404
    jour = timezone.localdate()
    pres = coach.seances_encadrees.exclude(statut=Presence.Statut.ANNULEE).select_related("client")
    return render(request, "gym/coachs/detail.html", {
        "coach": coach, "clients": coach.clients.filter(actif=True),
        "seances": pres[:50], "nb_total": pres.count(),
        "nb_mois": pres.filter(date__gte=jour.replace(day=1)).count(),
        "nb_clients_suivis": pres.values("client").distinct().count(),
        "observations": Observation.objects.filter(coach=coach).select_related("client")[:50],
    })


@tout_personnel
def mon_espace(request):
    coach = getattr(request.user, "coach", None)
    if not coach:
        messages.info(request, "Aucune fiche coach n'est associée à votre compte. Contactez le responsable.")
        return redirect("tableau_de_bord")
    return redirect("coach_detail", coach.pk)
