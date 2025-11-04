"""
Parser robuste pour les factures PDF mensuelles OPT

Fonctionnalités :
- Capture la 1ère ligne "Heures AT" (pas de gate/skip)
- Nettoyage des caractères invisibles (NBSP, ligatures)
- Parsing robuste tables + texte
- Déduplication par hash de fichier + (Catégorie, Heures, Coût)
- Cache Streamlit optionnel
"""
from __future__ import annotations
import re
import hashlib
import unicodedata
import datetime as dt
from pathlib import Path
from typing import Dict, Tuple, Optional, List

import pandas as pd
import streamlit as st

# --- Imports PDF avec fallback ---
try:
    import pdfplumber
    PDF_AVAILABLE = True
except ImportError:
    pdfplumber = None
    PDF_AVAILABLE = False

try:
    from PyPDF2 import PdfReader
    PYPDF2_AVAILABLE = True
except ImportError:
    PdfReader = None
    PYPDF2_AVAILABLE = False

if not PDF_AVAILABLE and not PYPDF2_AVAILABLE:
    st.warning("⚠️ Aucune bibliothèque PDF disponible (pdfplumber ou PyPDF2). Les factures PDF ne peuvent pas être lues.")


# --- Catégories acceptées + alias possibles ---
CATEGORY_ALIASES = {
    "AT": ["AT", "Heures AT", "Heure AT", "AT (heures)", "Assistants Tarmac"],
    "ATR": ["ATR", "Heures ATR", "Heure ATR"],
    "Coordinateurs": ["Coordinateurs", "Coordinateur", "Coord", "Heures Coordinateurs", "Heure Coordinateurs"],
    "ATF": ["ATF", "Heures ATF", "Heure ATF", "Formateurs AT"],
    "CSC": ["CSC", "Heures CSC", "Heure CSC"],
    "Gestion d'accès": ["Gestion d'accès", "Gestion d'acces", "Gestion acces", "Gestion d accès"],
    "Visitor Center": ["Visitor Center", "Visitor Centre", "Visitors Center"],
    "EES": ["EES", "Heures EES", "Heure EES"],
}

# Pattern générique : capture heures & coût (tolérant aux espaces/virgules/points/CHF)
HOURS_RE = r"(?P<hours>\d+(?:[.,\s]\d+)?)\s*h(?:eures?)?"
COST_RE = r"(?P<cost>\d{1,3}(?:[.'\s]\d{3})*(?:[.,]\d+)?|\d+(?:[.,]\d+)?)\s*(?:CHF|Fr\.?|Frs?)?"

# Patterns de lignes compilés
LINE_TEMPLATES: List[re.Pattern] = []


def _compile_line_templates():
    """Compile les patterns regex pour chaque alias de catégorie"""
    global LINE_TEMPLATES
    if LINE_TEMPLATES:
        return
    for canon, aliases in CATEGORY_ALIASES.items():
        for label in aliases:
            # tolérance : "Heures AT", "AT Heures", "AT"
            pat = rf"(?i)\b{re.escape(label)}\b.*?(?:{HOURS_RE}).*?(?:{COST_RE})"
            LINE_TEMPLATES.append((re.compile(pat), canon))


_compile_line_templates()


def _normalize_text(s: str) -> str:
    """
    Normalisation unicode + suppression NBSP et espaces multiples
    """
    s = unicodedata.normalize("NFKC", s)
    s = s.replace("\xa0", " ").replace("\u202f", " ").replace("\u2009", " ")
    s = s.replace("'", "'")  # unifie les apostrophes
    s = re.sub(r"\s+", " ", s).strip()
    return s


def _to_float(num: str) -> float:
    """
    Convertit "5'678.00" / "5 678,00" / "5678" en float
    """
    if num is None:
        return 0.0
    n = num.replace("'", "").replace(" ", "")
    # SI virgule décimale présente -> passer en point
    if "," in n and "." in n:
        # heuristique : si dernier séparateur est ',', c'est la décimale
        if n.rfind(",") > n.rfind("."):
            n = n.replace(".", "").replace(",", ".")
        else:
            n = n.replace(",", "")
    else:
        n = n.replace(",", ".")
    try:
        return float(n)
    except Exception:
        return 0.0


def _categorize(line: str) -> Optional[str]:
    """
    Retourne la catégorie canon à partir d'une ligne
    """
    for canon, aliases in CATEGORY_ALIASES.items():
        for alias in aliases:
            if re.search(rf"(?i)\b{re.escape(alias)}\b", line):
                return canon
    return None


def _parse_line(line: str) -> Optional[Tuple[str, float, float]]:
    """
    Tente d'extraire (Catégorie canon, Heures, Coût) depuis une ligne normalisée.
    Capte aussi la 1ʳᵉ ligne 'Heures AT' (pas de gate).
    """
    norm = _normalize_text(line)
    cat = _categorize(norm)
    if not cat:
        return None

    hours = None
    cost = None

    # extraction des nombres (heures + coût) même si l'ordre varie
    # 1) heures
    m_h = re.search(HOURS_RE, norm, flags=re.I)
    if m_h:
        hours = _to_float(m_h.group("hours"))

    # 2) coût
    m_c = re.search(COST_RE, norm, flags=re.I)
    if m_c:
        cost = _to_float(m_c.group("cost"))

    if hours is None and cost is None:
        # second essai: template complet
        for pat, template_cat in LINE_TEMPLATES:
            m = pat.search(norm)
            if m:
                try:
                    hours = _to_float(m.group("hours"))
                    cost = _to_float(m.group("cost"))
                    cat = template_cat  # utilise la catégorie du template
                    break
                except:
                    continue

    if hours is None and cost is None:
        return None

    return (cat, float(hours or 0.0), float(cost or 0.0))


def _pdf_file_hash(pdf_path: Path) -> str:
    """Calcule le hash SHA256 du fichier PDF pour déduplication"""
    h = hashlib.sha256()
    with open(pdf_path, "rb") as f:
        while True:
            chunk = f.read(1 << 20)  # 1MB chunks
            if not chunk:
                break
            h.update(chunk)
    return h.hexdigest()


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


def parse_invoice_pdf(pdf_path: Path) -> pd.DataFrame:
    """
    Parse un PDF de facture mensuelle.
    Retourne un DataFrame: [file, file_hash, month, year, categorie, heures, cout]

    - Capture la toute 1ʳᵉ ligne ('Heures AT') grâce à l'absence de gate.
    - Déduplique les lignes identiques au sein du PDF.
    """
    pdf_path = Path(pdf_path)

    if not pdf_path.exists():
        st.warning(f"⚠️ Fichier introuvable: {pdf_path}")
        return pd.DataFrame()

    file_hash = _pdf_file_hash(pdf_path)

    # Trouve mois/année via le nom
    month_year = extract_month_year_from_pdf_filename(pdf_path.name)
    if month_year is None:
        st.warning(f"⚠️ Impossible d'extraire la date du nom de fichier: {pdf_path.name}")
        return pd.DataFrame()

    month, year = month_year

    rows: List[Tuple[str, float, float]] = []
    seen_row_keys = set()

    # 1) Essai table via pdfplumber
    if pdfplumber is not None:
        try:
            with pdfplumber.open(str(pdf_path)) as pdf:
                for page in pdf.pages:
                    # tables d'abord
                    tables = page.extract_tables() or []
                    for tb in tables:
                        for raw_row in tb:
                            if not raw_row:
                                continue
                            line = " ".join([_normalize_text(str(x or "")) for x in raw_row])
                            parsed = _parse_line(line)
                            if parsed:
                                key = (parsed[0], round(parsed[1], 3), round(parsed[2], 2))
                                if key not in seen_row_keys:
                                    rows.append(parsed)
                                    seen_row_keys.add(key)

                    # puis texte (au cas où la 1ʳᵉ ligne n'était pas tabulée)
                    text = page.extract_text() or ""
                    for line in text.splitlines():
                        parsed = _parse_line(line)
                        if parsed:
                            key = (parsed[0], round(parsed[1], 3), round(parsed[2], 2))
                            if key not in seen_row_keys:
                                rows.append(parsed)
                                seen_row_keys.add(key)
        except Exception as e:
            st.warning(f"⚠️ Erreur pdfplumber pour {pdf_path.name}: {e}")

    # 2) Fallback PyPDF2 si rien vu
    if not rows and PdfReader is not None:
        try:
            reader = PdfReader(str(pdf_path))
            for p in reader.pages:
                txt = p.extract_text() or ""
                for line in txt.splitlines():
                    parsed = _parse_line(line)
                    if parsed:
                        key = (parsed[0], round(parsed[1], 3), round(parsed[2], 2))
                        if key not in seen_row_keys:
                            rows.append(parsed)
                            seen_row_keys.add(key)
        except Exception as e:
            st.warning(f"⚠️ Erreur PyPDF2 pour {pdf_path.name}: {e}")

    # Construire le DataFrame
    data = []
    for cat, h, c in rows:
        data.append({
            "file": pdf_path.name,
            "file_hash": file_hash,
            "year": year,
            "month": month,
            "categorie": cat,
            "heures": h,
            "cout": c
        })

    df = pd.DataFrame(data)

    # Consolidation (dedup stricte)
    if not df.empty:
        df = (df.groupby(["file_hash", "file", "year", "month", "categorie"], as_index=False)
                .agg({"heures": "sum", "cout": "sum"}))

    # Debug: afficher ce qui a été extrait
    if not df.empty:
        st.info(f"📄 {pdf_path.name} → {month}/{year} - {len(df)} catégories extraites")
        for _, row in df.iterrows():
            prix = row['cout'] / row['heures'] if row['heures'] > 0 else 0
            st.caption(f"  • {row['categorie']}: {row['heures']:.1f}h × {prix:.2f} CHF/h = {row['cout']:.2f} CHF")
    else:
        st.warning(f"⚠️ Aucune catégorie extraite de {pdf_path.name}")
        st.caption("Le PDF ne contient peut-être pas de lignes au format attendu (Catégorie + Heures + Coût)")

    return df


def load_pdf_facturation_data(factu_dir: Path, year: int) -> pd.DataFrame:
    """
    Lit toutes les factures PDF du dossier pour une année donnée.
    - Évite de compter 2x le même PDF (basé sur hash).
    - Optimisé pour une seule lecture par fichier.

    Returns:
        DataFrame avec colonnes: Date, [Heures_CATEGORY], [Cout_CATEGORY], Heures_Total, Cout_Total
    """
    if not PDF_AVAILABLE and not PYPDF2_AVAILABLE:
        return pd.DataFrame()

    factu_dir = Path(factu_dir)
    if not factu_dir.exists():
        st.warning(f"⚠️ Répertoire introuvable: {factu_dir}")
        return pd.DataFrame()

    # Trouver tous les PDFs
    pdfs = sorted([p for p in factu_dir.glob("F_*.pdf") if p.is_file()])

    if not pdfs:
        return pd.DataFrame()

    all_parts = []
    seen_hashes = set()

    for pdf_path in pdfs:
        # Filtrer par année d'abord (évite de parser des fichiers non pertinents)
        month_year = extract_month_year_from_pdf_filename(pdf_path.name)
        if month_year is None:
            continue

        pdf_month, pdf_year = month_year
        if pdf_year != year:
            continue

        # Parser le PDF
        df = parse_invoice_pdf(pdf_path)
        if df.empty:
            continue

        # Vérifier si déjà vu (évite doublons)
        h = df["file_hash"].iloc[0]
        if h in seen_hashes:
            st.warning(f"⚠️ PDF déjà traité (doublon détecté): {pdf_path.name}")
            continue
        seen_hashes.add(h)

        all_parts.append(df)

    if not all_parts:
        return pd.DataFrame()

    # Concat all
    big = pd.concat(all_parts, ignore_index=True)

    # Sécurité : re-groupby global pour éliminer tout doublon résiduel
    big = (big.groupby(["file_hash", "file", "year", "month", "categorie"], as_index=False)
              .agg({"heures": "sum", "cout": "sum"}))

    # Transformer en format attendu par l'app:
    # Colonnes: Date, Heures_CATEGORY, Cout_CATEGORY, Heures_Total, Cout_Total
    result_rows = []

    for (year_val, month_val), group in big.groupby(['year', 'month']):
        date = dt.date(year_val, month_val, 1)
        row = {'Date': date}

        total_heures = 0.0
        total_cout = 0.0

        for _, cat_row in group.iterrows():
            cat = cat_row['categorie']
            heures = cat_row['heures']
            cout = cat_row['cout']

            row[f'Heures_{cat}'] = heures
            row[f'Cout_{cat}'] = cout

            total_heures += heures
            total_cout += cout

        row['Heures_Total'] = total_heures
        row['Cout_Total'] = total_cout

        result_rows.append(row)

    if not result_rows:
        return pd.DataFrame()

    result_df = pd.DataFrame(result_rows)
    result_df = result_df.sort_values('Date').reset_index(drop=True)

    return result_df


# --- Fonctions de mapping (gardées pour compatibilité) ---

def get_category_mapping_for_pdf(pdf_categories: List[str], app_categories: List[str]) -> Dict[str, str]:
    """
    Crée un mapping initial entre les catégories PDF et les catégories de l'app.

    Args:
        pdf_categories: Liste des catégories trouvées dans le PDF
        app_categories: Liste des catégories disponibles dans l'app (Types de personnel)

    Returns:
        Dict[str, str]: Mapping PDF category → App category
    """
    mapping = {}

    # Mappings prédéfinis
    predefined_mappings = {
        'coordinateurs': 'Coordinateur',
        'coordinateur': 'Coordinateur',
        "gestion d'accès": 'Sect. France',
        "gestion d'acces": 'Sect. France',
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
