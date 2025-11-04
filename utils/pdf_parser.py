# utils/pdf_parser.py
from __future__ import annotations
import hashlib
import re
import datetime as dt
from pathlib import Path
from typing import Dict, List, Iterable, Optional

import pandas as pd

try:
    import pdfplumber
    PDF_AVAILABLE = True
except Exception:
    PDF_AVAILABLE = False


# ---------- Helpers ----------

_NUM_RE = re.compile(r"[^\d,.\-]")  # supprime tout sauf chiffre / séparateurs
_FN_DATE_RE = re.compile(r".*-(\d{8})\d{6}\.pdf$", re.IGNORECASE)  # ...-yyyymmddHHMMSS.pdf
_FN_YYYYMM_RE = re.compile(r".*-(\d{6})\d{2}\d{6}\.pdf$", re.IGNORECASE) # ...-yyyymm...... (sécurité)

def _parse_number(s: str | float | int) -> float:
    """Transforme '6 424.000' / '6.424,00' / '6424' en float robustement."""
    if s is None or (isinstance(s, float) and pd.isna(s)):
        return 0.0
    if isinstance(s, (int, float)):
        return float(s)
    s = str(s)
    s = s.replace("\u00A0", " ")
    # supprimer tout ce qui n'est pas ., , - ou chiffre
    s = _NUM_RE.sub("", s)
    if not s:
        return 0.0
    # heuristique décimale:
    # - si virgule et point présents: on suppose format "1.234,56" -> enlever points, virgule=decimal
    if "," in s and "." in s:
        s = s.replace(".", "")
        s = s.replace(",", ".")
    # - si seulement virgule: virgule=decimal
    elif "," in s and "." not in s:
        s = s.replace(",", ".")
    # sinon: déjà en "1234.56" ou "1234"
    try:
        return float(s)
    except ValueError:
        return 0.0


def _invoice_key_for(path: Path) -> str:
    """Hash court et stable du chemin pour mapper par facture."""
    return hashlib.sha1(str(path.resolve()).encode("utf-8")).hexdigest()[:12]


def _date_from_filename(path: Path) -> dt.date:
    """
    Extrait la date à partir du nom de fichier '...-yyyymmddHHMMSS.pdf'.
    On retourne le 1er jour du mois (clé mensuelle).
    """
    m = _FN_DATE_RE.match(path.name)
    if m:
        yyyymmdd = m.group(1)  # '20251104'
        year = int(yyyymmdd[0:4])
        month = int(yyyymmdd[4:6])
        return dt.date(year, month, 1)
    # fallback: essayer yyyymm
    m2 = _FN_YYYYMM_RE.match(path.name)
    if m2:
        yyyymm = m2.group(1)
        year = int(yyyymm[0:4])
        month = int(yyyymm[4:6])
        return dt.date(year, month, 1)
    # default: 1er du mois courant
    today = dt.date.today()
    return dt.date(today.year, today.month, 1)


def _normalize_header(row: Iterable[str]) -> List[str]:
    return [str(c or "").strip().replace("\n", " ") for c in row]


def _find_header_and_build_df(rows: List[List[str]]) -> pd.DataFrame:
    """
    Trouve la vraie ligne d'en-tête (celle qui contient 'Libellé' et au moins 'Quantité', 'Prix' ou 'Montant').
    NE SAUTE PAS la 1ère ligne de données (on coupe juste au bon endroit).
    """
    header_idx = -1
    for i, r in enumerate(rows):
        r_norm = _normalize_header(r)
        joined = " | ".join(r_norm).lower()
        if "libell" in joined and ("quant" in joined or "prix" in joined or "montant" in joined):
            header_idx = i
            break
    if header_idx == -1:
        # fallback: assume 1ère ligne = en-tête
        header_idx = 0

    header = _normalize_header(rows[header_idx])
    data_rows = rows[header_idx + 1 :]
    df = pd.DataFrame(data_rows, columns=header)

    # standardiser noms de colonnes de façon tolérante
    rename_map = {}
    for c in df.columns:
        cl = c.lower()
        if "libell" in cl:
            rename_map[c] = "Libellé"
        elif "quant" in cl:
            rename_map[c] = "Quantité"
        elif "prix" in cl or "pu" in cl:
            rename_map[c] = "Prix"
        elif "montant" in cl or "total" in cl:
            rename_map[c] = "Montant"
    if rename_map:
        df = df.rename(columns=rename_map)

    return df


def _extract_table_pdf(pdf_path: Path) -> pd.DataFrame:
    """
    Extrait la table principale (Libellé, Quantité, Prix, Montant) d'une facture PDF.
    Tente d'éviter les doublons et NE PERD PAS la 1ère ligne 'Heures AT ...'.
    """
    with pdfplumber.open(str(pdf_path)) as pdf:
        # On part sur la page 1 (facture mensuelle standard)
        page = pdf.pages[0]

        # Paramètres de table plus "stricts" (éviter dédoublement)
        ts = dict(
            vertical_strategy="lines",
            horizontal_strategy="lines",
            explicit_vertical_lines=[],   # si traitées correctement par pdfplumber
            explicit_horizontal_lines=[],
            intersection_x_tolerance=3,
            intersection_y_tolerance=3,
            snap_tolerance=3,
            min_words_horizontal=1,
            text_tolerance=3,
            join_tolerance=3,
        )

        tables = page.extract_tables(table_settings=ts)
        if not tables:
            # fallback: stratégie "text" plus permissive
            ts2 = dict(
                vertical_strategy="text",
                horizontal_strategy="text",
                text_tolerance=2,
                join_tolerance=2,
            )
            tables = page.extract_tables(table_settings=ts2)

        if not tables:
            return pd.DataFrame()

        # On prend la table la plus large (le plus de colonnes utiles)
        best = max(tables, key=lambda t: (len(t), len(t[0]) if t else 0))
        df = _find_header_and_build_df(best)

        # Filtrer les colonnes utiles si elles existent
        wanted = [c for c in ("Libellé", "Quantité", "Prix", "Montant") if c in df.columns]
        if not wanted:
            return pd.DataFrame()
        df = df[wanted].copy()

        # Nettoyage chiffres
        if "Quantité" in df.columns:
            df["Quantité"] = df["Quantité"].map(_parse_number)
        if "Prix" in df.columns:
            df["Prix"] = df["Prix"].map(_parse_number)
        if "Montant" in df.columns:
            df["Montant"] = df["Montant"].map(_parse_number)

        # Supprimer lignes vides / sous-totaux sans quantité
        if "Quantité" in df.columns:
            df = df[pd.to_numeric(df["Quantité"], errors="coerce").fillna(0.0) != 0.0]

        # De-dup au niveau ligne (certaines factures répètent le recap)
        df = df.drop_duplicates(subset=[c for c in df.columns if c in ("Libellé","Quantité","Prix","Montant")])

        return df


def _libelle_to_pdf_category(libelle: str) -> str:
    """
    Transforme un libellé ligne en catégorie PDF brute (avant mapping app).
    Exemple: 'Heures AT', 'ATF', 'CSC', 'Gestion d'accès', 'Coordinateurs', 'ATR', etc.
    """
    s = (libelle or "").strip().lower()
    # règles simples et extensibles
    if "gestion d'accès" in s or "sect. france" in s or "sect france" in s or "secteur france" in s:
        return "Gestion d'accès"
    if "coordinateur" in s:
        return "Coordinateurs"
    if re.search(r"\batr\b", s):
        return "ATR"
    if re.search(r"\batf\b", s):
        return "ATF"
    if re.search(r"\bcsc\b", s):
        return "CSC"
    if "heures at" in s or re.search(r"\bat\b", s):
        return "AT"
    # fallback: 1er mot capitalisé
    return libelle.strip().split()[0].capitalize() if libelle else "Autre"


# ---------- API exposée ----------

def load_pdf_facturation_data(dir_path: Path, year: int) -> pd.DataFrame:
    """
    Parcourt les PDF d'un dossier, agrège par facture/mois, et retourne un DF avec:
      Date, InvoiceFile, InvoiceKey,
      Heures_<Cat>, Coût_<Cat>, Heures_Total, Cout_Total
    """
    rows = []
    for pdf_file in Path(dir_path).glob("*.pdf"):
        try:
            date_m = _date_from_filename(pdf_file)
            if date_m.year != year:
                continue

            df_lines = _extract_table_pdf(pdf_file)
            if df_lines.empty:
                continue

            invoice_key = _invoice_key_for(pdf_file)

            # agrégation par catégorie brute PDF
            df_lines["__pdf_cat__"] = df_lines["Libellé"].map(_libelle_to_pdf_category)
            grp = df_lines.groupby("__pdf_cat__", as_index=False).agg(
                Quantite=("Quantité", "sum"),
                Montant=("Montant", "sum")
            )

            row = {
                "Date": pd.Timestamp(date_m),
                "InvoiceFile": pdf_file.name,
                "InvoiceKey": invoice_key,
            }

            heures_total, cout_total = 0.0, 0.0
            for _, r in grp.iterrows():
                cat = str(r["__pdf_cat__"])
                qte = float(r["Quantite"] or 0.0)
                mnt = float(r["Montant"] or 0.0)
                row[f"Heures_{cat}"] = qte
                row[f"Coût_{cat}"] = mnt
                heures_total += qte
                cout_total += mnt

            row["Heures_Total"] = heures_total
            row["Cout_Total"] = cout_total

            rows.append(row)

        except Exception:
            # on ignore ce PDF; la page d'analyse affichera un warning en amont si besoin
            continue

    if not rows:
        return pd.DataFrame()

    out = pd.DataFrame(rows).fillna(0.0)
    # harmoniser types
    if "Date" in out.columns:
        out["Date"] = pd.to_datetime(out["Date"])
    for c in out.columns:
        if c.startswith("Heures_") or c.startswith("Coût_") or c in ("Heures_Total","Cout_Total"):
            out[c] = pd.to_numeric(out[c], errors="coerce").fillna(0.0)
    # de-dup au niveau facture
    out = out.drop_duplicates(subset=["InvoiceKey","Date"], keep="first")
    return out


def get_category_mapping_for_pdf(pdf_categories: List[str], app_categories: List[str]) -> Dict[str, Optional[str]]:
    """
    Propose un mapping "auto" tolérant: match exact, casefold, variations simples.
    Les catégories non trouvées restent None (l'UI pourra demander à mapper).
    """
    mapping = {}
    acase = {a.lower(): a for a in app_categories or []}

    def norm(x: str) -> str:
        return (x or "").lower().replace("é", "e").replace("è", "e").replace("ê","e").replace("à","a").replace("’","'")

    for pdf_cat in pdf_categories:
        n = norm(pdf_cat)
        # correspondances directes
        if n in acase:
            mapping[pdf_cat] = acase[n]
            continue
        # heuristiques usuelles
        if n in ("gestion d'acces", "sect. france", "sect france", "secteur france"):
            mapping[pdf_cat] = acase.get("gestion d'accès", acase.get("sect. france", None))
            continue
        if n == "coordinateurs":
            mapping[pdf_cat] = acase.get("coordinateurs", None)
            continue
        mapping[pdf_cat] = None  # à mapper dans l'UI
    return mapping


def apply_category_mapping(pdf_df: pd.DataFrame, mapping: Dict[str, Optional[str]]) -> pd.DataFrame:
    """
    Renomme les colonnes Heures_/Coût_ de la catégorie PDF vers la catégorie App ciblée.
    Exemple: Heures_ATF -> Heures_AT (si l'utilisateur a mappé ATF -> AT ce mois-ci).
    """
    if pdf_df is None or pdf_df.empty:
        return pdf_df

    df = pdf_df.copy()
    rename_cols = {}

    # construire table de correspondances (source -> cible)
    for col in list(df.columns):
        if col.startswith("Heures_") or col.startswith("Coût_"):
            prefix, cat = col.split("_", 1)
            tgt = mapping.get(cat)  # peut être None
            if tgt and tgt != cat:
                # fusionner sous le nouveau nom
                new_col = f"{prefix}_{tgt}"
                if new_col not in df.columns:
                    df[new_col] = 0.0
                df[new_col] = pd.to_numeric(df[new_col], errors="coerce").fillna(0.0) + pd.to_numeric(df[col], errors="coerce").fillna(0.0)
                # marquer l'ancienne pour suppression
                rename_cols[col] = None

    # supprimer anciennes colonnes déplacées
    if rename_cols:
        df = df.drop(columns=[c for c, v in rename_cols.items() if v is None], errors="ignore")

    # recalc des totaux
    heure_cols = [c for c in df.columns if c.startswith("Heures_") and c != "Heures_Total"]
    cout_cols  = [c for c in df.columns if c.startswith("Coût_") and c != "Cout_Total"]

    if heure_cols:
        df["Heures_Total"] = df[heure_cols].sum(axis=1, numeric_only=True)
    if cout_cols:
        df["Cout_Total"] = df[cout_cols].sum(axis=1, numeric_only=True)

    return df
