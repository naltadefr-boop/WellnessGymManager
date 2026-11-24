from django.urls import path

from . import api
from .views import mobile
from .views import auth, clients, coachs, dashboard, finances, formules, parametres, personnel, presences, rapports

urlpatterns = [
    # Connexion
    path("connexion/", auth.connexion, name="connexion"),
    path("deconnexion/", auth.deconnexion, name="deconnexion"),
    path("installation/", auth.premier_demarrage, name="premier_demarrage"),
    path("mon-mot-de-passe/", auth.mot_de_passe, name="mot_de_passe"),
    # Tableau de bord / recherche
    path("", dashboard.tableau_de_bord, name="tableau_de_bord"),
    path("recherche/", dashboard.recherche, name="recherche"),
    # Clients
    path("clients/", clients.liste, name="clients"),
    path("clients/nouveau/", clients.nouveau, name="client_nouveau"),
    path("clients/<int:pk>/", clients.detail, name="client_detail"),
    path("clients/<int:pk>/modifier/", clients.modifier, name="client_modifier"),
    path("clients/<int:pk>/vente/", clients.vente, name="client_vente"),
    path("clients/<int:pk>/carte/", clients.carte, name="client_carte"),
    path("clients/<int:pk>/qr.png", clients.qr, name="client_qr"),
    path("clients/<int:pk>/observation/", clients.observation, name="client_observation"),
    path("clients/<int:pk>/reservation/", clients.reservation, name="client_reservation"),
    path("clients/<int:pk>/archiver/", clients.basculer_actif, name="client_basculer"),
    # Formules et abonnements
    path("formules/", formules.liste, name="formules"),
    path("formules/nouvelle/", formules.edition, name="formule_nouvelle"),
    path("formules/<int:pk>/", formules.edition, name="formule_modifier"),
    path("formules/<int:pk>/basculer/", formules.basculer, name="formule_basculer"),
    path("abonnements/", formules.abonnements, name="abonnements"),
    # Paiements et factures
    path("paiements/", finances.paiements, name="paiements"),
    path("transactions/<int:pk>/", finances.transaction, name="transaction"),
    path("transactions/<int:pk>/encaisser/", finances.encaisser, name="encaisser"),
    path("transactions/<int:pk>/annuler/", finances.annuler, name="transaction_annuler"),
    path("transactions/<int:pk>/rembourser/", finances.rembourser, name="rembourser"),
    path("reglements/<int:pk>/annuler/", finances.annuler_reglement, name="reglement_annuler"),
    path("factures/", finances.factures, name="factures"),
    path("factures/<int:pk>/pdf/", finances.facture_fichier, name="facture_pdf"),
    path("factures/<int:pk>/email/", finances.facture_email, name="facture_email"),
    path("recus/<int:pk>/pdf/", finances.recu_fichier, name="recu_pdf"),
    # Présences
    path("presences/", presences.index, name="presences"),
    path("presences/tableau/", presences.tableau, name="presences_tableau"),
    path("presences/entree/<int:pk>/", presences.entree, name="entree"),
    path("presences/entree-exceptionnelle/<int:pk>/", presences.entree_autorisee, name="entree_autorisee"),
    path("presences/sortie/<int:pk>/", presences.sortie, name="sortie"),
    path("presences/<int:pk>/annuler/", presences.annuler, name="presence_annuler"),
    path("reservations/", presences.reservations, name="reservations"),
    path("reservations/<int:pk>/<str:statut>/", presences.reservation_statut, name="reservation_statut"),
    # Coachs
    path("coachs/", coachs.liste, name="coachs"),
    path("coachs/nouveau/", coachs.edition, name="coach_nouveau"),
    path("coachs/<int:pk>/", coachs.detail, name="coach_detail"),
    path("coachs/<int:pk>/modifier/", coachs.edition, name="coach_modifier"),
    path("mon-espace/", coachs.mon_espace, name="mon_espace"),
    # Rapports
    path("rapports/", rapports.index, name="rapports"),
    path("rapports/<str:code>/", rapports.rapport, name="rapport"),
    # Personnel
    path("personnel/", personnel.liste, name="personnel"),
    path("personnel/nouveau/", personnel.edition, name="utilisateur_nouveau"),
    path("personnel/<int:pk>/", personnel.edition, name="utilisateur_modifier"),
    path("journal/", personnel.journal, name="journal"),
    # Paramètres
    path("parametres/", parametres.parametres, name="parametres"),
    path("parametres/modes/ajouter/", parametres.mode_ajouter, name="mode_ajouter"),
    path("parametres/modes/<int:pk>/basculer/", parametres.mode_basculer, name="mode_basculer"),
    path("sauvegardes/", parametres.sauvegardes, name="sauvegardes"),
    path("sauvegardes/<str:nom>/", parametres.sauvegarde_telecharger, name="sauvegarde_telecharger"),
    # Application mobile (PWA Android / iPhone)
    path("manifest.webmanifest", mobile.manifeste_bureau, name="manifeste"),
    path("m/", mobile.fichier, name="mobile"),
    path("m/<str:nom>", mobile.fichier, name="mobile_fichier"),
    # API v1 (application mobile)
    path("api/v1/connexion", api.connexion),
    path("api/v1/deconnexion", api.deconnexion),
    path("api/v1/moi", api.moi),
    path("api/v1/tableau", api.tableau),
    path("api/v1/clients", api.clients),
    path("api/v1/clients/creer", api.client_creer),
    path("api/v1/clients/<int:pk>", api.client),
    path("api/v1/clients/<int:pk>/entree", api.entree),
    path("api/v1/clients/<int:pk>/entree-exceptionnelle", api.entree_exceptionnelle),
    path("api/v1/clients/<int:pk>/vente", api.vente),
    path("api/v1/clients/<int:pk>/observation", api.observation),
    path("api/v1/scan", api.scan),
    path("api/v1/presences", api.presences),
    path("api/v1/presences/<int:pk>/sortie", api.sortie),
    path("api/v1/catalogue", api.catalogue),
    path("api/v1/transactions/<int:pk>", api.transaction),
    path("api/v1/transactions/<int:pk>/encaisser", api.encaisser),
    path("api/v1/factures/<int:pk>/pdf", api.facture_pdf),
]
