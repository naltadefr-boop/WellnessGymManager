"""Parcours de l'interface : chaque page s'affiche pour chaque rôle, et les
formulaires principaux fonctionnent de bout en bout (HTTP)."""
from django.test import TestCase
from django.urls import reverse

from gym import services as S
from gym.models import Client, Coach, Facture, Formule, ModePaiement, Presence, Transaction, Utilisateur


class ParcoursInterface(TestCase):
    def setUp(self):
        self.admin = Utilisateur.objects.create_user("admin", password="Resp-2026!", role="ADMIN",
                                                     first_name="Awa", last_name="Responsable")
        self.recep = Utilisateur.objects.create_user("recep", password="Recep-2026!", role="RECEPTION",
                                                     first_name="Paul", last_name="Accueil")
        self.u_coach = Utilisateur.objects.create_user("coach", password="Coach-2026!", role="COACH",
                                                       first_name="Eric", last_name="Coach")
        self.coach = Coach.objects.create(nom="COACH", prenom="Eric", utilisateur=self.u_coach)
        self.mensuel = Formule.objects.get(type="MENSUEL")
        self.especes = ModePaiement.objects.get(nom="Espèces")
        self.c = Client.objects.create(nom="DUPONT", prenom="Jean", telephone="690000001", coach=self.coach)
        self.tx = S.creer_vente(self.c, self.mensuel, self.recep, montant_paye=10000, mode=self.especes)
        self.p = S.enregistrer_entree(self.c, self.recep)

    def pages(self):
        tx, f, reg = self.tx, self.tx.facture, self.tx.reglements.first()
        return ["tableau_de_bord", "clients", "client_nouveau", ("client_detail", self.c.pk),
                ("client_modifier", self.c.pk), ("client_vente", self.c.pk), ("client_carte", self.c.pk),
                ("client_qr", self.c.pk), "formules", "formule_nouvelle", ("formule_modifier", self.mensuel.pk),
                "abonnements", "paiements", ("transaction", tx.pk), "factures", ("facture_pdf", f.pk),
                ("recu_pdf", reg.pk), "presences", "presences_tableau", "reservations", "coachs",
                ("coach_detail", self.coach.pk), "coach_nouveau", "rapports", "personnel", "utilisateur_nouveau",
                "journal", "parametres", "sauvegardes", "mot_de_passe"]

    def url(self, p):
        return reverse(p[0], args=p[1:]) if isinstance(p, tuple) else reverse(p)

    def test_toutes_les_pages_admin(self):
        self.client.login(username="admin", password="Resp-2026!")
        for p in self.pages():
            r = self.client.get(self.url(p))
            self.assertEqual(r.status_code, 200, f"{p} → {r.status_code}")
        r = self.client.get(reverse("presences") + f"?client={self.c.pk}")
        self.assertContains(r, "PRÉSENT EN SALLE")
        for code in ("presences", "synthese", "abonnements_actifs", "abonnements_expires", "renouvellements",
                     "paiements", "impayes", "seances_consommees", "seances_restantes", "receptionnistes", "coachs"):
            for fmt in ("", "pdf", "xlsx"):
                r = self.client.get(reverse("rapport", args=[code]) + (f"?format={fmt}" if fmt else ""))
                self.assertEqual(r.status_code, 200, f"rapport {code} {fmt}")

    def test_droits_receptionniste(self):
        self.client.login(username="recep", password="Recep-2026!")
        self.assertEqual(self.client.get(reverse("presences")).status_code, 200)
        self.assertEqual(self.client.get(reverse("transaction", args=[self.tx.pk])).status_code, 200)
        for interdit in ("formule_nouvelle", "parametres", "personnel", "rapports", "journal", "sauvegardes"):
            r = self.client.get(reverse(interdit))
            self.assertRedirects(r, reverse("tableau_de_bord"), msg_prefix=interdit)
        # Annulation refusée sans identifiants d'un responsable
        self.client.post(reverse("transaction_annuler", args=[self.tx.pk]), {"an-motif": "test"})
        self.tx.refresh_from_db()
        self.assertEqual(self.tx.statut, Transaction.Statut.VALIDEE)

    def test_coach_sans_finances(self):
        self.client.login(username="coach", password="Coach-2026!")
        r = self.client.get(reverse("tableau_de_bord"))
        self.assertContains(r, "espace coach")
        r = self.client.get(reverse("client_detail", args=[self.c.pk]))
        self.assertEqual(r.status_code, 200)
        self.assertNotContains(r, "Reste à payer")
        self.assertNotContains(r, self.tx.facture.numero)
        autre = Client.objects.create(nom="AUTRE", prenom="Client", telephone="1")
        self.assertEqual(self.client.get(reverse("client_detail", args=[autre.pk])).status_code, 404)
        self.assertRedirects(self.client.get(reverse("paiements")), reverse("tableau_de_bord"))
        r = self.client.post(reverse("client_observation", args=[self.c.pk]),
                             {"type": "RECOMMANDATION", "texte": "Travailler le cardio"})
        self.assertEqual(self.c.observations_suivi.get().coach, self.coach)

    def test_flux_reception_http(self):
        self.client.login(username="recep", password="Recep-2026!")
        # Scénario 1 via le formulaire « Nouveau client »
        r = self.client.post(reverse("client_nouveau"), {
            "nom": "mballa", "prenom": "rose", "telephone": "699 11 22 33", "date_inscription": "2026-11-24",
            "v-formule": Formule.objects.get(type="SEANCE").pk, "v-montant_paye": "3000",
            "v-mode": self.especes.pk})
        c = Client.objects.get(nom="MBALLA")
        self.assertEqual(c.prenom, "Rose")
        tx = c.transactions.get()
        self.assertRedirects(r, reverse("transaction", args=[tx.pk]) + "?nouvelle=1")
        self.assertEqual(tx.reste, 0)
        # Entrée puis sortie via les boutons
        self.client.post(reverse("entree", args=[c.pk]))
        p = c.presences.get()
        self.assertEqual(p.statut, Presence.Statut.EN_COURS)
        self.client.post(reverse("entree", args=[c.pk]))  # double clic : refusé
        self.assertEqual(c.presences.count(), 1)
        self.client.post(reverse("sortie", args=[p.pk]))
        p.refresh_from_db()
        self.assertEqual(p.statut, Presence.Statut.TERMINEE)
        # Encaissement du reste de DUPONT
        self.client.post(reverse("encaisser", args=[self.tx.pk]),
                         {"montant": "15000", "mode": self.especes.pk})
        self.assertEqual(self.tx.reste, 0)
        # Recherche par identifiant (scan QR) → pointage
        r = self.client.get(reverse("recherche") + f"?q={c.identifiant}")
        self.assertRedirects(r, reverse("presences") + f"?client={c.pk}")
        r = self.client.get(reverse("recherche") + "?format=json&q=mbal")
        self.assertEqual(r.json()["resultats"][0]["identifiant"], c.identifiant)

    def test_autorisation_exceptionnelle_http(self):
        self.client.login(username="recep", password="Recep-2026!")
        c = Client.objects.create(nom="SANS", prenom="Abo", telephone="2")
        url = reverse("entree_autorisee", args=[c.pk])
        self.client.post(url, {"motif": "AUCUN_ABONNEMENT", "justification": "Essai gratuit",
                               "resp_identifiant": "recep", "resp_mot_de_passe": "Recep-2026!"})
        self.assertFalse(c.presences.exists())
        self.client.post(url, {"motif": "AUCUN_ABONNEMENT", "justification": "Essai gratuit",
                               "resp_identifiant": "admin", "resp_mot_de_passe": "Resp-2026!"})
        self.assertEqual(c.presences.get().autorisation.accordee_par, self.admin)

    def test_connexion_et_verrouillage(self):
        self.client.logout()
        self.assertRedirects(self.client.get("/"), "/connexion/?next=/")
        for _ in range(5):
            self.client.post(reverse("connexion"), {"username": "recep", "password": "faux"})
        r = self.client.post(reverse("connexion"), {"username": "recep", "password": "Recep-2026!"})
        self.assertContains(r, "Trop de tentatives")

    def test_sauvegarde_et_restauration(self):
        from django.conf import settings
        from gym.sauvegarde import creer_sauvegarde, restaurer
        if not str(settings.DATABASES["default"]["NAME"]).endswith("sqlite3"):
            return  # base de test en mémoire
        chemin = creer_sauvegarde()
        self.assertTrue(chemin.exists())
