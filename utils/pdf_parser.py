"""
Parser pour les factures PDF mensuelles
"""
import re
from pathlib import Path
from typing import Dict, Tuple, Optional, List
import datetime as dt
import pandas as pd
import streamlit as st

try:
    import pdfplumber
    PDF_AVAILABLE = True
except ImportError:
    PDF_AVAILABLE = False
    st.warning("pdfplumber n'est pas installé. Les factures PDF ne peuvent pas être lues.")


def extract_month_year_from_pdf_filename(filename: str) -> Optional[Tuple[int, int]]:
    """
    Extrait le mois et l'année du nom de fichier PDF.

    Format attendu: F_5_XXXXXXX-YYYYMMDDHHMMSS.pdf
    Exemple: F_5_2609655-20251002095515.pdf → (10, 2025) pour octobre 2025

    Args:
        filename: Nom du fichier PDF

    Returns:
        Tuple (mois, année) ou None si le format n'est pas reconnu
    """
    # Pattern: F_5_XXXXXXX-YYYYMMDDHHMMSS.pdf
    pattern = r'F_\d+_\d+-(\d{4})(\d{2})\d{2}\d{6}\.pdf'
    match = re.match(pattern, filename)

    if match:
        year_str, month_str = match.groups()
        year = int(year_str)
        month = int(month_str)

        if 1 <= month <= 12:
            return (month, year)

    return None


def parse_invoice_pdf(pdf_path: Path) -> Dict:
    """
    Parse un PDF de facture et extrait les données.

    Structure attendue dans le PDF:
    - Catégories (AT, ATR, Coordinateurs, ATF, CSC, Sect. France, etc.)
    - Heures par catégorie
    - Coûts par catégorie

    Args:
        pdf_path: Chemin vers le fichier PDF

    Returns:
        Dict avec:
        - 'month': int (mois)
        - 'year': int (année)
        - 'categories': Dict[str, Dict[str, float]]
            Exemple: {
                'AT': {'heures': 1234.5, 'cout': 56789.0},
                'Coordinateurs': {'heures': 234.5, 'cout': 12345.0}
            }
        - 'total_heures': float
        - 'total_cout': float
        - 'filename': str
    """
    if not PDF_AVAILABLE:
        return {}

    # Extraire mois/année du nom du fichier
    month_year = extract_month_year_from_pdf_filename(pdf_path.name)
    if month_year is None:
        st.warning(f"Impossible d'extraire la date du nom de fichier: {pdf_path.name}")
        return {}

    month, year = month_year

    try:
        with pdfplumber.open(pdf_path) as pdf:
            # Extraire tout le texte du PDF
            all_text = ""
            for page in pdf.pages:
                all_text += page.extract_text() or ""

            # Parser les catégories et leurs valeurs
            categories = {}
            total_heures = 0.0
            total_cout = 0.0

            # Patterns courants pour détecter les catégories
            # Rechercher des lignes comme:
            # "AT              1234.50        56789.00"
            # "Coordinateurs   234.50         12345.00"

            lines = all_text.split('\n')

            for line in lines:
                # Nettoyer la ligne
                line = line.strip()

                # Pattern pour détecter une ligne de catégorie avec heures et coût
                # Exemple: "AT              1234.50        56789.00"
                #          "Coordinateurs   234.50         12345.00"
                parts = line.split()

                if len(parts) >= 3:
                    # Le dernier élément devrait être le coût
                    # L'avant-dernier devrait être les heures
                    # Tout avant devrait être le nom de la catégorie

                    try:
                        # Essayer de parser les 2 derniers éléments comme nombres
                        potential_cout = parts[-1].replace(',', '.').replace("'", "")
                        potential_heures = parts[-2].replace(',', '.').replace("'", "")

                        cout = float(potential_cout)
                        heures = float(potential_heures)

                        # Le reste est le nom de la catégorie
                        categorie = ' '.join(parts[:-2])

                        # Ignorer les lignes "Total", "Sous-total", etc. pour l'instant
                        if categorie and not any(x in categorie.lower() for x in ['total', 'sous-total', 'montant']):
                            categories[categorie] = {
                                'heures': heures,
                                'cout': cout
                            }
                    except (ValueError, IndexError):
                        # Pas une ligne de données valide
                        continue

            # Chercher aussi les totaux globaux
            # Pattern pour "Total" ou "TOTAL"
            for line in lines:
                if 'total' in line.lower() and 'sous' not in line.lower():
                    parts = line.split()
                    try:
                        if len(parts) >= 2:
                            potential_cout = parts[-1].replace(',', '.').replace("'", "")
                            potential_heures = parts[-2].replace(',', '.').replace("'", "")

                            total_cout = float(potential_cout)
                            total_heures = float(potential_heures)
                            break
                    except (ValueError, IndexError):
                        continue

            # Si on n'a pas trouvé de total, le calculer à partir des catégories
            if total_heures == 0 and categories:
                total_heures = sum(cat['heures'] for cat in categories.values())
            if total_cout == 0 and categories:
                total_cout = sum(cat['cout'] for cat in categories.values())

            return {
                'month': month,
                'year': year,
                'categories': categories,
                'total_heures': total_heures,
                'total_cout': total_cout,
                'filename': pdf_path.name,
                'date': dt.date(year, month, 1)  # Premier jour du mois
            }

    except Exception as e:
        st.error(f"Erreur lors de la lecture du PDF {pdf_path.name}: {e}")
        import traceback
        st.error(traceback.format_exc())
        return {}


def get_category_mapping_for_pdf(pdf_categories: List[str], app_categories: List[str]) -> Dict[str, str]:
    """
    Crée un mapping initial entre les catégories PDF et les catégories de l'app.

    Args:
        pdf_categories: Liste des catégories trouvées dans le PDF
        app_categories: Liste des catégories disponibles dans l'app

    Returns:
        Dict[str, str]: Mapping PDF category → App category
    """
    mapping = {}

    # Mappings prédéfinis
    predefined_mappings = {
        'coordinateurs': 'Coordinateur',
        'coordinateur': 'Coordinateur',
        'gestion d\'accès': 'Sect. France',
        'gestion d\'acces': 'Sect. France',
        'gestion acces': 'Sect. France',
        'sect france': 'Sect. France',
        'sect. france': 'Sect. France',
        'section france': 'Sect. France',
        'at': 'AT',
        'atr': 'ATR',
        'atf': 'ATF',
        'csc': 'CSC',
        'ees': 'EES'
    }

    for pdf_cat in pdf_categories:
        pdf_cat_lower = pdf_cat.lower().strip()

        # Chercher un mapping prédéfini
        if pdf_cat_lower in predefined_mappings:
            target = predefined_mappings[pdf_cat_lower]
            if target in app_categories:
                mapping[pdf_cat] = target
                continue

        # Chercher une correspondance exacte (insensible à la casse)
        exact_match = None
        for app_cat in app_categories:
            if pdf_cat.lower() == app_cat.lower():
                exact_match = app_cat
                break

        if exact_match:
            mapping[pdf_cat] = exact_match
        else:
            # Pas de mapping automatique - nécessitera une intervention manuelle
            mapping[pdf_cat] = None

    return mapping


def load_pdf_facturation_data(factu_dir: Path, year: int) -> pd.DataFrame:
    """
    Charge toutes les factures PDF pour une année donnée.

    Args:
        factu_dir: Répertoire contenant les factures
        year: Année à charger

    Returns:
        DataFrame avec colonnes: Date, [Heures_CATEGORY], [Cout_CATEGORY], Heures_Total, Cout_Total
    """
    if not PDF_AVAILABLE:
        return pd.DataFrame()

    # Pattern pour les fichiers PDF de facturation
    pattern = 'F_*.pdf'

    all_data = []
    all_categories = set()

    # Première passe: collecter toutes les catégories
    for pdf_path in factu_dir.glob(pattern):
        month_year = extract_month_year_from_pdf_filename(pdf_path.name)
        if month_year is None:
            continue

        month, file_year = month_year
        if file_year != year:
            continue

        data = parse_invoice_pdf(pdf_path)
        if data and 'categories' in data:
            all_categories.update(data['categories'].keys())

    # Deuxième passe: construire le DataFrame
    for pdf_path in factu_dir.glob(pattern):
        month_year = extract_month_year_from_pdf_filename(pdf_path.name)
        if month_year is None:
            continue

        month, file_year = month_year
        if file_year != year:
            continue

        data = parse_invoice_pdf(pdf_path)
        if not data or 'date' not in data:
            continue

        # Créer une ligne avec toutes les colonnes
        row = {'Date': data['date']}

        # Ajouter les heures et coûts par catégorie
        for cat in all_categories:
            if cat in data['categories']:
                row[f'Heures_{cat}'] = data['categories'][cat]['heures']
                row[f'Cout_{cat}'] = data['categories'][cat]['cout']
            else:
                row[f'Heures_{cat}'] = 0.0
                row[f'Cout_{cat}'] = 0.0

        # Ajouter les totaux
        row['Heures_Total'] = data.get('total_heures', 0.0)
        row['Cout_Total'] = data.get('total_cout', 0.0)

        all_data.append(row)

    if not all_data:
        return pd.DataFrame()

    # Créer le DataFrame
    df = pd.DataFrame(all_data)
    df = df.sort_values('Date').reset_index(drop=True)

    return df


def apply_category_mapping(df: pd.DataFrame, mapping: Dict[str, str]) -> pd.DataFrame:
    """
    Applique le mapping des catégories au DataFrame de facturation PDF.

    Args:
        df: DataFrame avec colonnes Heures_CATEGORY, Cout_CATEGORY
        mapping: Dict[pdf_category → app_category]

    Returns:
        DataFrame avec les catégories renommées selon le mapping
    """
    df_mapped = df.copy()

    for pdf_cat, app_cat in mapping.items():
        if app_cat is None:
            continue

        # Renommer les colonnes
        old_heures_col = f'Heures_{pdf_cat}'
        old_cout_col = f'Cout_{pdf_cat}'
        new_heures_col = f'Heures_{app_cat}'
        new_cout_col = f'Cout_{app_cat}'

        if old_heures_col in df_mapped.columns:
            # Si la nouvelle colonne existe déjà, additionner
            if new_heures_col in df_mapped.columns:
                df_mapped[new_heures_col] += df_mapped[old_heures_col]
                df_mapped[new_cout_col] += df_mapped[old_cout_col]
                df_mapped = df_mapped.drop(columns=[old_heures_col, old_cout_col])
            else:
                df_mapped = df_mapped.rename(columns={
                    old_heures_col: new_heures_col,
                    old_cout_col: new_cout_col
                })

    return df_mapped
