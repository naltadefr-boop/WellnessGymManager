# WELLNESS GYM MANAGER

Logiciel de gestion de la salle de sport de **WELLNESS HOTEL** : clients, formules et tarifs, abonnements avec calcul automatique des séances, pointage des entrées et sorties, paiements, factures PDF, coachs, rapports PDF et Excel, sauvegardes. Il est complété par une **application mobile Android / iPhone** pour le personnel.

## Démarrage rapide (Windows)

- **Installateur** : `WellnessGymManager-Installation-1.0.0.exe`. Voir `docs/INSTALLATION.md` pour obtenir ce fichier.
- **Depuis le code source** : installez Python 3.11 ou plus récent, puis double-cliquez sur **`Lancer Wellness Gym.bat`**.

Au premier lancement, créez le compte du responsable, puis complétez les **Paramètres** et vérifiez les **tarifs**.

## Documentation

| Document | Pour qui |
|---|---|
| `docs/GUIDE_UTILISATEUR` (.md / .pdf) | Réceptionnistes, coachs, responsables |
| `docs/INSTALLATION` (.md / .pdf) | Installation, réseau, sauvegardes, dépannage |
| `docs/APPLICATION_MOBILE` (.md / .pdf) | Android, iPhone, Play Store, App Store |
| `docs/ARCHITECTURE.md` | Informaticien / développeur |

## Développement

```
pip install -r requirements.txt
python manage.py test gym            # 25 tests, dont les 7 scénarios du cahier des charges
python manage.py donnees_demo        # données fictives de formation (base de test uniquement)
python lancer.py                     # lance le logiciel
```
