from datetime import timedelta

from django.contrib import messages
from django.db import transaction as db_tx
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_POST

from .. import services as S
from ..forms import AnnulationForm, AutorisationForm
from ..models import Client, Coach, Presence, Reservation
from ..permissions import personnel_requis, tout_personnel
from .commun import chercher_clients, clients_visibles, erreur, erreurs_formulaire, verifier_acces_client


def _lignes_tableau(user):
    jour = timezone.localdate()
    qs = Presence.objects.filter(date=jour).select_related("client", "abonnement", "entree_par", "coach")
    if user.est_coach:
        qs = qs.filter(client__in=clients_visibles(user))
    en_cours = [p for p in qs if p.statut == Presence.Statut.EN_COURS]
    autres = [p for p in qs if p.statut != Presence.Statut.EN_COURS]
    # Présences en cours d'un jour précédent (oubli de sortie)
    anciennes = Presence.objects.filter(statut=Presence.Statut.EN_COURS, date__lt=jour).select_related("client")
    return {"en_cours": sorted(en_cours, key=lambda p: p.heure_entree), "autres": autres,
            "anciennes": anciennes, "maintenant": timezone.now()}


@tout_personnel
def index(request):
    q = request.GET.get("q", "").strip()
    resultats, panneau = [], None
    if q:
        exact = clients_visibles(request.user).filter(identifiant__iexact=q).first()
        if exact:
            return redirect(reverse("presences") + f"?client={exact.pk}")
        for c in chercher_clients(q, clients_visibles(request.user))[:12]:
            abo = S.abonnement_courant(c)
            resultats.append({"c": c, "abo": abo, "present": c.presence_en_cours()})
    if request.GET.get("client"):
        client = get_object_or_404(Client, pk=request.GET["client"])
        verifier_acces_client(request.user, client)
        panneau = {"client": client, "r": S.resume_client(client),
                   "auto_form": AutorisationForm(user=request.user)}
        acces = panneau["r"]["acces"]
        if not acces.autorise and acces.code:
            panneau["auto_form"] = AutorisationForm(user=request.user, initial={
                "motif": acces.code if acces.code in dict(S.AutorisationExceptionnelle.Motif.choices) else "AUTRE"})
    ctx = {"q": q, "resultats": resultats, "panneau": panneau,
           "coachs": Coach.objects.filter(statut=Coach.Statut.ACTIF)}
    ctx.update(_lignes_tableau(request.user))
    return render(request, "gym/presences/index.html", ctx)


@tout_personnel
def tableau(request):
    return render(request, "gym/presences/_tableau.html", _lignes_tableau(request.user))


def _coach_choisi(request):
    cid = request.POST.get("coach")
    return Coach.objects.filter(pk=cid).first() if cid else None


@personnel_requis
@require_POST
def entree(request, pk):
    client = get_object_or_404(Client, pk=pk)
    try:
        p = S.enregistrer_entree(client, request.user, coach=_coach_choisi(request), request=request)
    except S.ErreurMetier as e:
        erreur(request, e)
        return redirect(reverse("presences") + f"?client={pk}")
    solde = ("accès illimité" if p.seances_restantes_semaine is None and p.abonnement and p.abonnement.est_mensuel
             else f"séances restantes cette semaine : {p.seances_restantes_semaine}"
             if p.abonnement and p.abonnement.est_mensuel else p.type_abonnement)
    messages.success(request, f"ENTRÉE enregistrée : {client.nom_complet} à "
                              f"{timezone.localtime(p.heure_entree):%H:%M} — {solde}.")
    return redirect("presences")


@personnel_requis
@require_POST
def entree_autorisee(request, pk):
    client = get_object_or_404(Client, pk=pk)
    form = AutorisationForm(request.POST, user=request.user)
    if not form.is_valid():
        erreurs_formulaire(request, form)
        return redirect(reverse("presences") + f"?client={pk}")
    try:
        with db_tx.atomic():
            resp = form.responsable()
            auto = S.accorder_autorisation(client, form.cleaned_data["motif"], form.cleaned_data["justification"],
                                           resp, request.user, request=request)
            p = S.enregistrer_entree(client, request.user, coach=_coach_choisi(request), autorisation=auto,
                                     request=request)
    except S.ErreurMetier as e:
        erreur(request, e)
        return redirect(reverse("presences") + f"?client={pk}")
    messages.warning(request, f"ENTRÉE EXCEPTIONNELLE enregistrée pour {client.nom_complet} à "
                              f"{timezone.localtime(p.heure_entree):%H:%M} (autorisée par {resp.nom_complet}).")
    return redirect("presences")


@personnel_requis
@require_POST
def sortie(request, pk):
    p = get_object_or_404(Presence, pk=pk)
    try:
        p, tx = S.enregistrer_sortie(p, request.user, request=request)
    except S.ErreurMetier as e:
        erreur(request, e)
        return redirect("presences")
    if tx:
        messages.warning(request, f"SORTIE de {p.client.nom_complet} — durée {S.duree_lisible(p.duree_minutes)}. "
                                  f"DÉPASSEMENT de {p.depassement_minutes} min : supplément de {S.fcfa(tx.montant_du)} "
                                  "à régler maintenant.")
        return redirect("transaction", tx.pk)
    txt = f"SORTIE enregistrée : {p.client.nom_complet} — durée {S.duree_lisible(p.duree_minutes)}"
    if p.depassement_minutes:
        txt += f" (dépassement de {p.depassement_minutes} min dans la tolérance)"
    if p.seances_restantes_semaine is not None and p.abonnement and p.abonnement.est_mensuel:
        txt += f" — nouveau solde : {p.seances_restantes_semaine} séance(s) cette semaine, " \
               f"{p.seances_restantes_total} sur la période"
    messages.success(request, txt + ".")
    return redirect(request.POST.get("retour") or "presences")


@personnel_requis
@require_POST
def annuler(request, pk):
    p = get_object_or_404(Presence, pk=pk)
    form = AnnulationForm(request.POST, user=request.user, prefix=f"ap{pk}")
    if form.is_valid():
        try:
            S.annuler_presence(p, form.responsable(), form.cleaned_data["motif"], request=request)
        except S.ErreurMetier as e:
            erreur(request, e)
        else:
            messages.success(request, "Présence annulée : la séance a été recréditée.")
    else:
        erreurs_formulaire(request, form)
    return redirect("client_detail", p.client_id)


@tout_personnel
def reservations(request):
    jour = timezone.localdate()
    try:
        debut = timezone.datetime.strptime(request.GET.get("date", ""), "%Y-%m-%d").date()
    except ValueError:
        debut = jour
    qs = Reservation.objects.filter(date__gte=debut, date__lte=debut + timedelta(days=6)).select_related(
        "client", "coach")
    if request.user.est_coach:
        qs = qs.filter(client__in=clients_visibles(request.user))
    return render(request, "gym/presences/reservations.html", {
        "reservations": qs, "debut": debut, "fin": debut + timedelta(days=6), "jour": jour,
        "precedent": debut - timedelta(days=7), "suivant": debut + timedelta(days=7)})


@personnel_requis
@require_POST
def reservation_statut(request, pk, statut):
    r = get_object_or_404(Reservation, pk=pk)
    if statut in (Reservation.Statut.ABSENT, Reservation.Statut.ANNULEE, Reservation.Statut.PREVUE):
        r.statut = statut
        r.save(update_fields=["statut"])
        S.journaliser(request.user, "RESERVATION", r.client.identifiant,
                      f"Réservation du {r.date:%d/%m/%Y} : {r.get_statut_display()}", request=request)
        msg = f"Réservation marquée « {r.get_statut_display()} »."
        if statut == Reservation.Statut.ABSENT and S.Parametres.get().absence_decompte_seance:
            msg += " Une séance a été décomptée (règle de l'établissement)."
        messages.success(request, msg)
    return redirect(request.POST.get("retour") or "reservations")
