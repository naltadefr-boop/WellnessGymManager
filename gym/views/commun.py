from django.contrib import messages
from django.core.paginator import Paginator
from django.db.models import Q
from django.http import Http404

from ..models import Client


def paginer(request, qs, n=25):
    return Paginator(qs, n).get_page(request.GET.get("page"))


def chercher_clients(texte, qs=None):
    qs = qs if qs is not None else Client.objects.all()
    texte = (texte or "").strip()
    if not texte:
        return qs
    for mot in texte.split():
        qs = qs.filter(Q(nom__icontains=mot) | Q(prenom__icontains=mot) | Q(telephone__icontains=mot)
                       | Q(identifiant__icontains=mot) | Q(email__icontains=mot))
    return qs


def clients_visibles(user, qs=None):
    """Un coach ne voit que les clients qui lui sont affectés."""
    qs = qs if qs is not None else Client.objects.all()
    if user.est_coach:
        coach = getattr(user, "coach", None)
        return qs.filter(coach=coach) if coach else qs.none()
    return qs


def verifier_acces_client(user, client):
    if user.est_coach and (not getattr(user, "coach", None) or client.coach_id != user.coach.pk):
        raise Http404("Client non affecté à ce coach.")


def erreur(request, e):
    messages.error(request, str(e))


def erreurs_formulaire(request, form):
    for champ, errs in form.errors.items():
        lib = form.fields[champ].label if champ in form.fields else ""
        for e in errs:
            messages.error(request, f"{lib} : {e}" if lib else e)
