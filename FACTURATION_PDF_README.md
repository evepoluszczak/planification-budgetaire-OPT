# Support des Factures PDF

## 📋 Vue d'ensemble

L'application supporte maintenant les factures PDF mensuelles en complément (ou remplacement) des fichiers Excel. Les PDFs sont automatiquement détectés et intégrés dans les analyses budgétaires.

## 📁 Format de fichier attendu

### Nom de fichier

```
F_5_XXXXXXX-YYYYMMDDHHMMSS.pdf
```

**Exemples:**
- `F_5_2609655-20251002095515.pdf` → Octobre 2025
- `F_5_2624308-20251104112400.pdf` → Novembre 2025

**Extraction automatique:**
- Le mois et l'année sont extraits du timestamp dans le nom de fichier
- Format du timestamp: `YYYYMMDD` (Année-Mois-Jour)

### Contenu du PDF

Le PDF doit contenir un tableau structuré avec:
- **Catégories** (AT, ATR, Coordinateurs, ATF, CSC, Sect. France, etc.)
- **Heures** par catégorie
- **Coûts** par catégorie (optionnel mais recommandé)

**Exemple de structure:**

```
Catégorie          Heures      Coût
----------------------------------------
AT                 1234.50     56789.00
Coordinateurs       234.50     12345.00
CSC                 456.00     20000.00
Sect. France        123.00      6500.00
----------------------------------------
TOTAL             2048.00     95634.00
```

## 🔧 Installation

Pour activer le support PDF, installez la dépendance `pdfplumber`:

```bash
pip install pdfplumber
```

Ou installez toutes les dépendances:

```bash
pip install -r requirements.txt
```

## 📍 Emplacement des fichiers

Placez les fichiers PDF dans le répertoire:

```
input_files/facturation/
```

**Organisation recommandée:**
```
input_files/
└── facturation/
    ├── Facturation Lot A 01.2025.xlsx    # Excel (format ancien)
    ├── F_5_2609655-20251002095515.pdf     # PDF Octobre 2025
    ├── F_5_2624308-20251104112400.pdf     # PDF Novembre 2025
    └── ...
```

## 🗺️ Mapping des catégories

### Mappings automatiques

L'application détecte automatiquement les catégories PDF et crée des mappings basés sur des règles prédéfinies:

| Catégorie PDF | Catégorie App | Note |
|---|---|---|
| `Coordinateurs` | `Coordinateur` | Pluriel → Singulier |
| `Gestion d'accès` | `Sect. France` | Alias |
| `AT`, `ATR`, `ATF` | Identique | Correspondance exacte |
| `CSC`, `EES` | Identique | Correspondance exacte |

### Configuration manuelle

Si une catégorie PDF n'est pas reconnue automatiquement:

1. Allez dans **Configuration → 4 - Mapping des Catégories PDF**
2. Sélectionnez la catégorie de l'app correspondante dans la liste déroulante
3. Cliquez sur "Appliquer" pour sauvegarder

**Le mapping est persistant** et sera réutilisé pour tous les PDFs futurs.

## 📊 Utilisation dans l'application

### Analyse Budgétaire

Les données PDF sont automatiquement chargées et fusionnées avec les données Excel:

1. Allez sur la page **Analyse Budgétaire**
2. Sélectionnez l'année
3. Les PDFs de l'année sélectionnée sont automatiquement chargés
4. Les données sont affichées dans les graphiques et tableaux

### Compatibilité Excel + PDF

- **Les deux formats sont supportés** simultanément
- **Fusion automatique** des données par date
- **Priorité:** Si les deux existent pour le même mois, les deux sont inclus
- **Harmonisation:** Les colonnes sont normalisées (Excel: `Heures` → `Heures_AT`)

## 🐛 Dépannage

### "pdfplumber n'est pas installé"

```bash
pip install pdfplumber
```

### "Impossible d'extraire la date du nom de fichier"

Vérifiez que le nom du fichier respecte le format:
```
F_5_XXXXXXX-YYYYMMDDHHMMSS.pdf
```

### "Catégorie PDF non reconnue"

1. Allez dans **Configuration → 4 - Mapping des Catégories PDF**
2. Mappez manuellement la catégorie
3. Rechargez les données

### "Aucune donnée extraite du PDF"

Le parser recherche un tableau avec des lignes contenant:
- Un nom de catégorie
- Des valeurs numériques (heures et coûts)

Si le format du PDF est très différent, contactez le support.

## 🔄 Migration Excel → PDF

Pour migrer progressivement des Excel vers les PDF:

1. **Phase 1:** Garder les deux formats (recommandé pour transition)
2. **Phase 2:** Ajouter uniquement les nouveaux mois en PDF
3. **Phase 3:** Conserver les Excel historiques, nouveaux mois en PDF uniquement

**L'application gère automatiquement** les deux formats sans configuration supplémentaire.

## 📝 Notes techniques

### Extraction du texte

- Utilise `pdfplumber` pour extraire le texte structuré
- Parse ligne par ligne pour détecter les catégories
- Conversion automatique des virgules (`,`) en points (`.`) pour les nombres
- Support des séparateurs de milliers (`'` ou ` `)

### Structure des données

**Données exportées par le parser:**
```python
{
    'month': 10,                    # Mois (1-12)
    'year': 2025,                   # Année
    'categories': {
        'AT': {
            'heures': 1234.5,
            'cout': 56789.0
        },
        'Coordinateurs': {
            'heures': 234.5,
            'cout': 12345.0
        }
    },
    'total_heures': 2048.0,
    'total_cout': 95634.0,
    'filename': 'F_5_2609655-20251002095515.pdf',
    'date': date(2025, 10, 1)      # Premier jour du mois
}
```

### Intégration dans `calendar_df`

Les données PDF sont intégrées dans la structure existante:
- Une ligne par mois
- Colonnes: `Date`, `Heures_CATEGORY`, `Cout_CATEGORY`, `Heures_Total`, `Cout_Total`
- Fusion avec les données de planification pour analyse comparative

## 🆘 Support

Pour toute question ou problème:
1. Vérifiez ce README
2. Consultez les logs de l'application (erreurs affichées en rouge)
3. Vérifiez la page **Configuration → 4 - Mapping des Catégories PDF**
