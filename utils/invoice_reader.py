from __future__ import annotations
import hashlib, re, unicodedata
from pathlib import Path
from typing import Dict, List, Tuple
import pandas as pd
import pdfplumber

# ============================================================
# Helpers
# ============================================================

def _file_hash(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1<<16), b""):
            h.update(chunk)
    return h.hexdigest()[:16]

def _norm(s: str) -> str:
    if s is None:
        return ""
    s = str(s)
    s = unicodedata.normalize("NFKD", s)
    s = "".join(ch for ch in s if not unicodedata.combining(ch))
    s = s.replace("\xa0", " ")
    s = re.sub(r"\s+", " ", s).strip()
    return s

def _num(s) -> float:
    """Parse nombres au format FR/CH: espaces, apostrophes, virgules."""
    if s is None: 
        return 0.0
    t = str(s)
    # supprime séparateurs de milliers
    t = t.replace(" ", "").replace("’", "").replace("'", "")
    # cas "6 424.000" (point déjà décimal) -> garde le point
    # cas "6'424,00" -> virgule décimale
    # si on a à la fois . et , on suppose que la virgule est décimale
    if "," in t and "." in t:
        t = t.replace(".", "").replace(",", ".")
    else:
        # si virgule seule, convertir en point
        t = t.replace(",", ".")
    try:
        return float(t)
    except Exception:
        return 0.0

def _parse_year_month_from_filename(path: Path) -> Tuple[int|None,int|None]:
    # Ex: ...-20251104112400.pdf -> 202511 => year=2025, month=11
    m = re.search(r"-(\d{6})", path.stem)
    if m:
        yyyymm = m.group(1)
        return int(yyyymm[:4]), int(yyyymm[4:6])
    # fallback mm.yyyy
    m = re.search(r"(\d{2})\.(\d{4})", path.stem)
    if m:
        return int(m.group(2)), int(m.group(1))
    return None, None

# ============================================================
# Extraction PDF (tables)
# ============================================================

EXPECTED_HEADERS = ["Libellé", "Quantité", "Prix", "Montant"]
EXPECTED_HEADERS_NORM = [h.lower() for h in EXPECTED_HEADERS]

TABLE_SETTINGS = {
    "vertical_strategy": "lines",
    "horizontal_strategy": "lines",
    "intersection_y_tolerance": 3,
    "intersection_x_tolerance": 3,
    "snap_tolerance": 3,
    "join_tolerance": 3,
    "edge_min_length": 20,
    "min_words_vertical": 1,
    "min_words_horizontal": 1,
    "keep_blank_chars": False,
    "text_tolerance": 2,
}

def _headers_match(row: List[str]) -> bool:
    if not row:
        return False
    r = [(_norm(x)).lower() for x in row]
    # on tolère ordre exact; si ordre différent, on remettra en forme après
    found = sum(1 for x in r if x in EXPECTED_HEADERS_NORM)
    return found >= 3  # >=3 colonnes détectées suffit à considérer que c’est l’en-tête

def _reorder_columns(df: pd.DataFrame) -> pd.DataFrame:
    """Réorganise/renomme pour obtenir exactement: Libellé, Quantité, Prix, Montant"""
    # map par similarité simple
    cols_norm = {c: _norm(c).lower() for c in df.columns}
    col_map = {}
    for target in EXPECTED_HEADERS:
        tnorm = target.lower()
        # exact
        match = [c for c, n in cols_norm.items() if n == tnorm]
        if not match:
            # contains (ex: "Prix unitaire" -> Prix)
            match = [c for c, n in cols_norm.items() if tnorm in n]
        col_map[target] = match[0] if match else None

    # construire le DF final dans l'ordre attendu
    out = pd.DataFrame()
    for target in EXPECTED_HEADERS:
        src = col_map[target]
        out[target] = df[src] if src in df.columns else None
    return out

def extract_invoice_rows_from_pdf(pdf_path: Path) -> pd.DataFrame:
    """
    Retourne colonnes :
      file_hash, file, year, month, raw_label, hours, unit_rate, cost
    Règles confirmées :
      - Quantité = heures
      - Prix = coût horaire
      - Montant = coût total = Quantité * Prix
    """
    pdf_path = Path(pdf_path)
    file_hash = _file_hash(pdf_path)
    year, month = _parse_year_month_from_filename(pdf_path)

    pages_tables: List[pd.DataFrame] = []

    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages:
            # 1) Essai extraction avec paramètres stricts (lignes)
            tbl = page.extract_table(TABLE_SETTINGS)
            if not tbl:
                # 2) Fallback extraction par défaut
                tbl = page.extract_table()
            if not tbl:
                continue

            # Si la première ligne ressemble à l'en-tête, on la conserve comme header
            headers = tbl[0] if tbl else None
            if headers and _headers_match(headers):
                df = pd.DataFrame(tbl[1:], columns=headers)
            else:
                # parfois pdfplumber renvoie les en-têtes en 2e ligne -> on tente 2 lignes
                if len(tbl) >= 2 and _headers_match(tbl[1]):
                    df = pd.DataFrame(tbl[2:], columns=tbl[1])
                else:
                    # Dernier recours: pas d’en-têtes fiables -> ne pas utiliser cette table
                    continue

            if df is None or df.empty:
                continue

            # Réordonner et renommer pour obtenir exactement nos 4 colonnes
            df = _reorder_columns(df)
            # Filtrer lignes vides
            df = df.dropna(how="all")
            if not df.empty:
                pages_tables.append(df)

    if not pages_tables:
        return pd.DataFrame(columns=["file_hash","file","year","month","raw_label","hours","unit_rate","cost"])

    # Concat sans double comptage : on concatène une seule fois par page
    df_all = pd.concat(pages_tables, ignore_index=True)

    # Nettoyage/parse
    df_all["Libellé"] = df_all["Libellé"].apply(_norm)
    df_all["Quantité"] = df_all["Quantité"].apply(_num)
    df_all["Prix"]     = df_all["Prix"].apply(_num)
    df_all["Montant"]  = df_all["Montant"].apply(_num)

    # Ignore lignes non chiffrées
    df_all = df_all[(df_all["Libellé"] != "") & ((df_all["Quantité"]>0) | (df_all["Montant"]>0))].copy()

    # Construction des champs finaux
    out = pd.DataFrame({
        "file_hash": file_hash,
        "file": pdf_path.name,
        "year": year,
        "month": month,
        "raw_label": df_all["Libellé"],
        "hours": df_all["Quantité"],       # heures = Quantité
        "unit_rate": df_all["Prix"],       # coût horaire = Prix
        "cost": df_all["Montant"],         # coût total = Montant
    })

    # Si le PDF contient sous-totaux/doublons visuels, on agrège par libellé
    out = out.groupby(["file_hash","file","year","month","raw_label"], as_index=False).agg(
        hours=("hours","sum"),
        cost=("cost","sum")
    )
    # recalcul du taux moyen observé
    out["unit_rate"] = out.apply(lambda r: (r["cost"]/r["hours"]) if r["hours"]>0 else 0.0, axis=1)
    return out

# ============================================================
# Agrégation + mapping par facture (au cas par cas)
# ============================================================

def aggregate_invoice_with_mapping(pdf_path: Path, mapping_per_file: Dict[str, str]) -> pd.DataFrame:
    """
    mapping_per_file: { libellé brut -> catégorie interne } pour CE PDF uniquement.
    Retourne: file_hash,file,year,month,category,hours,cost,unit_rate
    """
    rows = extract_invoice_rows_from_pdf(pdf_path)
    if rows.empty:
        return rows

    def map_cat(raw: str) -> str:
        r = _norm(raw)
        # appariement exact au cas par cas (tu fournis via UI)
        for k, v in mapping_per_file.items():
            if _norm(k) == r:
                return v
        # fallback heuristique très simple (corrigeable par l’UI)
        low = r.lower()
        if "coordinateur" in low: return "Coordinateurs"
        if "gestion d" in low or "sect. fr" in low or "sect fr" in low: return "Gestion d'accès"
        if "atf" in low or "formateur" in low: return "ATF"
        if re.search(r"\batr\b", low): return "ATR"
        if re.search(r"\bcsc\b", low): return "CSC"
        if re.search(r"\bat\b", low):  return "AT"
        return "AUTRE"

    rows["category"] = rows["raw_label"].apply(map_cat)
    agg = rows.groupby(["file_hash","file","year","month","category"], as_index=False).agg(
        hours=("hours","sum"),
        cost=("cost","sum")
    )
    agg["unit_rate"] = agg.apply(lambda r: (r["cost"]/r["hours"]) if r["hours"]>0 else 0.0, axis=1)
    return agg
