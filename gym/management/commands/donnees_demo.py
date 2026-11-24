"""
Crée un jeu de données de DÉMONSTRATION / FORMATION (comptes, coachs, clients,
abonnements, passages et paiements sur les 5 dernières semaines).

    python manage.py donnees_demo

À utiliser sur une installation de test uniquement : la commande refuse de
s'exécuter si des clients existent déjà (sauf option --forcer).
"""
import random
from datetime import datetime, time, timedelta
from unittest import mock

from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from gym import services as S
from gym.models import Client, Coach, Formule, ModePaiement, Observation, Reservation, Utilisateur

PRENOMS = ["Jean", "Rose", "Eric", "Aïcha", "Paul", "Mireille", "Serge", "Carine", "Hervé", "Nadège", "Boris",
           "Linda", "Patrick", "Sandrine", "Yves", "Brigitte", "Franck", "Estelle"]
NOMS = ["MBALLA", "NGONO", "ESSOMBA", "FOUDA", "ATANGANA", "BIYA", "ONANA", "NKOULOU", "EYENGA", "MANGA",
        "OWONA", "TCHAMI", "KAMGA", "NJOYA", "BELLO", "ABENA", "ZE", "MEKA"]


class Command(BaseCommand):
    help = "Crée des données de démonstration pour la formation du personnel."

    def add_arguments(self, parser):
        parser.add_argument("--forcer", action="store_true")

    def handle(self, *args, **o):
        if Client.objects.exists() and not o["forcer"]:
            raise CommandError("Des clients existent déjà : données de démonstration non créées (--forcer pour passer outre).")
        random.seed(7)
        tz = timezone.get_current_timezone()
        reel = timezone.now()
        horloge = {"t": reel}
        patch = mock.patch("django.utils.timezone.now", side_effect=lambda: horloge["t"])
        patch.start()
        try:
            self._creer(horloge, tz, reel)
        finally:
            patch.stop()
        self.stdout.write(self.style.SUCCESS(
            "Données de démonstration créées. Comptes : admin / Admin-2026!  ·  reception / Accueil-2026!  ·  "
            "coach / Coach-2026!"))

    def _creer(self, horloge, tz, reel):
        def regler(jour, h, m=0):
            horloge["t"] = datetime.combine(jour, time(h, m), tzinfo=tz)

        admin = Utilisateur.objects.filter(role="ADMIN").first() or Utilisateur.objects.create_user(
            "admin", password="Admin-2026!", role="ADMIN", first_name="Awa", last_name="Responsable")
        recep, _ = Utilisateur.objects.get_or_create(username="reception", defaults=dict(
            role="RECEPTION", first_name="Paul", last_name="Ndzana"))
        recep.set_password("Accueil-2026!"); recep.save()
        uc, _ = Utilisateur.objects.get_or_create(username="coach", defaults=dict(
            role="COACH", first_name="Eric", last_name="Tchoua"))
        uc.set_password("Coach-2026!"); uc.save()
        c1, _ = Coach.objects.get_or_create(nom="TCHOUA", prenom="Eric", defaults=dict(
            telephone="677 10 20 30", fonction="Coach musculation", utilisateur=uc))
        c2, _ = Coach.objects.get_or_create(nom="NANA", prenom="Sylvie", defaults=dict(
            telephone="699 40 50 60", fonction="Coach fitness et cardio"))
        mensuel = Formule.objects.filter(type="MENSUEL", actif=True).first()
        seance = Formule.objects.filter(type="SEANCE", actif=True).first()
        horaires = list(Formule.objects.filter(type="HORAIRE", actif=True))
        modes = list(ModePaiement.objects.filter(actif=True)[:4])
        aujourdhui = timezone.localtime(reel).date()
        debut_hist = aujourdhui - timedelta(days=35)

        clients = []
        for i in range(18):
            jour_insc = debut_hist + timedelta(days=random.randint(0, 20))
            regler(jour_insc, 8, 30)
            c = Client.objects.create(
                nom=NOMS[i], prenom=PRENOMS[i], sexe=random.choice(["M", "F"]),
                telephone=f"6{random.randint(50, 99)} {random.randint(10, 99)} {random.randint(10, 99)} {random.randint(10, 99)}",
                date_inscription=jour_insc, coach=random.choice([c1, c2, None]), cree_par=recep)
            clients.append((c, jour_insc))

        for i, (c, jour) in enumerate(clients):
            regler(jour, 8, 45)
            if i < 12:
                paye = mensuel.prix if i % 5 else mensuel.prix // 2  # quelques paiements partiels
                if i in (3, 7):  # abonnements déjà expirés (souscrits il y a plus d'un mois)
                    regler(aujourdhui - timedelta(days=45 + i), 9)
                    S.creer_vente(c, mensuel, recep, montant_paye=mensuel.prix, mode=modes[0])
                    continue
                S.creer_vente(c, mensuel, recep, montant_paye=paye, mode=random.choice(modes))
            # Passages
            d = jour
            while d < aujourdhui:
                if random.random() < (0.55 if i < 12 else 0.12):
                    h = random.choice([6, 7, 8, 12, 17, 18, 19])
                    regler(d, h, random.randint(0, 50))
                    if i >= 12:
                        f = random.choice([seance] + horaires)
                        S.creer_vente(c, f, recep, montant_paye=f.prix, mode=random.choice(modes))
                    if S.verifier_acces(c, d).autorise:
                        p = S.enregistrer_entree(c, recep)
                        horloge["t"] += timedelta(minutes=random.randint(45, 140))
                        p, tx = S.enregistrer_sortie(p, recep)
                        if tx and random.random() < 0.7:
                            S.encaisser(tx, tx.montant_du, modes[0], recep)
                d += timedelta(days=1)

        # Situation du jour : quelques clients présents en ce moment
        maintenant = timezone.localtime(reel)
        for c, _ in clients[:12]:
            if random.random() < 0.35:
                horloge["t"] = reel - timedelta(minutes=random.randint(10, 80))
                if S.verifier_acces(c).autorise:
                    S.enregistrer_entree(c, recep)
        horloge["t"] = reel
        for c, _ in clients[:4]:
            Reservation.objects.create(client=c, date=aujourdhui + timedelta(days=random.randint(0, 5)),
                                       heure=time(random.choice([7, 17, 18])), coach=c.coach, cree_par=recep)
        Observation.objects.create(client=clients[0][0], coach=c1, auteur=uc, type="RECOMMANDATION",
                                   texte="Augmenter progressivement les charges ; travailler le gainage.")
        self.stdout.write(f"{len(clients)} clients créés ({maintenant:%d/%m/%Y %H:%M}).")
