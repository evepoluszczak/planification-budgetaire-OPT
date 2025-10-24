# Intégration des Données AT de Base

## Vue d'ensemble

Les données de planification AT (Agent de Trafic) ont été intégrées dans le système via le fichier `models/planif_AT_base.py`. Ces données définissent les grilles de planification par défaut pour chaque combinaison jour-type × saison.

## Structure des données

### Couverture complète

- **21 jour-types** : 7 jours × 3 saisons
  - Jours : Lundi, Mardi, Mercredi, Jeudi, Vendredi, Samedi, Dimanche
  - Saisons : Standard, Été, Hiver

- **22 périmètres AT** au total (certains spécifiques aux saisons)

- **40 créneaux horaires** : de 04:00 à 23:30 par intervalles de 30 minutes

### Périmètres par saison

#### Périmètres communs (toutes saisons)
- Check in 1, Check in 2, Guichet info, Transit
- Aile Est Départ, Aile Est Départ ABC
- Aile Est Arrivée, Aile Est Arrivée ABC, Aile Est Arrivée Transf., Aile Est Arrivée dispatch
- Hall bagage (+ Transfert)
- Priority Lane
- Visitor's Center

#### Périmètres spécifiques Été
- Accueil famille AE
- Accueil famille CSC
- Sect. France

#### Périmètres spécifiques Hiver
- Accueil famille CSC
- Accès Sect. France
- Check in 3 (Samedi/Dimanche uniquement)

#### Périmètres spécifiques Samedi/Dimanche Hiver
- T2 Arrivée
- T2 Départ
- T2 Portier
- T2 Renfort

## Fichiers modifiés

### 1. `models/planif_AT_base.py` (nouveau)

Contient le dictionnaire `DATA` avec toutes les grilles AT :

```python
DATA = {
    "Lundi Standard": {
        "Aile Est Arrivée": [np.nan]*5 + [1]*34,
        "Check in 1": [np.nan]*1 + [1]*28 + [np.nan]*10,
        ...
    },
    "Lundi Été": {...},
    "Lundi Hiver": {...},
    ...
}
```

### 2. `models/session_state.py` (modifié)

- **Import ajouté** : `from models.planif_AT_base import DATA as AT_DATA`
- **Liste des périmètres AT étendue** : ajout de tous les nouveaux périmètres (Accueil famille AE/CSC, Accès Sect. France, T2 *)
- **Correction de nom** : 'Aile Est Arrivée Dispatch.' → 'Aile Est Arrivée dispatch'
- **Chargement des données** : remplacement de la grille vide par défaut par les 21 grilles jour-type × saison

```python
if cat == 'AT':
    # Charger les données AT depuis planif_AT_base.py
    for jour_saison, day_data in AT_DATA.items():
        st.session_state.planning_data[cat][jour_saison] = parse_grid_from_markers(day_data, perims)
```

## Format des données

Chaque grille est une liste de 39-40 éléments :
- `1` ou `np.nan` : poste occupé
- `0` ou absence : poste non occupé

La fonction `parse_grid_from_markers()` convertit automatiquement :
- `np.nan` + `1` → `1`
- Tout le reste → `0`
- Complète à 40 éléments si nécessaire

## Exemples de couverture

### Lundi Standard
- 13 périmètres actifs
- 345 créneaux horaires au total
- Périmètres principaux : Check-in, Aile Est Départ/Arrivée, Transit, Priority Lane

### Lundi Été
- 16 périmètres actifs (+3 vs Standard)
- Ajout : Accueil famille AE, Accueil famille CSC, Sect. France

### Samedi Hiver
- 20 périmètres actifs
- Inclut les 4 périmètres T2 (Terminal 2)
- Check in 3 actif

## Validation

Tests effectués :
- ✅ Import des données sans erreur
- ✅ 21 jour-types complets
- ✅ Toutes les grilles à 40 colonnes après parsing
- ✅ Périmètres saisonniers correctement assignés
- ✅ Intégration dans session_state fonctionnelle

## Utilisation

Au démarrage de l'application, les données AT sont automatiquement chargées dans `st.session_state.planning_data['AT']` avec les clés :

- "Lundi Standard", "Lundi Été", "Lundi Hiver"
- "Mardi Standard", "Mardi Été", "Mardi Hiver"
- ... (7 jours × 3 saisons)

Ces grilles servent de base pour la génération du budget annuel et peuvent être modifiées via l'interface de planification.
