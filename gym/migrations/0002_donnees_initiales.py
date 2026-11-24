"""Données initiales : modes de paiement et formules de départ.
Les prix sont des EXEMPLES à ajuster par le responsable dans « Formules et tarifs »."""
from django.db import migrations

MODES = ["Espèces", "Orange Money", "MTN Mobile Money", "Mobile Money (autre)",
         "Carte bancaire", "Virement bancaire", "Autre"]

FORMULES = [
    dict(nom="Abonnement mensuel — 4 séances/semaine", type="MENSUEL", prix=25000, duree_mois=1,
         seances_par_semaine=4, description="Accès 4 séances par semaine pendant un mois."),
    dict(nom="Séance journalière", type="SEANCE", prix=3000, description="Une séance, valable le jour de l'achat."),
    dict(nom="Formule 1 heure", type="HORAIRE", prix=1500, duree_minutes=60, tarif_depassement=500),
    dict(nom="Formule 1 h 30", type="HORAIRE", prix=2000, duree_minutes=90, tarif_depassement=500),
    dict(nom="Formule 2 heures", type="HORAIRE", prix=2500, duree_minutes=120, tarif_depassement=500),
    dict(nom="Formule 3 heures", type="HORAIRE", prix=3500, duree_minutes=180, tarif_depassement=500),
]


def creer(apps, schema_editor):
    ModePaiement = apps.get_model("gym", "ModePaiement")
    Formule = apps.get_model("gym", "Formule")
    Parametres = apps.get_model("gym", "Parametres")
    for i, nom in enumerate(MODES):
        ModePaiement.objects.get_or_create(nom=nom, defaults={"ordre": i})
    for f in FORMULES:
        Formule.objects.get_or_create(nom=f["nom"], defaults=f)
    Parametres.objects.get_or_create(pk=1)


class Migration(migrations.Migration):
    dependencies = [("gym", "0001_initial")]
    operations = [migrations.RunPython(creer, migrations.RunPython.noop)]
