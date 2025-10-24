# Dossier Input Files

Ce dossier contient les fichiers de données d'entrée nécessaires au fonctionnement de l'application.

## Fichiers attendus

### 1. Forecast_pax.xlsx
**Données PAX futures (prévisions)**

- **Description** : Données de passagers prévisionnelles
- **Format** : Excel (.xlsx)
- **Colonnes requises** :
  - `Local Schedule Time` : Date et heure au format `dd.mm.yyyy HH:MM`
  - `Expected Pax` : Nombre de passagers attendus
  - `Schengen Flight` : `Y` (Schengen) ou `N` (Non-Schengen)
  - `Arrival - Departure Code` : `A` (Arrivée) ou `D` (Départ)

- **Période couverte** : Dates futures (≥ aujourd'hui)
- **Utilisation** : Comparaison Historique, Besoin Jour, simulations

### 2. Historic_pax.xlsx
**Données PAX historiques (passées)**

- **Description** : Données de passagers historiques réelles
- **Format** : Excel (.xlsx)
- **Colonnes requises** : Identiques à Forecast_pax.xlsx
- **Période couverte** : Dates passées (< aujourd'hui)
- **Utilisation** : Comparaison Historique, analyse de tendances

## Comment charger les fichiers

1. Placez vos fichiers `Forecast_pax.xlsx` et `Historic_pax.xlsx` dans ce dossier
2. Dans l'application, allez dans la sidebar
3. Section **"Données PAX"**
4. Cliquez sur **"🔄 Lancer le chargement PAX"**
5. Le chargement se fait en arrière-plan, vous pouvez continuer à utiliser l'app

## Résolution de problèmes

### Erreur "Aucun fichier PAX trouvé"
- Vérifiez que les fichiers sont bien nommés :
  - `Forecast_pax.xlsx` (pas de majuscules/minuscules différentes)
  - `Historic_pax.xlsx`
- Vérifiez qu'ils sont dans le dossier `input_files/`

### Erreur "Colonnes manquantes"
- Vérifiez que votre fichier contient les 4 colonnes requises
- Vérifiez l'orthographe exacte des noms de colonnes

### Chargement partiel
- L'application peut fonctionner avec un seul des deux fichiers
- Un warning vous indiquera quel fichier est manquant

## Notes

- Les fichiers ne sont **pas versionnés** dans Git (pour protéger les données sensibles)
- Le dossier `input_files/` est créé automatiquement
- Format maximum recommandé : quelques Mo par fichier pour des performances optimales
