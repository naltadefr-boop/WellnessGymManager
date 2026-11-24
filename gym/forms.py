from django import forms
from django.contrib.auth.password_validation import validate_password
from django.utils import timezone

from .models import (
    AutorisationExceptionnelle, Client, Coach, Formule, ModePaiement, Observation, Parametres,
    Reservation, Utilisateur,
)

DATE = forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d")
TIME = forms.TimeInput(attrs={"type": "time"}, format="%H:%M")


class BaseForm:
    """Ajoute les classes CSS à tous les champs."""

    def _styler(self):
        for f in self.fields.values():
            w = f.widget
            if isinstance(w, forms.CheckboxInput):
                w.attrs.setdefault("class", "check")
            else:
                w.attrs.setdefault("class", "champ")


class StyledForm(BaseForm, forms.Form):
    def __init__(self, *a, **k):
        super().__init__(*a, **k)
        self._styler()


class StyledModelForm(BaseForm, forms.ModelForm):
    def __init__(self, *a, **k):
        super().__init__(*a, **k)
        self._styler()


# ---------------------------------------------------------------------------
class ClientForm(StyledModelForm):
    class Meta:
        model = Client
        fields = ["nom", "prenom", "sexe", "telephone", "email", "date_inscription", "coach", "observations"]
        widgets = {"date_inscription": DATE, "observations": forms.Textarea(attrs={"rows": 2})}

    def __init__(self, *a, **k):
        super().__init__(*a, **k)
        self.fields["coach"].queryset = Coach.objects.filter(statut=Coach.Statut.ACTIF)
        self.fields["sexe"].required = False
        self.fields["nom"].widget.attrs["autofocus"] = True

    def clean_nom(self):
        return self.cleaned_data["nom"].strip().upper()

    def clean_prenom(self):
        return self.cleaned_data["prenom"].strip().title()

    def clean_telephone(self):
        return " ".join(self.cleaned_data["telephone"].split())


class VenteForm(StyledForm):
    formule = forms.ModelChoiceField(queryset=Formule.objects.none(), label="Formule",
                                     empty_label="— Choisir une formule —")
    date_debut = forms.DateField(label="Date de début", required=False, widget=DATE,
                                 help_text="Vide = aujourd'hui (ou le lendemain de la fin de l'abonnement en cours).")
    montant_paye = forms.DecimalField(label="Montant payé maintenant", min_value=0, decimal_places=0,
                                      max_digits=12, required=False)
    mode = forms.ModelChoiceField(queryset=ModePaiement.objects.none(), label="Mode de paiement", required=False)
    reference = forms.CharField(label="Référence (n° Mobile Money, virement…)", required=False, max_length=80)
    coach = forms.ModelChoiceField(queryset=Coach.objects.none(), label="Coach responsable", required=False)
    observations = forms.CharField(label="Observations", required=False, max_length=255)

    def __init__(self, *a, formule_requise=True, **k):
        super().__init__(*a, **k)
        self.fields["formule"].queryset = Formule.objects.filter(actif=True).order_by("type", "prix")
        self.fields["formule"].required = formule_requise
        self.fields["mode"].queryset = ModePaiement.objects.filter(actif=True)
        self.fields["mode"].initial = ModePaiement.objects.filter(actif=True).first()
        self.fields["coach"].queryset = Coach.objects.filter(statut=Coach.Statut.ACTIF)
        self.fields["formule"].widget.attrs["data-formule-select"] = "1"
        self.fields["montant_paye"].widget.attrs["data-montant"] = "1"

    def clean(self):
        cd = super().clean()
        if cd.get("formule") and (cd.get("montant_paye") or 0) > 0 and not cd.get("mode"):
            self.add_error("mode", "Choisissez le mode de paiement.")
        return cd


class FormuleForm(StyledModelForm):
    class Meta:
        model = Formule
        fields = ["nom", "type", "description", "prix", "duree_mois", "seances_par_semaine", "report_seances",
                  "duree_minutes", "tolerance_minutes", "tranche_depassement_minutes", "tarif_depassement", "actif"]

    def clean(self):
        cd = super().clean()
        t = cd.get("type")
        if t == Formule.Type.HORAIRE and not cd.get("duree_minutes"):
            self.add_error("duree_minutes", "Indiquez la durée autorisée pour une formule horaire.")
        if t == Formule.Type.MENSUEL and not cd.get("duree_mois"):
            self.add_error("duree_mois", "Indiquez la durée en mois.")
        return cd


class EncaissementForm(StyledForm):
    montant = forms.DecimalField(label="Montant encaissé", min_value=1, decimal_places=0, max_digits=12)
    mode = forms.ModelChoiceField(queryset=ModePaiement.objects.none(), label="Mode de paiement", empty_label=None)
    reference = forms.CharField(label="Référence", required=False, max_length=80)

    def __init__(self, *a, **k):
        super().__init__(*a, **k)
        self.fields["mode"].queryset = ModePaiement.objects.filter(actif=True)


class ResponsableMixin(StyledForm):
    """Identifiants d'un responsable, exigés si l'utilisateur connecté n'est pas administrateur."""
    resp_identifiant = forms.CharField(label="Identifiant du responsable", required=False)
    resp_mot_de_passe = forms.CharField(label="Mot de passe du responsable", required=False,
                                        widget=forms.PasswordInput(attrs={"autocomplete": "off"}))

    def __init__(self, *a, user=None, **k):
        super().__init__(*a, **k)
        self.user = user
        if user is not None and user.est_admin:
            del self.fields["resp_identifiant"]
            del self.fields["resp_mot_de_passe"]

    def responsable(self):
        from .services import verifier_responsable
        if self.user is not None and self.user.est_admin:
            return self.user
        return verifier_responsable(self.cleaned_data.get("resp_identifiant"),
                                    self.cleaned_data.get("resp_mot_de_passe"))


class AnnulationForm(ResponsableMixin):
    motif = forms.CharField(label="Motif (obligatoire)", max_length=255)
    field_order = ["motif", "resp_identifiant", "resp_mot_de_passe"]


class AutorisationForm(ResponsableMixin):
    motif = forms.ChoiceField(label="Motif", choices=AutorisationExceptionnelle.Motif.choices)
    justification = forms.CharField(label="Justification (obligatoire)", widget=forms.Textarea(attrs={"rows": 2}))
    field_order = ["motif", "justification", "resp_identifiant", "resp_mot_de_passe"]


class RemboursementForm(ResponsableMixin):
    montant = forms.DecimalField(label="Montant remboursé", min_value=1, decimal_places=0, max_digits=12)
    mode = forms.ModelChoiceField(queryset=ModePaiement.objects.none(), label="Mode de remboursement", empty_label=None)
    motif = forms.CharField(label="Motif (obligatoire)", max_length=255)
    annuler_abonnement = forms.BooleanField(label="Annuler l'abonnement correspondant", required=False)
    field_order = ["montant", "mode", "motif", "annuler_abonnement", "resp_identifiant", "resp_mot_de_passe"]

    def __init__(self, *a, **k):
        super().__init__(*a, **k)
        self.fields["mode"].queryset = ModePaiement.objects.filter(actif=True)


class CoachForm(StyledModelForm):
    class Meta:
        model = Coach
        fields = ["nom", "prenom", "telephone", "fonction", "date_enregistrement", "statut", "utilisateur"]
        widgets = {"date_enregistrement": DATE}

    def __init__(self, *a, **k):
        super().__init__(*a, **k)
        self.fields["utilisateur"].queryset = Utilisateur.objects.filter(role=Utilisateur.Role.COACH)
        self.fields["utilisateur"].help_text = "Compte (rôle Coach) qui permettra à ce coach de se connecter."


class ObservationForm(StyledModelForm):
    class Meta:
        model = Observation
        fields = ["type", "texte"]
        widgets = {"texte": forms.Textarea(attrs={"rows": 3})}


class ReservationForm(StyledModelForm):
    class Meta:
        model = Reservation
        fields = ["date", "heure", "coach", "note"]
        widgets = {"date": DATE, "heure": TIME}

    def __init__(self, *a, **k):
        super().__init__(*a, **k)
        self.fields["coach"].queryset = Coach.objects.filter(statut=Coach.Statut.ACTIF)
        self.fields["date"].initial = timezone.localdate()


class UtilisateurForm(StyledModelForm):
    mot_de_passe = forms.CharField(label="Mot de passe", widget=forms.PasswordInput, required=False)
    confirmation = forms.CharField(label="Confirmation du mot de passe", widget=forms.PasswordInput, required=False)

    class Meta:
        model = Utilisateur
        fields = ["username", "first_name", "last_name", "role", "telephone", "email", "is_active"]
        labels = {"username": "Identifiant de connexion", "first_name": "Prénom", "last_name": "Nom",
                  "is_active": "Compte actif"}

    def __init__(self, *a, creation=False, **k):
        super().__init__(*a, **k)
        self.creation = creation
        self.fields["username"].help_text = ""
        self.fields["first_name"].required = True
        self.fields["last_name"].required = True
        if creation:
            self.fields["mot_de_passe"].required = True
            self.fields["confirmation"].required = True
        else:
            self.fields["mot_de_passe"].help_text = "Laisser vide pour ne pas changer."

    def clean(self):
        cd = super().clean()
        mdp, conf = cd.get("mot_de_passe"), cd.get("confirmation")
        if mdp or conf:
            if mdp != conf:
                self.add_error("confirmation", "Les deux mots de passe ne correspondent pas.")
            else:
                try:
                    validate_password(mdp, self.instance)
                except forms.ValidationError as e:
                    self.add_error("mot_de_passe", e)
        return cd

    def save(self, commit=True):
        u = super().save(commit=False)
        if self.cleaned_data.get("mot_de_passe"):
            u.set_password(self.cleaned_data["mot_de_passe"])
        if commit:
            u.save()
        return u


class PremierAdminForm(UtilisateurForm):
    class Meta(UtilisateurForm.Meta):
        fields = ["username", "first_name", "last_name", "telephone", "email"]

    def __init__(self, *a, **k):
        super().__init__(*a, creation=True, **k)


class MotDePasseForm(StyledForm):
    ancien = forms.CharField(label="Mot de passe actuel", widget=forms.PasswordInput)
    nouveau = forms.CharField(label="Nouveau mot de passe", widget=forms.PasswordInput)
    confirmation = forms.CharField(label="Confirmation", widget=forms.PasswordInput)

    def __init__(self, *a, user=None, **k):
        super().__init__(*a, **k)
        self.user = user

    def clean(self):
        cd = super().clean()
        if not self.user.check_password(cd.get("ancien") or ""):
            self.add_error("ancien", "Mot de passe actuel incorrect.")
        if cd.get("nouveau") != cd.get("confirmation"):
            self.add_error("confirmation", "Les mots de passe ne correspondent pas.")
        elif cd.get("nouveau"):
            try:
                validate_password(cd["nouveau"], self.user)
            except forms.ValidationError as e:
                self.add_error("nouveau", e)
        return cd


class ParametresForm(StyledModelForm):
    class Meta:
        model = Parametres
        exclude = ["derniere_sauvegarde"]
        widgets = {"smtp_mot_de_passe": forms.PasswordInput(render_value=True)}


class ModePaiementForm(StyledModelForm):
    class Meta:
        model = ModePaiement
        fields = ["nom", "ordre", "actif"]


class FiltreRapportForm(StyledForm):
    debut = forms.DateField(label="Du", widget=DATE, required=False)
    fin = forms.DateField(label="Au", widget=DATE, required=False)
    client = forms.CharField(label="Client (nom, téléphone ou identifiant)", required=False)
    receptionniste = forms.ModelChoiceField(queryset=Utilisateur.objects.none(), required=False,
                                            label="Réceptionniste")
    coach = forms.ModelChoiceField(queryset=Coach.objects.all(), required=False, label="Coach")
    formule = forms.ModelChoiceField(queryset=Formule.objects.all(), required=False, label="Formule")

    def __init__(self, *a, **k):
        super().__init__(*a, **k)
        self.fields["receptionniste"].queryset = Utilisateur.objects.exclude(role=Utilisateur.Role.COACH)
