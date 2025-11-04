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

    IMPORTANT: La date dans le nom de fichier correspond à la date de RÉCEPTION,
    donc il faut soustraire 1 mois pour obtenir le mois facturé.

    Format attendu: F_5_XXXXXXX-YYYYMMDDHHMMSS.pdf
    Exemple: F_5_2624308-20251104112400.pdf → 2025-11-04 (reçu) → octobre 2025 (facturé)

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
            # Créer une date pour soustraire 1 mois
            reception_date = dt.date(year, month, 1)
            # Soustraire 1 mois pour obtenir le mois facturé
            if month == 1:
                # Janvier → Décembre de l'année précédente
                facture_month = 12
                facture_year = year - 1
            else:
                facture_month = month - 1
                facture_year = year

            return (facture_month, facture_year)

    return None


def parse_invoice_pdf(pdf_path: Path) -> Dict:
    """
    Parse un PDF de facture et extrait les données.

    Structure attendue dans le PDF (2 formats possibles):
    Format 1 (avec mots-clés):
        Heures AT : Quantité: 6 424.000 Prix: 45.50 Montant: 292 292.00
    Format 2 (sans mots-clés):
        Heures Coordinateurs: 472.500 55.00 25 987.50

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

            lines = all_text.split('\n')

            # Patterns de parsing
            # Format 1: Heures <CATEGORY> : Quantité: 6 424.000 Prix: 45.50 Montant: 292 292.00
            # Format 2: Heures <CATEGORY>: 472.500 55.00 25 987.50
            # Format 3: <CATEGORY>: 217.000 45.50 9 873.50 (sans "Heures")

            for line in lines:
                line = line.strip()
                if not line:
                    continue

                # Format 1: avec mots-clés "Quantité" et "Montant"
                if 'quantité' in line.lower() or 'quantite' in line.lower():
                    # Extraire le nom de catégorie (après "Heures" et avant "Quantité")
                    category_match = re.match(r'.*?heures\s+([^:]+?)[\s:]+(?:quantit[ée]|quantit[ée])', line, re.IGNORECASE)
                    if category_match:
                        categorie = category_match.group(1).strip()
                    else:
                        continue

                    # Extraire Quantité (heures)
                    quant_match = re.search(r'quantit[ée]\s*:\s*([\d\s]+\.\d+)', line, re.IGNORECASE)
                    if quant_match:
                        heures_str = quant_match.group(1).replace(' ', '')
                        heures = float(heures_str)
                    else:
                        continue

                    # Extraire Montant (coût)
                    montant_match = re.search(r'montant\s*:\s*([\d\s]+\.\d+)', line, re.IGNORECASE)
                    if montant_match:
                        cout_str = montant_match.group(1).replace(' ', '')
                        cout = float(cout_str)
                    else:
                        continue

                    categories[categorie] = {
                        'heures': heures,
                        'cout': cout
                    }

                # Format 2 & 3: sans mots-clés, juste 3 nombres (heures, prix unitaire, montant)
                elif ':' in line and any(keyword in line.lower() for keyword in ['heures', 'at', 'atr', 'atf', 'csc', 'coordinateur', 'gestion', 'visitor']):
                    # Extraire le nom de catégorie (avant le ":")
                    parts = line.split(':')
                    if len(parts) < 2:
                        continue

                    categorie_part = parts[0].strip()
                    # Enlever "Heures" du début si présent
                    if categorie_part.lower().startswith('heures'):
                        categorie = categorie_part[6:].strip()
                    else:
                        categorie = categorie_part

                    # La partie après ":" contient les nombres
                    numbers_part = ':'.join(parts[1:])

                    # Extraire tous les nombres (en gérant les espaces dans les milliers)
                    # Pattern: cherche des nombres avec espaces optionnels (ex: "6 424.000" ou "292 292.00")
                    number_pattern = r'([\d\s]+\.\d+)'
                    numbers = re.findall(number_pattern, numbers_part)

                    if len(numbers) >= 3:
                        # Format: Quantité Prix Montant
                        # On prend le premier (heures) et le dernier (montant)
                        heures_str = numbers[0].replace(' ', '')
                        cout_str = numbers[-1].replace(' ', '')
                        heures = float(heures_str)
                        cout = float(cout_str)

                        categories[categorie] = {
                            'heures': heures,
                            'cout': cout
                        }
                    elif len(numbers) == 2:
                        # Juste 2 nombres: heures et montant
                        heures_str = numbers[0].replace(' ', '')
                        cout_str = numbers[1].replace(' ', '')
                        heures = float(heures_str)
                        cout = float(cout_str)

                        categories[categorie] = {
                            'heures': heures,
                            'cout': cout
                        }

            # Chercher les totaux globaux
            for line in lines:
                if 'total' in line.lower() and 'sous' not in line.lower():
                    # Chercher le dernier montant dans la ligne
                    number_pattern = r'([\d\s]+\.\d+)'
                    numbers = re.findall(number_pattern, line)

                    if len(numbers) >= 2:
                        # Prendre les 2 derniers: heures et coût
                        heures_str = numbers[-2].replace(' ', '')
                        cout_str = numbers[-1].replace(' ', '')
                        try:
                            total_heures = float(heures_str)
                            total_cout = float(cout_str)
                            break
                        except ValueError:
                            continue

            # Si on n'a pas trouvé de total, le calculer à partir des catégories
            if total_heures == 0 and categories:
                total_heures = sum(cat['heures'] for cat in categories.values())
            if total_cout == 0 and categories:
                total_cout = sum(cat['cout'] for cat in categories.values())

            # Debug: afficher ce qui a été extrait
            if categories:
                st.info(f"📄 {pdf_path.name} → {month}/{year} - {len(categories)} catégories extraites")
                for cat, vals in categories.items():
                    st.caption(f"  • {cat}: {vals['heures']:.1f}h → {vals['cout']:.2f} CHF")
            else:
                st.warning(f"⚠️ Aucune catégorie extraite de {pdf_path.name}")

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
        'visitor center': 'Visitor Center',
        'visitors center': 'Visitor Center',
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
