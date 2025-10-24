# ui/pages/analyse_budgetaire.py
import datetime as dt
from pathlib import Path
from typing import Optional
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

def _detect_header_row(df: pd.DataFrame, candidates=("Date ouvrable", "Heures", "Montant")) -> Optional[int]:
    """Trouve la ligne d'entête quand elle est sur la 3e ligne, etc."""
    max_probe = min(10, len(df))
    for i in range(max_probe):
        row_vals = df.iloc[i].astype(str).str.strip().tolist()
        # on exige au moins les 2 premières colonnes potentielles (date/heure)
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
    if (not dir_path) or (not Path(dir_path).exists()):
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
            if "Date ouvrable" in df.columns:
                col_date = "Date ouvrable"
            elif "Jour" in df.columns:
                col_date = "Jour"

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
        return pd.DataFrame(columns=["Date", "Heures", "Montant"])

    all_df = pd.concat(frames, ignore_index=True)
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
    for key in ("calendar_df_adjusted", "calendar_df"):
        df = st.session_state.get(key)
        if isinstance(df, pd.DataFrame) and (not df.empty) and ("Date" in df.columns):
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
    # Catégorie 'Mois' déjà triée via Année/Mois_Num
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
        st.info("Budget non encore généré. Rendez-vous sur **Budget Annuel** pour générer le calendrier de coûts.")
        return

    tabs = st.tabs(["Synthèse (CHF)", "Synthèse (Heures)", "Courbes cumulées", "Détails Mensuels"])

    # ======================
    # A) Synthèse (CHF)
    # ======================
    with tabs[0]:
        st.subheader("Synthèse (CHF)")

        monthly_chf = _monthly_pivot(calendar_df, "Coût_")
        if monthly_chf.empty:
            st.warning("Aucune colonne de coût (préfixe 'Coût_') détectée.")
        else:
            chf_cols = [c for c in monthly_chf.columns if c not in ("Année","Mois_Num","Mois")]
            monthly_chf["Budget_Annuel_CHF"] = monthly_chf[chf_cols].sum(axis=1)
            monthly_chf["Budget_Modifié_CHF"] = monthly_chf["Budget_Annuel_CHF"]  # adapte si tu as une source distincte

            if not factu_df.empty and "Montant" in factu_df.columns:
                factu_df2 = factu_df.copy()
                factu_df2["Date"] = pd.to_datetime(factu_df2["Date"], errors="coerce")
                factu_df2 = factu_df2.dropna(subset=["Date"])
                factu_df2["Année"] = factu_df2["Date"].dt.year
                factu_df2["Mois_Num"] = factu_df2["Date"].dt.month
                factu_month = (factu_df2.groupby(["Année","Mois_Num"], as_index=False)["Montant"].sum())
                monthly_chf = monthly_chf.merge(factu_month, on=["Année","Mois_Num"], how="left")
                monthly_chf["Montant"] = monthly_chf["Montant"].fillna(0.0)
                monthly_chf["Facturation_CHF"] = monthly_chf["Montant"]
                monthly_chf = monthly_chf.drop(columns=["Montant"])
            else:
                monthly_chf["Facturation_CHF"] = 0.0

            k1, k2, k3 = st.columns(3)
            k1.metric("Budget Annuel (CHF)", _format_money_chf(monthly_chf["Budget_Annuel_CHF"].sum()))
            k2.metric("Budget Modifié (CHF)", _format_money_chf(monthly_chf["Budget_Modifié_CHF"].sum()))
            k3.metric("Facturation cumulée (CHF)", _format_money_chf(monthly_chf["Facturation_CHF"].sum()))

            show_cols = ["Mois", "Budget_Annuel_CHF", "Budget_Modifié_CHF", "Facturation_CHF"]
            df_display = monthly_chf[show_cols].copy()
            st.dataframe(
                df_display.style.format({
                    "Budget_Annuel_CHF": _format_money_chf,
                    "Budget_Modifié_CHF": _format_money_chf,
                    "Facturation_CHF": _format_money_chf
                }),
                use_container_width=True
            )

    # ======================
    # B) Synthèse (Heures)
    # ======================
    with tabs[1]:
        st.subheader("Synthèse (Heures)")

        monthly_h = _monthly_pivot(calendar_df, "Heures_")
        if monthly_h.empty:
            st.info("Aucune colonne d'heures (préfixe 'Heures_') détectée.")
        else:
            hour_cols = [c for c in monthly_h.columns if c not in ("Année","Mois_Num","Mois")]
            monthly_h["Budget_Annuel_h"] = monthly_h[hour_cols].sum(axis=1)
            monthly_h["Budget_Modifié_h"] = monthly_h["Budget_Annuel_h"]  # adapte si source distincte

            if not factu_df.empty and "Heures" in factu_df.columns:
                factu_df2 = factu_df.copy()
                factu_df2["Date"] = pd.to_datetime(factu_df2["Date"], errors="coerce")
                factu_df2 = factu_df2.dropna(subset=["Date"])
                factu_df2["Année"] = factu_df2["Date"].dt.year
                factu_df2["Mois_Num"] = factu_df2["Date"].dt.month
                factu_month = (factu_df2.groupby(["Année","Mois_Num"], as_index=False)["Heures"].sum())
                monthly_h = monthly_h.merge(factu_month, on=["Année","Mois_Num"], how="left")
                monthly_h["Heures"] = monthly_h["Heures"].fillna(0.0)
                monthly_h["Heures_facturées"] = monthly_h["Heures"]
                monthly_h = monthly_h.drop(columns=["Heures"])
            else:
                monthly_h["Heures_facturées"] = 0.0

            k1, k2, k3 = st.columns(3)
            k1.metric("Budget Annuel (h)", _format_hours(monthly_h["Budget_Annuel_h"].sum()))
            k2.metric("Budget Modifié (h)", _format_hours(monthly_h["Budget_Modifié_h"].sum()))
            k3.metric("Heures facturées (h)", _format_hours(monthly_h["Heures_facturées"].sum()))

            show_cols = ["Mois", "Budget_Annuel_h", "Budget_Modifié_h", "Heures_facturées"]
            df_display = monthly_h[show_cols].copy()
            st.dataframe(
                df_display.style.format({
                    "Budget_Annuel_h": _format_hours,
                    "Budget_Modifié_h": _format_hours,
                    "Heures_facturées": _format_hours
                }),
                use_container_width=True
            )

    # ======================
    # C) Courbes cumulées
    # ======================
    with tabs[2]:
        st.subheader("Courbes cumulées (journalier → cumul)")

        daily_chf = _daily_series(calendar_df, "Coût_")
        daily_h = _daily_series(calendar_df, "Heures_")

        factu_daily = pd.DataFrame(columns=["Date","Montant","Heures"])
        if not factu_df.empty:
            factu_daily = factu_df.copy()
            factu_daily["Date"] = pd.to_datetime(factu_daily["Date"], errors="coerce")
            factu_daily = factu_daily.dropna(subset=["Date"]).sort_values("Date")

        colA, colB = st.columns(2)

        with colA:
            st.markdown("**CHF cumulés**")
            if not daily_chf.empty:
                s = daily_chf.copy().sort_values("Date")
                s["Cum_Budget_CHF"] = s["Total"].cumsum()
                frames = [pd.DataFrame({"Date": s["Date"], "Valeur": s["Cum_Budget_CHF"], "Série": "Budget Annuel (CHF)"})]
                if not factu_daily.empty and "Montant" in factu_daily.columns:
                    f = factu_daily[["Date","Montant"]].copy().sort_values("Date")
                    f["Cum_Facturation"] = f["Montant"].cumsum()
                    frames.append(pd.DataFrame({"Date": f["Date"], "Valeur": f["Cum_Facturation"], "Série": "Facturation (CHF)"}))
                plot_df = pd.concat(frames, ignore_index=True)
                ch = alt.Chart(plot_df).mark_line().encode(
                    x="Date:T", y="Valeur:Q", color="Série:N"
                ).properties(height=300)
                st.altair_chart(ch, use_container_width=True)
            else:
                st.info("Pas de série CHF (préfixe 'Coût_').")

        with colB:
            st.markdown("**Heures cumulées**")
            if not daily_h.empty:
                s = daily_h.copy().sort_values("Date")
                s["Cum_Budget_h"] = s["Total"].cumsum()
                frames = [pd.DataFrame({"Date": s["Date"], "Valeur": s["Cum_Budget_h"], "Série": "Budget Annuel (h)"})]
                if not factu_daily.empty and "Heures" in factu_daily.columns:
                    f = factu_daily[["Date","Heures"]].copy().sort_values("Date")
                    f["Cum_Heures"] = f["Heures"].cumsum()
                    frames.append(pd.DataFrame({"Date": f["Date"], "Valeur": f["Cum_Heures"], "Série": "Heures facturées (h)"}))
                plot_df = pd.concat(frames, ignore_index=True)
                ch = alt.Chart(plot_df).mark_line().encode(
                    x="Date:T", y="Valeur:Q", color="Série:N"
                ).properties(height=300)
                st.altair_chart(ch, use_container_width=True)
            else:
                st.info("Pas de série Heures (préfixe 'Heures_').")

    # ======================
    # D) Détails Mensuels
    # ======================
    with tabs[3]:
        st.subheader("Détails Mensuels")

        monthly_chf = _monthly_pivot(calendar_df, "Coût_")
        monthly_h = _monthly_pivot(calendar_df, "Heures_")

        month_opts = []
        if not monthly_chf.empty:
            month_opts = (monthly_chf[["Année","Mois_Num","Mois"]]
                          .drop_duplicates().sort_values(["Année","Mois_Num"]).values.tolist())
        elif not monthly_h.empty:
            month_opts = (monthly_h[["Année","Mois_Num","Mois"]]
                          .drop_duplicates().sort_values(["Année","Mois_Num"]).values.tolist())

        if not month_opts:
            st.info("Pas de données mensuelles disponibles.")
            return

        labels = [m[2] for m in month_opts]
        idx_default = len(labels)-1
        sel = st.selectbox("Mois", labels, index=idx_default, key="ab_month_select")
        idx = labels.index(sel)
        year_sel, m_sel, _ = month_opts[idx]

        def _filter_month(df):
            if df.empty:
                return df
            return df[(df["Année"]==year_sel) & (df["Mois_Num"]==m_sel)]

        col1, col2 = st.columns(2)

        with col1:
            st.markdown("**Coûts (CHF) par type**")
            if monthly_chf.empty:
                st.info("Aucune colonne 'Coût_'.")
            else:
                subset = _filter_month(monthly_chf).copy()
                cat_cols = [c for c in subset.columns if c not in ("Année","Mois_Num","Mois")]
                tidy = subset.melt(id_vars=["Mois"], value_vars=cat_cols, var_name="Type", value_name="CHF")
                tidy["Type"] = tidy["Type"].astype(str)
                tidy = tidy.sort_values("Type")
                st.dataframe(tidy.style.format({"CHF": _format_money_chf}), use_container_width=True)

        with col2:
            st.markdown("**Heures par type**")
            if monthly_h.empty:
                st.info("Aucune colonne 'Heures_'.")
            else:
                subset = _filter_month(monthly_h).copy()
                cat_cols = [c for c in subset.columns if c not in ("Année","Mois_Num","Mois")]
                tidy = subset.melt(id_vars=["Mois"], value_vars=cat_cols, var_name="Type", value_name="Heures")
                tidy["Type"] = tidy["Type"].astype(str)
                tidy = tidy.sort_values("Type")
                st.dataframe(tidy.style.format({"Heures": _format_hours}), use_container_width=True)
