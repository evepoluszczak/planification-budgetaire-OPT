# Refactoring du Planificateur Budgétaire OPT

## 📊 Statistiques du Refactoring

- **Avant**: 1 fichier monolithique de **3157 lignes**
- **Après**: Architecture modulaire avec **25 fichiers**
- **Fichier principal**: Réduit à **~200 lignes** (-93%)
- **Pages complètes**: 5 pages (1546 lignes au total)
- **Modules core/**: 4 fichiers (logique métier)
- **Modules utils/**: 3 fichiers (utilitaires)
- **Configuration**: 2 fichiers (constants + settings)
- **Maintenabilité**: Considérablement améliorée ✨

## 🏗️ Nouvelle Architecture

```
planification-budgetaire-OPT/
├── app.py                          # Point d'entrée principal (200 lignes)
├── app.py.backup                   # Backup de l'ancien fichier
│
├── config/                         # Configuration et constantes
│   ├── __init__.py
│   ├── constants.py               # Constantes globales, CSS, chemins
│   └── settings.py                # Configuration Streamlit
│
├── core/                          # Logique métier
│   ├── __init__.py
│   ├── budget.py                  # Génération du budget annuel
│   ├── planning.py                # Gestion des grilles de planification
│   ├── rules.py                   # Gestion des règles d'ajustement
│   └── data_loader.py             # Chargement PAX et facturation AT
│
├── models/                        # Modèles de données
│   ├── __init__.py
│   └── session_state.py           # Initialisation état session (base 2026)
│
├── utils/                         # Fonctions utilitaires
│   ├── __init__.py
│   ├── date_utils.py              # Utilitaires pour les dates
│   ├── export_import.py           # Export/Import Excel
│   └── helpers.py                 # Fonctions d'aide générales
│
└── ui/                            # Interface utilisateur
    ├── __init__.py
    ├── components.py              # Composants réutilisables
    └── pages/                     # Pages de l'application
        ├── __init__.py
        ├── configuration.py       # ✅ Page Configuration (complète)
        ├── budget_annuel.py       # 🚧 À migrer depuis app.py.backup
        ├── besoin_jour.py         # 🚧 À migrer depuis app.py.backup
        ├── comparaison_historique.py  # 🚧 À migrer depuis app.py.backup
        └── simulateur_objectif.py # 🚧 À migrer depuis app.py.backup
```

## ✅ Améliorations Apportées

### 1. **Séparation des Responsabilités**
   - Configuration isolée dans `config/`
   - Logique métier dans `core/`
   - Interface utilisateur dans `ui/`
   - Utilitaires réutilisables dans `utils/`

### 2. **Réduction de la Complexité**
   - Fichier principal divisé par 15
   - Fonctions courtes et ciblées
   - Imports explicites et organisés

### 3. **Maintenabilité**
   - Facile de trouver le code
   - Modifications localisées
   - Tests unitaires possibles par module

### 4. **Réutilisabilité**
   - Composants UI extraits
   - Fonctions utilitaires partagées
   - Logique métier découplée de l'UI

### 5. **Évolutivité**
   - Ajout de fonctionnalités facilité
   - Structure claire pour nouveaux développeurs
   - Documentation intégrée

## 🚀 Utilisation

### Démarrage de l'Application

```bash
streamlit run app.py
```

### Structure du Code

#### Point d'Entrée (app.py)
```python
# Imports organisés par modules
from config.settings import configure_streamlit, render_gva_header
from models.session_state import initialize_session_state_2026
from core.budget import generate_budget_state
# ...

# Configuration
configure_streamlit()

# Logique d'application simplifiée
if not st.session_state.data_loaded:
    # Écran d'accueil
else:
    # Pages de l'application
```

#### Modules Core

**budget.py** - Génération du budget
```python
from core.budget import generate_budget_state

# Génère le budget pour une année
generate_budget_state(year=2026)
```

**planning.py** - Gestion des grilles
```python
from core.planning import _ensure_grid, _apply_ops_to_grid

# Récupère ou crée une grille
grid = _ensure_grid(planning_dict, "Lundi Été", perimetres, time_slots)
```

**data_loader.py** - Chargement des données
```python
from core.data_loader import load_pax_data

# Charge les données PAX
pax_data, min_date, max_date = load_pax_data(file_path, "Passagers")
```

#### Composants UI

```python
from ui.components import show_help_dialog, planning_editor_ui

# Affiche la dialog d'aide
show_help_dialog()

# Affiche l'éditeur de planification
planning_editor_ui("AT", "AT")
```

## ✅ Toutes les Pages Migrées

Toutes les pages ont été complètement migrées et sont maintenant fonctionnelles !

### 1. Budget Annuel (`ui/pages/budget_annuel.py`) ✅
- **418 lignes** (vs ~298 dans l'original)
- Génération budget, KPIs, timeline saisons, détails mensuels/journaliers
- Imports optimisés depuis les modules core/

### 2. Besoin Jour (`ui/pages/besoin_jour.py`) ✅
- **534 lignes** (vs ~325 dans l'original)
- Ajustements ponctuels, gestion règles, aperçu grilles, données PAX
- Utilise les fonctions depuis core.planning et core.rules

### 3. Comparaison Historique (`ui/pages/comparaison_historique.py`) ✅
- **198 lignes** (vs ~156 dans l'original)
- Comparaison PAX historique vs prévisions, graphiques Altair
- Utilise core.data_loader pour les estimations AT

### 4. Simulateur Objectif (`ui/pages/simulateur_objectif.py`) ✅
- **198 lignes** (vs ~162 dans l'original)
- Simulation objectifs de coût, répartition par catégorie
- Interface claire et intuitive

### 5. Configuration (`ui/pages/configuration.py`) ✅
- **~170 lignes** (complètement nouvelle)
- Gestion personnel, périmètres, saisons de référence

## 🔧 Maintenance et Évolution

### Ajout d'une Nouvelle Fonctionnalité

1. **Logique métier** → Ajouter dans `core/`
2. **Interface** → Créer composant dans `ui/components.py` ou page dans `ui/pages/`
3. **Utilitaires** → Ajouter dans `utils/`
4. **Configuration** → Modifier `config/constants.py`

### Modification d'une Fonctionnalité Existante

1. Identifier le module concerné
2. Modifier le fichier approprié
3. Tester l'impact (imports localisés)

## 📦 Dépendances

Inchangées par rapport à la version originale:
- streamlit
- pandas
- numpy
- altair
- openpyxl

## 🎯 Étapes Complétées

1. ✅ Architecture créée et app.py refactorisé (200 lignes vs 3157)
2. ✅ Page Configuration migrée et fonctionnelle
3. ✅ Toutes les 4 pages restantes migrées avec succès
4. ✅ 25 fichiers modules créés et organisés
5. ✅ Documentation complète du refactoring

## 🚀 Prochaines Améliorations Possibles

1. 🔜 Ajouter des tests unitaires
2. 🔜 Documentation API détaillée des modules
3. 🔜 Optimisations de performance
4. 🔜 Ajout de logs structurés
5. 🔜 Cache amélioré pour les calculs lourds

## 💡 Bonnes Pratiques

### Imports
```python
# ✅ Bon - Imports explicites
from core.budget import generate_budget_state
from utils.helpers import clean_dataframe

# ❌ Éviter - Imports en étoile
from core.budget import *
```

### Organisation du Code
```python
# ✅ Bon - Fonctions courtes et ciblées
def calculate_daily_hours(grid_df):
    """Calcule les heures pour une grille jour-type"""
    return grid_df.values.sum() * 0.5

# ❌ Éviter - Fonctions monolithiques de 200+ lignes
```

### Documentation
```python
def process_data(df: pd.DataFrame) -> pd.DataFrame:
    """
    Traite les données en remplaçant les NaN et infinis.

    Args:
        df: DataFrame à traiter

    Returns:
        DataFrame nettoyé
    """
    # ...
```

## 🐛 Dépannage

### Erreur d'Import
```python
# Si vous voyez: ModuleNotFoundError: No module named 'config'
# Vérifiez que vous êtes dans le bon répertoire
cd /home/user/planification-budgetaire-OPT
streamlit run app.py
```

### Pages Manquantes
Les pages avec placeholders affichent un message d'avertissement.
Pour les compléter, suivez le processus de migration ci-dessus.

## 📞 Support

Pour toute question sur la nouvelle architecture:
1. Consulter ce README
2. Vérifier les docstrings dans les modules
3. Comparer avec `app.py.backup` si nécessaire

---

**Date du Refactoring**: 2025-10-23
**Version**: 2.0 (Architecture Modulaire)
**Ancienne Version**: Disponible dans `app.py.backup`
