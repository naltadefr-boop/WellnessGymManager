# Wellness Gym Manager — Documentation d'installation

**Établissement :** WELLNESS HOTEL · **Service :** Salle de sport et fitness · **Version :** 1.0.0

---

## 1. Ce qu'il faut savoir avant d'installer

- Le logiciel s'installe sur **l'ordinateur Windows de la réception** (Windows 10 ou 11, 4 Go de mémoire suffisent).
- Il fonctionne **sans connexion Internet**. Toutes les données restent dans l'hôtel.
- Il s'utilise dans le navigateur (Chrome, Edge ou Firefox), qui s'ouvre tout seul au lancement. Le logiciel ne se trouve pas sur Internet : le navigateur sert seulement d'écran d'affichage.
- Les données sont rangées dans un dossier séparé du programme : `C:\ProgramData\WellnessGymManager`. Une mise à jour ou une désinstallation ne les supprime jamais.

| Contenu du dossier de données | Rôle |
|---|---|
| `wellness_gym.sqlite3` | La base de données (clients, paiements, présences…) |
| `sauvegardes\` | Les sauvegardes automatiques et manuelles (.zip) |
| `media\` | Logo et cachet de l'hôtel |
| `config.ini` | Réglages réseau et base de données |
| `secret.key` | Clé de sécurité. **Ne pas supprimer, ne pas partager.** |

---

## 2. Méthode A — Installateur Windows (recommandée)

1. Lancez `WellnessGymManager-Installation-1.0.0.exe` en tant qu'administrateur.
2. Choisissez vos options :
   - **Raccourci sur le Bureau** (conseillé) ;
   - **Lancement automatique** à l'ouverture de Windows (conseillé pour la réception) ;
   - **Autoriser les téléphones et tablettes du réseau** : à cocher si le personnel utilisera l'application mobile (le pare-feu est réglé automatiquement).
3. Terminez l'installation, puis lancez **Wellness Gym Manager**.

> **Obtenir l'installateur.** Le fichier `.exe` se fabrique à partir du code source. Deux façons de faire :
> - **Automatiquement et gratuitement**, avec GitHub : déposez le dossier du projet dans un dépôt GitHub privé, ouvrez l'onglet **Actions**, choisissez **Construire**, puis **Run workflow**. Au bout d'environ 10 minutes, téléchargez l'installateur dans la rubrique **Artifacts**. La même opération produit aussi l'application Android.
> - **Sur un PC Windows** équipé de Python 3.11 ou plus récent et d'[Inno Setup 6](https://jrsoftware.org/isinfo.php) : double-cliquez sur `installer\construire_windows.bat`.

## 3. Méthode B — Lancement direct depuis le code source

1. Installez [Python 3.11 ou plus récent](https://www.python.org/downloads/windows/). Pendant l'installation, cochez **« Add python.exe to PATH »**.
2. Copiez le dossier `WellnessGymManager` sur le PC (par exemple dans `C:\WellnessGymManager`).
3. Double-cliquez sur **`Lancer Wellness Gym.bat`**. Au premier lancement, les composants s'installent automatiquement : il faut Internet pendant quelques minutes, une seule fois.

Les lancements suivants fonctionnent sans Internet.

---

## 4. Premier démarrage

1. Une fenêtre noire s'ouvre : c'est le moteur du logiciel. **Ne la fermez pas** pendant l'utilisation. Vous pouvez la réduire.
2. Le navigateur affiche **« Premier démarrage »**. Créez le compte du **responsable** (administrateur).
3. Dans **Paramètres**, complétez les informations de l'établissement :
   - logo (format PNG ou JPG), adresse, téléphone, e-mail, mentions légales (RCCM, NIU) ;
   - image du cachet, si vous en avez une (elle sera imprimée sur les factures) ;
   - indicatif téléphonique du pays, pour l'envoi par WhatsApp (237 pour le Cameroun, 226 pour le Burkina Faso…) ;
   - règles de gestion : alertes, calcul des semaines incomplètes, déconnexion automatique, sauvegarde.
4. Dans **Formules et tarifs**, **vérifiez et ajustez les prix**. Les formules installées au départ ne sont que des exemples :

   | Formule | Prix d'exemple |
   |---|---|
   | Mensuel 4 séances/semaine | 25 000 FCFA |
   | Séance journalière | 3 000 FCFA |
   | 1 h / 1 h 30 / 2 h / 3 h | 1 500 / 2 000 / 2 500 / 3 500 FCFA (+ 500 FCFA par tranche de 30 min de dépassement) |

5. Dans **Personnel et utilisateurs**, créez un compte personnel pour chaque réceptionniste et chaque coach. Pour un coach, créez ensuite sa fiche dans **Gestion des coachs** et associez-y son compte.

> **Formation du personnel.** Sur une installation **de test** (jamais sur la base réelle), la commande `python manage.py donnees_demo` crée des clients et un historique fictifs. Elle crée aussi trois comptes : `admin / Admin-2026!`, `reception / Accueil-2026!`, `coach / Coach-2026!`.

---

## 5. Utilisation sur plusieurs appareils (réseau de l'hôtel)

Par défaut, le logiciel n'est accessible que depuis l'ordinateur de la réception. Pour l'ouvrir aussi depuis d'autres postes, tablettes ou téléphones :

1. Ouvrez `C:\ProgramData\WellnessGymManager\config.ini` avec le Bloc-notes.
2. Remplacez `hote = 127.0.0.1` par `hote = 0.0.0.0`, puis enregistrez.
3. Autorisez le port 8000 dans le pare-feu Windows. L'option de l'installateur le fait automatiquement. Sinon, tapez cette commande dans une invite de commandes lancée en administrateur :
   `netsh advfirewall firewall add rule name="Wellness Gym Manager" dir=in action=allow protocol=TCP localport=8000 profile=private`
4. Relancez le logiciel. La fenêtre noire affiche alors l'adresse à utiliser sur les autres appareils, par exemple `http://192.168.1.20:8000/`. L'application mobile se trouve à la même adresse suivie de `/m/`.

**Conseil :** demandez à votre technicien de donner une **adresse IP fixe** à l'ordinateur de la réception (réglage de la box ou du routeur), pour que cette adresse ne change jamais.

### Base de données centralisée (PostgreSQL) — évolution

Pour plusieurs sites, ou un grand nombre de postes :

1. Installez PostgreSQL et créez une base `wellness_gym`.
2. Ajoutez `psycopg[binary]` dans `requirements.txt`.
3. Dans `config.ini`, section `[base_de_donnees]`, indiquez `moteur = postgresql`, puis le nom de la base, l'utilisateur, le mot de passe et l'hôte.
4. Relancez le logiciel : les tables se créent automatiquement.
5. Sauvegardes : utilisez `pg_dump` et `pg_restore`. La sauvegarde intégrée du logiciel ne fonctionne qu'avec SQLite.

---

## 6. Sauvegardes et restauration

- **Automatique** : toutes les 12 heures par défaut (réglable dans Paramètres). Le logiciel garde les 30 dernières sauvegardes automatiques.
- **Copie externe** : dans Paramètres, indiquez un dossier sur une clé USB ou un disque externe (par exemple `E:\Sauvegardes_Gym`). Chaque sauvegarde y sera aussi copiée.
- **Manuelle** : menu **Sauvegardes → Sauvegarder maintenant**, puis **Télécharger** pour la copier où vous voulez.
- **Restauration** : menu **Sauvegardes → Restaurer**, puis tapez `RESTAURER` pour confirmer. Avant de restaurer, le logiciel sauvegarde automatiquement l'état actuel : il reste donc possible de revenir en arrière.

> **Bonne pratique :** une fois par semaine, copiez la dernière sauvegarde sur une clé USB conservée hors de la réception.

## 7. Mise à jour du logiciel

Lancez le nouvel installateur par-dessus l'ancien. Les données de `C:\ProgramData\WellnessGymManager` sont conservées, et la base est mise à jour automatiquement au démarrage. Par précaution, faites une sauvegarde manuelle juste avant.

## 8. Sécurité

- Chaque membre du personnel a **son propre compte**. Ne partagez jamais un mot de passe.
- Après **5 essais de mot de passe incorrects**, le compte est bloqué pendant 5 minutes.
- La **déconnexion automatique** intervient après 15 minutes d'inactivité (réglable).
- Les mots de passe sont chiffrés de manière irréversible (PBKDF2). Les jetons de l'application mobile sont stockés hachés et expirent après 30 jours sans utilisation.
- Aucune transaction, aucun encaissement et aucune entrée du journal ne peut être supprimé. Toute correction passe par une **annulation**, enregistrée avec son motif et le nom du responsable qui l'a autorisée.

## 9. Dépannage

| Problème | Solution |
|---|---|
| Le navigateur affiche « Ce site est inaccessible » | Le logiciel n'est pas lancé : ouvrez **Wellness Gym Manager**. La fenêtre noire doit rester ouverte. |
| « Le logiciel est déjà en cours d'exécution » | Normal : il est déjà ouvert. Le navigateur s'ouvre sur la bonne page. |
| Les téléphones n'accèdent pas au logiciel | Vérifiez `hote = 0.0.0.0` dans `config.ini`, la règle du pare-feu, et que le téléphone est bien connecté au **Wi-Fi de l'hôtel**. |
| Une facture ne s'imprime pas | Ouvrez-la (elle s'affiche en PDF), puis utilisez **Imprimer** dans le navigateur (Ctrl + P). |
| Mot de passe du responsable oublié | Un autre administrateur peut le réinitialiser dans **Personnel**. C'est pourquoi il est conseillé d'avoir **deux comptes administrateur**. Pour une installation depuis le code source, la commande `python manage.py changepassword <identifiant>` permet aussi de le réinitialiser. |
| Erreur technique | Le détail est consigné dans `C:\ProgramData\WellnessGymManager\journal_technique.log`. |
