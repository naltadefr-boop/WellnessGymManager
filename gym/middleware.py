from django.shortcuts import redirect
from django.urls import reverse

from .models import Parametres, Utilisateur


class PremierDemarrageMiddleware:
    """Au tout premier lancement (aucun compte), redirige vers la création du
    compte administrateur."""
    _comptes_existent = False

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if not PremierDemarrageMiddleware._comptes_existent:
            if Utilisateur.objects.exists():
                PremierDemarrageMiddleware._comptes_existent = True
            else:
                url = reverse("premier_demarrage")
                if not request.path.startswith((url, "/static/", "/media/")):
                    return redirect(url)
        return self.get_response(request)


class InactiviteMiddleware:
    """Déconnexion automatique après la durée d'inactivité définie dans les paramètres."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if request.user.is_authenticated and not request.path.startswith("/presences/tableau"):
            # Le rafraîchissement automatique du tableau des présences ne compte pas comme une activité.
            minutes = Parametres.get().duree_inactivite_minutes or 15
            request.session.set_expiry(minutes * 60)
        return self.get_response(request)
