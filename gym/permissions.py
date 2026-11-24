"""Contrôle des droits d'accès par rôle."""
from functools import wraps

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect


def role_requis(*roles):
    """Autorise l'administrateur + les rôles listés."""
    def decorateur(vue):
        @login_required
        @wraps(vue)
        def enveloppe(request, *args, **kwargs):
            u = request.user
            if u.est_admin or u.role in roles:
                return vue(request, *args, **kwargs)
            messages.error(request, "Vous n'avez pas les droits nécessaires pour accéder à cette page.")
            return redirect("tableau_de_bord")
        return enveloppe
    return decorateur


admin_requis = role_requis()                          # responsable uniquement
personnel_requis = role_requis("RECEPTION")           # responsable + réception
tout_personnel = role_requis("RECEPTION", "COACH")    # tous les comptes
