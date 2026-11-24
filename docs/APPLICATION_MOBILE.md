# Wellness Gym — Application mobile (Android et iPhone)

L'application mobile est destinée au **personnel** : réception, coachs et responsable. Elle se connecte au logiciel installé à la réception, à travers le Wi-Fi de l'hôtel. Elle applique **exactement les mêmes règles** que le logiciel : quotas, abonnements expirés, doublons, autorisations. Un téléphone ne peut contourner aucun contrôle.

## Ce que fait l'application

| Onglet | Fonctions |
|---|---|
| **Accueil** | Présents, entrées du jour, encaissements (selon les droits), alertes : à renouveler, expirés, quota épuisé, dépassements, impayés. |
| **Scanner** | Lecture du **QR code de la carte de membre** avec l'appareil photo, ou saisie de l'identifiant. La fiche de pointage s'ouvre directement. |
| **Clients** | Recherche ; fiche avec verdict d'accès (autorisé ou bloqué), soldes de la semaine et de la période, calendrier des droits. Boutons **ENTRÉE** et **SORTIE**, autorisation exceptionnelle, vente et renouvellement, observations, factures en PDF. |
| **Présents** | Clients en salle avec la durée en direct, et bouton **SORTIE**. Mise à jour automatique. |
| **Profil** | Compte connecté, déconnexion. |

Un **coach** voit uniquement ses clients, sans boutons de pointage et sans données financières. Il peut ajouter des observations.

---

## Option 1 — Installation immédiate depuis le navigateur (gratuite, sans boutique d'applications)

Prérequis : le logiciel de la réception doit être **ouvert au réseau** (voir INSTALLATION, section 5), et le téléphone connecté au **Wi-Fi de l'hôtel**.

1. Sur le téléphone, ouvrez l'adresse indiquée dans la fenêtre noire du logiciel, suivie de `/m/`. Par exemple : `http://192.168.1.20:8000/m/`.
2. Connectez-vous avec votre identifiant personnel.
3. Ajoutez l'application à l'écran d'accueil :
   - **Android (Chrome)** : menu ⋮ → **Installer l'application** (ou **Ajouter à l'écran d'accueil**) ;
   - **iPhone (Safari)** : bouton **Partager** → **Sur l'écran d'accueil**.

L'icône **Wellness Gym** apparaît alors sur l'écran du téléphone, et l'application s'ouvre en plein écran.

**Scanner la carte :** en installation par le navigateur, les téléphones n'autorisent pas la caméra en direct sur une adresse `http://` du réseau local. Utilisez le bouton **« Photographier le QR code »** : l'appareil photo s'ouvre, vous prenez la carte en photo, et le code est lu automatiquement. La caméra en direct fonctionne dans l'application native (option 2).

---

## Option 2 — Application native (fichier APK Android, App Store, Play Store)

Le dossier `mobile/` contient le projet **Capacitor**. Il utilise **le même code** que l'option 1 : toute amélioration profite aux deux versions. Au premier lancement, l'application demande **l'adresse du logiciel de la réception** (par exemple `192.168.1.20:8000`).

### Android — fichier APK

**Méthode automatique (sans rien installer) :** déposez le projet sur GitHub, ouvrez **Actions**, choisissez **Construire**, puis **Run workflow**. Téléchargez ensuite l'artefact **Application-Android** : il contient `app-debug.apk`.

Pour installer l'APK sur un téléphone :

1. Copiez le fichier sur le téléphone.
2. Ouvrez-le. Autorisez l'installation depuis cette source si le téléphone le demande.

**Méthode manuelle (sur un PC avec Android Studio et Node.js 20) :**

```
cd mobile
npm install
npm run android:init      # crée le projet Android, les icônes et les autorisations
npm run android:ouvrir    # ouvre Android Studio → Build → Build APK(s)
```

**Publication sur le Google Play Store :**

1. Créez un compte développeur Google Play (25 $, à payer une seule fois).
2. Dans Android Studio : **Build → Generate Signed Bundle**, pour obtenir un fichier `.aab` signé.
3. Remplissez la fiche de l'application dans la Play Console : description, captures d'écran, politique de confidentialité.

Pour un usage réservé au personnel, le Play Store n'est pas nécessaire : l'APK suffit.

### iPhone (iOS)

La compilation pour iPhone **exige un Mac** équipé de Xcode, ainsi qu'un **compte Apple Developer** (99 $ par an) pour installer l'application sur des iPhone ou la publier.

```
cd mobile
npm install
npm run ios:init          # crée le projet iOS, les icônes, et autorise réseau local + caméra
npm run ios:ouvrir        # ouvre Xcode → choisir l'équipe (compte Apple) → Run / Archive
```

Pour distribuer l'application au personnel sans la publier : **TestFlight**, ou distribution interne (Apple Business Manager). Pour la publier : **App Store Connect**.

> **Sans Mac ni compte Apple**, l'option 1 fonctionne parfaitement sur iPhone.

---

## Sécurité de l'application mobile

- Connexion avec le **compte personnel** de chaque membre du personnel. Après 5 erreurs de mot de passe, le compte est bloqué pendant 5 minutes.
- Le téléphone conserve un **jeton de session**. Ce jeton est stocké sous forme hachée sur le serveur et expire après 30 jours sans utilisation. **Se déconnecter** l'annule immédiatement.
- Les données restent sur l'ordinateur de la réception : le téléphone ne garde aucune liste de clients.
- Toutes les opérations faites depuis un téléphone apparaissent dans l'**Historique des opérations**, avec le nom de leur auteur.

## Évolution prévue : application pour les clients

L'API (`/api/v1/`) a été conçue pour servir aussi, plus tard, une application destinée aux **clients**. Celle-ci pourrait leur permettre de consulter leur solde, leur carte de membre avec QR code et leurs factures, et de réserver une séance. Elle nécessitera un serveur accessible depuis Internet, donc un hébergement.
