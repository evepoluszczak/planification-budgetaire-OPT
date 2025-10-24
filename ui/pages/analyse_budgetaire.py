# ui/pages/analyse_budgetaire.py
from typing import Optional, Dict
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

def _format_pct(v):
    try:
        return f"{float(v)*100:,.1f}%".replace(",", " ")
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

def _style_variance(val):
    try:
        v = float(val)
        if v > 0:
            return "background-color: rgba(255, 0, 0, 0.15); color: #8a0000;"
        if v < 0:
            return "background-color: rgba(0, 128, 0, 0.12); color: #0b5;"
        return "color: #666;"
    except Exception:
        return ""

def _style_variance_pct(val):
    try:
        v = float(val)
        if v > 0.0:
            return "background-color: rgba(255, 0, 0, 0.10); color: #8a0000;"
        if v < 0.0:
            return "background-color: rgba(0, 128, 0, 0.08); color: #0b5;"
        return "color: #666;"
    except Exception:
        return ""

# ==========================
# Détection de l'année sélectionnée
# ==========================

def _find_selected_year() -> Optional[int]:
    """
    Cherche l'année de référence définie par la page Budget Annuel dans st.session_state.
    Clés possibles (ajoute d'autres si besoin) :
      - 'selected_year', 'budget_year', 'annee_budget', 'year', 'config_year'
      - dans st.session_state['budget_state'] : mêmes variantes
    """
    candidates = ["selected_year", "budget_year", "annee_budget", "year", "config_year"]
    # top-level
    for k in candidates:
        y = st.session_state.get(k)
        try:
            if 2010 <= int(y) <= 2100:
                return int(y)
        except Exception:
            pass
    # nested
    for container_key in ("budget_state", "bs", "budget"):
        sub = st.session_state.get(container_key)
        if isinstance(sub, dict):
            for k in candidates:
                y = sub.get(k)
                try:
                    if 2010 <= int(y) <= 2100:
                        return int(y)
                except Exception:
                    pass
    return None

def _filter_year(df: pd.DataFrame, year: Optional[int]) -> pd.DataFrame:
    if df.empty or year is None or "Date" not in df.columns:
        return df
    w = df.copy()
    w["Date"] = pd.to_datetime(w["Date"], errors="coerce")
    w = w.dropna(subset=["Date"])
    return w[w["Date"].dt.year == int(year)]

# ==========================
# Facturation (robuste)
# ==========================

def _read_any(path: Path) -> pd.DataFrame:
    if path.suffix.lower() in [".xlsx", ".xls"]:
        try:
            return pd.read_excel(path, engine="openpyxl", header=None)
        except Exception:
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

def _detect_header_row(df: pd.DataFrame, candidates=("Date ouvrable","Heures","Montant")) -> Optional[int]:
    max_probe = min(10, len(df))
    for i in range(max_probe):
        row_vals = df.iloc[i].astype(str).str.strip().tolist()
        if all(any(cand.lower() in str(v).lower() for v in row_vals) for cand in candidates[:2]):
            return i
    return None

@st.cache_data(show_spinner=False)
def load_facturation_dir(dir_path: Path) -> pd.DataFrame:
    """
    Consolidation de toutes les factures (xlsx/xls/csv) du dossier FACTU_AT_DIR.
    Produit un DF 'Date','Heures','Montant' agrégé par jour.
    """
    if (not dir_path) or (not Path(dir_path).exists()):
        return pd.DataFrame(columns=["Date","Heures","Montant"])

    files = sorted([p for p in Path(dir_path).glob("**/*") if p.suffix.lower() in (".xlsx",".xls",".csv")])
    if not files:
        return pd.DataFrame(columns=["Date","Heures","Montant"])

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
            df = raw.copy()
            df.columns = df.iloc[0].astype(str).str.strip()
            df = df.iloc[1:].reset_index(drop=True)

        col_date = next((c for c in df.columns if str(c).lower().startswith("date")), None)
        col_heures = next((c for c in df.columns if "heure" in str(c).lower()), None)
        col_montant = next((c for c in df.columns if any(k in str(c).lower() for k in ["montant","total","chf","amount"])), None)

        if not col_date:
            if "Date ouvrable" in df.columns: col_date = "Date ouvrable"
            elif "Jour" in df.columns: col_date = "Jour"

        out = pd.DataFrame()
        if col_date:
            out["Date"] = _ensure_datetime(df[col_date]).dt.date
        else:
            continue

        if col_heures:
            out["Heures"] = pd.to_numeric(df[col_heures], errors="coerce").fillna(0.0)
        else:
            out["Heures"] = 0.0

        if col_montant:
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
        return pd.DataFrame(columns=["Date","Heures","Montant"])

    all_df = pd.concat(frames, ignore_index=True)
    # Agrège par jour (si doublons)
    agg = (all_df.groupby("Date", as_index=False)[["Heures","Montant"]].sum())
    return agg

# ==========================
# Sélection des DataFrames Budget (Annuel / Modifié)
# ==========================

@st.cache_data(show_spinner=False)
def _scan_budget_dfs_from_session() -> Dict[str, pd.DataFrame]:
    """
    Scanne st.session_state et ses sous-dicts usuels pour trouver des DataFrames budget.
    Retourne dict {label: df} où df contient 'Date' + colonnes 'Coût_'/'Heures_'.
    """
    def _ok(df):
        return isinstance(df, pd.DataFrame) and ("Date" in df.columns) and any(
            isinstance(c, str) and (c.startswith("Coût_") or c.startswith("Heures_")) for c in df.columns
        )

    candidates = {}
    # Top-level
    for k, v in st.session_state.items():
        if _ok(v):
            candidates[k] = v
    # Sous-dictionnaires courants
    for container_key in ("budget_state", "bs", "budget"):
        sub = st.session_state.get(container_key)
        if isinstance(sub, dict):
            for k, v in sub.items():
                if _ok(v):
                    candidates[f"{container_key}.{k}"] = v
    return candidates

def _pick_calendar_base_and_modified_interactive(year: Optional[int]):
    """
    Choix explicite Annuel/Modifié parmi les DFs détectés.
    Filtre immédiatement chaque DF sur l'année choisie.
    """
    cands = _scan_budget_dfs_from_session()
    if not cands:
        st.session_state["_ab_found_calendars"] = {"detected": [], "reason": "aucun DF avec Date + Coût_/Heures_"}
        return pd.DataFrame(), pd.DataFrame(), []

    labels = list(cands.keys())
    st.session_state["_ab_found_calendars"] = {"detected": labels}

    # Heuristiques de présélection
    def _preselect(labels, prefer=("calendar_df_adjusted","calendar_df_after_needs","calendar_df_mod"), fallback=None):
        for p in prefer:
            for lab in labels:
                if lab.endswith(p) or p in lab:
                    return lab
        return fallback or (labels[0] if labels else None)

    annual_default = _preselect(labels, prefer=("calendar_df","generated_calendar_df","budget_calendar_df"), fallback=(labels[0] if labels else None))
    modified_default = _preselect(labels, prefer=("calendar_df_adjusted","calendar_df_after_needs","calendar_df_mod"), fallback=annual_default)

    with st.expander("🔧 Sources des données (Annuel / Modifié)", expanded=False):
        sel_ann = st.selectbox("DataFrame Budget Annuel", labels, index=labels.index(annual_default) if annual_default in labels else 0, key="ab_sel_ann")
        sel_mod = st.selectbox("DataFrame Budget Modifié (Besoin Jour)", labels, index=labels.index(modified_default) if modified_default in labels else 0, key="ab_sel_mod")

        def _summary(df):
            w = df.copy()
            w["Date"] = pd.to_datetime(w["Date"], errors="coerce")
            w = w.dropna(subset=["Date"])
            if year is not None:
                w = w[w["Date"].dt.year == int(year)]
            cost_cols = [c for c in w.columns if isinstance(c, str) and c.startswith("Coût_")]
            hour_cols = [c for c in w.columns if isinstance(c, str) and c.startswith("Heures_")]
            s_cost = float(w[cost_cols].sum().sum()) if cost_cols else 0.0
            s_hour = float(w[hour_cols].sum().sum()) if hour_cols else 0.0
            start = w["Date"].min().date() if not w.empty else "–"
            end = w["Date"].max().date() if not w.empty else "–"
            return f"lignes={len(w)}, période={start}→{end}, ΣCoût={int(np.ceil(s_cost)):,} CHF, ΣHeures={int(np.ceil(s_hour)):,} h".replace(",", " ")

        st.caption(f"Annuel → {sel_ann}: {_summary(cands[sel_ann])}")
        st.caption(f"Modifié → {sel_mod}: {_summary(cands[sel_mod])}")

    # Filtre année tout de suite
    df_ann = _filter_year(cands[sel_ann].copy(), year)
    df_mod = _filter_year(cands[sel_mod].copy(), year)

    # Avertit si ce sont exactement les mêmes objets (risque de confondre ann/mod)
    if id(cands[sel_ann]) == id(cands[sel_mod]):
        st.info("ℹ️ Annuel et Modifié pointent vers le **même DataFrame**. Choisis un DF différent pour 'Modifié' si tu attends des écarts.")

    return df_ann, df_mod, labels

# ==========================
# Agrégations & écarts
# ==========================

def _budget_columns(df: pd.DataFrame, prefix: str):
    """
    Colonnes de budget à agréger :
      - commencent par prefix ('Coût_' ou 'Heures_')
      - exclure les totaux ('Total', 'Total_Mois', etc.) pour éviter le double comptage
    """
    cols = []
    for c in df.columns:
        if not isinstance(c, str):
            continue
        if not c.startswith(prefix):
            continue
        lc = c.lower()
        if ("total" in lc) or ("_mois" in lc):
            # Exclut Coût_Total, Coût_Total_Mois, Heures_Total, etc.
            continue
        cols.append(c)
    return cols

def _monthly_total(df: pd.DataFrame, prefix: str) -> pd.DataFrame:
    """Retourne Année, Mois_Num, Mois, Total (somme des colonnes prefixées, sans 'Total*')."""
    if df.empty or "Date" not in df.columns:
        return pd.DataFrame(columns=["Année","Mois_Num","Mois","Total"])
    work = df.copy()
    work["Date"] = pd.to_datetime(work["Date"], errors="coerce")
    work = work.dropna(subset=["Date"])
    cols = _budget_columns(work, prefix)
    if not cols:
        return pd.DataFrame(columns=["Année","Mois_Num","Mois","Total"])
    for c in cols:
        work[c] = pd.to_numeric(work[c], errors="coerce").fillna(0.0)
    work["Année"] = work["Date"].dt.year.astype(int)
    work["Mois_Num"] = work["Date"].dt.month.astype(int)
    work["Mois"] = work["Mois_Num"].map(_month_fr) + " " + work["Année"].astype(str)
    out = work.groupby(["Année","Mois_Num","Mois"], as_index=False)[cols].sum()
    out["Total"] = out[cols].sum(axis=1)
    return out[["Année","Mois_Num","Mois","Total"]].sort_values(["Année","Mois_Num"])

def _daily_series(df: pd.DataFrame, prefix: str) -> pd.DataFrame:
    """Série journalière Total = somme des colonnes budget (sans 'Total*')."""
    if df.empty or "Date" not in df.columns:
        return pd.DataFrame(columns=["Date","Total"])
    work = df.copy()
    work["Date"] = pd.to_datetime(work["Date"], errors="coerce")
    work = work.dropna(subset=["Date"])
    cols = _budget_columns(work, prefix)
    if not cols:
        return pd.DataFrame(columns=["Date","Total"])
    for c in cols:
        work[c] = pd.to_numeric(work[c], errors="coerce").fillna(0.0)
    work["Total"] = work[cols].sum(axis=1)
    ser = (work[["Date","Total"]]
           .groupby("Date", as_index=False)["Total"].sum()
           .sort_values("Date"))
    return ser

def _variance_cols(df, col_ref, col_cmp, prefix):
    out = df.copy()
    ref = out[col_ref].astype(float)
    cmpv = out[col_cmp].astype(float)
    out[prefix + "_Ecart"] = (cmpv - ref)
    out[prefix + "_Ecart_pct"] = np.where(ref == 0,
                                          np.where(cmpv == 0, 0.0, 1.0),
                                          (cmpv - ref) / ref)
    return out

# ==========================
# Page renderer
# ==========================

def render_analyse_budgetaire_page():
    st.title("Analyse Budgétaire")

    # ---- 1) Année : lit celle de Budget Annuel, sinon propose une liste détectée
    year_in_session = _find_selected_year()

    # on détecte les bornes à partir des DFs disponibles (si déjà en session)
    all_cands = _scan_budget_dfs_from_session()
    years_detected = []
    for df in all_cands.values():
        if "Date" in df.columns:
            d = pd.to_datetime(df["Date"], errors="coerce")
            ys = d.dt.year.dropna().astype(int).unique().tolist()
            years_detected.extend(ys)
    years_detected = sorted(set([y for y in years_detected if 2010 <= y <= 2100]))

    if years_detected:
        default_year = year_in_session if (year_in_session in years_detected) else years_detected[0]
        sel_year = st.selectbox("Année analysée", years_detected, index=years_detected.index(default_year), key="ab_year_select")
    else:
        sel_year = year_in_session  # peut être None
        if sel_year is None:
            st.info("Aucune année détectée pour l’instant. Dès que le budget sera généré, l’année apparaîtra ici.")
            # on continue : les sections en dessous gèreront l'absence

    # ---- 2) Sélection explicite des sources Annuel / Modifié (filtrées sur l’année)
    df_annuel, df_mod, labels_found = _pick_calendar_base_and_modified_interactive(sel_year)
    if df_annuel.empty:
        st.info("Budget non encore généré pour l’année sélectionnée.")
        found = st.session_state.get("_ab_found_calendars", {})
        with st.expander("Debug — DFs détectés"):
            st.write("Candidats trouvés :", found.get("detected"))
            st.write("Clés présentes dans st.session_state :", list(st.session_state.keys()))
        return

    # ---- 3) Facturation
    factu_all = load_facturation_dir(FACTU_AT_DIR)
    if factu_all.empty:
        factu_df = factu_all
    else:
        factu_all["Date"] = pd.to_datetime(factu_all["Date"], errors="coerce")
        factu_df = factu_all[factu_all["Date"].dt.year == int(sel_year)] if sel_year is not None else factu_all

    tabs = st.tabs(["Synthèse (CHF)","Synthèse (Heures)","Courbes cumulées","Détails Mensuels"])

    # ======================
    # A) Synthèse (CHF) + écarts
    # ======================
    with tabs[0]:
        st.subheader(f"Synthèse (CHF) — {sel_year} — Prévu vs Modifié vs Réalisé")

        ann_chf = _monthly_total(df_annuel, "Coût_")
        mod_chf = _monthly_total(df_mod, "Coût_")
        if ann_chf.empty:
            st.warning("Aucune colonne de coût (préfixe 'Coût_') détectée.")
        else:
            factu_month = pd.DataFrame(columns=["Année","Mois_Num","Total"])
            if not factu_df.empty and "Montant" in factu_df.columns:
                f2 = factu_df.copy()
                f2["Année"] = f2["Date"].dt.year.astype(int)
                f2["Mois_Num"] = f2["Date"].dt.month.astype(int)
                factu_month = f2.groupby(["Année","Mois_Num"], as_index=False)["Montant"].sum()
                factu_month.rename(columns={"Montant":"Total"}, inplace=True)

            for df_ in (ann_chf, mod_chf, factu_month):
                if not df_.empty:
                    df_["Année"] = df_["Année"].astype(int)
                    df_["Mois_Num"] = df_["Mois_Num"].astype(int)

            base = ann_chf.merge(mod_chf, on=["Année","Mois_Num","Mois"], how="outer", suffixes=("_Annuel","_Modifie")).fillna(0.0)
            base = base.merge(factu_month, on=["Année","Mois_Num"], how="left")
            base.rename(columns={"Total":"Total_Reel"}, inplace=True)
            base["Total_Reel"] = base["Total_Reel"].fillna(0.0)

            base = _variance_cols(base, "Total_Annuel", "Total_Modifie", "Mod_vs_Ann")
            base = _variance_cols(base, "Total_Modifie", "Total_Reel",   "Reel_vs_Mod")

            k1, k2, k3 = st.columns(3)
            k1.metric("Budget Annuel (CHF)", _format_money_chf(base["Total_Annuel"].sum()))
            k2.metric("Budget Modifié (CHF)", _format_money_chf(base["Total_Modifie"].sum()))
            k3.metric("Facturation cumulée (CHF)", _format_money_chf(base["Total_Reel"].sum()))

            show = base.copy().sort_values(["Année","Mois_Num"])
            fmt = {
                "Total_Annuel": _format_money_chf,
                "Total_Modifie": _format_money_chf,
                "Total_Reel": _format_money_chf,
                "Mod_vs_Ann_Ecart": _format_money_chf,
                "Reel_vs_Mod_Ecart": _format_money_chf,
                "Mod_vs_Ann_Ecart_pct": _format_pct,
                "Reel_vs_Mod_Ecart_pct": _format_pct,
            }
            styler = (show[["Mois","Total_Annuel","Total_Modifie","Total_Reel",
                            "Mod_vs_Ann_Ecart","Mod_vs_Ann_Ecart_pct",
                            "Reel_vs_Mod_Ecart","Reel_vs_Mod_Ecart_pct"]]
                      .style
                      .applymap(_style_variance, subset=["Mod_vs_Ann_Ecart","Reel_vs_Mod_Ecart"])
                      .applymap(_style_variance_pct, subset=["Mod_vs_Ann_Ecart_pct","Reel_vs_Mod_Ecart_pct"])
                      .format(fmt))
            st.dataframe(styler, use_container_width=True)

            with st.expander("🔎 Debug Facturation (CHF)"):
                st.caption(f"FACTU_AT_DIR = {FACTU_AT_DIR}")
                st.write("Lignes facturation (jour, année filtrée):", len(factu_df))
                if not factu_df.empty:
                    st.dataframe(factu_df.head(10), use_container_width=True)
                st.write("Lignes facturation (mois):", len(factu_month))
                if not factu_month.empty:
                    st.dataframe(factu_month.head(12), use_container_width=True)

    # ======================
    # B) Synthèse (Heures) + écarts
    # ======================
    with tabs[1]:
        st.subheader(f"Synthèse (Heures) — {sel_year} — Prévu vs Modifié vs Réalisé")

        ann_h = _monthly_total(df_annuel, "Heures_")
        mod_h = _monthly_total(df_mod, "Heures_")
        if ann_h.empty:
            st.info("Aucune colonne d'heures (préfixe 'Heures_') détectée.")
        else:
            factu_month_h = pd.DataFrame(columns=["Année","Mois_Num","Total"])
            if not factu_df.empty and "Heures" in factu_df.columns:
                f2 = factu_df.copy()
                f2["Année"] = f2["Date"].dt.year.astype(int)
                f2["Mois_Num"] = f2["Date"].dt.month.astype(int)
                factu_month_h = f2.groupby(["Année","Mois_Num"], as_index=False)["Heures"].sum()
                factu_month_h.rename(columns={"Heures":"Total"}, inplace=True)

            for df_ in (ann_h, mod_h, factu_month_h):
                if not df_.empty:
                    df_["Année"] = df_["Année"].astype(int)
                    df_["Mois_Num"] = df_["Mois_Num"].astype(int)

            base = ann_h.merge(mod_h, on=["Année","Mois_Num","Mois"], how="outer", suffixes=("_Annuel","_Modifie")).fillna(0.0)
            base = base.merge(factu_month_h, on=["Année","Mois_Num"], how="left")
            base.rename(columns={"Total":"Total_Reel"}, inplace=True)
            base["Total_Reel"] = base["Total_Reel"].fillna(0.0)

            base = _variance_cols(base, "Total_Annuel", "Total_Modifie", "Mod_vs_Ann")
            base = _variance_cols(base, "Total_Modifie", "Total_Reel",   "Reel_vs_Mod")

            k1, k2, k3 = st.columns(3)
            k1.metric("Budget Annuel (h)", _format_hours(base["Total_Annuel"].sum()))
            k2.metric("Budget Modifié (h)", _format_hours(base["Total_Modifie"].sum()))
            k3.metric("Heures facturées (h)", _format_hours(base["Total_Reel"].sum()))

            show = base.copy().sort_values(["Année","Mois_Num"])
            fmt = {
                "Total_Annuel": _format_hours,
                "Total_Modifie": _format_hours,
                "Total_Reel": _format_hours,
                "Mod_vs_Ann_Ecart": _format_hours,
                "Reel_vs_Mod_Ecart": _format_hours,
                "Mod_vs_Ann_Ecart_pct": _format_pct,
                "Reel_vs_Mod_Ecart_pct": _format_pct,
            }
            styler = (show[["Mois","Total_Annuel","Total_Modifie","Total_Reel",
                            "Mod_vs_Ann_Ecart","Mod_vs_Ann_Ecart_pct",
                            "Reel_vs_Mod_Ecart","Reel_vs_Mod_Ecart_pct"]]
                      .style
                      .applymap(_style_variance, subset=["Mod_vs_Ann_Ecart","Reel_vs_Mod_Ecart"])
                      .applymap(_style_variance_pct, subset=["Mod_vs_Ann_Ecart_pct","Reel_vs_Mod_Ecart_pct"])
                      .format(fmt))
            st.dataframe(styler, use_container_width=True)

            with st.expander("🔎 Debug Facturation (Heures)"):
                st.write("Lignes facturation (mois):", len(factu_month_h))
                if not factu_month_h.empty:
                    st.dataframe(factu_month_h.head(12), use_container_width=True)

    # ======================
    # C) Courbes cumulées (journalier → cumul)
    # ======================
    with tabs[2]:
        st.subheader(f"Courbes cumulées — {sel_year}")

        daily_chf_ann = _daily_series(df_annuel, "Coût_")
        daily_chf_mod = _daily_series(df_mod, "Coût_")

        factu_daily = pd.DataFrame(columns=["Date","Montant","Heures"])
        if not factu_df.empty:
            factu_daily = factu_df.copy().sort_values("Date")

        colA, colB = st.columns(2)

        with colA:
            st.markdown("**CHF cumulés**")
            frames = []
            if not daily_chf_ann.empty:
                s = daily_chf_ann.copy().sort_values("Date")
                s["Cum"] = s["Total"].cumsum()
                frames.append(pd.DataFrame({"Date": s["Date"], "Valeur": s["Cum"], "Série": "Annuel (CHF)"}))
            if not daily_chf_mod.empty:
                s = daily_chf_mod.copy().sort_values("Date")
                s["Cum"] = s["Total"].cumsum()
                frames.append(pd.DataFrame({"Date": s["Date"], "Valeur": s["Cum"], "Série": "Modifié (CHF)"}))
            if not factu_daily.empty and "Montant" in factu_daily.columns:
                f = factu_daily[["Date","Montant"]].copy().sort_values("Date")
                f["Cum"] = f["Montant"].cumsum()
                frames.append(pd.DataFrame({"Date": f["Date"], "Valeur": f["Cum"], "Série": "Réalisé (CHF)"}))
            if frames:
                plot_df = pd.concat(frames, ignore_index=True)
                ch = alt.Chart(plot_df).mark_line().encode(
                    x="Date:T", y="Valeur:Q", color="Série:N"
                ).properties(height=300)
                st.altair_chart(ch, use_container_width=True)
            else:
                st.info("Pas de données CHF à tracer.")

        with colB:
            st.markdown("**Heures cumulées**")
            daily_h_ann = _daily_series(df_annuel, "Heures_")
            daily_h_mod = _daily_series(df_mod, "Heures_")
            frames = []
            if not daily_h_ann.empty:
                s = daily_h_ann.copy().sort_values("Date")
                s["Cum"] = s["Total"].cumsum()
                frames.append(pd.DataFrame({"Date": s["Date"], "Valeur": s["Cum"], "Série": "Annuel (h)"}))
            if not daily_h_mod.empty:
                s = daily_h_mod.copy().sort_values("Date")
                s["Cum"] = s["Total"].cumsum()
                frames.append(pd.DataFrame({"Date": s["Date"], "Valeur": s["Cum"], "Série": "Modifié (h)"}))
            if not factu_daily.empty and "Heures" in factu_daily.columns:
                f = factu_daily[["Date","Heures"]].copy().sort_values("Date")
                f["Cum"] = f["Heures"].cumsum()
                frames.append(pd.DataFrame({"Date": f["Date"], "Valeur": f["Cum"], "Série": "Réalisé (h)"}))
            if frames:
                plot_df = pd.concat(frames, ignore_index=True)
                ch = alt.Chart(plot_df).mark_line().encode(
                    x="Date:T", y="Valeur:Q", color="Série:N"
                ).properties(height=300)
                st.altair_chart(ch, use_container_width=True)
            else:
                st.info("Pas de données Heures à tracer.")

    # ======================
    # D) Détails Mensuels (lecture par type)
    # ======================
    with tabs[3]:
        st.subheader(f"Détails Mensuels — {sel_year}")

        month_opts = (_monthly_total(df_annuel, "Coût_")[["Année","Mois_Num","Mois"]]
                      .drop_duplicates()
                      .sort_values(["Année","Mois_Num"])
                      .values.tolist())
        if not month_opts:
            st.info("Pas de données mensuelles disponibles.")
            return

        labels = [m[2] for m in month_opts]
        idx_default = len(labels) - 1
        sel = st.selectbox("Mois", labels, index=idx_default, key="ab_month_select")
        idx = labels.index(sel)
        year_sel, m_sel, _ = month_opts[idx]

        def _monthly_pivot(df: pd.DataFrame, prefix: str) -> pd.DataFrame:
            if df.empty or "Date" not in df.columns:
                return pd.DataFrame()
            work = df.copy()
            work["Date"] = pd.to_datetime(work["Date"], errors="coerce")
            work = work.dropna(subset=["Date"])
            cols = _budget_columns(work, prefix)
            if not cols:
                return pd.DataFrame()
            for c in cols:
                work[c] = pd.to_numeric(work[c], errors="coerce").fillna(0.0)
            work["Année"] = work["Date"].dt.year.astype(int)
            work["Mois_Num"] = work["Date"].dt.month.astype(int)
            work = work[(work["Année"]==year_sel) & (work["Mois_Num"]==m_sel)]
            if work.empty:
                return pd.DataFrame()
            tidy = work[cols].sum().reset_index()
            tidy.columns = ["Type","Valeur"]
            tidy["Type"] = tidy["Type"].astype(str).str.replace(prefix, "", regex=False)
            return tidy.sort_values("Type")

        col1, col2 = st.columns(2)

        with col1:
            st.markdown("**Coûts (CHF) par type — Annuel vs Modifié**")
            ann_tidy = _monthly_pivot(df_annuel, "Coût_")
            mod_tidy = _monthly_pivot(df_mod, "Coût_")
            if ann_tidy.empty and mod_tidy.empty:
                st.info("Aucune colonne 'Coût_'.")
            else:
                base = ann_tidy.merge(mod_tidy, on="Type", how="outer", suffixes=("_Annuel","_Modifie")).fillna(0.0)
                base = _variance_cols(base, "Valeur_Annuel", "Valeur_Modifie", "Mod_vs_Ann")
                styler = (base[["Type","Valeur_Annuel","Valeur_Modifie","Mod_vs_Ann_Ecart","Mod_vs_Ann_Ecart_pct"]]
                          .style
                          .applymap(_style_variance, subset=["Mod_vs_Ann_Ecart"])
                          .applymap(_style_variance_pct, subset=["Mod_vs_Ann_Ecart_pct"])
                          .format({
                              "Valeur_Annuel": _format_money_chf,
                              "Valeur_Modifie": _format_money_chf,
                              "Mod_vs_Ann_Ecart": _format_money_chf,
                              "Mod_vs_Ann_Ecart_pct": _format_pct
                          }))
                st.dataframe(styler, use_container_width=True)

        with col2:
            st.markdown("**Heures par type — Annuel vs Modifié**")
            ann_tidy = _monthly_pivot(df_annuel, "Heures_")
            mod_tidy = _monthly_pivot(df_mod, "Heures_")
            if ann_tidy.empty and mod_tidy.empty:
                st.info("Aucune colonne 'Heures_'.")
            else:
                base = ann_tidy.merge(mod_tidy, on="Type", how="outer", suffixes=("_Annuel","_Modifie")).fillna(0.0)
                base = _variance_cols(base, "Valeur_Annuel", "Valeur_Modifie", "Mod_vs_Ann")
                styler = (base[["Type","Valeur_Annuel","Valeur_Modifie","Mod_vs_Ann_Ecart","Mod_vs_Ann_Ecart_pct"]]
                          .style
                          .applymap(_style_variance, subset=["Mod_vs_Ann_Ecart"])
                          .applymap(_style_variance_pct, subset=["Mod_vs_Ann_Ecart_pct"])
                          .format({
                              "Valeur_Annuel": _format_hours,
                              "Valeur_Modifie": _format_hours,
                              "Mod_vs_Ann_Ecart": _format_hours,
                              "Mod_vs_Ann_Ecart_pct": _format_pct
                          }))
                st.dataframe(styler, use_container_width=True)
