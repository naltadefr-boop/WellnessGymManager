# Wellness Gym Manager — Guide d'utilisation

**Pour :** réceptionnistes, coachs et responsables de la salle de sport de WELLNESS HOTEL.

---

## 1. Se connecter

Ouvrez **Wellness Gym Manager**, puis saisissez votre identifiant et votre mot de passe personnels. Le menu de gauche affiche uniquement les rubriques autorisées pour votre rôle.

| Rôle | Ce qu'il peut faire |
|---|---|
| **Responsable** | Tout : tarifs, personnel, paramètres, rapports, annulations, remboursements, autorisations exceptionnelles, historique. |
| **Réceptionniste** | Clients, ventes, paiements, factures, entrées et sorties. Il ne peut ni modifier un tarif ni annuler un paiement sans les identifiants d'un responsable. |
| **Coach** | Ses clients, leurs présences, ses observations. Il ne voit **aucune donnée financière**. |

**Rechercher un client :** la barre en haut de l'écran fonctionne depuis toutes les pages. Tapez un nom, un numéro de téléphone ou un identifiant (`WG00012`). Si vous scannez une carte de membre avec un lecteur de QR code USB, la fiche de pointage s'ouvre directement.

---

## 2. Les opérations de tous les jours

### 2.1 Un nouveau client arrive

1. Cliquez sur **Nouveau client**.
2. Remplissez son identité (nom, prénom, téléphone).
3. Dans la même page, choisissez la **formule**. Le prix se remplit tout seul. Indiquez le **montant payé** et le **mode de paiement**. Pour un paiement Mobile Money, notez la référence de la transaction.
4. Cliquez sur **Enregistrer le client**, puis confirmez.
5. La facture est créée automatiquement. Selon le besoin, cliquez sur **Imprimer la facture**, **Enregistrer en PDF** ou **WhatsApp**.

Le client reçoit un identifiant unique (`WG00001`, `WG00002`…). Depuis sa fiche, vous pouvez imprimer sa **carte de membre**, qui porte un QR code.

> Si le client ne paie qu'une partie, enregistrez le montant réellement versé. Le reste apparaît dans **Paiements en attente**.

### 2.2 Un abonné arrive : ENTRÉE

1. Menu **Présences et pointages**. Tapez son nom ou scannez sa carte.
2. Le logiciel vérifie tout seul :
   - **ACCÈS AUTORISÉ** en vert : l'abonnement est valide et il reste des séances cette semaine ;
   - **ACCÈS BLOQUÉ** en rouge, avec la raison : abonnement expiré, quota de la semaine épuisé, séance déjà consommée, etc.
3. Les compteurs indiquent les séances **autorisées cette semaine**, **consommées** et **restantes**.
4. Cliquez sur le grand bouton vert **→ ENTRÉE**. L'heure d'arrivée et votre nom sont enregistrés.

Un double clic n'enregistre jamais deux entrées : le logiciel refuse un client déjà présent.

### 2.3 Le client repart : SORTIE

Dans le **tableau des présences en temps réel**, en bas de la page Présences, cliquez sur **SORTIE** en face du client, puis confirmez. Le logiciel enregistre l'heure de départ, calcule la durée et affiche le nouveau solde de séances.

Le tableau se met à jour tout seul toutes les 20 secondes. Une ligne rouge signale un **dépassement horaire en cours**.

### 2.4 Séance journalière

Recherchez le client, ou créez-le. Cliquez sur **Renouveler / vendre**, puis choisissez **Séance journalière** et encaissez. Ensuite : ENTRÉE, puis SORTIE.

La séance est consommée dès qu'elle a été utilisée. Pour revenir, le client doit payer une nouvelle séance.

### 2.5 Formule horaire (1 h, 1 h 30, 2 h, 3 h)

À la sortie, le logiciel compare la durée réelle avec la durée payée. Au-delà de la tolérance (5 minutes par défaut), il :

- signale le **dépassement** et sa durée ;
- calcule le **supplément** selon le tarif configuré (par exemple 500 FCFA par tranche de 30 minutes entamée) ;
- crée la facture du supplément et ouvre directement l'écran d'encaissement pour **régulariser** tout de suite.

*Exemple : formule 2 heures, le client reste 2 h 30. Dépassement de 30 minutes, soit 1 tranche : supplément de 500 FCFA.*

### 2.6 Renouveler un abonnement

Depuis la fiche du client, ou directement depuis l'écran de pointage quand l'accès est bloqué, cliquez sur **Renouveler / vendre**. Le dossier du client n'est pas recréé et tout son historique est conservé.

Si le client renouvelle **avant** la fin de son abonnement, le nouveau démarre le lendemain de la fin de l'ancien : il ne perd aucun jour.

### 2.7 Quota épuisé ou abonnement expiré : autorisation exceptionnelle

Quand l'accès est bloqué, un **responsable** peut accorder une exception :

1. Ouvrez **Autorisation exceptionnelle**.
2. Écrivez la justification (obligatoire).
3. Le responsable saisit **son** identifiant et **son** mot de passe. Si c'est lui qui est connecté, ce n'est pas nécessaire.
4. L'entrée est enregistrée avec la mention « exception », la justification et le nom du responsable.

---

## 3. Comment sont calculées les séances

Un abonnement mensuel « 4 séances par semaine » est découpé en **semaines de 7 jours à partir de la date de début** :

- semaine 1 = jours 1 à 7, semaine 2 = jours 8 à 14, etc. ;
- chaque semaine complète donne droit à 4 séances ;
- la dernière semaine est souvent incomplète. Son quota dépend du réglage choisi par le responsable (Paramètres) :

| Mois de 31 jours (4 semaines + 3 jours) | Total |
|---|---|
| Au prorata, arrondi au supérieur (réglage par défaut) | 16 + 2 = **18 séances** |
| Au prorata, arrondi à l'inférieur | 16 + 1 = **17 séances** |
| Quota complet | 16 + 4 = **20 séances** |

En février (28 jours), le total est de **16 séances**. Le logiciel ne compte donc pas aveuglément 16 séances pour tous les mois.

**Séances non utilisées :** pour chaque formule, le responsable décide si elles sont **perdues** en fin de semaine (réglage par défaut) ou **reportées** sur la semaine suivante. Le calendrier des droits, sur la fiche du client, montre chaque semaine avec ses séances consommées et autorisées.

Une séance est décomptée dès **l'entrée**, et validée à la sortie. Si une présence a été pointée par erreur, son annulation recrédite la séance : fiche client, **Derniers passages**, **Annuler**, avec un motif.

---

## 4. Paiements et factures

- **Encaisser un reste à payer** : menu **Paiements et finances**, onglet **Paiements en attente**, puis **Encaisser**.
- **Chaque encaissement** produit un **reçu simplifié** au format ticket de caisse 80 mm.
- **La facture** (format A4) porte le logo, le numéro unique, la formule, la période de validité, les séances autorisées, le montant, ce qui a été payé, le reste et le mode de paiement. Elle prévoit aussi les signatures du client, du réceptionniste et du coach, ainsi qu'un emplacement pour le cachet.
- **Réimprimer** : menu **Factures**. Chaque réimpression est notée dans l'historique.
- **Envoyer par WhatsApp** : téléchargez le PDF, cliquez sur **WhatsApp** (le message est prérempli), puis joignez le PDF dans la conversation.
- **Envoyer par e-mail** : bouton **Envoyer par e-mail** (il faut d'abord configurer la messagerie dans les Paramètres).

### Corriger une erreur

On ne supprime **jamais** une opération. On l'annule, et l'annulation reste visible :

| Situation | Que faire |
|---|---|
| Paiement saisi par erreur | Ouvrez la transaction, puis **Encaissements → Annuler**, en indiquant le motif. Un responsable valide. |
| Le client part et doit être remboursé | **Corrections → Rembourser le client**. Indiquez le montant, le mode et le motif. Un responsable valide. |
| Vente enregistrée par erreur | Annulez d'abord l'encaissement (ou remboursez), puis **Annuler la transaction**. L'abonnement associé est annulé. |

---

## 5. Les alertes (tableau de bord)

Toutes les alertes sont visibles dès l'ouverture du logiciel :

| Alerte | Signification |
|---|---|
| **Clients présents** | Qui est en salle en ce moment, et depuis quelle heure. |
| **À renouveler** | L'abonnement se termine dans moins de 5 jours (réglable). Proposez le renouvellement. |
| **Expirés** | Clients dont l'abonnement est terminé et non renouvelé. Ce sont les clients à relancer. |
| **Quota épuisé** | Les 4 séances de la semaine ont été utilisées. |
| **Dernière séance** | Il ne reste qu'une séance cette semaine. |
| **Dépassements horaires** | Formules horaires dépassées (en cours ou dans la journée). |
| **Paiements en attente** | Factures non soldées, avec le montant restant. |

En dessous des alertes, le tableau de bord affiche les statistiques sur les clients, les présences et les encaissements (jour, semaine, mois), ainsi que les graphiques des 14 derniers jours.

---

## 6. Coachs

- Le responsable enregistre les coachs (**Gestion des coachs**) et associe à chaque coach son compte de connexion.
- Un client peut avoir un **coach attitré**. À chaque entrée, on peut choisir le coach de la séance.
- Le coach voit ses clients, leurs séances, et ajoute des **observations**, **recommandations** ou **incidents**.
- Sa fiche indique le nombre de séances encadrées, les clients suivis et ses observations.

**Réservations et absences :** sur la fiche du client, ouvrez **Réserver une séance**. Si le client ne vient pas, marquez-le **Absent** (menu Réservations). Une absence ne décompte une séance que si le responsable l'a décidé dans les Paramètres.

---

## 7. Rapports (responsable)

Le menu **Rapports** donne accès aux rapports suivants : présences du jour, synthèse de la semaine ou du mois, abonnements actifs et expirés, renouvellements, paiements (avec le détail par mode), paiements en attente, séances consommées et restantes, activités des réceptionnistes et des coachs.

Chaque rapport peut être filtré par dates, client, réceptionniste, coach et formule. Il s'exporte en **PDF** ou en **Excel**.

**Historique des opérations :** chaque action importante y est inscrite (qui, quoi, quand, depuis quel poste). Ce journal ne peut pas être modifié.

---

## 8. Application mobile

Le personnel peut aussi utiliser son téléphone Android ou son iPhone. L'application permet de scanner la carte de membre avec l'appareil photo, de pointer les entrées et les sorties, de consulter les soldes et les alertes, de vendre une formule et d'envoyer la facture.

Pour l'installer, voir le document **APPLICATION_MOBILE**.
