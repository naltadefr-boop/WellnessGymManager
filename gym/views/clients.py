import json

from django.contrib import messages
from django.db import transaction as db_tx
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_POST

from .. import services as S
from ..forms import ClientForm, ObservationForm, ReservationForm, VenteForm
from ..models import Abonnement, Client, Formule, Observation, Presence, Reservation, Transaction
from ..pdf import carte_membre_pdf, qr_image
from ..permissions import admin_requis, personnel_requis, tout_personnel
from .commun import (
    chercher_clients, clients_visibles, erreur, erreurs_formulaire, paginer, verifier_acces_client,
)

CHAMPS_SUIVIS = ["nom", "prenom", "sexe", "telephone", "email", "date_inscription", "coach", "observations"]


def _formules_json():
    """Prix et date de début proposée, utilisés par le formulaire de vente."""
    return json.dumps({f.pk: {"prix": int(f.prix), "type": f.type} for f in Formule.objects.filter(actif=True)})


@tout_personnel
def liste(request):
    q = request.GET.get("q", "")
    filtre = request.GET.get("filtre", "tous")
    jour = timezone.localdate()
    qs = chercher_clients(q, clients_visibles(request.user)).select_related("coach")
    if filtre == "actifs":
        qs = qs.filter(abonnements__statut=Abonnement.Statut.ACTIF, abonnements__date_debut__lte=jour,
                       abonnements__date_fin__gte=jour).distinct()
    elif filtre == "presents":
        qs = qs.filter(presences__statut=Presence.Statut.EN_COURS)
    elif filtre == "inactifs":
        qs = qs.filter(actif=False)
    page = paginer(request, qs)
    lignes = []
    for c in page:
        abo = S.abonnement_courant(c, jour)
        droits = S.etat_droits(abo, jour) if abo and abo.etat == "ACTIF" else None
        lignes.append({"c": c, "abo": abo, "droits": droits, "present": c.presence_en_cours()})
    return render(request, "gym/clients/liste.html",
                  {"page": page, "lignes": lignes, "q": q, "filtre": filtre})


@personnel_requis
def nouveau(request):
    form = ClientForm(request.POST or None)
    vente = VenteForm(request.POST or None, prefix="v", formule_requise=False)
    doublon = None
    if request.method == "POST" and form.is_valid() and vente.is_valid():
        doublon = Client.objects.filter(telephone=form.cleaned_data["telephone"]).first()
        if doublon and not request.POST.get("confirmer_doublon"):
            messages.warning(request, f"Un client possède déjà ce numéro : {doublon.nom_complet} "
                                      f"({doublon.identifiant}). Cochez « Créer quand même » si ce n'est pas la même personne.")
        else:
            try:
                with db_tx.atomic():
                    client = form.save(commit=False)
                    client.cree_par = request.user
                    client.save()
                    S.journaliser(request.user, "CLIENT_CREE", client.identifiant,
                                  f"Nouveau client : {client.nom_complet}", request=request)
                    tx = None
                    v = vente.cleaned_data
                    if v.get("formule"):
                        tx = S.creer_vente(client, v["formule"], request.user, v.get("date_debut"),
                                           v.get("montant_paye") or 0, v.get("mode"), v.get("reference", ""),
                                           v.get("coach") or client.coach, v.get("observations", ""), request)
            except S.ErreurMetier as e:
                erreur(request, e)
            else:
                messages.success(request, f"Client {client.nom_complet} enregistré sous l'identifiant {client.identifiant}.")
                if tx:
                    return redirect(reverse("transaction", args=[tx.pk]) + "?nouvelle=1")
                return redirect("client_detail", client.pk)
    elif request.method == "POST":
        erreurs_formulaire(request, form)
        erreurs_formulaire(request, vente)
    return render(request, "gym/clients/nouveau.html",
                  {"form": form, "vente": vente, "doublon": doublon, "formules_json": _formules_json()})


def _historique(client, voit_finances):
    ev = []
    for a in client.abonnements.select_related("cree_par"):
        ev.append((a.cree_le, "abonnement", f"{'Renouvellement' if a.est_renouvellement else 'Souscription'} : "
                   f"{a.designation} (du {a.date_debut:%d/%m/%Y} au {a.date_fin:%d/%m/%Y})"
                   + (" — ANNULÉ" if a.statut == Abonnement.Statut.ANNULE else ""), a.cree_par))
    for p in client.presences.select_related("entree_par", "sortie_par", "autorisation__accordee_par"):
        txt = f"Entrée ({p.type_abonnement})"
        if p.autorisation_id:
            txt += f" — autorisation exceptionnelle de {p.autorisation.accordee_par} : {p.autorisation.justification}"
        if p.statut == Presence.Statut.ANNULEE:
            txt += f" — ANNULÉE ({p.motif_annulation})"
        ev.append((p.heure_entree, "entree", txt, p.entree_par))
        if p.heure_sortie and p.statut != Presence.Statut.ANNULEE:
            ev.append((p.heure_sortie, "sortie", f"Sortie — durée {S.duree_lisible(p.duree_minutes)}"
                       + (f", dépassement {p.depassement_minutes} min" if p.depassement_minutes else ""), p.sortie_par))
    if voit_finances:
        for t in client.transactions.select_related("cree_par", "facture"):
            ev.append((t.cree_le, "facture", f"Facture {t.facture.numero} — {t.designation} — {S.fcfa(t.montant_du)}"
                       + (" — ANNULÉE" if t.statut == Transaction.Statut.ANNULEE else ""), t.cree_par))
            for r in t.reglements.select_related("mode", "recu_par"):
                ev.append((r.date, "paiement", f"Paiement {r.numero} : {S.fcfa(r.montant)} ({r.mode.nom})"
                           + (" — ANNULÉ" if r.annule else ""), r.recu_par))
            for r in t.remboursements.select_related("effectue_par"):
                ev.append((r.date, "remboursement", f"Remboursement {r.numero} : {S.fcfa(r.montant)} — {r.motif}",
                           r.effectue_par))
    for o in client.observations_suivi.select_related("auteur"):
        ev.append((o.date, o.type.lower(), f"{o.get_type_display()} : {o.texte}", o.auteur))
    from ..models import JournalAudit
    for j in JournalAudit.objects.filter(objet=client.identifiant, action="CLIENT_MODIFIE").select_related("utilisateur"):
        ev.append((j.date, "modification", j.description, j.utilisateur))
    ev.sort(key=lambda e: e[0], reverse=True)
    return [{"date": d, "type": t, "texte": x, "auteur": a} for d, t, x, a in ev]


@tout_personnel
def detail(request, pk):
    client = get_object_or_404(Client.objects.select_related("coach", "cree_par"), pk=pk)
    verifier_acces_client(request.user, client)
    resume = S.resume_client(client)
    abonnements = []
    for a in client.abonnements.select_related("formule", "cree_par"):
        abonnements.append({"a": a, "tx": a.transactions.exclude(type=Transaction.Type.SUPPLEMENT).first()})
    return render(request, "gym/clients/detail.html", {
        "client": client, "r": resume, "abonnements": abonnements,
        "historique": _historique(client, request.user.voit_finances)[:80],
        "transactions": client.transactions.select_related("facture") if request.user.voit_finances else [],
        "presences_recentes": client.presences.select_related("entree_par")[:10],
        "reservations": client.reservations.filter(date__gte=timezone.localdate()).select_related("coach"),
        "obs_form": ObservationForm(), "resa_form": ReservationForm(),
    })


@personnel_requis
def modifier(request, pk):
    client = get_object_or_404(Client, pk=pk)
    avant = {c: str(getattr(client, c) or "") for c in CHAMPS_SUIVIS}
    form = ClientForm(request.POST or None, instance=client)
    if request.method == "POST" and form.is_valid():
        client = form.save()
        apres = {c: str(getattr(client, c) or "") for c in CHAMPS_SUIVIS}
        changes = {c: [avant[c], apres[c]] for c in CHAMPS_SUIVIS if avant[c] != apres[c]}
        if changes:
            S.journaliser(request.user, "CLIENT_MODIFIE", client.identifiant,
                          "Modification de la fiche : " + "; ".join(
                              f"{Client._meta.get_field(c).verbose_name} « {v[0]} » → « {v[1]} »"
                              for c, v in changes.items()), details=changes, request=request)
        messages.success(request, "Fiche client mise à jour.")
        return redirect("client_detail", client.pk)
    return render(request, "gym/form_page.html", {"form": form, "titre": f"Modifier — {client.nom_complet}",
                                                  "bouton": "Enregistrer", "retour": reverse("client_detail", args=[pk])})


@personnel_requis
def vente(request, pk):
    """Vente / renouvellement rapide depuis la fiche, sans recréer le dossier."""
    client = get_object_or_404(Client, pk=pk)
    initial = {}
    if request.GET.get("formule"):
        initial["formule"] = request.GET["formule"]
    form = VenteForm(request.POST or None, initial=initial or None)
    if request.method == "POST" and form.is_valid():
        v = form.cleaned_data
        try:
            tx = S.creer_vente(client, v["formule"], request.user, v.get("date_debut"), v.get("montant_paye") or 0,
                               v.get("mode"), v.get("reference", ""), v.get("coach"), v.get("observations", ""),
                               request)
        except S.ErreurMetier as e:
            erreur(request, e)
        else:
            messages.success(request, f"{tx.get_type_display()} enregistré(e) — facture {tx.facture.numero}.")
            return redirect(reverse("transaction", args=[tx.pk]) + "?nouvelle=1")
    elif request.method == "POST":
        erreurs_formulaire(request, form)
    propositions = json.dumps({f.pk: S.date_debut_proposee(client, f).strftime("%d/%m/%Y")
                               for f in Formule.objects.filter(actif=True)})
    return render(request, "gym/clients/vente.html", {
        "client": client, "form": form, "formules_json": _formules_json(), "propositions": propositions,
        "r": S.resume_client(client)})


@personnel_requis
def carte(request, pk):
    client = get_object_or_404(Client, pk=pk)
    abo = S.abonnement_courant(client)
    pdf = carte_membre_pdf(client, abo)
    r = HttpResponse(pdf, content_type="application/pdf")
    r["Content-Disposition"] = f'inline; filename="carte_{client.identifiant}.pdf"'
    return r


@tout_personnel
def qr(request, pk):
    client = get_object_or_404(Client, pk=pk)
    verifier_acces_client(request.user, client)
    return HttpResponse(qr_image(client.identifiant, box=6).getvalue(), content_type="image/png")


@tout_personnel
@require_POST
def observation(request, pk):
    client = get_object_or_404(Client, pk=pk)
    verifier_acces_client(request.user, client)
    form = ObservationForm(request.POST)
    if form.is_valid():
        o = form.save(commit=False)
        o.client, o.auteur = client, request.user
        o.coach = getattr(request.user, "coach", None) if request.user.est_coach else None
        o.presence = client.presences.filter(date=timezone.localdate()).first()
        if o.presence and not o.coach:
            o.coach = o.presence.coach
        o.save()
        S.journaliser(request.user, o.type, client.identifiant, f"{o.get_type_display()} : {o.texte[:100]}",
                      request=request)
        messages.success(request, f"{o.get_type_display()} enregistrée.")
    else:
        erreurs_formulaire(request, form)
    return redirect("client_detail", pk)


@personnel_requis
@require_POST
def reservation(request, pk):
    client = get_object_or_404(Client, pk=pk)
    form = ReservationForm(request.POST)
    if form.is_valid():
        r = form.save(commit=False)
        r.client, r.cree_par = client, request.user
        r.save()
        S.journaliser(request.user, "RESERVATION", client.identifiant,
                      f"Réservation pour le {r.date:%d/%m/%Y}", request=request)
        messages.success(request, f"Séance réservée le {r.date:%d/%m/%Y}.")
    else:
        erreurs_formulaire(request, form)
    return redirect("client_detail", pk)


@admin_requis
@require_POST
def basculer_actif(request, pk):
    client = get_object_or_404(Client, pk=pk)
    client.actif = not client.actif
    client.save(update_fields=["actif"])
    S.journaliser(request.user, "CLIENT_MODIFIE", client.identifiant,
                  f"Fiche {'réactivée' if client.actif else 'désactivée (archivée)'}", request=request)
    messages.success(request, "Fiche client " + ("réactivée." if client.actif else "archivée (historique conservé)."))
    return redirect("client_detail", pk)
