from django.contrib import messages
from django.contrib.auth import authenticate, login, logout, update_session_auth_hash
from django.contrib.auth.decorators import login_required
from django.core.cache import cache
from django.shortcuts import redirect, render
from django.utils.http import url_has_allowed_host_and_scheme

from ..forms import MotDePasseForm, PremierAdminForm
from ..models import Utilisateur
from ..services import journaliser

MAX_ECHECS = 5


def connexion(request):
    if request.user.is_authenticated:
        return redirect("tableau_de_bord")
    erreur, identifiant = None, ""
    if request.method == "POST":
        identifiant = request.POST.get("username", "").strip()
        cle = f"echecs:{identifiant.lower()}"
        echecs = cache.get(cle, 0)
        if echecs >= MAX_ECHECS:
            erreur = "Trop de tentatives échouées. Réessayez dans 5 minutes."
        else:
            user = authenticate(request, username=identifiant, password=request.POST.get("password", ""))
            if user:
                cache.delete(cle)
                login(request, user)
                journaliser(user, "CONNEXION", user.username, "Connexion au logiciel", request=request)
                suivant = request.POST.get("next") or ""
                if suivant and url_has_allowed_host_and_scheme(suivant, {request.get_host()}):
                    return redirect(suivant)
                return redirect("tableau_de_bord")
            cache.set(cle, echecs + 1, 300)
            erreur = "Identifiant ou mot de passe incorrect."
    elif request.GET.get("inactivite"):
        messages.info(request, "Vous avez été déconnecté après une période d'inactivité.")
    return render(request, "gym/connexion.html",
                  {"erreur": erreur, "identifiant": identifiant, "next": request.GET.get("next", "")})


def deconnexion(request):
    if request.user.is_authenticated:
        journaliser(request.user, "DECONNEXION", request.user.username,
                    "Déconnexion" + (" (inactivité)" if request.GET.get("inactivite") else ""), request=request)
    logout(request)
    if request.GET.get("inactivite"):
        return redirect("/connexion/?inactivite=1")
    return redirect("connexion")


def premier_demarrage(request):
    if Utilisateur.objects.exists():
        return redirect("connexion")
    form = PremierAdminForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        u = form.save(commit=False)
        u.role = Utilisateur.Role.ADMIN
        u.save()
        login(request, u)
        journaliser(u, "INSTALLATION", u.username, "Création du compte administrateur initial", request=request)
        messages.success(request, "Bienvenue ! Complétez maintenant les paramètres de l'établissement "
                                  "(logo, adresse, téléphone) puis vérifiez les tarifs.")
        return redirect("parametres")
    return render(request, "gym/premier_demarrage.html", {"form": form})


@login_required
def mot_de_passe(request):
    form = MotDePasseForm(request.POST or None, user=request.user)
    if request.method == "POST" and form.is_valid():
        request.user.set_password(form.cleaned_data["nouveau"])
        request.user.save()
        update_session_auth_hash(request, request.user)
        journaliser(request.user, "MOT_DE_PASSE", request.user.username, "Changement de mot de passe",
                    request=request)
        messages.success(request, "Mot de passe modifié.")
        return redirect("tableau_de_bord")
    return render(request, "gym/form_page.html", {"form": form, "titre": "Changer mon mot de passe",
                                                  "bouton": "Enregistrer"})
