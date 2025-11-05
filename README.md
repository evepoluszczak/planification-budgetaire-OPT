# Planification Budgétaire OPT - Aéroport de Genève

## Description

Application web de planification budgétaire et de gestion des ressources pour les opérations passagers trafic (OPT) de l'Aéroport de Genève. Cette application permet de gérer les prévisions budgétaires, d'analyser les besoins en personnel AT (Agent de Trafic) et de comparer les coûts prévus aux coûts réels.

## Fonctionnalités Principales

### 1. Budget Annuel
- Génération automatique du budget annuel basé sur les plannings
- Visualisation des coûts par mois, catégorie et périmètre
- Indicateurs clés de performance (KPIs)
- Comparaison de scénarios budgétaires
- Timeline interactive des saisons (Standard, Été, Hiver)
- Export Excel des budgets

### 2. Besoin Jour
- Calcul des besoins journaliers en personnel selon les prévisions PAX
- Grilles de planification par type de jour (21 types : 7 jours × 3 saisons)
- 22 périmètres de l'aéroport couverts
- Gestion des règles d'ajustement personnalisées
- Visualisation des impacts budgétaires en temps réel

### 3. Analyse Budgétaire
- Comparaison budget prévisionnel vs réel
- Chargement automatique des factures (Excel et PDF)
- Analyse mensuelle détaillée des écarts
- Détection automatique des formats de facturation
- Indicateurs de performance (écarts, pourcentages)

### 4. Comparaison Historique
- Comparaison des données PAX historiques vs prévisions
- Analyse des tendances de fréquentation
- Estimation des heures AT basée sur les variations PAX
- Graphiques interactifs de comparaison

### 5. Simulateur d'Objectifs
- Simulation d'objectifs de coûts annuels
- Répartition par catégorie avec pourcentages personnalisables
- Calcul automatique de l'impact en heures
- Validation en temps réel des saisies

### 6. Configuration
- Gestion des règles d'ajustement (création, modification, suppression)
- Configuration des périmètres et catégories
- Gestion des saisons de référence
- Sauvegarde automatique des paramètres

## Installation

### Prérequis
- Python 3.8 ou supérieur
- pip (gestionnaire de paquets Python)

### Étapes d'installation

1. **Cloner ou télécharger le projet**
```bash
git clone <url-du-repo>
cd planification-budgetaire-OPT
```

2. **Créer un environnement virtuel (recommandé)**
```bash
python -m venv venv

# Windows
venv\Scripts\activate

# Linux/Mac
source venv/bin/activate
```

3. **Installer les dépendances**
```bash
pip install -r requirements.txt
```

## Démarrage de l'Application

```bash
streamlit run app.py
```

L'application s'ouvrira automatiquement dans votre navigateur par défaut à l'adresse `http://localhost:8501`

## Utilisation

### Premier Démarrage

Lors du premier lancement, vous avez 3 options :

1. **Charger Base 2026** : Charge les données de planification de base pour l'année 2026
2. **Importer depuis Excel** : Importe un état de session précédemment exporté
3. **Reprendre Session** : Reprend la dernière session sauvegardée automatiquement

### Chargement des Données PAX

Après le démarrage, cliquez sur le bouton **"Charger données PAX"** dans la barre latérale pour :
- Charger les prévisions PAX (Forecast_pax.xlsx)
- Charger l'historique PAX (Historic_pax.xlsx)

Le chargement se fait en arrière-plan et ne bloque pas l'utilisation de l'application.

### Navigation

Utilisez le menu de navigation dans la barre latérale pour accéder aux différentes pages :
- Budget Annuel
- Besoin Jour
- Analyse Budgétaire
- Comparaison Historique
- Simulateur Objectif
- Configuration

### Sauvegarde et Export

#### Sauvegarde Automatique
L'application sauvegarde automatiquement votre session toutes les 30 secondes dans le fichier `session_autosave.json`.

#### Export Manuel
Utilisez le bouton **"Exporter l'état complet"** dans la barre latérale pour créer une sauvegarde Excel complète incluant :
- Budgets annuels
- Grilles de planification
- Règles d'ajustement
- Paramètres de configuration

## Structure des Fichiers

### Fichiers de Données d'Entrée

Placez vos fichiers de données dans le dossier `input_files/` :

```
input_files/
├── Forecast_pax.xlsx        # Prévisions PAX futures
├── Historic_pax.xlsx         # Données PAX historiques
└── facturation/             # Fichiers de facturation
    ├── Facturation Lot A *.xlsx  # Factures mensuelles Excel
    └── F_5_*.pdf                 # Factures PDF (nouveau format)
```

#### Format des Fichiers PAX

**Forecast_pax.xlsx** et **Historic_pax.xlsx** doivent contenir :
- Colonne `Date` : dates au format date Excel
- Colonne `Dep` : nombre de passagers départs
- Colonne `Arr` : nombre de passagers arrivées

Pour plus de détails, consultez `input_files/README.md`

#### Format des Fichiers de Facturation

**Fichiers Excel** : Format "Facturation Lot A MM-YYYY.xlsx"
- Colonnes : Date, Catégorie, Périmètre, Heures, Coût

**Fichiers PDF** : Format "F_5_YYYYMM_description.pdf"
- Extraction automatique des données tabulaires

Pour plus de détails, consultez `FACTURATION_PDF_README.md`

### Fichiers de Configuration

- `.streamlit/config.toml` : Configuration de l'interface Streamlit
- `config/constants.py` : Constantes globales (chemins, CSS, tranches horaires)
- `config/settings.py` : Configuration de la page Streamlit

### Fichiers de Sortie

- `session_autosave.json` : Sauvegarde automatique de la session
- `regles_besoin_jour.json` : Règles d'ajustement sauvegardées
- Exports Excel : générés à la demande via le bouton d'export

## Architecture Technique

L'application est organisée en modules distincts pour une meilleure maintenabilité :

```
planification-budgetaire-OPT/
├── app.py                   # Point d'entrée principal
├── config/                  # Configuration globale
├── core/                    # Logique métier
│   ├── budget.py           # Génération budgets
│   ├── data_loader.py      # Chargement données
│   ├── planning.py         # Gestion plannings
│   └── rules.py            # Gestion règles
├── models/                  # Modèles de données
│   ├── planif_AT_base.py   # Plannings de base
│   └── session_state.py    # État de session
├── ui/                      # Interface utilisateur
│   ├── components.py       # Composants réutilisables
│   └── pages/              # Pages de l'application
└── utils/                   # Utilitaires
    ├── async_loader.py     # Chargement asynchrone
    ├── autosave.py         # Sauvegarde automatique
    ├── date_utils.py       # Utilitaires dates
    ├── export_import.py    # Export/Import Excel
    ├── helpers.py          # Fonctions d'aide
    └── invoice_reader.py   # Lecture factures PDF
```

## Dépendances Principales

- **Streamlit** (≥1.28.0) : Framework d'application web
- **Pandas** (≥2.0.0) : Manipulation de données
- **NumPy** (≥1.24.0) : Calculs numériques
- **Altair** (≥5.0.0) : Visualisations interactives
- **OpenPyXL** (≥3.1.0) : Lecture/écriture Excel
- **pdfplumber** (≥0.10.0) : Extraction de données PDF
- **PyPDF2** (≥3.0.0) : Traitement PDF

## Résolution de Problèmes

### L'application ne démarre pas
1. Vérifiez que Python 3.8+ est installé : `python --version`
2. Vérifiez que toutes les dépendances sont installées : `pip list`
3. Réinstallez les dépendances : `pip install -r requirements.txt --force-reinstall`

### Erreur de chargement des fichiers PAX
1. Vérifiez que les fichiers sont bien dans `input_files/`
2. Vérifiez le format des colonnes (Date, Dep, Arr)
3. Consultez `input_files/README.md` pour les spécifications exactes

### Erreur de chargement des factures
1. Vérifiez le format des noms de fichiers
2. Pour les PDF, consultez `FACTURATION_PDF_README.md`
3. Vérifiez que les fichiers ne sont pas corrompus

### La session ne se sauvegarde pas
1. Vérifiez les permissions d'écriture dans le dossier de l'application
2. Supprimez `session_autosave.json` et relancez l'application

### Les graphiques ne s'affichent pas
1. Videz le cache du navigateur
2. Essayez un autre navigateur (Chrome, Firefox recommandés)
3. Vérifiez la console JavaScript du navigateur pour les erreurs

## Documentation Complémentaire

- `FACTURATION_PDF_README.md` : Spécifications détaillées des formats de facturation PDF
- `input_files/README.md` : Guide des fichiers de données d'entrée
- `docs/AT_DATA_INTEGRATION.md` : Structure des données de planification AT
- `docs/CHARGEMENT_PAX_ASYNC.md` : Documentation du chargement asynchrone PAX

## Concepts Clés

### Types de Jour
21 types de jour différents combinant :
- **7 jours de la semaine** : Lundi, Mardi, Mercredi, Jeudi, Vendredi, Samedi, Dimanche
- **3 saisons** : Standard, Été, Hiver

Exemples : "Lundi Standard", "Samedi Été", "Dimanche Hiver"

### Périmètres
22 zones de l'aéroport nécessitant du personnel AT :
- TRAD (Trafic Traditionnel)
- DI (Dépose Immédiate)
- PC (Parking Couvert)
- SCHENGEN, etc.

### Tranches Horaires
40 tranches de 30 minutes de 04:00 à 23:30

### Catégories de Personnel
- **CAT1** : Personnel principal
- **CAT2** : Personnel secondaire
- **CAT3** : Personnel support

### Saisons
- **Standard** : Périodes normales d'activité
- **Été** : Haute saison estivale (juin-septembre)
- **Hiver** : Saison hivernale (décembre-mars)

## Support et Contact

Pour toute question ou problème :
1. Consultez d'abord cette documentation et les fichiers README spécifiques
2. Vérifiez les messages d'erreur dans l'interface
3. Contactez l'équipe de support technique de l'Aéroport de Genève

## Licence

Propriété de l'Aéroport International de Genève.
Tous droits réservés.

---

**Version** : 2.0 (Architecture modulaire)
**Dernière mise à jour** : Novembre 2025
**Développé pour** : Aéroport International de Genève - Opérations Passagers Trafic (OPT)
