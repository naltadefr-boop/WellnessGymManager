import re
from datetime import timedelta
from urllib.parse import quote

from django.contrib import messages
from django.core.mail import EmailMessage, get_connection
from django.db.models import Q
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from .. import services as S
from ..forms import AnnulationForm, EncaissementForm, RemboursementForm
from ..models import Facture, Parametres, Reglement, Transaction
from ..pdf import facture_pdf, recu_pdf
from ..permissions import personnel_requis
from .commun import chercher_clients, erreur, erreurs_formulaire, paginer


@personnel_requis
def paiements(request):
    jour = timezone.localdate()
    q = request.GET.get("q", "")
    filtre = request.GET.get("filtre", "toutes")
    periode = request.GET.get("periode", "mois")
    qs = Transaction.objects.select_related("client", "cree_par", "facture")
    if periode == "jour":
        qs = qs.filter(cree_le__date=jour)
    elif periode == "semaine":
        qs = qs.filter(cree_le__date__gte=jour - timedelta(days=jour.weekday()))
    elif periode == "mois":
        qs = qs.filter(cree_le__date__gte=jour.replace(day=1))
    if q:
        qs = qs.filter(Q(numero__icontains=q) | Q(client__in=chercher_clients(q)) | Q(facture__numero__icontains=q))
    if filtre == "impayees":
        ids = S.transactions_impayees_qs().values("pk")
        qs = Transaction.objects.filter(pk__in=ids).select_related("client", "cree_par", "facture")
    elif filtre == "annulees":
        qs = qs.filter(statut=Transaction.Statut.ANNULEE)
    elif filtre in Transaction.Type.values:
        qs = qs.filter(type=filtre)
    debut_semaine = jour - timedelta(days=jour.weekday())
    ctx = {
        "page": paginer(request, qs), "q": q, "filtre": filtre, "periode": periode,
        "types": Transaction.Type.choices,
        "enc_jour": S.total_encaisse(jour, jour), "enc_semaine": S.total_encaisse(debut_semaine, jour),
        "enc_mois": S.total_encaisse(jour.replace(day=1), jour),
        "derniers_reglements": Reglement.objects.select_related("transaction__client", "mode", "recu_par")[:10],
    }
    return render(request, "gym/finances/paiements.html", ctx)


def _whatsapp(tx):
    params = Parametres.get()
    chiffres = re.sub(r"\D", "", tx.client.telephone or "")
    if chiffres.startswith("00"):
        chiffres = chiffres[2:]
    elif params.indicatif_pays and not chiffres.startswith(params.indicatif_pays):
        chiffres = params.indicatif_pays + chiffres.lstrip("0")
    texte = (f"Bonjour {tx.client.prenom}, voici votre facture {tx.facture.numero} de {params.nom_etablissement} "
             f"({params.service}) : {tx.designation}. Montant : {S.fcfa(tx.montant_du)}, payé : "
             f"{S.fcfa(tx.montant_paye)}, reste : {S.fcfa(tx.reste)}. {params.mention_remerciement}")
    return f"https://wa.me/{chiffres}?text={quote(texte)}"


@personnel_requis
def transaction(request, pk):
    tx = get_object_or_404(Transaction.objects.select_related("client", "abonnement", "facture", "cree_par"), pk=pk)
    ctx = {
        "tx": tx, "nouvelle": request.GET.get("nouvelle"),
        "reglements": tx.reglements.select_related("mode", "recu_par", "annule_par"),
        "remboursements": tx.remboursements.select_related("mode", "autorise_par", "effectue_par"),
        "enc_form": EncaissementForm(initial={"montant": int(tx.reste)}),
        "annul_form": AnnulationForm(user=request.user, prefix="an"),
        "rmb_form": RemboursementForm(user=request.user, prefix="rb", initial={"montant": int(tx.net_encaisse)}),
        "whatsapp": _whatsapp(tx),
    }
    return render(request, "gym/finances/transaction.html", ctx)


@personnel_requis
@require_POST
def encaisser(request, pk):
    tx = get_object_or_404(Transaction, pk=pk)
    form = EncaissementForm(request.POST)
    if form.is_valid():
        try:
            reg = S.encaisser(tx, form.cleaned_data["montant"], form.cleaned_data["mode"], request.user,
                              form.cleaned_data["reference"], request=request)
        except S.ErreurMetier as e:
            erreur(request, e)
        else:
            messages.success(request, f"Encaissement de {S.fcfa(reg.montant)} enregistré (reçu {reg.numero}).")
    else:
        erreurs_formulaire(request, form)
    return redirect("transaction", pk)


@personnel_requis
@require_POST
def annuler(request, pk):
    tx = get_object_or_404(Transaction, pk=pk)
    form = AnnulationForm(request.POST, user=request.user, prefix="an")
    if form.is_valid():
        try:
            S.annuler_transaction(tx, form.responsable(), form.cleaned_data["motif"], request=request)
        except S.ErreurMetier as e:
            erreur(request, e)
        else:
            messages.success(request, f"Transaction {tx.numero} annulée (trace conservée).")
    else:
        erreurs_formulaire(request, form)
    return redirect("transaction", pk)


@personnel_requis
@require_POST
def annuler_reglement(request, pk):
    reg = get_object_or_404(Reglement, pk=pk)
    form = AnnulationForm(request.POST, user=request.user, prefix=f"ar{pk}")
    if form.is_valid():
        try:
            S.annuler_reglement(reg, form.responsable(), form.cleaned_data["motif"], request=request)
        except S.ErreurMetier as e:
            erreur(request, e)
        else:
            messages.success(request, f"Encaissement {reg.numero} annulé (trace conservée).")
    else:
        erreurs_formulaire(request, form)
    return redirect("transaction", reg.transaction_id)


@personnel_requis
@require_POST
def rembourser(request, pk):
    tx = get_object_or_404(Transaction, pk=pk)
    form = RemboursementForm(request.POST, user=request.user, prefix="rb")
    if form.is_valid():
        cd = form.cleaned_data
        try:
            rb = S.rembourser(tx, cd["montant"], cd["mode"], cd["motif"], form.responsable(), request.user,
                              cd.get("annuler_abonnement"), request=request)
        except S.ErreurMetier as e:
            erreur(request, e)
        else:
            messages.success(request, f"Remboursement {rb.numero} de {S.fcfa(rb.montant)} enregistré.")
    else:
        erreurs_formulaire(request, form)
    return redirect("transaction", pk)


@personnel_requis
def factures(request):
    q = request.GET.get("q", "")
    qs = Facture.objects.select_related("transaction__client", "emise_par")
    if q:
        qs = qs.filter(Q(numero__icontains=q) | Q(transaction__numero__icontains=q)
                       | Q(transaction__client__in=chercher_clients(q)))
    return render(request, "gym/finances/factures.html", {"page": paginer(request, qs), "q": q})


def _pdf_reponse(contenu, nom, telecharger):
    r = HttpResponse(contenu, content_type="application/pdf")
    r["Content-Disposition"] = f'{"attachment" if telecharger else "inline"}; filename="{nom}"'
    return r


@personnel_requis
def facture_fichier(request, pk):
    f = get_object_or_404(Facture.objects.select_related("transaction__client"), pk=pk)
    Facture.objects.filter(pk=pk).update(nb_impressions=f.nb_impressions + 1)
    if f.nb_impressions:
        S.journaliser(request.user, "FACTURE_REEDITEE", f.numero, f"Réédition de la facture {f.numero}",
                      request=request)
    return _pdf_reponse(facture_pdf(f), f"Facture_{f.numero}.pdf", request.GET.get("telecharger"))


@personnel_requis
def recu_fichier(request, pk):
    reg = get_object_or_404(Reglement.objects.select_related("transaction__client", "mode"), pk=pk)
    return _pdf_reponse(recu_pdf(reg), f"Recu_{reg.numero}.pdf", request.GET.get("telecharger"))


@personnel_requis
@require_POST
def facture_email(request, pk):
    f = get_object_or_404(Facture.objects.select_related("transaction__client"), pk=pk)
    params = Parametres.get()
    dest = (request.POST.get("email") or f.transaction.client.email or "").strip()
    if not dest:
        messages.error(request, "Indiquez l'adresse électronique du client.")
    elif not params.smtp_hote:
        messages.error(request, "L'envoi d'e-mails n'est pas configuré (Paramètres > Courrier électronique). "
                                "Téléchargez le PDF et envoyez-le depuis votre messagerie.")
    else:
        try:
            conn = get_connection(host=params.smtp_hote, port=params.smtp_port, username=params.smtp_utilisateur,
                                  password=params.smtp_mot_de_passe, use_tls=params.smtp_tls, timeout=20)
            msg = EmailMessage(
                subject=f"Votre facture {f.numero} — {params.nom_etablissement}",
                body=(f"Bonjour {f.transaction.client.prenom},\n\nVeuillez trouver ci-joint votre facture "
                      f"{f.numero} ({f.transaction.designation}).\n\n{params.mention_remerciement}\n\n"
                      f"{params.nom_etablissement} — {params.service}\n{params.telephone}"),
                from_email=params.smtp_expediteur or params.smtp_utilisateur, to=[dest], connection=conn)
            msg.attach(f"Facture_{f.numero}.pdf", facture_pdf(f), "application/pdf")
            msg.send()
        except Exception as e:
            messages.error(request, f"Échec de l'envoi : {e}")
        else:
            S.journaliser(request.user, "FACTURE_ENVOYEE", f.numero, f"Facture envoyée à {dest}", request=request)
            messages.success(request, f"Facture envoyée à {dest}.")
    return redirect("transaction", f.transaction_id)
