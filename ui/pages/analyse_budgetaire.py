import datetime as dt
from pathlib import Path
import pandas as pd
import numpy as np
import streamlit as st
import altair as alt

from config.constants import FACTU_AT_DIR  # dossier des factures (Excel/CSV)

# ==========================
# Helpers robustes & formats
# ==========================

def _format_money_chf(v):
    try:
        return f"{int(np.ceil(float(v))):,} CHF".replace(",", " ")
    except Exception:
        return v

def _format_hours(v):
    try:
        return f"{int(np.ceil(float(v))):,} h".replace(",", " ")
    except Exception:
        return v

def _month_fr(n):
    return {
        1:"Janvier",2:"Février",3:"Mars",4:"Avril",5:"Mai",6:"Juin",
        7:"Juillet",8:"Août",9:"Septembre",10:"Octobre",11:"Novembre",12:"Décembre"
    }.get(int(n), str(n))

def _ensure_datetime(s, fmt="%d.%m.%Y"):
    ser = pd.to_datetime(s, errors="coerce")
    if ser.isna().all():
        ser = pd.to_datetime(s, format=fmt, errors="coerce")
    return ser

# ==========================
# Chargement facturation (robuste)
# ==========================

def _read_any(path: Path) -> pd.DataFrame:
    if path.suffix.lower() in [".xlsx", ".xls"]:
        try:
            return pd.read_excel(path, engine="openpyxl", header=None)
        except Exception:
            # parfois fichier renommé .xlsx mais c'est un CSV
            try:
                return pd.read_csv(path, sep=";", header=None, encoding="utf-8")
            except Exception:
                return pd.read_csv(path, sep=",", header=None)
    elif path.suffix.lower() == ".csv":
        try:
            return pd.read_csv(path, sep=";", header=None, encoding="utf-8")
        except Exception:
            return pd.read_csv(path, sep=",", header=None)
    else:
        return pd.DataFrame()

def _detect_header_row(df: pd.DataFrame, candidates=("Date ouvrable", "Heures", "Montant")) -> int | None:
    """Trouve la ligne d'entête quand elle est sur la 3e ligne, etc."""
    for i in range(min(10, len(df))):
        row_vals = df.iloc[i].astype(str).str.strip().tolist()
        if all(any(cand.lower() in str(v).lower() for v in row_vals) for cand in candidates[:2]):
            return i
    return None

def load_facturation_dir(dir_path: Path) -> pd.DataFrame:
    """
    Charge toutes les factures dans FACTU_AT_DIR en détectant l'entête et en consolidant.
    Colonnes reconnues (si présentes) :
      - Date ouvrable / Date / Jour
      - Heures
      - Montant / Total / CHF
    Retourne DataFrame avec colonnes: Date (date), Heures (float), Montant (float).
    """
    if not dir_path or not Path(dir_path).exists():
        return pd.DataFrame(columns=["Date", "Heures", "Montant"])

    files = sorted([p for p in Path(dir_path).glob("**/*") if p.suffix.lower() in (".xlsx", ".xls", ".csv")])
    if not files:
        return pd.DataFrame(columns=["Date", "Heures", "Montant"])

    frames = []
    for f in files:
        raw = _read_any(f)
        if raw.empty:
            continue
        header_row = _detect_header_row(raw)
        if header_row is not None:
            df = raw.iloc[header_row:].reset_index(drop=True)
            df.columns = df.iloc[0].astype(str).str.strip()
            df = df.iloc[1:].reset_index(drop=True)
        else:
            # fallback: première ligne comme header
            df = raw.copy()
            df.columns = df.iloc[0].astype(str).str.strip()
            df = df.iloc[1:].reset_index(drop=True)

        # mapping colonnes
        col_date = next((c for c in df.columns if str(c).lower().startswith("date")), None)
        col_heures = next((c for c in df.columns if "heure" in str(c).lower()), None)
        col_montant = next((c for c in df.columns if any(k in str(c).lower() for k in ["montant","total","chf","amount"])), None)

        if not col_date:
            # tente colonnes usuelles par position
            if "Date ouvrable" in df.columns: col_date = "Date ouvrable"
            elif "Jour" in df.columns: col_date = "Jour"

        out = pd.DataFrame()
        if col_date:
            out["Date"] = _ensure_datetime(df[col_date]).dt.date
        else:
            # si pas de date, ignore
            continue

        if col_heures:
            out["Heures"] = pd.to_numeric(df[col_heures], errors="coerce").fillna(0.0)
        else:
            out["Heures"] = 0.0

        if col_montant:
            # Remplace séparateurs FR éventuels
            vals = (df[col_montant].astype(str)
                    .str.replace("\u00a0", "", regex=False)
                    .str.replace(" ", "", regex=False)
                    .str.replace(",", ".", regex=False))
            out["Montant"] = pd.to_numeric(vals, errors="coerce").fillna(0.0)
        else:
            out["Montant"] = 0.0

        out = out.dropna(subset=["Date"])
        if not out.empty:
            frames.append(out)

    if not frames:
        return pd.DataFrame(columns=["Date", "Heures", "Montant"])

    all_df = pd.concat(frames, ignore_index=True)
    # agrège par jour (si doublons)
    agg = (all_df.groupby("Date", as_index=False)[["Heures","Montant"]].sum())

    return agg


# ==========================
# Extraction Budget & Modifié
# ==========================

def _pick_calendar_df() -> pd.DataFrame:
    """
    Cherche le calendrier de coût généré (budget annuel).
    Attendus: colonnes Date + Coût_* (+ Heures_* si dispo).
    """
    # sources possibles selon ta base
    for key in ("calendar_df_adjusted", "calendar_df",):
        df = st.session_state.get(key)
        if isinstance(df, pd.DataFrame) and not df.empty and "Date" in df.columns:
            return df.copy()
    return pd.DataFrame()

def _monthly_pivot(df: pd.DataFrame, prefix: str) -> pd.DataFrame:
    if df.empty or "Date" not in df.columns:
        return pd.DataFrame()
    work = df.copy()
    work["Date"] = pd.to_datetime(work["Date"], errors="coerce")
    work = work.dropna(subset=["Date"])
    cols = [c for c in work.columns if isinstance(c, str) and c.startswith(prefix)]
    if not cols:
        return pd.DataFrame()
    for c in cols:
        work[c] = pd.to_numeric(work[c], errors="coerce").fillna(0.0)
    work["Année"] = work["Date"].dt.year
    work["Mois_Num"] = work["Date"].dt.month
    work["Mois"] = work["Mois_Num"].map(_month_fr) + " " + work["Année"].astype(str)
    long_ = work.melt(id_vars=["Année","Mois_Num","Mois"], value_vars=cols,
                      var_name="Catégorie", value_name="Valeur")
    if prefix:
        long_["Catégorie"] = long_["Catégorie"].str.replace(prefix, "", regex=False)
    monthly = (long_.groupby(["Année","Mois_Num","Mois","Catégorie"], as_index=False)["Valeur"].sum())
    pivot = (monthly.pivot(index=["Année","Mois_Num","Mois"], columns="Catégorie", values="Valeur")
                     .fillna(0.0).reset_index().sort_values(["Année","Mois_Num"]))
    pivot["Mois"] = pd.Categorical(pivot["Mois"], ordered=True, categories=pivot["Mois"].tolist())
    return pivot

def _daily_series(df: pd.DataFrame, prefix: str) -> pd.DataFrame:
    """retourne Date + Total (somme de colonnes prefixées)"""
    if df.empty or "Date" not in df.columns:
        return pd.DataFrame(columns=["Date","Total"])
    work = df.copy()
    work["Date"] = pd.to_datetime(work["Date"], errors="coerce")
    work = work.dropna(subset=["Date"])
    cols = [c for c in work.columns if isinstance(c, str) and c.startswith(prefix)]
    if not cols:
        return pd.DataFrame(columns=["Date","Total"])
    for c in cols:
        work[c] = pd.to_numeric(work[c], errors="coerce").fillna(0.0)
    work["Total"] = work[cols].sum(axis=1)
    ser = (work[["Date","Total"]]
           .groupby("Date", as_index=False)["Total"].sum()
           .sort_values("Date"))
    return ser

# ==========================
# Page renderer
# ==========================

def render_analyse_budgetaire_page():
    st.title("Analyse Budgétaire")

    # Sources
    calendar_df = _pick_calendar_df()
    factu_df = load_facturation_dir(FACTU_AT_DIR)

    if calendar_df.empty:
        st.info("Budget non encore généré. Rendez-vous sur **Budget Annuel** pour générer le calendrie
