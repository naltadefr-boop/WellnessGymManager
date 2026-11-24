from django.contrib import messages
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render

from .. import services as S
from ..forms import UtilisateurForm
from ..models import JournalAudit, Utilisateur
from ..permissions import admin_requis
from .commun import paginer


@admin_requis
def liste(request):
    return render(request, "gym/personnel/liste.html",
                  {"utilisateurs": Utilisateur.objects.select_related("coach").order_by("-is_active", "role")})


@admin_requis
def edition(request, pk=None):
    u = get_object_or_404(Utilisateur, pk=pk) if pk else None
    avant = (u.role, u.is_active) if u else None
    form = UtilisateurForm(request.POST or None, instance=u, creation=u is None)
    if request.method == "POST" and form.is_valid():
        nouvel = form.save(commit=False)
        admins_restants = Utilisateur.objects.filter(role=Utilisateur.Role.ADMIN, is_active=True).exclude(
            pk=nouvel.pk).count()
        if u and avant[0] == Utilisateur.Role.ADMIN and (nouvel.role != Utilisateur.Role.ADMIN or not nouvel.is_active) \
                and admins_restants == 0:
            messages.error(request, "Impossible : il doit rester au moins un administrateur actif.")
        else:
            nouvel.save()
            desc = ("Création" if not u else "Modification") + f" du compte {nouvel.username} ({nouvel.get_role_display()})"
            if form.cleaned_data.get("mot_de_passe") and u:
                desc += " — mot de passe réinitialisé"
            S.journaliser(request.user, "UTILISATEUR", nouvel.username, desc, request=request)
            messages.success(request, "Compte enregistré.")
            return redirect("personnel")
    return render(request, "gym/form_page.html", {
        "form": form, "titre": f"Modifier le compte — {u}" if u else "Nouveau compte utilisateur",
        "bouton": "Enregistrer",
        "aide": "Rôles : Administrateur = accès complet · Réceptionniste = clients, paiements, factures, pointage "
                "(sans modification des tarifs ni annulation) · Coach = ses clients, présences et observations, "
                "sans données financières."})


@admin_requis
def journal(request):
    q = request.GET.get("q", "")
    action = request.GET.get("action", "")
    qs = JournalAudit.objects.select_related("utilisateur")
    if q:
        qs = qs.filter(Q(description__icontains=q) | Q(objet__icontains=q) | Q(utilisateur__username__icontains=q))
    if action:
        qs = qs.filter(action=action)
    if request.GET.get("utilisateur"):
        qs = qs.filter(utilisateur_id=request.GET["utilisateur"])
    actions = JournalAudit.objects.order_by("action").values_list("action", flat=True).distinct()
    return render(request, "gym/personnel/journal.html", {
        "page": paginer(request, qs, 50), "q": q, "action": action, "actions": actions,
        "utilisateurs": Utilisateur.objects.all(), "utilisateur_sel": request.GET.get("utilisateur", "")})
