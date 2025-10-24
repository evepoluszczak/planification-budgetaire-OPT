# Chargement PAX Non Bloquant

## Vue d'ensemble

Le chargement des données PAX (Forecast_pax) a été implémenté de manière asynchrone pour ne pas bloquer l'utilisation de l'application pendant le chargement des fichiers volumineux.

## Fonctionnalités

### 🔄 Chargement en arrière-plan

- **Thread séparé** : Le chargement s'exécute dans un thread dédié
- **Application réactive** : Vous pouvez continuer à utiliser l'app pendant le chargement
- **Polling automatique** : L'interface vérifie l'état du chargement toutes les 0.5 secondes

### 📊 Interface utilisateur (Sidebar)

La section "Données PAX" dans la sidebar affiche différents états :

#### État IDLE (Inactif)
```
Données PAX
🔄 [Lancer le chargement PAX]
```
- Cliquez sur le bouton pour démarrer le chargement
- Un toast confirme le démarrage

#### État LOADING (En cours)
```
Données PAX
⏳ Chargement en cours... (2.3s)
[Barre de progression animée]
```
- Affiche le temps écoulé en temps réel
- Barre de progression animée
- Auto-refresh toutes les 0.5s
- **L'application reste utilisable**

#### État SUCCESS (Succès)
```
Données PAX
✅ Données PAX chargées
📊 Forecast : 2025-01-01 → 2025-12-31
📈 Historique : 2023-01-01 → 2024-12-31
🔄 [Recharger]
```
- Confirmation visuelle du succès
- Affichage des plages de dates chargées
- Bouton pour recharger si nécessaire

#### État ERROR (Erreur)
```
Données PAX
❌ Erreur de chargement
Détails : Fichier non trouvé
🔄 [Réessayer]
```
- Message d'erreur clair
- Détails de l'erreur
- Bouton pour réessayer

## Architecture technique

### Fichiers modifiés

#### 1. `utils/async_loader.py` (nouveau)

Module dédié au chargement asynchrone contenant :

- **`PaxLoaderThread`** : Classe thread pour le chargement
  - Exécute `_load_pax_uncached()` sans cache
  - Stocke les résultats dans `self.result`
  - Gère les erreurs dans `self.error`

- **`start_pax_loading(file_path)`** : Démarre le chargement
  - Crée un nouveau thread
  - Initialise l'état dans `session_state`
  - Lance le thread en mode daemon

- **`check_pax_loading_status()`** : Vérifie l'état du chargement
  - Retourne : `'idle'`, `'loading'`, `'success'`, ou `'error'`
  - Met à jour `session_state` avec les résultats
  - Nettoie la référence au thread une fois terminé

- **`get_pax_loading_info()`** : Récupère les infos d'affichage
  - Temps écoulé
  - Statut des données (forecast/historical)
  - Messages d'erreur

#### 2. `app.py` (modifié)

Modifications principales :

**Imports ajoutés** :
```python
from utils.async_loader import start_pax_loading, check_pax_loading_status, get_pax_loading_info
```

**Chargement automatique désactivé** :
- Lignes 33-40 : Le chargement automatique au démarrage a été remplacé par une simple initialisation d'état
- Évite de bloquer l'application au lancement

**Section sidebar** (lignes 105-171) :
- Bouton "Lancer le chargement PAX"
- Affichage de l'état en temps réel
- Barre de progression pendant le chargement
- Toasts pour les notifications
- Boutons contextuels (Recharger/Réessayer)

### Flux de données

```
┌─────────────────────┐
│ Utilisateur clique  │
│ sur le bouton       │
└──────────┬──────────┘
           │
           ▼
┌─────────────────────┐
│ start_pax_loading() │
│ - Crée le thread    │
│ - Lance le thread   │
└──────────┬──────────┘
           │
           ▼
┌─────────────────────┐
│ PaxLoaderThread     │
│ - Charge le fichier │
│ - Parse les données │
│ - Sépare hist/fc    │
└──────────┬──────────┘
           │
           ▼
┌─────────────────────────┐
│ check_pax_loading_      │
│ status() [polling]      │
│ - Vérifie si terminé    │
│ - Récupère les résultats│
│ - Met à jour UI         │
└─────────────────────────┘
```

## Variables session_state

Le système utilise les variables suivantes dans `st.session_state` :

### Variables de contrôle
- `pax_loading_status` : `'idle'`, `'loading'`, `'success'`, `'error'`
- `pax_loading_elapsed` : Temps écoulé en secondes
- `pax_loading_error` : Message d'erreur si échec
- `pax_loader_thread` : Référence au thread (temporaire)
- `pax_loader_start_time` : Timestamp du démarrage

### Variables de données
- `pax_forecast_data` : DataFrame avec données forecast
- `pax_historical_data` : DataFrame avec données historiques
- `pax_forecast_min_date` / `pax_forecast_max_date` : Plage forecast
- `pax_historical_min_date` / `pax_historical_max_date` : Plage historique
- `pax_forecast_status` : `'loaded'` ou `'no_data_found'`
- `pax_historical_status` : `'loaded'` ou `'no_data_found'`

## Utilisation

### 1. Démarrer l'application

```bash
streamlit run app.py
```

### 2. Charger un scénario

Sur l'écran d'accueil, choisissez :
- "Démarrer avec la base 2026"
- Ou "Charger un scénario existant"

### 3. Lancer le chargement PAX

Dans la sidebar (à gauche) :
1. Localisez la section **"Données PAX"**
2. Cliquez sur **"🔄 Lancer le chargement PAX"**
3. Un toast confirme le démarrage
4. L'interface affiche l'état en temps réel

### 4. Pendant le chargement

- ✅ **Vous pouvez** : Naviguer entre les pages, modifier la configuration, consulter les données
- ✅ **Auto-refresh** : L'état se met à jour automatiquement
- ⏱️ **Durée** : Variable selon la taille du fichier (généralement 2-10 secondes)

### 5. Après le chargement

- **Succès** : Les données sont disponibles dans "Comparaison Historique" et "Besoin Jour"
- **Erreur** : Cliquez sur "Réessayer" ou vérifiez que le fichier existe

## Configuration

Le fichier PAX à charger est défini dans `config/constants.py` :

```python
PAX_DATA_FILE_PATH = Path("data/Forecast_pax.xlsx")
```

Pour utiliser un autre fichier, modifiez cette constante.

## Avantages

### ✅ Performance
- Pas de blocage au démarrage de l'app
- Chargement en arrière-plan (thread séparé)
- Application reste réactive

### ✅ Expérience utilisateur
- Feedback visuel en temps réel
- Toasts pour les notifications
- Barre de progression
- Messages d'erreur clairs

### ✅ Flexibilité
- Chargement à la demande
- Bouton Recharger pour forcer un rechargement
- Gestion d'erreur robuste

## Limitations

### Threads et Streamlit

Streamlit n'est pas nativement thread-safe. Voici les précautions prises :

1. **Communication unidirectionnelle** : Le thread ne modifie que ses propres variables (`self.result`, `self.error`)
2. **Mise à jour dans le thread principal** : Seul `check_pax_loading_status()` (dans le thread Streamlit) modifie `session_state`
3. **Thread daemon** : Le thread se termine automatiquement avec l'application

### Polling

L'auto-refresh utilise `time.sleep(0.5)` suivi de `st.rerun()`. Cela peut :
- Consommer légèrement plus de ressources pendant le chargement
- Créer un effet de "flash" lors des reloads

Pour désactiver l'auto-refresh, commentez les lignes 135-136 dans `app.py`.

## Dépannage

### Problème : "Fichier non trouvé"

**Cause** : Le fichier `Forecast_pax.xlsx` n'existe pas à l'emplacement spécifié

**Solution** :
1. Vérifiez que le fichier existe dans `data/Forecast_pax.xlsx`
2. Ou modifiez `PAX_DATA_FILE_PATH` dans `config/constants.py`

### Problème : Chargement infini

**Cause** : Le thread est bloqué ou a crashé silencieusement

**Solution** :
1. Rafraîchissez la page (F5)
2. Vérifiez les logs Streamlit dans le terminal
3. Vérifiez que le fichier n'est pas corrompu

### Problème : "Colonnes manquantes"

**Cause** : Le fichier PAX n'a pas le format attendu

**Solution** :
- Le fichier doit contenir les colonnes :
  - `Local Schedule Time`
  - `Expected Pax`
  - `Schengen Flight`
  - `Arrival - Departure Code`

## Tests

Pour tester le système :

1. **Test nominal** : Fichier PAX valide
   - Résultat attendu : Chargement réussi en 2-5 secondes

2. **Test fichier manquant** : Renommer temporairement le fichier
   - Résultat attendu : Erreur "Fichier non trouvé"

3. **Test fichier corrompu** : Fichier Excel invalide
   - Résultat attendu : Erreur avec message explicite

4. **Test pendant utilisation** : Lancer le chargement puis naviguer
   - Résultat attendu : Application reste réactive

## Évolutions futures possibles

- [ ] Upload de fichier PAX via l'interface
- [ ] Chargement de plusieurs fichiers PAX (scénarios multiples)
- [ ] Cache intelligent avec détection de modification
- [ ] Progression réelle (% du fichier lu)
- [ ] Annulation du chargement en cours
