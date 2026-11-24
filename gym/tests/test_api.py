"""API de l'application mobile : mêmes règles que le logiciel de réception."""
import json

from django.test import TestCase

from gym import services as S
from gym.models import Client, Coach, Formule, JetonAPI, ModePaiement, Utilisateur


class APIMobile(TestCase):
    def setUp(self):
        self.admin = Utilisateur.objects.create_user("admin", password="Resp-2026!", role="ADMIN")
        Utilisateur.objects.create_user("recep", password="Recep-2026!", role="RECEPTION", first_name="Paul")
        uc = Utilisateur.objects.create_user("coach", password="Coach-2026!", role="COACH")
        self.coach = Coach.objects.create(nom="C", prenom="Eric", utilisateur=uc)
        self.c = Client.objects.create(nom="DUPONT", prenom="Jean", telephone="690", coach=self.coach)
        self.mensuel = Formule.objects.get(type="MENSUEL")
        self.especes = ModePaiement.objects.get(nom="Espèces")

    def connecter(self, u, p):
        r = self.client.post("/api/v1/connexion", json.dumps({"identifiant": u, "mot_de_passe": p}),
                             content_type="application/json")
        self.assertEqual(r.status_code, 200, r.content)
        return {"HTTP_AUTHORIZATION": "Token " + r.json()["jeton"]}

    def post(self, url, h, data=None):
        return self.client.post(url, json.dumps(data or {}), content_type="application/json", **h)

    def test_parcours_reception(self):
        self.assertEqual(self.client.get("/api/v1/moi").status_code, 401)
        self.assertEqual(self.client.get("/api/v1/moi", HTTP_AUTHORIZATION="Token faux").status_code, 401)
        h = self.connecter("recep", "Recep-2026!")
        self.assertFalse(JetonAPI.objects.filter(empreinte=h["HTTP_AUTHORIZATION"][6:]).exists())  # stocké haché
        r = self.client.get(f"/api/v1/scan?code={self.c.identifiant.lower()}", **h)
        self.assertEqual(r.json()["acces"]["code"], "AUCUN_ABONNEMENT")
        self.assertEqual(self.post(f"/api/v1/clients/{self.c.pk}/entree", h).status_code, 409)
        r = self.post(f"/api/v1/clients/{self.c.pk}/vente", h,
                      {"formule": self.mensuel.pk, "montant": "25000", "mode": self.especes.pk})
        self.assertEqual(r.status_code, 201)
        fid = r.json()["transaction"]["facture_id"]
        r = self.client.get(f"/api/v1/factures/{fid}/pdf", **h)
        self.assertTrue(r.content.startswith(b"%PDF"))
        r = self.post(f"/api/v1/clients/{self.c.pk}/entree", h)
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()["presence"]["solde_semaine"], 3)
        self.assertEqual(self.post(f"/api/v1/clients/{self.c.pk}/entree", h).status_code, 409)  # doublon
        pid = r.json()["presence"]["id"]
        self.assertEqual(len(self.client.get("/api/v1/presences", **h).json()["presences"]), 1)
        self.assertEqual(self.post(f"/api/v1/presences/{pid}/sortie", h).json()["presence"]["statut"], "TERMINEE")
        d = self.client.get("/api/v1/tableau", **h).json()
        self.assertEqual(d["encaisse_jour"], 25000)
        r = self.post("/api/v1/clients/creer", h, {"nom": "ngono", "prenom": "eric", "telephone": "690"})
        self.assertEqual(r.status_code, 409)  # même téléphone
        r = self.post("/api/v1/clients/creer", h, {"nom": "ngono", "prenom": "eric", "telephone": "690",
                                                   "confirmer_doublon": True})
        self.assertEqual(r.json()["nom"], "Eric NGONO")
        self.assertEqual(self.post("/api/v1/deconnexion", h).status_code, 200)
        self.assertEqual(self.client.get("/api/v1/moi", **h).status_code, 401)

    def test_exception_et_roles(self):
        h = self.connecter("recep", "Recep-2026!")
        url = f"/api/v1/clients/{self.c.pk}/entree-exceptionnelle"
        r = self.post(url, h, {"motif": "AUCUN_ABONNEMENT", "justification": "Essai",
                               "resp_identifiant": "recep", "resp_mot_de_passe": "Recep-2026!"})
        self.assertEqual(r.status_code, 409)
        r = self.post(url, h, {"motif": "AUCUN_ABONNEMENT", "justification": "Essai",
                               "resp_identifiant": "admin", "resp_mot_de_passe": "Resp-2026!"})
        self.assertEqual(r.status_code, 200)
        hc = self.connecter("coach", "Coach-2026!")
        d = self.client.get(f"/api/v1/clients/{self.c.pk}", **hc).json()
        self.assertNotIn("reste_a_payer", d)
        self.assertNotIn("encaisse_jour", self.client.get("/api/v1/tableau", **hc).json())
        self.assertEqual(self.post(f"/api/v1/presences/{d['presence']['id']}/sortie", hc).status_code, 403)
        autre = Client.objects.create(nom="X", prenom="Y", telephone="1")
        self.assertEqual(self.client.get(f"/api/v1/clients/{autre.pk}", **hc).status_code, 404)
        self.assertEqual(self.post(f"/api/v1/clients/{self.c.pk}/observation", hc,
                                   {"type": "RECOMMANDATION", "texte": "Cardio"}).status_code, 201)

    def test_cors_et_application(self):
        r = self.client.options("/api/v1/connexion")
        self.assertEqual(r["Access-Control-Allow-Origin"], "*")
        self.assertEqual(self.client.get("/m/").status_code, 200)
        self.assertEqual(self.client.get("/m/app.js")["Content-Type"], "application/javascript; charset=utf-8")
        self.assertEqual(self.client.get("/m/../settings.py").status_code, 404)
        self.assertEqual(self.client.get("/manifest.webmanifest").status_code, 200)
