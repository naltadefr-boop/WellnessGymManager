"""
Scénarios obligatoires du cahier des charges (section 19) + règles de calcul.
Lancer :  python manage.py test gym
"""
from datetime import date, datetime, timedelta
from decimal import Decimal
from unittest import mock
from zoneinfo import ZoneInfo

from django.test import TestCase
from django.utils import timezone

from gym import services as S
from gym.models import (
    Abonnement, Client, Facture, Formule, ModePaiement, Parametres, Presence, Reglement,
    Transaction, Utilisateur,
)

TZ = ZoneInfo("Africa/Douala")


class Horloge:
    """Fixe l'heure « actuelle » du logiciel pendant un test."""

    def __init__(self, testcase, dt):
        self.dt = dt.replace(tzinfo=TZ) if dt.tzinfo is None else dt
        p = mock.patch("django.utils.timezone.now", side_effect=lambda: self.dt)
        p.start()
        testcase.addCleanup(p.stop)

    def regler(self, dt):
        self.dt = dt.replace(tzinfo=TZ)

    def avancer(self, **kw):
        self.dt = self.dt + timedelta(**kw)


class Base(TestCase):
    def setUp(self):
        self.admin = Utilisateur.objects.create_user("admin", password="Resp-2026!", role="ADMIN",
                                                     first_name="Awa", last_name="Responsable")
        self.recep = Utilisateur.objects.create_user("recep", password="Recep-2026!", role="RECEPTION",
                                                     first_name="Paul", last_name="Accueil")
        self.especes = ModePaiement.objects.get(nom="Espèces")
        self.om = ModePaiement.objects.get(nom="Orange Money")
        self.mensuel = Formule.objects.get(type="MENSUEL")
        self.seance = Formule.objects.get(type="SEANCE")
        self.deux_heures = Formule.objects.get(nom="Formule 2 heures")
        self.horloge = Horloge(self, datetime(2026, 12, 1, 8, 0))  # mardi 1er décembre 2026

    def nouveau_client(self, nom="DUPONT", prenom="Jean"):
        return Client.objects.create(nom=nom, prenom=prenom, telephone="690000000", cree_par=self.recep)


class Scenario1NouveauClient(Base):
    def test_inscription_paiement_facture(self):
        c = self.nouveau_client()
        self.assertEqual(c.identifiant, f"WG{c.pk:05d}")
        tx = S.creer_vente(c, self.mensuel, self.recep, montant_paye=25000, mode=self.om, reference="OM123")
        self.assertEqual(tx.type, Transaction.Type.ABONNEMENT)
        self.assertEqual(tx.montant_du, Decimal(25000))
        self.assertEqual(tx.montant_paye, Decimal(25000))
        self.assertEqual(tx.reste, 0)
        self.assertTrue(Facture.objects.filter(transaction=tx).exists())
        self.assertTrue(tx.facture.numero.startswith("FAC-2026-"))
        self.assertEqual(tx.reglements.get().numero, "REC-2026-00001")
        abo = tx.abonnement
        self.assertEqual((abo.date_debut, abo.date_fin), (date(2026, 12, 1), date(2026, 12, 31)))
        # 31 jours : 4 semaines complètes (16) + 3 jours au prorata supérieur (2) = 18
        self.assertEqual(abo.seances_total, 18)
        # Facture PDF réellement générée
        from gym.pdf import facture_pdf
        pdf = facture_pdf(tx.facture)
        self.assertTrue(pdf.startswith(b"%PDF"))
        self.assertGreater(len(pdf), 2000)

    def test_paiement_partiel_signale(self):
        c = self.nouveau_client()
        tx = S.creer_vente(c, self.mensuel, self.recep, montant_paye=10000, mode=self.especes)
        self.assertEqual(tx.reste, Decimal(15000))
        self.assertIn(tx, S.transactions_impayees())
        res = S.verifier_acces(c)
        self.assertTrue(res.autorise)
        self.assertTrue(any("Paiement en attente" in a for a in res.avertissements))
        S.encaisser(tx, 15000, self.especes, self.recep)
        self.assertEqual(tx.reste, 0)
        with self.assertRaises(S.ErreurMetier):
            S.encaisser(tx, 1, self.especes, self.recep)


class Scenario2ClientAbonne(Base):
    def test_entree_sortie_actualise_solde(self):
        c = self.nouveau_client()
        S.creer_vente(c, self.mensuel, self.recep, montant_paye=25000, mode=self.especes)
        res = S.verifier_acces(c)
        self.assertTrue(res.autorise)
        self.assertEqual(res.droits["courante"]["restantes"], 4)
        p = S.enregistrer_entree(c, self.recep)
        self.assertEqual(p.statut, Presence.Statut.EN_COURS)
        self.assertEqual(p.entree_par, self.recep)
        self.assertEqual(p.seances_restantes_semaine, 3)
        # Double pointage impossible
        with self.assertRaises(S.ErreurMetier):
            S.enregistrer_entree(c, self.recep)
        self.horloge.avancer(hours=1, minutes=15)
        p, supplement = S.enregistrer_sortie(p, self.recep)
        self.assertIsNone(supplement)
        self.assertEqual(p.duree_minutes, 75)
        self.assertEqual(p.statut, Presence.Statut.TERMINEE)
        d = S.etat_droits(p.abonnement)
        self.assertEqual((d["courante"]["utilisees"], d["courante"]["restantes"]), (1, 3))
        self.assertEqual(d["total_restantes"], 17)
        with self.assertRaises(S.ErreurMetier):
            S.enregistrer_sortie(p, self.recep)


class Scenario3QuotaEpuise(Base):
    def test_cinquieme_seance_bloquee_sauf_autorisation(self):
        c = self.nouveau_client()
        S.creer_vente(c, self.mensuel, self.recep, montant_paye=25000, mode=self.especes)
        for jour in range(1, 5):  # 1er au 4 décembre
            self.horloge.regler(datetime(2026, 12, jour, 9, 0))
            p = S.enregistrer_entree(c, self.recep)
            self.horloge.avancer(hours=1)
            S.enregistrer_sortie(p, self.recep)
        self.horloge.regler(datetime(2026, 12, 5, 9, 0))  # même semaine (1er–7)
        res = S.verifier_acces(c)
        self.assertFalse(res.autorise)
        self.assertEqual(res.code, "QUOTA_EPUISE")
        self.assertTrue(res.peut_deroger)
        with self.assertRaises(S.ErreurMetier):
            S.enregistrer_entree(c, self.recep)
        # Autorisation : un réceptionniste ne peut pas s'auto-autoriser
        with self.assertRaises(S.ErreurMetier):
            S.verifier_responsable("recep", "Recep-2026!")
        resp = S.verifier_responsable("admin", "Resp-2026!")
        auto = S.accorder_autorisation(c, "QUOTA_EPUISE", "Séance de rattrapage validée par la direction",
                                       resp, self.recep)
        p = S.enregistrer_entree(c, self.recep, autorisation=auto)
        self.assertEqual(p.autorisation, auto)
        # Semaine suivante : quota de nouveau disponible
        S.enregistrer_sortie(p, self.recep)
        self.horloge.regler(datetime(2026, 12, 8, 9, 0))
        self.assertTrue(S.verifier_acces(c).autorise)


class Scenario4AbonnementExpire(Base):
    def test_expiration_signalee_et_renouvellement_propose(self):
        c = self.nouveau_client()
        self.horloge.regler(datetime(2026, 10, 1, 9, 0))
        S.creer_vente(c, self.mensuel, self.recep, montant_paye=25000, mode=self.especes)
        self.horloge.regler(datetime(2026, 11, 24, 9, 0))
        res = S.verifier_acces(c)
        self.assertFalse(res.autorise)
        self.assertEqual(res.code, "ABONNEMENT_EXPIRE")
        self.assertTrue(res.proposer_renouvellement)
        self.assertIn("31/10/2026", res.message)
        alertes = S.alertes()
        self.assertEqual([a.client for a in alertes["expires"]], [c])


class Scenario5ClientJournalier(Base):
    def test_seance_unique(self):
        c = self.nouveau_client("MBALLA", "Rose")
        tx = S.creer_vente(c, self.seance, self.recep, montant_paye=3000, mode=self.especes)
        self.assertEqual(tx.type, Transaction.Type.SEANCE)
        self.assertTrue(tx.facture)
        p = S.enregistrer_entree(c, self.recep)
        self.horloge.avancer(minutes=50)
        p, _ = S.enregistrer_sortie(p, self.recep)
        self.assertEqual(p.duree_minutes, 50)
        self.assertEqual(tx.abonnement.etat, "CONSOMME")
        res = S.verifier_acces(c)
        self.assertFalse(res.autorise)
        self.assertEqual(res.code, "SEANCE_CONSOMMEE")
        # Nouveau paiement => nouvelle séance
        S.creer_vente(c, self.seance, self.recep, montant_paye=3000, mode=self.especes)
        self.assertTrue(S.verifier_acces(c).autorise)


class Scenario6DepassementHoraire(Base):
    def test_deux_heures_trente_pour_deux_heures(self):
        c = self.nouveau_client("NGONO", "Eric")
        S.creer_vente(c, self.deux_heures, self.recep, montant_paye=2500, mode=self.especes)
        p = S.enregistrer_entree(c, self.recep)
        self.horloge.avancer(hours=2, minutes=10)
        self.assertEqual(Presence.objects.get(pk=p.pk).depassement_en_cours(), 10)  # alerte en direct
        self.horloge.avancer(minutes=20)
        p, tx = S.enregistrer_sortie(p, self.recep)
        self.assertEqual(p.duree_minutes, 150)
        self.assertEqual(p.depassement_minutes, 30)
        # Tarif : 500 par tranche de 30 min entamée, tolérance 5 min => 1 tranche
        self.assertEqual(p.supplement, Decimal(500))
        self.assertEqual(tx.type, Transaction.Type.SUPPLEMENT)
        self.assertEqual(tx.reste, Decimal(500))
        self.assertIn(tx, S.transactions_impayees())
        S.encaisser(tx, 500, self.especes, self.recep)  # régularisation
        self.assertEqual(tx.reste, 0)

    def test_tolerance_sans_supplement(self):
        c = self.nouveau_client("NGONO", "Eric")
        S.creer_vente(c, self.deux_heures, self.recep, montant_paye=2500, mode=self.especes)
        p = S.enregistrer_entree(c, self.recep)
        self.horloge.avancer(hours=2, minutes=4)
        p, tx = S.enregistrer_sortie(p, self.recep)
        self.assertEqual(p.depassement_minutes, 4)
        self.assertIsNone(tx)


class Scenario7Renouvellement(Base):
    def test_renouvellement_conserve_historique(self):
        c = self.nouveau_client()
        self.horloge.regler(datetime(2026, 10, 1, 9, 0))
        ancien = S.creer_vente(c, self.mensuel, self.recep, montant_paye=25000, mode=self.especes).abonnement
        p = S.enregistrer_entree(c, self.recep)
        self.horloge.avancer(hours=1)
        S.enregistrer_sortie(p, self.recep)
        self.horloge.regler(datetime(2026, 11, 24, 9, 0))
        self.assertEqual(S.verifier_acces(c).code, "ABONNEMENT_EXPIRE")
        tx = S.creer_vente(c, self.mensuel, self.recep, montant_paye=25000, mode=self.om)
        self.assertEqual(tx.type, Transaction.Type.RENOUVELLEMENT)
        nouveau = tx.abonnement
        self.assertTrue(nouveau.est_renouvellement)
        self.assertEqual(nouveau.precedent, ancien)
        self.assertEqual(nouveau.date_debut, date(2026, 11, 24))
        self.assertEqual(c.abonnements.count(), 2)
        self.assertEqual(c.presences.count(), 1)  # historique conservé
        self.assertTrue(S.verifier_acces(c).autorise)

    def test_renouvellement_anticipe_sans_perte_de_jours(self):
        c = self.nouveau_client()
        S.creer_vente(c, self.mensuel, self.recep, montant_paye=25000, mode=self.especes)
        self.horloge.regler(datetime(2026, 12, 28, 9, 0))
        tx = S.creer_vente(c, self.mensuel, self.recep, montant_paye=25000, mode=self.especes)
        self.assertEqual(tx.abonnement.date_debut, date(2027, 1, 1))
        self.assertEqual(tx.abonnement.date_fin, date(2027, 1, 31))


class CalculDesDroits(Base):
    def abo(self, debut):
        c = self.nouveau_client()
        self.horloge.regler(datetime.combine(debut, datetime.min.time()).replace(hour=9))
        return S.creer_vente(c, self.mensuel, self.recep, date_debut=debut).abonnement

    def test_fevrier_et_mois_longs(self):
        self.assertEqual(self.abo(date(2027, 2, 1)).seances_total, 16)   # 28 jours
        self.assertEqual(self.abo(date(2026, 12, 1)).seances_total, 18)  # 31 jours
        self.assertEqual(self.abo(date(2026, 11, 1)).seances_total, 18)  # 30 jours : +2 j → 2

    def test_modes_semaine_partielle(self):
        p = Parametres.get()
        p.mode_semaine_partielle = Parametres.SemainePartielle.PRORATA_INF
        p.save()
        self.assertEqual(self.abo(date(2026, 12, 1)).seances_total, 17)  # 3 j → floor(12/7)=1
        p.mode_semaine_partielle = Parametres.SemainePartielle.COMPLET
        p.save()
        self.assertEqual(self.abo(date(2026, 12, 1)).seances_total, 20)

    def test_report_des_seances(self):
        self.mensuel.report_seances = True
        self.mensuel.save()
        abo = self.abo(date(2026, 12, 1))
        p = S.enregistrer_entree(abo.client, self.recep)  # 1 séance semaine 1
        self.horloge.avancer(hours=1)
        S.enregistrer_sortie(p, self.recep)
        d = S.etat_droits(abo, date(2026, 12, 9))
        self.assertEqual(d["courante"]["report_entrant"], 3)
        self.assertEqual(d["courante"]["autorisees"], 7)

    def test_seances_perdues_sans_report(self):
        abo = self.abo(date(2026, 12, 1))
        d = S.etat_droits(abo, date(2026, 12, 9))
        self.assertEqual(d["courante"]["autorisees"], 4)
        self.assertEqual(d["total_restantes"], 4 + 4 + 4 + 2)


class Tracabilite(Base):
    def test_annulation_et_remboursement_controles(self):
        c = self.nouveau_client()
        tx = S.creer_vente(c, self.mensuel, self.recep, montant_paye=25000, mode=self.especes)
        with self.assertRaises(PermissionError):
            tx.delete()
        with self.assertRaises(S.ErreurMetier):  # argent encaissé : remboursement d'abord
            S.annuler_transaction(tx, self.admin, "Erreur de saisie")
        with self.assertRaises(S.ErreurMetier):
            S.rembourser(tx, 30000, self.especes, "Trop", self.admin, self.recep)
        S.rembourser(tx, 25000, self.especes, "Départ du client", self.admin, self.recep)
        S.annuler_transaction(tx, self.admin, "Abonnement annulé après remboursement")
        tx.refresh_from_db()
        self.assertEqual(tx.statut, Transaction.Statut.ANNULEE)
        self.assertEqual(tx.abonnement.statut, Abonnement.Statut.ANNULE)
        self.assertEqual(S.total_encaisse(date(2026, 12, 1), date(2026, 12, 1)), 0)
        actions = set(c for c in __import__("gym.models", fromlist=["JournalAudit"]).JournalAudit
                      .objects.values_list("action", flat=True))
        self.assertTrue({"TRANSACTION", "ENCAISSEMENT", "REMBOURSEMENT", "TRANSACTION_ANNULEE"} <= actions)
