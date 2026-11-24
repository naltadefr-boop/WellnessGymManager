"""
Modèle de données de WELLNESS GYM MANAGER.

Principes :
  * Aucune donnée financière n'est supprimée : on ANNULE avec motif + auteur.
  * Les abonnements gardent une COPIE des conditions de la formule au moment
    de la vente (prix, quota, durée…) : modifier un tarif ne change jamais
    l'historique.
  * Chaque opération importante est rattachée à son auteur et inscrite dans
    le journal d'audit (JournalAudit).
"""
from decimal import Decimal

from django.conf import settings
from django.contrib.auth.models import AbstractUser
from django.db import models, transaction
from django.db.models import Q, Sum
from django.utils import timezone

USER = settings.AUTH_USER_MODEL


def aujourdhui():
    return timezone.localdate()


def maintenant():
    return timezone.now()


# ---------------------------------------------------------------------------
# Utilisateurs et paramètres
# ---------------------------------------------------------------------------
class Utilisateur(AbstractUser):
    class Role(models.TextChoices):
        ADMIN = "ADMIN", "Administrateur / Responsable"
        RECEPTION = "RECEPTION", "Réceptionniste"
        COACH = "COACH", "Coach"

    role = models.CharField("rôle", max_length=12, choices=Role.choices, default=Role.RECEPTION)
    telephone = models.CharField("téléphone", max_length=30, blank=True)

    class Meta:
        verbose_name = "utilisateur"
        ordering = ["last_name", "first_name", "username"]

    @property
    def nom_complet(self):
        return self.get_full_name() or self.username

    @property
    def est_admin(self):
        return self.is_superuser or self.role == self.Role.ADMIN

    @property
    def est_reception(self):
        return self.role == self.Role.RECEPTION

    @property
    def est_coach(self):
        return self.role == self.Role.COACH and not self.is_superuser

    @property
    def voit_finances(self):
        return not self.est_coach

    def __str__(self):
        return self.nom_complet


class Parametres(models.Model):
    """Paramètres généraux (une seule ligne en base)."""

    class SemainePartielle(models.TextChoices):
        PRORATA_SUP = "PRORATA_SUP", "Au prorata des jours, arrondi au supérieur"
        PRORATA_INF = "PRORATA_INF", "Au prorata des jours, arrondi à l'inférieur"
        COMPLET = "COMPLET", "Quota complet même pour une semaine incomplète"

    nom_etablissement = models.CharField("nom de l'établissement", max_length=120, default="WELLNESS HOTEL")
    service = models.CharField(max_length=120, default="Salle de sport et fitness")
    adresse = models.CharField(max_length=255, blank=True)
    telephone = models.CharField("téléphone", max_length=60, blank=True)
    email = models.EmailField("adresse électronique", blank=True)
    mentions_legales = models.CharField(
        "mentions légales (RCCM, NIU…)", max_length=255, blank=True,
        help_text="Affichées en bas des factures.")
    logo = models.ImageField(upload_to="identite/", blank=True)
    cachet = models.ImageField("image du cachet (facultatif)", upload_to="identite/", blank=True)
    devise = models.CharField(max_length=10, default="FCFA")
    indicatif_pays = models.CharField(
        "indicatif téléphonique du pays (WhatsApp)", max_length=5, default="237",
        help_text="Ajouté aux numéros locaux pour l'envoi WhatsApp (ex. 237 Cameroun, 226 Burkina Faso).")
    mention_remerciement = models.CharField(
        max_length=255,
        default="Merci de votre confiance. WELLNESS HOTEL vous souhaite d'excellentes séances !")

    # Règles de gestion
    jours_alerte_expiration = models.PositiveSmallIntegerField(
        "alerte « bientôt expiré » (jours avant la fin)", default=5)
    seuil_alerte_seances = models.PositiveSmallIntegerField(
        "alerte « dernière(s) séance(s) » quand il reste au plus", default=1)
    mode_semaine_partielle = models.CharField(
        "calcul des semaines incomplètes", max_length=12,
        choices=SemainePartielle.choices, default=SemainePartielle.PRORATA_SUP)
    validite_ticket_jours = models.PositiveSmallIntegerField(
        "validité d'une séance journalière / horaire (jours)", default=1,
        help_text="1 = utilisable uniquement le jour de l'achat.")
    absence_decompte_seance = models.BooleanField(
        "une réservation non honorée (absence) décompte une séance", default=False)
    bloquer_si_impaye = models.BooleanField(
        "bloquer l'entrée si un paiement est en attente", default=False)

    # Sécurité / sauvegarde
    duree_inactivite_minutes = models.PositiveSmallIntegerField(
        "déconnexion automatique après inactivité (minutes)", default=15)
    sauvegarde_auto = models.BooleanField("sauvegarde automatique", default=True)
    sauvegarde_intervalle_heures = models.PositiveSmallIntegerField(
        "intervalle entre deux sauvegardes automatiques (heures)", default=12)
    sauvegarde_conservation = models.PositiveSmallIntegerField(
        "nombre de sauvegardes automatiques conservées", default=30)
    dossier_sauvegarde_externe = models.CharField(
        "copie supplémentaire vers (clé USB, disque externe…)", max_length=255, blank=True,
        help_text="Ex. : E:\\Sauvegardes_Gym. Laisser vide pour ne pas copier.")
    derniere_sauvegarde = models.DateTimeField(null=True, blank=True, editable=False)

    # Courrier électronique (envoi des factures)
    smtp_hote = models.CharField("serveur SMTP", max_length=120, blank=True)
    smtp_port = models.PositiveIntegerField("port SMTP", default=587)
    smtp_utilisateur = models.CharField("identifiant SMTP", max_length=120, blank=True)
    smtp_mot_de_passe = models.CharField("mot de passe SMTP", max_length=120, blank=True)
    smtp_tls = models.BooleanField("utiliser TLS", default=True)
    smtp_expediteur = models.EmailField("adresse d'expédition", blank=True)

    class Meta:
        verbose_name = "paramètres"

    def save(self, *args, **kwargs):
        self.pk = 1
        super().save(*args, **kwargs)

    @classmethod
    def get(cls):
        obj, _ = cls.objects.get_or_create(pk=1)
        return obj


class ModePaiement(models.Model):
    nom = models.CharField(max_length=60, unique=True)
    actif = models.BooleanField(default=True)
    ordre = models.PositiveSmallIntegerField(default=0)

    class Meta:
        ordering = ["ordre", "nom"]
        verbose_name = "mode de paiement"

    def __str__(self):
        return self.nom


class Sequence(models.Model):
    """Compteurs de numérotation (factures, reçus, transactions…)."""
    code = models.CharField(max_length=20)
    annee = models.PositiveIntegerField()
    dernier = models.PositiveIntegerField(default=0)

    class Meta:
        unique_together = [("code", "annee")]

    @classmethod
    def suivant(cls, code: str, prefixe: str) -> str:
        annee = timezone.localdate().year
        with transaction.atomic():
            seq, _ = cls.objects.select_for_update().get_or_create(code=code, annee=annee)
            seq.dernier += 1
            seq.save(update_fields=["dernier"])
            return f"{prefixe}-{annee}-{seq.dernier:05d}"


# ---------------------------------------------------------------------------
# Coachs, formules, clients, abonnements
# ---------------------------------------------------------------------------
class Coach(models.Model):
    class Statut(models.TextChoices):
        ACTIF = "ACTIF", "Actif"
        INACTIF = "INACTIF", "Inactif"

    nom = models.CharField(max_length=80)
    prenom = models.CharField("prénom", max_length=80)
    telephone = models.CharField("téléphone", max_length=30, blank=True)
    fonction = models.CharField(max_length=80, default="Coach sportif")
    date_enregistrement = models.DateField("date d'enregistrement", default=aujourdhui)
    statut = models.CharField(max_length=10, choices=Statut.choices, default=Statut.ACTIF)
    utilisateur = models.OneToOneField(
        USER, null=True, blank=True, on_delete=models.SET_NULL, related_name="coach",
        verbose_name="compte de connexion", limit_choices_to={"role": "COACH"})

    class Meta:
        ordering = ["nom", "prenom"]

    def __str__(self):
        return f"{self.prenom} {self.nom}"


class Formule(models.Model):
    class Type(models.TextChoices):
        MENSUEL = "MENSUEL", "Abonnement mensuel"
        SEANCE = "SEANCE", "Séance journalière"
        HORAIRE = "HORAIRE", "Formule horaire"

    nom = models.CharField(max_length=100, unique=True)
    type = models.CharField(max_length=10, choices=Type.choices)
    description = models.CharField(max_length=255, blank=True)
    prix = models.DecimalField(max_digits=12, decimal_places=0)
    # Abonnement mensuel
    duree_mois = models.PositiveSmallIntegerField("durée (mois)", default=1)
    seances_par_semaine = models.PositiveSmallIntegerField(
        "séances par semaine", default=4, help_text="0 = accès illimité.")
    report_seances = models.BooleanField(
        "séances non utilisées reportables sur la semaine suivante", default=False,
        help_text="Décoché : les séances non utilisées sont perdues à la fin de chaque semaine.")
    # Formule horaire
    duree_minutes = models.PositiveIntegerField("durée autorisée (minutes)", null=True, blank=True)
    tolerance_minutes = models.PositiveSmallIntegerField("tolérance avant supplément (minutes)", default=5)
    tranche_depassement_minutes = models.PositiveSmallIntegerField("tranche de dépassement (minutes)", default=30)
    tarif_depassement = models.DecimalField(
        "supplément par tranche entamée", max_digits=12, decimal_places=0, default=0)
    actif = models.BooleanField(default=True)
    cree_le = models.DateTimeField(auto_now_add=True)
    modifie_le = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-actif", "type", "prix"]

    def __str__(self):
        return self.nom

    @property
    def est_mensuel(self):
        return self.type == self.Type.MENSUEL


class Client(models.Model):
    class Sexe(models.TextChoices):
        M = "M", "Masculin"
        F = "F", "Féminin"

    identifiant = models.CharField(max_length=12, unique=True, editable=False, blank=True)
    nom = models.CharField(max_length=80)
    prenom = models.CharField("prénom", max_length=80)
    sexe = models.CharField(max_length=1, choices=Sexe.choices, blank=True)
    telephone = models.CharField("téléphone", max_length=30)
    email = models.EmailField("adresse électronique", blank=True)
    date_inscription = models.DateField("date d'inscription", default=aujourdhui)
    coach = models.ForeignKey(Coach, null=True, blank=True, on_delete=models.SET_NULL,
                              related_name="clients", verbose_name="coach attitré")
    observations = models.TextField(blank=True)
    actif = models.BooleanField(default=True)
    cree_par = models.ForeignKey(USER, null=True, on_delete=models.SET_NULL, related_name="+",
                                 verbose_name="enregistré par")
    cree_le = models.DateTimeField(auto_now_add=True)
    modifie_le = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["nom", "prenom"]
        indexes = [models.Index(fields=["nom", "prenom"]), models.Index(fields=["telephone"])]

    def save(self, *args, **kwargs):
        nouveau = self.pk is None
        super().save(*args, **kwargs)
        if nouveau and not self.identifiant:
            self.identifiant = f"WG{self.pk:05d}"
            super().save(update_fields=["identifiant"])

    def __str__(self):
        return f"{self.prenom} {self.nom}"

    @property
    def nom_complet(self):
        return f"{self.prenom} {self.nom.upper()}"

    def presence_en_cours(self):
        return self.presences.filter(statut=Presence.Statut.EN_COURS).first()

    def reste_a_payer(self):
        return sum((t.reste for t in self.transactions.filter(statut=Transaction.Statut.VALIDEE)), Decimal(0))


class Abonnement(models.Model):
    """Droit d'accès vendu à un client (mensuel, séance ou horaire).
    Les conditions de la formule sont COPIÉES à la vente."""

    class Statut(models.TextChoices):
        ACTIF = "ACTIF", "Valide"
        ANNULE = "ANNULE", "Annulé"

    client = models.ForeignKey(Client, on_delete=models.PROTECT, related_name="abonnements")
    formule = models.ForeignKey(Formule, on_delete=models.PROTECT, related_name="abonnements")
    type = models.CharField(max_length=10, choices=Formule.Type.choices)
    designation = models.CharField("désignation", max_length=120)
    date_debut = models.DateField("date de début")
    date_fin = models.DateField("date de fin")
    prix = models.DecimalField(max_digits=12, decimal_places=0)
    seances_par_semaine = models.PositiveSmallIntegerField(default=0)
    report_seances = models.BooleanField(default=False)
    seances_total = models.PositiveIntegerField(
        "séances autorisées sur la période", null=True, blank=True, help_text="Vide = illimité")
    duree_minutes = models.PositiveIntegerField(null=True, blank=True)
    tolerance_minutes = models.PositiveSmallIntegerField(default=0)
    tranche_depassement_minutes = models.PositiveSmallIntegerField(default=30)
    tarif_depassement = models.DecimalField(max_digits=12, decimal_places=0, default=0)
    statut = models.CharField(max_length=10, choices=Statut.choices, default=Statut.ACTIF)
    est_renouvellement = models.BooleanField(default=False)
    precedent = models.ForeignKey("self", null=True, blank=True, on_delete=models.SET_NULL,
                                  related_name="suivants")
    coach = models.ForeignKey(Coach, null=True, blank=True, on_delete=models.SET_NULL,
                              related_name="abonnements")
    cree_par = models.ForeignKey(USER, null=True, on_delete=models.SET_NULL, related_name="+")
    cree_le = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-date_debut", "-id"]

    def __str__(self):
        return f"{self.designation} ({self.date_debut:%d/%m/%Y} → {self.date_fin:%d/%m/%Y})"

    @property
    def est_mensuel(self):
        return self.type == Formule.Type.MENSUEL

    @property
    def est_horaire(self):
        return self.type == Formule.Type.HORAIRE

    def seances_utilisees(self):
        return self.presences.exclude(statut=Presence.Statut.ANNULEE).count()

    @property
    def etat(self):
        """ANNULE, A_VENIR, EXPIRE, CONSOMME ou ACTIF (à la date du jour)."""
        jour = timezone.localdate()
        if self.statut == self.Statut.ANNULE:
            return "ANNULE"
        if jour < self.date_debut:
            return "A_VENIR"
        if jour > self.date_fin:
            return "EXPIRE"
        if not self.est_mensuel and self.seances_utilisees() >= 1:
            return "CONSOMME"
        return "ACTIF"

    @property
    def etat_libelle(self):
        return {"ANNULE": "Annulé", "A_VENIR": "À venir", "EXPIRE": "Expiré",
                "CONSOMME": "Consommé", "ACTIF": "Actif"}[self.etat]

    @property
    def jours_restants(self):
        return (self.date_fin - timezone.localdate()).days


class AutorisationExceptionnelle(models.Model):
    class Motif(models.TextChoices):
        QUOTA_EPUISE = "QUOTA_EPUISE", "Quota hebdomadaire épuisé"
        ABONNEMENT_EXPIRE = "ABONNEMENT_EXPIRE", "Abonnement expiré"
        AUCUN_ABONNEMENT = "AUCUN_ABONNEMENT", "Aucun abonnement valide"
        SEANCE_CONSOMMEE = "SEANCE_CONSOMMEE", "Séance déjà consommée"
        PAIEMENT_EN_ATTENTE = "PAIEMENT_EN_ATTENTE", "Paiement en attente"
        AUTRE = "AUTRE", "Autre"

    client = models.ForeignKey(Client, on_delete=models.PROTECT, related_name="autorisations")
    motif = models.CharField(max_length=20, choices=Motif.choices)
    justification = models.TextField()
    accordee_par = models.ForeignKey(USER, on_delete=models.PROTECT, related_name="+",
                                     verbose_name="accordée par (responsable)")
    demandee_par = models.ForeignKey(USER, on_delete=models.PROTECT, related_name="+")
    date = models.DateTimeField(default=maintenant)

    class Meta:
        ordering = ["-date"]


class Presence(models.Model):
    class Statut(models.TextChoices):
        EN_COURS = "EN_COURS", "Présent"
        TERMINEE = "TERMINEE", "Sorti"
        ANNULEE = "ANNULEE", "Annulée"

    client = models.ForeignKey(Client, on_delete=models.PROTECT, related_name="presences")
    abonnement = models.ForeignKey(Abonnement, null=True, blank=True, on_delete=models.PROTECT,
                                   related_name="presences")
    date = models.DateField(default=aujourdhui, db_index=True)
    heure_entree = models.DateTimeField("heure d'arrivée", default=maintenant)
    heure_sortie = models.DateTimeField("heure de départ", null=True, blank=True)
    duree_minutes = models.PositiveIntegerField(null=True, blank=True)
    statut = models.CharField(max_length=10, choices=Statut.choices, default=Statut.EN_COURS)
    type_abonnement = models.CharField(max_length=120, blank=True)
    seances_restantes_semaine = models.IntegerField(
        "solde de la semaine après cette séance", null=True, blank=True)
    seances_restantes_total = models.IntegerField(
        "solde total après cette séance", null=True, blank=True)
    autorisation = models.OneToOneField(AutorisationExceptionnelle, null=True, blank=True,
                                        on_delete=models.PROTECT, related_name="presence")
    coach = models.ForeignKey(Coach, null=True, blank=True, on_delete=models.SET_NULL,
                              related_name="seances_encadrees")
    depassement_minutes = models.PositiveIntegerField(default=0)
    supplement = models.DecimalField(max_digits=12, decimal_places=0, default=0)
    entree_par = models.ForeignKey(USER, null=True, on_delete=models.SET_NULL, related_name="+")
    sortie_par = models.ForeignKey(USER, null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    motif_annulation = models.CharField(max_length=255, blank=True)
    annulee_par = models.ForeignKey(USER, null=True, blank=True, on_delete=models.SET_NULL, related_name="+")

    class Meta:
        ordering = ["-heure_entree"]
        constraints = [
            # Empêche physiquement deux présences « en cours » pour un même client.
            models.UniqueConstraint(fields=["client"], condition=Q(statut="EN_COURS"),
                                    name="une_seule_presence_en_cours"),
        ]

    def __str__(self):
        return f"{self.client} — {timezone.localtime(self.heure_entree):%d/%m/%Y %H:%M}"

    def duree_actuelle(self):
        fin = self.heure_sortie or timezone.now()
        return int((fin - self.heure_entree).total_seconds() // 60)

    def depassement_en_cours(self):
        """Minutes au-delà de la durée autorisée (formule horaire en cours)."""
        if self.abonnement and self.abonnement.est_horaire and self.abonnement.duree_minutes:
            return max(0, self.duree_actuelle() - self.abonnement.duree_minutes)
        return 0


class Reservation(models.Model):
    class Statut(models.TextChoices):
        PREVUE = "PREVUE", "Prévue"
        HONOREE = "HONOREE", "Honorée"
        ABSENT = "ABSENT", "Absent (non présenté)"
        ANNULEE = "ANNULEE", "Annulée"

    client = models.ForeignKey(Client, on_delete=models.CASCADE, related_name="reservations")
    date = models.DateField()
    heure = models.TimeField(null=True, blank=True)
    coach = models.ForeignKey(Coach, null=True, blank=True, on_delete=models.SET_NULL, related_name="reservations")
    statut = models.CharField(max_length=10, choices=Statut.choices, default=Statut.PREVUE)
    note = models.CharField(max_length=255, blank=True)
    cree_par = models.ForeignKey(USER, null=True, on_delete=models.SET_NULL, related_name="+")
    cree_le = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["date", "heure"]


# ---------------------------------------------------------------------------
# Finances
# ---------------------------------------------------------------------------
class Transaction(models.Model):
    """Opération facturée : vente d'abonnement, séance, supplément…"""

    class Type(models.TextChoices):
        ABONNEMENT = "ABONNEMENT", "Abonnement"
        RENOUVELLEMENT = "RENOUVELLEMENT", "Renouvellement"
        SEANCE = "SEANCE", "Séance journalière"
        HORAIRE = "HORAIRE", "Formule horaire"
        SUPPLEMENT = "SUPPLEMENT", "Supplément (dépassement horaire)"
        AUTRE = "AUTRE", "Autre prestation"

    class Statut(models.TextChoices):
        VALIDEE = "VALIDEE", "Validée"
        ANNULEE = "ANNULEE", "Annulée"

    numero = models.CharField("numéro de transaction", max_length=20, unique=True)
    client = models.ForeignKey(Client, on_delete=models.PROTECT, related_name="transactions")
    abonnement = models.ForeignKey(Abonnement, null=True, blank=True, on_delete=models.PROTECT,
                                   related_name="transactions")
    presence = models.ForeignKey(Presence, null=True, blank=True, on_delete=models.PROTECT,
                                 related_name="transactions")
    type = models.CharField(max_length=15, choices=Type.choices)
    designation = models.CharField("désignation", max_length=200)
    quantite = models.PositiveIntegerField("quantité", default=1)
    prix_unitaire = models.DecimalField(max_digits=12, decimal_places=0)
    montant_du = models.DecimalField("montant à payer", max_digits=12, decimal_places=0)
    coach = models.ForeignKey(Coach, null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    statut = models.CharField(max_length=10, choices=Statut.choices, default=Statut.VALIDEE)
    observations = models.CharField(max_length=255, blank=True)
    cree_par = models.ForeignKey(USER, null=True, on_delete=models.SET_NULL, related_name="+",
                                 verbose_name="réceptionniste")
    cree_le = models.DateTimeField(default=maintenant)
    motif_annulation = models.CharField(max_length=255, blank=True)
    annulee_par = models.ForeignKey(USER, null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    annulee_le = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-cree_le"]

    def __str__(self):
        return f"{self.numero} — {self.designation}"

    def delete(self, *args, **kwargs):
        raise PermissionError("Une transaction ne peut pas être supprimée : utilisez l'annulation.")

    @property
    def montant_paye(self):
        return self.reglements.filter(annule=False).aggregate(s=Sum("montant"))["s"] or Decimal(0)

    @property
    def montant_rembourse(self):
        return self.remboursements.aggregate(s=Sum("montant"))["s"] or Decimal(0)

    @property
    def net_encaisse(self):
        return self.montant_paye - self.montant_rembourse

    @property
    def reste(self):
        if self.statut == self.Statut.ANNULEE:
            return Decimal(0)
        return max(Decimal(0), self.montant_du - self.montant_paye)

    @property
    def est_soldee(self):
        return self.reste == 0

    def modes_paiement(self):
        return ", ".join(sorted({r.mode.nom for r in self.reglements.filter(annule=False)})) or "—"


class Reglement(models.Model):
    """Encaissement (un reçu par encaissement)."""
    numero = models.CharField("numéro de reçu", max_length=20, unique=True)
    transaction = models.ForeignKey(Transaction, on_delete=models.PROTECT, related_name="reglements")
    montant = models.DecimalField(max_digits=12, decimal_places=0)
    mode = models.ForeignKey(ModePaiement, on_delete=models.PROTECT, verbose_name="mode de paiement")
    reference = models.CharField("référence (n° de transaction Mobile Money, chèque…)", max_length=80, blank=True)
    date = models.DateTimeField(default=maintenant)
    recu_par = models.ForeignKey(USER, null=True, on_delete=models.SET_NULL, related_name="+",
                                 verbose_name="réceptionniste")
    annule = models.BooleanField(default=False)
    motif_annulation = models.CharField(max_length=255, blank=True)
    annule_par = models.ForeignKey(USER, null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    annule_le = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-date"]

    def delete(self, *args, **kwargs):
        raise PermissionError("Un encaissement ne peut pas être supprimé : utilisez l'annulation.")


class Remboursement(models.Model):
    numero = models.CharField(max_length=20, unique=True)
    transaction = models.ForeignKey(Transaction, on_delete=models.PROTECT, related_name="remboursements")
    montant = models.DecimalField(max_digits=12, decimal_places=0)
    mode = models.ForeignKey(ModePaiement, on_delete=models.PROTECT)
    motif = models.CharField(max_length=255)
    autorise_par = models.ForeignKey(USER, on_delete=models.PROTECT, related_name="+",
                                     verbose_name="autorisé par")
    effectue_par = models.ForeignKey(USER, on_delete=models.PROTECT, related_name="+")
    date = models.DateTimeField(default=maintenant)

    class Meta:
        ordering = ["-date"]

    def delete(self, *args, **kwargs):
        raise PermissionError("Un remboursement ne peut pas être supprimé.")


class Facture(models.Model):
    numero = models.CharField(max_length=20, unique=True)
    transaction = models.OneToOneField(Transaction, on_delete=models.PROTECT, related_name="facture")
    date_emission = models.DateTimeField(default=maintenant)
    emise_par = models.ForeignKey(USER, null=True, on_delete=models.SET_NULL, related_name="+")
    nb_impressions = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["-date_emission"]

    def __str__(self):
        return self.numero


# ---------------------------------------------------------------------------
# Suivi : observations, incidents, journal
# ---------------------------------------------------------------------------
class Observation(models.Model):
    class Type(models.TextChoices):
        OBSERVATION = "OBSERVATION", "Observation"
        RECOMMANDATION = "RECOMMANDATION", "Recommandation"
        INCIDENT = "INCIDENT", "Incident"

    client = models.ForeignKey(Client, on_delete=models.CASCADE, related_name="observations_suivi")
    presence = models.ForeignKey(Presence, null=True, blank=True, on_delete=models.SET_NULL,
                                 related_name="observations")
    coach = models.ForeignKey(Coach, null=True, blank=True, on_delete=models.SET_NULL, related_name="observations")
    type = models.CharField(max_length=15, choices=Type.choices, default=Type.OBSERVATION)
    texte = models.TextField()
    auteur = models.ForeignKey(USER, null=True, on_delete=models.SET_NULL, related_name="+")
    date = models.DateTimeField(default=maintenant)

    class Meta:
        ordering = ["-date"]


class JournalAudit(models.Model):
    date = models.DateTimeField(default=maintenant, db_index=True)
    utilisateur = models.ForeignKey(USER, null=True, on_delete=models.SET_NULL, related_name="+")
    action = models.CharField(max_length=40, db_index=True)
    objet = models.CharField(max_length=120, blank=True)
    description = models.TextField()
    details = models.JSONField(default=dict, blank=True)
    adresse_ip = models.GenericIPAddressField(null=True, blank=True)

    class Meta:
        ordering = ["-date"]
        verbose_name = "journal d'audit"

    def delete(self, *args, **kwargs):
        raise PermissionError("Le journal d'audit ne peut pas être modifié.")


class JetonAPI(models.Model):
    """Jeton de connexion de l'application mobile (stocké haché : le jeton en
    clair n'est connu que du téléphone)."""
    utilisateur = models.ForeignKey(USER, on_delete=models.CASCADE, related_name="jetons")
    empreinte = models.CharField(max_length=64, unique=True)
    appareil = models.CharField(max_length=120, blank=True)
    cree_le = models.DateTimeField(default=maintenant)
    derniere_utilisation = models.DateTimeField(null=True, blank=True)
    actif = models.BooleanField(default=True)

    class Meta:
        ordering = ["-cree_le"]
        verbose_name = "jeton d'application mobile"

    @staticmethod
    def hacher(brut: str) -> str:
        import hashlib
        return hashlib.sha256(brut.encode()).hexdigest()

    @classmethod
    def emettre(cls, utilisateur, appareil=""):
        import secrets
        brut = secrets.token_urlsafe(32)
        cls.objects.create(utilisateur=utilisateur, empreinte=cls.hacher(brut), appareil=appareil[:120])
        return brut
