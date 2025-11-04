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


def _normalize_number(s: str) -> float:
    """
    Convertit '292 292.00' ou '67 513,79' -> float, robuste aux espaces/virgule.
    """
    s = s.replace("\u00A0", " ").strip()
    # Si virgule est le séparateur décimal (fr), remplace par point
    if s.count(",") == 1 and s.rfind(",") > s.rfind("."):
        s = s.replace(".", "").replace(",", ".")
    else:
        s = s.replace(" ", "")
    try:
        return float(s)
    except Exception:
        # ultime fallback
        s2 = re.sub(r"[^\d\.\-]", "", s)
        return float(s2) if s2 else 0.0


def _infer_category_from_label(label: str) -> str:
    """
    Mappe le libellé 'Heures XXX' vers une catégorie courte.
    L'ordre est important: ATF/ATR avant AT pour éviter les faux positifs.
    """
    base = label.lower()

    if "atf" in base:
        return "ATF"
    if "atr" in base:
        return "ATR"
    if "coordinateur" in base:
        return "Coordinateurs"
    if "csc" in base:
        return "CSC"
    if "gestion d'accès" in base or "gestion d'acces" in base or "gestion d acces" in base:
        return "Gestion d'accès"
    if "visitor" in base:
        return "Visitor Center"
    # 'AT' doit venir après ATF/ATR pour ne pas les absorber
    if re.search(r"\bat\b", base):
        return "AT"

    # fallback: garder le dernier mot significatif après 'Heures'
    after = re.sub(r"^Heures?\s*", "", label, flags=re.IGNORECASE).strip()
    return after or label


def parse_invoice_pdf(pdf_path: Path) -> Dict:
    """
    Parse un PDF de facture et extrait les données avec un pattern robuste.

    Cherche des lignes structurées du type:
        PRIX(45.50)   QUANTITÉ(6424.000)   LIBELLÉ(Heures AT)   MONTANT(292 292.00)

    Args:
        pdf_path: Chemin vers le fichier PDF

    Returns:
        Dict avec:
        - 'month': int (mois)
        - 'year': int (année)
        - 'categories': Dict[str, Dict[str, float]]
            Exemple: {
                'AT': {'heures': 1234.5, 'cout': 56789.0, 'prix': 45.50},
                'Coordinateurs': {'heures': 234.5, 'cout': 12345.0, 'prix': 55.00}
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

            # Pattern regex robuste pour capturer:
            # Prix   Quantité   Libellé(Heures XXX)   Montant
            # Nombre tolérant (espaces insécables, virgule ou point)
            NUM = r"(?:\d{1,3}(?:[ \u00A0]\d{3})*|\d+)(?:[.,]\d+)?"
            LABEL = r"([A-Za-zÀ-ÖØ-öø-ÿ''().\-\/ ]+?)"

            ROW_PATTERN = re.compile(
                rf"(?P<price>{NUM})\s+(?P<qty>{NUM})\s+(?P<label>{LABEL})\s+(?P<amount>{NUM})",
                re.MULTILINE
            )

            categories = {}
            total_heures = 0.0
            total_cout = 0.0

            # Extraire toutes les lignes correspondant au pattern
            all_matches = []
            for match in ROW_PATTERN.finditer(all_text):
                price = _normalize_number(match.group("price"))
                qty = _normalize_number(match.group("qty"))
                amount = _normalize_number(match.group("amount"))
                label = match.group("label").strip()

                # Nettoyer les espaces multiples
                label = re.sub(r"\s{2,}", " ", label)

                # Filtrer: ne garder que les lignes "Heures XXX" ou "Heure XXX"
                # Pattern flexible: cherche "heure" ou "heures" (case insensitive)
                if not re.search(r"\bheure(s)?\b", label, re.IGNORECASE):
                    continue

                all_matches.append((price, qty, label, amount))

            # Afficher toutes les lignes capturées pour debug
            if all_matches:
                st.info(f"🔍 {len(all_matches)} lignes de facturation détectées dans {pdf_path.name}")
                for price, qty, label, amount in all_matches[:5]:  # Afficher max 5 premières
                    st.caption(f"  → '{label}': {qty:.1f}h × {price:.2f} = {amount:.2f} CHF")
                if len(all_matches) > 5:
                    st.caption(f"  ... et {len(all_matches) - 5} autres lignes")

            # Traiter chaque match
            for price, qty, label, amount in all_matches:
                # Inférer la catégorie depuis le libellé
                categorie = _infer_category_from_label(label)

                # Agréger si la catégorie existe déjà (facture avec lignes répétées)
                if categorie in categories:
                    categories[categorie]['heures'] += qty
                    categories[categorie]['cout'] += amount
                else:
                    categories[categorie] = {
                        'heures': qty,
                        'cout': amount,
                        'prix': price
                    }

            # Calculer les totaux
            if categories:
                total_heures = sum(cat['heures'] for cat in categories.values())
                total_cout = sum(cat['cout'] for cat in categories.values())

            # Debug: afficher ce qui a été extrait
            if categories:
                st.info(f"📄 {pdf_path.name} → {month}/{year} - {len(categories)} catégories extraites")
                for cat, vals in categories.items():
                    st.caption(f"  • {cat}: {vals['heures']:.1f}h × {vals['prix']:.2f} CHF/h = {vals['cout']:.2f} CHF")
            else:
                st.warning(f"⚠️ Aucune catégorie extraite de {pdf_path.name}")
                st.caption("Le PDF ne contient peut-être pas de lignes au format: Prix Quantité Libellé Montant")

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
