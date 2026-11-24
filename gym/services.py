"""
Logique métier de WELLNESS GYM MANAGER.

Toutes les opérations sensibles passent par ce module (jamais directement par
les vues) afin de garantir les mêmes contrôles partout : quotas, doublons,
montants, autorisations et journalisation.
"""
from __future__ import annotations

import calendar
import math
from collections import Counter
from dataclasses import dataclass, field
from datetime import date, timedelta
from decimal import Decimal

from django.contrib.auth import authenticate
from django.db import IntegrityError, transaction as db_tx
from django.db.models import DecimalField, F, Q, Sum
from django.db.models.functions import Coalesce
from django.utils import timezone

from .models import (
    Abonnement, AutorisationExceptionnelle, Client, Facture, Formule, JournalAudit,
    ModePaiement, Parametres, Presence, Reglement, Remboursement, Reservation, Sequence,
    Transaction,
)


class ErreurMetier(Exception):
    """Erreur de règle de gestion, affichée telle quelle à l'utilisateur."""


def fcfa(montant) -> str:
    try:
        n = int(Decimal(montant))
    except Exception:
        return str(montant)
    return f"{n:,}".replace(",", " ") + " " + Parametres.get().devise


# ---------------------------------------------------------------------------
# Journal d'audit
# ---------------------------------------------------------------------------
def journaliser(utilisateur, action, objet, description, details=None, request=None):
    ip = None
    if request is not None:
        ip = request.META.get("REMOTE_ADDR")
    return JournalAudit.objects.create(
        utilisateur=utilisateur if (utilisateur and utilisateur.is_authenticated) else None,
        action=action, objet=str(objet)[:120], description=description,
        details=details or {}, adresse_ip=ip,
    )


def verifier_responsable(identifiant: str, mot_de_passe: str):
    """Valide les identifiants d'un responsable (autorisation exceptionnelle,
    remboursement…). Renvoie l'utilisateur ou lève ErreurMetier."""
    user = authenticate(username=(identifiant or "").strip(), password=mot_de_passe or "")
    if user is None or not user.is_active:
        raise ErreurMetier("Identifiants du responsable incorrects.")
    if not user.est_admin:
        raise ErreurMetier("Ce compte n'est pas habilité à accorder cette autorisation (responsable requis).")
    return user


# ---------------------------------------------------------------------------
# Dates et calendrier des droits
# ---------------------------------------------------------------------------
def ajouter_mois(d: date, n: int) -> date:
    m = d.month - 1 + n
    annee, mois = d.year + m // 12, m % 12 + 1
    jour = min(d.day, calendar.monthrange(annee, mois)[1])
    return date(annee, mois, jour)


def calculer_date_fin(formule: Formule, date_debut: date, params: Parametres | None = None) -> date:
    params = params or Parametres.get()
    if formule.type == Formule.Type.MENSUEL:
        return ajouter_mois(date_debut, max(1, formule.duree_mois)) - timedelta(days=1)
    return date_debut + timedelta(days=max(1, params.validite_ticket_jours) - 1)


def _quota_semaine(par_semaine: int, jours: int, mode: str) -> int:
    if jours >= 7 or mode == Parametres.SemainePartielle.COMPLET:
        return par_semaine
    brut = par_semaine * jours / 7
    if mode == Parametres.SemainePartielle.PRORATA_INF:
        return math.floor(brut)
    return math.ceil(brut)


def decouper_semaines(abo: Abonnement, params: Parametres | None = None) -> list[dict]:
    """Découpe la période en semaines glissantes à partir de la date de début
    (semaine 1 = jours 1 à 7, etc.). La dernière semaine peut être incomplète :
    son quota est alors calculé selon le paramètre « semaines incomplètes ».
    Ex. : 4 séances/sem. du 1er au 31 → 4 semaines × 4 + 3 jours (2 séances) = 18,
          et non 16 appliqué aveuglément ; février (28 jours) → 16."""
    params = params or Parametres.get()
    if not abo.est_mensuel:
        return [{"numero": 1, "debut": abo.date_debut, "fin": abo.date_fin,
                 "jours": (abo.date_fin - abo.date_debut).days + 1, "quota": 1}]
    semaines, debut, num = [], abo.date_debut, 1
    while debut <= abo.date_fin:
        fin = min(debut + timedelta(days=6), abo.date_fin)
        jours = (fin - debut).days + 1
        quota = None if abo.seances_par_semaine == 0 else _quota_semaine(
            abo.seances_par_semaine, jours, params.mode_semaine_partielle)
        semaines.append({"numero": num, "debut": debut, "fin": fin, "jours": jours, "quota": quota})
        debut, num = fin + timedelta(days=1), num + 1
    return semaines


def calculer_seances_total(abo: Abonnement, params: Parametres | None = None):
    semaines = decouper_semaines(abo, params)
    if any(s["quota"] is None for s in semaines):
        return None
    return sum(s["quota"] for s in semaines)


def _consommations_par_jour(abo: Abonnement, params: Parametres) -> Counter:
    c = Counter(abo.presences.exclude(statut=Presence.Statut.ANNULEE).values_list("date", flat=True))
    if params.absence_decompte_seance and abo.est_mensuel:
        absences = Reservation.objects.filter(
            client_id=abo.client_id, statut=Reservation.Statut.ABSENT,
            date__gte=abo.date_debut, date__lte=abo.date_fin).values_list("date", flat=True)
        c.update(absences)
    return c


def etat_droits(abo: Abonnement, jour: date | None = None, params: Parametres | None = None) -> dict:
    """Calendrier complet des droits d'un abonnement à une date donnée."""
    params = params or Parametres.get()
    jour = jour or timezone.localdate()
    semaines = decouper_semaines(abo, params)
    conso = _consommations_par_jour(abo, params)
    illimite = any(s["quota"] is None for s in semaines)
    report = 0
    courante = None
    for s in semaines:
        s["utilisees"] = sum(n for d, n in conso.items() if s["debut"] <= d <= s["fin"])
        if illimite:
            s.update(report_entrant=0, autorisees=None, restantes=None)
        else:
            s["report_entrant"] = report if abo.report_seances else 0
            s["autorisees"] = s["quota"] + s["report_entrant"]
            s["restantes"] = max(0, s["autorisees"] - s["utilisees"])
            report = s["restantes"]
        if s["fin"] < jour:
            s["statut"] = "passee"
        elif s["debut"] > jour:
            s["statut"] = "a_venir"
        else:
            s["statut"] = "courante"
            courante = s
    total_utilisees = sum(conso.values())
    if illimite:
        total_droits = total_restantes = None
    else:
        total_droits = sum(s["quota"] for s in semaines)
        if jour < abo.date_debut:
            total_restantes = total_droits
        elif jour > abo.date_fin:
            total_restantes = 0
        else:
            futur = sum(s["quota"] for s in semaines if s["statut"] == "a_venir")
            total_restantes = (courante["restantes"] if courante else 0) + futur
    return {
        "abonnement": abo, "semaines": semaines, "courante": courante, "illimite": illimite,
        "total_droits": total_droits, "total_utilisees": total_utilisees,
        "total_restantes": total_restantes,
    }


def abonnement_courant(client: Client, jour: date | None = None):
    """Abonnement mensuel valide aujourd'hui (ou le plus récent si aucun)."""
    jour = jour or timezone.localdate()
    qs = client.abonnements.filter(statut=Abonnement.Statut.ACTIF)
    valide = qs.filter(date_debut__lte=jour, date_fin__gte=jour).order_by("type", "-date_debut").first()
    if valide:
        return valide
    return qs.order_by("-date_fin").first()


def resume_client(client: Client, jour: date | None = None) -> dict:
    """Résumé utilisé par la réception (solde en quelques secondes)."""
    jour = jour or timezone.localdate()
    abo = abonnement_courant(client, jour)
    droits = etat_droits(abo, jour) if abo else None
    return {"abonnement": abo, "droits": droits, "acces": verifier_acces(client, jour),
            "presence": client.presence_en_cours(), "reste_a_payer": client.reste_a_payer()}


# ---------------------------------------------------------------------------
# Contrôle d'accès et pointage
# ---------------------------------------------------------------------------
@dataclass
class ResultatAcces:
    autorise: bool
    abonnement: Abonnement | None = None
    code: str = ""
    message: str = ""
    avertissements: list = field(default_factory=list)
    droits: dict | None = None
    peut_deroger: bool = True
    proposer_renouvellement: bool = False


def verifier_acces(client: Client, jour: date | None = None) -> ResultatAcces:
    params = Parametres.get()
    jour = jour or timezone.localdate()
    if client.presence_en_cours():
        return ResultatAcces(False, code="DEJA_PRESENT", peut_deroger=False,
                             message="Ce client est déjà enregistré comme présent. Enregistrez d'abord sa sortie.")
    if not client.actif:
        return ResultatAcces(False, code="CLIENT_INACTIF", peut_deroger=False,
                             message="La fiche de ce client est désactivée.")

    valides = list(client.abonnements.filter(
        statut=Abonnement.Statut.ACTIF, date_debut__lte=jour, date_fin__gte=jour
    ).order_by("cree_le"))
    mensuels = [a for a in valides if a.est_mensuel]
    tickets = [a for a in valides if not a.est_mensuel]

    choisi, droits = None, None
    for abo in mensuels + tickets:
        d = etat_droits(abo, jour, params)
        if d["illimite"] or (d["courante"] and d["courante"]["restantes"] > 0):
            choisi, droits = abo, d
            break

    reste = client.reste_a_payer()
    if choisi:
        res = ResultatAcces(True, abonnement=choisi, droits=droits, code="OK",
                            message="Accès autorisé.")
        if choisi.est_mensuel:
            if choisi.jours_restants <= params.jours_alerte_expiration:
                res.avertissements.append(
                    f"Abonnement bientôt expiré : fin le {choisi.date_fin:%d/%m/%Y} "
                    f"({choisi.jours_restants} jour(s)). Proposez le renouvellement.")
                res.proposer_renouvellement = True
            if not droits["illimite"]:
                apres = droits["courante"]["restantes"] - 1
                if apres <= params.seuil_alerte_seances:
                    res.avertissements.append(
                        f"Après cette séance, il restera {apres} séance(s) cette semaine.")
        if reste > 0:
            res.avertissements.append(f"Paiement en attente : {fcfa(reste)} restent à régler.")
            if params.bloquer_si_impaye:
                res.autorise = False
                res.code = "PAIEMENT_EN_ATTENTE"
                res.message = f"Entrée bloquée : {fcfa(reste)} restent à régler."
        return res

    # Aucun droit utilisable : on identifie la raison exacte.
    if mensuels:
        abo = mensuels[0]
        return ResultatAcces(
            False, abonnement=abo, droits=etat_droits(abo, jour, params), code="QUOTA_EPUISE",
            message=f"Quota hebdomadaire épuisé ({abo.seances_par_semaine} séances/semaine déjà consommées).")
    if tickets:
        return ResultatAcces(False, code="SEANCE_CONSOMMEE",
                             message="La séance payée a déjà été consommée. Une nouvelle séance nécessite un nouveau paiement.")
    futur = client.abonnements.filter(statut=Abonnement.Statut.ACTIF, date_debut__gt=jour).order_by("date_debut").first()
    if futur:
        return ResultatAcces(False, abonnement=futur, code="AUCUN_ABONNEMENT",
                             message=f"L'abonnement ne commence que le {futur.date_debut:%d/%m/%Y}.")
    dernier = client.abonnements.filter(statut=Abonnement.Statut.ACTIF).order_by("-date_fin").first()
    if dernier:
        return ResultatAcces(False, code="ABONNEMENT_EXPIRE", proposer_renouvellement=True,
                             message=f"Abonnement expiré depuis le {dernier.date_fin:%d/%m/%Y}. Proposez le renouvellement.")
    return ResultatAcces(False, code="AUCUN_ABONNEMENT", proposer_renouvellement=True,
                         message="Aucun abonnement ni séance payée pour ce client.")


def accorder_autorisation(client, motif, justification, responsable, demandeur, request=None):
    if not (justification or "").strip():
        raise ErreurMetier("La justification de l'autorisation exceptionnelle est obligatoire.")
    if motif not in AutorisationExceptionnelle.Motif.values:
        motif = AutorisationExceptionnelle.Motif.AUTRE
    auto = AutorisationExceptionnelle.objects.create(
        client=client, motif=motif, justification=justification.strip(),
        accordee_par=responsable, demandee_par=demandeur)
    journaliser(demandeur, "AUTORISATION", client.identifiant,
                f"Autorisation exceptionnelle accordée par {responsable.nom_complet} "
                f"({auto.get_motif_display()}) : {auto.justification}", request=request)
    return auto


def enregistrer_entree(client: Client, utilisateur, coach=None, autorisation=None, request=None) -> Presence:
    with db_tx.atomic():
        client = Client.objects.select_for_update().get(pk=client.pk)
        res = verifier_acces(client)
        if not res.autorise:
            if autorisation is None or not res.peut_deroger:
                raise ErreurMetier(res.message)
        abo = res.abonnement if (res.autorise or res.code in ("QUOTA_EPUISE", "PAIEMENT_EN_ATTENTE")) else None
        try:
            with db_tx.atomic():
                presence = Presence.objects.create(
                    client=client, abonnement=abo, date=timezone.localdate(),
                    heure_entree=timezone.now(), entree_par=utilisateur,
                    type_abonnement=abo.designation if abo else "Autorisation exceptionnelle",
                    coach=coach or client.coach, autorisation=autorisation)
        except IntegrityError:
            raise ErreurMetier("Ce client est déjà enregistré comme présent.")
        _figer_soldes(presence)
        presence.save()
        Reservation.objects.filter(client=client, date=presence.date,
                                   statut=Reservation.Statut.PREVUE).update(statut=Reservation.Statut.HONOREE)
        journaliser(utilisateur, "ENTREE", client.identifiant,
                    f"Entrée de {client.nom_complet} ({presence.type_abonnement})"
                    + (" — autorisation exceptionnelle" if autorisation else ""), request=request)
    return presence


def _figer_soldes(presence: Presence):
    abo = presence.abonnement
    if not abo:
        presence.seances_restantes_semaine = presence.seances_restantes_total = None
        return
    d = etat_droits(abo, presence.date)
    if d["illimite"]:
        presence.seances_restantes_semaine = presence.seances_restantes_total = None
    else:
        presence.seances_restantes_semaine = d["courante"]["restantes"] if d["courante"] else 0
        presence.seances_restantes_total = d["total_restantes"]


def enregistrer_sortie(presence: Presence, utilisateur, request=None):
    """Clôture la présence ; calcule durée, dépassement et supplément éventuel.
    Renvoie (presence, transaction_supplement_ou_None)."""
    with db_tx.atomic():
        presence = Presence.objects.select_for_update().get(pk=presence.pk)
        if presence.statut != Presence.Statut.EN_COURS:
            raise ErreurMetier("La sortie de ce client a déjà été enregistrée.")
        presence.heure_sortie = timezone.now()
        presence.duree_minutes = presence.duree_actuelle()
        presence.statut = Presence.Statut.TERMINEE
        presence.sortie_par = utilisateur
        tx = None
        abo = presence.abonnement
        if abo and abo.est_horaire and abo.duree_minutes:
            depassement = max(0, presence.duree_minutes - abo.duree_minutes)
            presence.depassement_minutes = depassement
            if depassement > abo.tolerance_minutes and abo.tarif_depassement > 0:
                tranche = max(1, abo.tranche_depassement_minutes)
                nb = math.ceil(depassement / tranche)
                presence.supplement = abo.tarif_depassement * nb
                tx = creer_transaction(
                    presence.client, Transaction.Type.SUPPLEMENT,
                    f"Supplément dépassement horaire : {depassement} min au-delà de "
                    f"{duree_lisible(abo.duree_minutes)} ({nb} tranche(s) de {tranche} min)",
                    abo.tarif_depassement, utilisateur, quantite=nb, abonnement=abo,
                    presence=presence, request=request)
        _figer_soldes(presence)
        presence.save()
        journaliser(utilisateur, "SORTIE", presence.client.identifiant,
                    f"Sortie de {presence.client.nom_complet} — durée {duree_lisible(presence.duree_minutes)}"
                    + (f", dépassement {presence.depassement_minutes} min" if presence.depassement_minutes else ""),
                    request=request)
    return presence, tx


def annuler_presence(presence: Presence, responsable, motif: str, request=None):
    if not (motif or "").strip():
        raise ErreurMetier("Le motif d'annulation est obligatoire.")
    if presence.statut == Presence.Statut.ANNULEE:
        raise ErreurMetier("Cette présence est déjà annulée.")
    presence.statut = Presence.Statut.ANNULEE
    presence.motif_annulation = motif.strip()
    presence.annulee_par = responsable
    if presence.heure_sortie is None:
        presence.heure_sortie = timezone.now()
    presence.save()
    journaliser(responsable, "PRESENCE_ANNULEE", presence.client.identifiant,
                f"Présence du {presence.date:%d/%m/%Y} annulée (séance recréditée) : {motif}", request=request)


def duree_lisible(minutes) -> str:
    if minutes is None:
        return "—"
    h, m = divmod(int(minutes), 60)
    return f"{h} h {m:02d}" if h else f"{m} min"


# ---------------------------------------------------------------------------
# Ventes, encaissements, annulations, remboursements
# ---------------------------------------------------------------------------
def creer_transaction(client, type_, designation, prix_unitaire, utilisateur, quantite=1,
                      abonnement=None, presence=None, coach=None, observations="", request=None):
    prix_unitaire = Decimal(prix_unitaire)
    tx = Transaction.objects.create(
        numero=Sequence.suivant("TR", "TR"), client=client, type=type_, designation=designation,
        quantite=quantite, prix_unitaire=prix_unitaire, montant_du=prix_unitaire * quantite,
        abonnement=abonnement, presence=presence, coach=coach, observations=observations,
        cree_par=utilisateur)
    Facture.objects.create(numero=Sequence.suivant("FAC", "FAC"), transaction=tx, emise_par=utilisateur)
    journaliser(utilisateur, "TRANSACTION", tx.numero,
                f"{tx.get_type_display()} — {client.nom_complet} — {fcfa(tx.montant_du)}", request=request)
    return tx


def date_debut_proposee(client: Client, formule: Formule) -> date:
    """Renouvellement anticipé : le nouvel abonnement démarre le lendemain de
    la fin de l'abonnement en cours (aucun jour perdu)."""
    jour = timezone.localdate()
    if formule.type != Formule.Type.MENSUEL:
        return jour
    dernier = client.abonnements.filter(statut=Abonnement.Statut.ACTIF, type=Formule.Type.MENSUEL
                                        ).order_by("-date_fin").first()
    if dernier and dernier.date_fin >= jour:
        return dernier.date_fin + timedelta(days=1)
    return jour


def creer_vente(client: Client, formule: Formule, utilisateur, date_debut: date | None = None,
                montant_paye=0, mode: ModePaiement | None = None, reference="", coach=None,
                observations="", request=None) -> Transaction:
    """Vente d'une formule : crée l'abonnement, la transaction, la facture et
    l'encaissement éventuel — en une seule opération atomique."""
    if not formule.actif:
        raise ErreurMetier("Cette formule est désactivée.")
    montant_paye = Decimal(montant_paye or 0)
    if montant_paye < 0:
        raise ErreurMetier("Le montant payé ne peut pas être négatif.")
    if montant_paye > formule.prix:
        raise ErreurMetier(f"Le montant payé dépasse le prix de la formule ({fcfa(formule.prix)}).")
    if montant_paye > 0 and mode is None:
        raise ErreurMetier("Choisissez le mode de paiement.")
    params = Parametres.get()
    with db_tx.atomic():
        date_debut = date_debut or date_debut_proposee(client, formule)
        precedent = client.abonnements.filter(statut=Abonnement.Statut.ACTIF, type=formule.type
                                              ).order_by("-date_fin").first()
        renouvellement = formule.est_mensuel and client.abonnements.filter(
            type=Formule.Type.MENSUEL).exclude(statut=Abonnement.Statut.ANNULE).exists()
        abo = Abonnement(
            client=client, formule=formule, type=formule.type, designation=formule.nom,
            date_debut=date_debut, date_fin=calculer_date_fin(formule, date_debut, params),
            prix=formule.prix,
            seances_par_semaine=formule.seances_par_semaine if formule.est_mensuel else 0,
            report_seances=formule.report_seances if formule.est_mensuel else False,
            duree_minutes=formule.duree_minutes if formule.type == Formule.Type.HORAIRE else None,
            tolerance_minutes=formule.tolerance_minutes,
            tranche_depassement_minutes=formule.tranche_depassement_minutes,
            tarif_depassement=formule.tarif_depassement,
            est_renouvellement=renouvellement, precedent=precedent if renouvellement else None,
            coach=coach or client.coach, cree_par=utilisateur)
        abo.save()
        abo.seances_total = calculer_seances_total(abo, params)
        abo.save(update_fields=["seances_total"])

        if formule.est_mensuel:
            type_tx = Transaction.Type.RENOUVELLEMENT if renouvellement else Transaction.Type.ABONNEMENT
            designation = f"{formule.nom} — du {abo.date_debut:%d/%m/%Y} au {abo.date_fin:%d/%m/%Y}"
        elif formule.type == Formule.Type.SEANCE:
            type_tx = Transaction.Type.SEANCE
            designation = f"{formule.nom} — 1 séance — valable le {abo.date_debut:%d/%m/%Y}" if abo.date_debut == abo.date_fin \
                else f"{formule.nom} — 1 séance — valable du {abo.date_debut:%d/%m/%Y} au {abo.date_fin:%d/%m/%Y}"
        else:
            type_tx = Transaction.Type.HORAIRE
            designation = f"{formule.nom} — {duree_lisible(abo.duree_minutes)} — le {abo.date_debut:%d/%m/%Y}"
        tx = creer_transaction(client, type_tx, designation, formule.prix, utilisateur, abonnement=abo,
                               coach=abo.coach, observations=observations, request=request)
        if montant_paye > 0:
            encaisser(tx, montant_paye, mode, utilisateur, reference, request=request)
    return tx


def encaisser(tx: Transaction, montant, mode: ModePaiement, utilisateur, reference="", request=None) -> Reglement:
    montant = Decimal(montant or 0)
    with db_tx.atomic():
        tx = Transaction.objects.select_for_update().get(pk=tx.pk)
        if tx.statut == Transaction.Statut.ANNULEE:
            raise ErreurMetier("Impossible d'encaisser une transaction annulée.")
        if montant <= 0:
            raise ErreurMetier("Le montant encaissé doit être supérieur à zéro.")
        if montant > tx.reste:
            raise ErreurMetier(f"Le montant dépasse le reste à payer ({fcfa(tx.reste)}).")
        if mode is None:
            raise ErreurMetier("Choisissez le mode de paiement.")
        reg = Reglement.objects.create(numero=Sequence.suivant("REC", "REC"), transaction=tx,
                                       montant=montant, mode=mode, reference=reference, recu_par=utilisateur)
        journaliser(utilisateur, "ENCAISSEMENT", reg.numero,
                    f"Encaissement de {fcfa(montant)} ({mode.nom}) sur {tx.numero} — {tx.client.nom_complet}",
                    request=request)
    return reg


def annuler_reglement(reg: Reglement, responsable, motif: str, request=None):
    if not (motif or "").strip():
        raise ErreurMetier("Le motif est obligatoire.")
    if reg.annule:
        raise ErreurMetier("Cet encaissement est déjà annulé.")
    if reg.transaction.montant_paye - reg.montant < reg.transaction.montant_rembourse:
        raise ErreurMetier("Cet encaissement a déjà fait l'objet d'un remboursement.")
    reg.annule, reg.motif_annulation, reg.annule_par, reg.annule_le = True, motif.strip(), responsable, timezone.now()
    reg.save()
    journaliser(responsable, "ENCAISSEMENT_ANNULE", reg.numero,
                f"Encaissement {reg.numero} de {fcfa(reg.montant)} annulé : {motif}", request=request)


def annuler_transaction(tx: Transaction, responsable, motif: str, request=None):
    if not (motif or "").strip():
        raise ErreurMetier("Le motif d'annulation est obligatoire.")
    if tx.statut == Transaction.Statut.ANNULEE:
        raise ErreurMetier("Cette transaction est déjà annulée.")
    if tx.net_encaisse > 0:
        raise ErreurMetier(
            f"{fcfa(tx.net_encaisse)} ont été encaissés sur cette transaction : "
            "enregistrez d'abord le remboursement (ou annulez l'encaissement erroné).")
    with db_tx.atomic():
        tx.statut, tx.motif_annulation = Transaction.Statut.ANNULEE, motif.strip()
        tx.annulee_par, tx.annulee_le = responsable, timezone.now()
        tx.save()
        if tx.abonnement and tx.type != Transaction.Type.SUPPLEMENT:
            tx.abonnement.statut = Abonnement.Statut.ANNULE
            tx.abonnement.save(update_fields=["statut"])
        journaliser(responsable, "TRANSACTION_ANNULEE", tx.numero,
                    f"Transaction {tx.numero} ({fcfa(tx.montant_du)}) annulée : {motif}", request=request)


def rembourser(tx: Transaction, montant, mode: ModePaiement, motif: str, responsable, utilisateur,
               annuler_abonnement=False, request=None) -> Remboursement:
    montant = Decimal(montant or 0)
    if not (motif or "").strip():
        raise ErreurMetier("Le motif du remboursement est obligatoire.")
    if montant <= 0:
        raise ErreurMetier("Le montant du remboursement doit être supérieur à zéro.")
    if montant > tx.net_encaisse:
        raise ErreurMetier(f"Le remboursement dépasse le montant encaissé ({fcfa(tx.net_encaisse)}).")
    with db_tx.atomic():
        rb = Remboursement.objects.create(
            numero=Sequence.suivant("RMB", "RMB"), transaction=tx, montant=montant, mode=mode,
            motif=motif.strip(), autorise_par=responsable, effectue_par=utilisateur)
        journaliser(utilisateur, "REMBOURSEMENT", rb.numero,
                    f"Remboursement de {fcfa(montant)} sur {tx.numero} autorisé par "
                    f"{responsable.nom_complet} : {motif}", request=request)
        if annuler_abonnement and tx.abonnement:
            tx.abonnement.statut = Abonnement.Statut.ANNULE
            tx.abonnement.save(update_fields=["statut"])
            journaliser(utilisateur, "ABONNEMENT_ANNULE", tx.client.identifiant,
                        f"Abonnement « {tx.abonnement} » annulé suite au remboursement {rb.numero}", request=request)
    return rb


# ---------------------------------------------------------------------------
# Indicateurs et alertes
# ---------------------------------------------------------------------------
def total_encaisse(debut: date, fin: date) -> Decimal:
    """Encaissements nets (encaissements – remboursements) du jour début au jour fin inclus."""
    enc = Reglement.objects.filter(annule=False, date__date__gte=debut, date__date__lte=fin
                                   ).aggregate(s=Sum("montant"))["s"] or Decimal(0)
    rmb = Remboursement.objects.filter(date__date__gte=debut, date__date__lte=fin
                                       ).aggregate(s=Sum("montant"))["s"] or Decimal(0)
    return enc - rmb


def transactions_impayees_qs():
    """Transactions validées dont le montant payé est inférieur au montant dû (une requête)."""
    return (Transaction.objects.filter(statut=Transaction.Statut.VALIDEE)
            .annotate(paye=Coalesce(Sum("reglements__montant", filter=Q(reglements__annule=False)),
                                    Decimal(0), output_field=DecimalField()))
            .filter(montant_du__gt=F("paye")).select_related("client").order_by("cree_le"))


def transactions_impayees():
    return list(transactions_impayees_qs())


def alertes(jour: date | None = None) -> dict:
    params = Parametres.get()
    jour = jour or timezone.localdate()
    a = {k: [] for k in ("a_renouveler", "expires", "quota_epuise", "derniere_seance",
                         "depassements", "paiements_attente", "presents")}
    actifs = Abonnement.objects.filter(statut=Abonnement.Statut.ACTIF, type=Formule.Type.MENSUEL
                                       ).select_related("client")
    # Dernier abonnement mensuel de chaque client
    derniers = {}
    for abo in actifs.order_by("client_id", "date_fin"):
        derniers[abo.client_id] = abo
    for abo in derniers.values():
        if not abo.client.actif:
            continue
        if abo.date_fin < jour:
            a["expires"].append(abo)
        elif abo.date_debut <= jour:
            if (abo.date_fin - jour).days <= params.jours_alerte_expiration:
                a["a_renouveler"].append(abo)
    for abo in actifs.filter(date_debut__lte=jour, date_fin__gte=jour):
        d = etat_droits(abo, jour, params)
        if d["illimite"] or not d["courante"]:
            continue
        r = d["courante"]["restantes"]
        if r == 0:
            a["quota_epuise"].append((abo, d))
        elif r <= params.seuil_alerte_seances:
            a["derniere_seance"].append((abo, d))
    a["expires"].sort(key=lambda x: x.date_fin, reverse=True)
    a["a_renouveler"].sort(key=lambda x: x.date_fin)
    for p in Presence.objects.filter(statut=Presence.Statut.EN_COURS).select_related("client", "abonnement"):
        a["presents"].append(p)
        if p.depassement_en_cours() > 0:
            a["depassements"].append(p)
    a["depassements"] += list(Presence.objects.filter(
        date=jour, statut=Presence.Statut.TERMINEE, depassement_minutes__gt=0).select_related("client"))
    a["paiements_attente"] = transactions_impayees()
    return a
