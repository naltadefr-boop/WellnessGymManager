# Wellness Gym Manager — Architecture technique

## 1. Choix technologiques

| Besoin | Choix | Raison |
|---|---|---|
| Langage | **Python 3.11+** | Fiable, lisible, facile à maintenir. |
| Cadre applicatif | **Django 5.1** | Comptes, mots de passe chiffrés, protection CSRF, ORM, migrations automatiques de la base, traductions françaises intégrées. |
| Base de données | **SQLite** (local) → **PostgreSQL** (centralisé) | SQLite ne demande aucune installation et fonctionne hors ligne. Pour passer à PostgreSQL, il suffit de modifier `config.ini`, sans toucher au code. |
| Serveur | **Waitress** | Serveur de production en Python pur, stable sous Windows. |
| Interface | Pages Django + CSS/JS sans dépendance externe | Fonctionne sans Internet, aucune étape de compilation, s'adapte au téléphone. |
| PDF | **ReportLab** | Factures, reçus, cartes de membre et rapports, sans dépendance système. |
| Excel | **openpyxl** | Export des rapports. |
| QR codes | **qrcode** (génération), **jsQR** et BarcodeDetector (lecture sur mobile) | Fonctionne hors ligne. |
| Mobile | **PWA + Capacitor** | Une seule base de code pour Android, iPhone et le navigateur. |
| Paquet Windows | **PyInstaller + Inno Setup** | Un fichier `.exe` d'installation, sans Python à installer sur le poste. |

## 2. Organisation

```
lancer.py                  Lanceur : migrations, serveur Waitress, sauvegarde automatique, navigateur
wellness_gym/settings.py   Configuration (dossier de données, config.ini, sécurité)
gym/models.py              Modèle de données
gym/services.py            Logique métier : TOUTES les règles (quotas, pointage, paiements, audit)
gym/views/                 Écrans web (une vue = un contrôle de rôle + appel aux services)
gym/api.py                 API JSON v1 de l'application mobile (mêmes services)
gym/pdf.py                 Facture, reçu, carte de membre, rapports PDF
gym/rapports.py            Moteur de rapports (affichage, PDF, Excel)
gym/sauvegarde.py          Sauvegarde à chaud SQLite, rotation, restauration
gym/static/gym/mobile/     Application mobile (servie sous /m/, copiée dans Capacitor)
gym/tests/                 Tests automatisés : 7 scénarios obligatoires, interface, API
mobile/                    Projet Capacitor (Android / iOS)
installer/                 PyInstaller (.spec) + Inno Setup (.iss) + script de construction
.github/workflows/         Construction automatique : installateur Windows + APK Android
```

**Principe central :** les écrans web et l'API mobile n'enregistrent jamais rien directement. Ils appellent `services.py`. Les contrôles sont donc identiques partout et testés une seule fois.

## 3. Modèle de données

- **Utilisateur** (rôle : ADMIN, RECEPTION ou COACH) ; **Coach**, éventuellement lié à un compte.
- **Client** : identifiant unique `WG00001`, coach attitré, fiche archivable sans perte d'historique.
- **Formule** : MENSUEL (durée en mois, séances par semaine, report), SEANCE, ou HORAIRE (durée, tolérance, tranche et tarif de dépassement). On la désactive au lieu de la supprimer.
- **Abonnement** : droit vendu à un client. Il **copie** les conditions de la formule au moment de la vente (prix, quota, report, durée, tarif de dépassement), pour qu'une modification de tarif ne change jamais l'historique. Il est chaîné au précédent en cas de renouvellement.
- **Presence** : entrée et sortie, durée, soldes figés au moment du pointage, dépassement, supplément, autorisation. Une **contrainte en base** empêche d'avoir deux présences « en cours » pour un même client.
- **AutorisationExceptionnelle** : motif, justification, responsable, demandeur.
- **Transaction**, qui donne lieu à une **Facture** (relation 1-1), à des **Reglements** (un reçu chacun) et à des **Remboursements**. Le montant payé et le reste sont toujours **calculés**, jamais saisis. La suppression est bloquée au niveau du modèle : on annule avec motif et auteur.
- **Reservation** (prévue, honorée, absent, annulée) ; **Observation** (observation, recommandation, incident).
- **JournalAudit** : journal non modifiable de toutes les opérations importantes.
- **Sequence** : numérotation annuelle sans doublon (`FAC-2026-00001`, `REC-…`, `TR-…`, `RMB-…`).
- **JetonAPI** : sessions mobiles, stockées hachées en SHA-256.
- **Parametres** (une seule ligne) et **ModePaiement**.

## 4. Règle de calcul des séances

`services.decouper_semaines()` découpe la période en semaines **glissantes de 7 jours à partir de la date de début**. Le quota d'une semaine incomplète vaut `séances_par_semaine × jours / 7`, arrondi selon le paramètre choisi (supérieur, inférieur, ou quota complet).

`services.etat_droits()` calcule, semaine par semaine : les séances utilisées, le report éventuel, les séances autorisées et les restantes, ainsi que les totaux de la période.

`services.verifier_acces()` renvoie le verdict : autorisé, ou bloqué avec une raison précise (DEJA_PRESENT, QUOTA_EPUISE, ABONNEMENT_EXPIRE, SEANCE_CONSOMMEE, AUCUN_ABONNEMENT, PAIEMENT_EN_ATTENTE). Il précise aussi si une dérogation est possible.

## 5. API v1 (application mobile)

Authentification : `POST /api/v1/connexion` → `{jeton}`. Les appels suivants portent l'en-tête `Authorization: Token <jeton>`. Les en-têtes CORS sont ouverts : l'authentification se fait par jeton, sans cookie.

| Méthode | Chemin | Rôle |
|---|---|---|
| GET | `/api/v1/moi`, `/tableau`, `/presences` | Tous |
| GET | `/api/v1/clients?q=`, `/clients/<id>`, `/scan?code=` | Tous (un coach ne voit que ses clients) |
| POST | `/api/v1/clients/creer`, `/clients/<id>/entree`, `/entree-exceptionnelle`, `/vente` | Réception et responsable |
| POST | `/api/v1/presences/<id>/sortie`, `/transactions/<id>/encaisser` | Réception et responsable |
| GET | `/api/v1/catalogue`, `/transactions/<id>`, `/factures/<id>/pdf` | Réception et responsable |
| POST | `/api/v1/clients/<id>/observation`, `/deconnexion` | Tous |

Les erreurs métier sont renvoyées avec le code **409** et un message en français, affiché tel quel à l'utilisateur.

## 6. Tests

```
python manage.py test gym
```

Les 25 tests couvrent :

- les **7 scénarios obligatoires** du cahier des charges ;
- le calcul des droits : février, mois de 30 et 31 jours, les 3 modes d'arrondi, le report des séances ;
- la traçabilité : suppression interdite, annulation après remboursement ;
- l'affichage de chaque page pour les 3 rôles, et les droits d'accès ;
- les rapports PDF et Excel ;
- l'API mobile.

## 7. Évolutions possibles

- **Base PostgreSQL centralisée** et accès multi-sites : réglage dans `config.ini`.
- **Application client** : consultation du solde, carte QR et réservations, en réutilisant l'API. Elle nécessite un hébergement accessible depuis Internet.
- **Rappels automatiques** de renouvellement par SMS ou WhatsApp Business : la liste des clients à relancer est déjà calculée.
- **Lien avec la plateforme de l'hôtel** (réservations des chambres, point de vente) : l'API et le modèle de données le permettent.
