from pathlib import Path

from django.conf import settings
from django.contrib import messages
from django.contrib.auth import logout
from django.http import FileResponse, Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from .. import services as S
from ..forms import ModePaiementForm, ParametresForm
from ..models import ModePaiement, Parametres
from ..permissions import admin_requis
from ..sauvegarde import creer_sauvegarde, est_sqlite, lister_sauvegardes, restaurer


@admin_requis
def parametres(request):
    p = Parametres.get()
    form = ParametresForm(request.POST or None, request.FILES or None, instance=p)
    if request.method == "POST" and form.is_valid():
        form.save()
        S.journaliser(request.user, "PARAMETRES", "Paramètres",
                      "Paramètres modifiés : " + ", ".join(form.changed_data), request=request)
        messages.success(request, "Paramètres enregistrés.")
        return redirect("parametres")
    return render(request, "gym/parametres/index.html", {
        "form": form, "modes": ModePaiement.objects.all(), "mode_form": ModePaiementForm(),
        "config_file": settings.CONFIG_FILE, "data_dir": settings.DATA_DIR})


@admin_requis
@require_POST
def mode_ajouter(request):
    form = ModePaiementForm(request.POST)
    if form.is_valid():
        m = form.save()
        S.journaliser(request.user, "PARAMETRES", m.nom, f"Mode de paiement ajouté : {m.nom}", request=request)
        messages.success(request, f"Mode de paiement « {m.nom} » ajouté.")
    else:
        messages.error(request, "Ce mode de paiement existe déjà ou le nom est invalide.")
    return redirect("parametres")


@admin_requis
@require_POST
def mode_basculer(request, pk):
    m = get_object_or_404(ModePaiement, pk=pk)
    m.actif = not m.actif
    m.save(update_fields=["actif"])
    S.journaliser(request.user, "PARAMETRES", m.nom, f"Mode de paiement {'activé' if m.actif else 'désactivé'}",
                  request=request)
    return redirect("parametres")


@admin_requis
def sauvegardes(request):
    if request.method == "POST":
        action = request.POST.get("action")
        try:
            if action == "creer":
                chemin = creer_sauvegarde(auto=False)
                S.journaliser(request.user, "SAUVEGARDE", chemin.name, "Sauvegarde manuelle", request=request)
                messages.success(request, f"Sauvegarde créée : {chemin.name}")
            elif action == "restaurer":
                if request.POST.get("confirmation", "").strip().upper() != "RESTAURER":
                    raise ValueError("Tapez RESTAURER pour confirmer la restauration.")
                if request.FILES.get("fichier"):
                    source = request.FILES["fichier"]
                    nom = source.name
                else:
                    nom = Path(request.POST.get("nom", "")).name
                    source = Path(settings.BACKUP_DIR) / nom
                    if not nom or not source.exists():
                        raise ValueError("Sauvegarde introuvable.")
                utilisateur = request.user.username
                securite = restaurer(source)
                S.journaliser(None, "RESTAURATION", nom,
                              f"Restauration de la sauvegarde {nom} par {utilisateur} "
                              f"(état précédent conservé dans {securite.name})")
                logout(request)
                messages.success(request, f"Données restaurées depuis {nom}. Reconnectez-vous. "
                                          f"(L'état précédent a été sauvegardé dans {securite.name}.)")
                return redirect("connexion")
        except Exception as e:
            messages.error(request, f"Opération impossible : {e}")
        return redirect("sauvegardes")
    return render(request, "gym/parametres/sauvegardes.html", {
        "sauvegardes": lister_sauvegardes(), "dossier": settings.BACKUP_DIR, "sqlite": est_sqlite(),
        "params": Parametres.get()})


@admin_requis
def sauvegarde_telecharger(request, nom):
    chemin = Path(settings.BACKUP_DIR) / Path(nom).name
    if not chemin.exists() or chemin.suffix != ".zip":
        raise Http404
    return FileResponse(open(chemin, "rb"), as_attachment=True, filename=chemin.name)
