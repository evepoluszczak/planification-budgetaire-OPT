# ui/pages/analyse_budgetaire.py
from typing import Optional
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
    """Colorisation: rouge si dépassement (>0), vert si en-dessous (<0), gris si 0."""
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

def load_facturation_dir(dir_path: Path) -> pd.DataFrame:
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
    agg = (all_df.groupby("Date", as_index=False)[["Heures","Montant"]].sum())
    return agg

# ==========================
# Extraction Budget & Modifié
# ==========================

def _pick_calendar_base_and_modified():
    """
    Renvoie (df_annuel, df_modifie) en cherchant dans:
      - st.session_state[...] (top-level)
      - st.session_state['budget_state'][...] (dict bs)
    et quelques alias courants.
    """
    def _is_ok(df):
        return isinstance(df, pd.DataFrame) and (not df.empty) and ("Date" in df.columns)

    # 1) Cherche au top-level
    top_candidates = {}
    for k in [
        "calendar_df_adjusted", "calendar_df",
        "generated_calendar_df", "budget_calendar_df"
    ]:
        df = st.session_state.get(k)
        if _is_ok(df):
            top_candidates[k] = df

    # 2) Cherche dans les sous-dicts éventuels (budget_state / bs / budget)
    nested_candidates = {}
    for container_key in ["budget_state", "bs", "budget"]:
        sub = st.session_state.get(container_key)
        if isinstance(sub, dict):
            for k in [
                "calendar_df_adjusted", "calendar_df",
                "generated_calendar_df", "budget_calendar_df"
            ]:
                df = sub.get(k)
                if _is_ok(df):
                    nested_candidates[f"{container_key}.{k}"] = df

    # Fusion affichage (pour debug éventuel)
    found = {**top_candidates, **nested_candidates}

    # Sélection priorisée
    df_annuel = None
    df_mod = None

    # Préfère les clés 'adjusted' pour modifié
    for key in ["calendar_df_adjusted", "generated_calendar_df_adjusted"]:
        # top-level
        if key in top_candidates:
            df_mod = top_candidates[key]
        # nested
        for nk, v in nested_candidates.items():
            if nk.endswith("." + key):
                df_mod = v
    # Si pas trouvé, on prendra le même que l’annuel plus bas

    # Annuel : préférer 'calendar_df'
    for key in ["calendar_df", "generated_calendar_df", "budget_calendar_df"]:
        if df_annuel is None and key in top_candidates:
            df_annuel = top_candidates[key]
        if df_annuel is None:
            for nk, v in nested_candidates.items():
                if nk.endswith("." + key):
                    df_annuel = v
                    break

    # Si modifié introuvable, utilise l’annuel (équivaut à “pas d’ajustements”)
    if df_mod is None:
        df_mod = df_annuel if _is_ok(df_annuel) else pd.DataFrame()

    # Dernière sécurité
    if not _is_ok(df_annuel):
        df_annuel = pd.DataFrame()
    if not _is_ok(df_mod):
        df_mod = pd.DataFrame()

    # Stocke la liste de ce qu'on a trouvé pour le panneau debug
    st.session_state["_ab_found_calendars"] = {
        "top_level": list(top_candidates.keys()),
        "nested": list(nested_candidates.keys())
    }

    return df_annuel.copy(), df_mod.copy()


def _monthly_total(df: pd.DataFrame, prefix: str) -> pd.DataFrame:
    """Retourne Année, Mois_Num, Mois, Total (somme des colonnes prefixées)."""
    if df.empty or "Date" not in df.columns:
        return pd.DataFrame(columns=["Année","Mois_Num","Mois","Total"])
    work = df.copy()
    work["Date"] = pd.to_datetime(work["Date"], errors="coerce")
    work = work.dropna(subset=["Date"])
    cols = [c for c in work.columns if isinstance(c, str) and c.startswith(prefix)]
    if not cols:
        return pd.DataFrame(columns=["Année","Mois_Num","Mois","Total"])
    for c in cols:
        work[c] = pd.to_numeric(work[c], errors="coerce").fillna(0.0)
    work["Année"] = work["Date"].dt.year
    work["Mois_Num"] = work["Date"].dt.month
    work["Mois"] = work["Mois_Num"].map(_month_fr) + " " + work["Année"].astype(str)
    out = work.groupby(["Année","Mois_Num","Mois"], as_index=False)[cols].sum()
    out["Total"] = out[cols].sum(axis=1)
    return out[["Année","Mois_Num","Mois","Total"]].sort_values(["Année","Mois_Num"])

def _daily_series(df: pd.DataFrame, prefix: str) -> pd.DataFrame:
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

def _variance_cols(df, col_ref, col_cmp, prefix):
    """
    Ajoute 2 colonnes:
      - prefix+'_Ecart'      = col_cmp - col_ref (valeur)
      - prefix+'_Ecart_pct'  = (col_cmp - col_ref) / col_ref, sécurisé
    """
    out = df.copy()
    ref = out[col_ref].astype(float)
    cmpv = out[col_cmp].astype(float)
    out[prefix + "_Ecart"] = (cmpv - ref)
    # évite div/0 : si ref==0 & cmp==0 -> 0 ; si ref==0 & cmp>0 -> 1.0 (100%)
    out[prefix + "_Ecart_pct"] = np.where(ref == 0,
                                          np.where(cmpv == 0, 0.0, 1.0),
                                          (cmpv - ref) / ref)
    return out

# ==========================
# Page renderer
# ==========================

def render_analyse_budgetaire_page():
    st.title("Analyse Budgétaire")

    df_annuel, df_mod = _pick_calendar_base_and_modified()
    if df_annuel.empty:
        st.info("Budget non encore généré. Rendez-vous sur **Budget Annuel** pour générer le calendrier de coûts.")
        # 🔎 Panneau debug pour comprendre pourquoi
        found = st.session_state.get("_ab_found_calendars", {})
        with st.expander("Debug — Clés candidates détectées"):
            st.write("Top-level:", found.get("top_level"))
            st.write("Dans budget_state/bs:", found.get("nested"))
            # Montre aussi les clés de session pour repérage rapide
            st.write("Clés présentes dans st.session_state :", list(st.session_state.keys()))
        return

    factu_df = load_facturation_dir(FACTU_AT_DIR)

    tabs = st.tabs(["Synthèse (CHF)","Synthèse (Heures)","Courbes cumulées","Détails Mensuels"])

    # ======================
    # A) Synthèse (CHF) + écarts
    # ======================
    with tabs[0]:
        st.subheader("Synthèse (CHF) — Prévu vs Modifié vs Réalisé")

        ann_chf = _monthly_total(df_annuel, "Coût_")
        mod_chf = _monthly_total(df_mod, "Coût_")
        if ann_chf.empty:
            st.warning("Aucune colonne de coût (préfixe 'Coût_') détectée.")
        else:
            # Réalisé (facturation) mensuel
            factu_month = pd.DataFrame(columns=["Année","Mois_Num","Total"])
            if not factu_df.empty and "Montant" in factu_df.columns:
                f2 = factu_df.copy()
                f2["Date"] = pd.to_datetime(f2["Date"], errors="coerce")
                f2 = f2.dropna(subset=["Date"])
                f2["Année"] = f2["Date"].dt.year
                f2["Mois_Num"] = f2["Date"].dt.month
                factu_month = f2.groupby(["Année","Mois_Num"], as_index=False)["Montant"].sum()
                factu_month.rename(columns={"Montant":"Total"}, inplace=True)

            base = ann_chf.merge(mod_chf, on=["Année","Mois_Num","Mois"], how="outer", suffixes=("_Annuel","_Modifie")).fillna(0.0)
            base = base.merge(factu_month, on=["Année","Mois_Num"], how="left")
            base.rename(columns={"Total":"Total_Reel"}, inplace=True)
            base["Total_Reel"] = base["Total_Reel"].fillna(0.0)

            # Écarts (Modifié vs Annuel) puis (Réalisé vs Modifié)
            base = _variance_cols(base, "Total_Annuel", "Total_Modifie", "Mod_vs_Ann")
            base = _variance_cols(base, "Total_Modifie", "Total_Reel",   "Reel_vs_Mod")

            # KPIs (arrondi sup)
            k1, k2, k3 = st.columns(3)
            k1.metric("Budget Annuel (CHF)", _format_money_chf(base["Total_Annuel"].sum()))
            k2.metric("Budget Modifié (CHF)", _format_money_chf(base["Total_Modifie"].sum()))
            k3.metric("Facturation cumulée (CHF)", _format_money_chf(base["Total_Reel"].sum()))

            show = base.copy().sort_values(["Année","Mois_Num"])
            show["Mod_vs_Ann_Ecart_pct"] = show["Mod_vs_Ann_Ecart_pct"].astype(float)
            show["Reel_vs_Mod_Ecart_pct"] = show["Reel_vs_Mod_Ecart_pct"].astype(float)

            # Styling & formats
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

    # ======================
    # B) Synthèse (Heures) + écarts
    # ======================
    with tabs[1]:
        st.subheader("Synthèse (Heures) — Prévu vs Modifié vs Réalisé")

        ann_h = _monthly_total(df_annuel, "Heures_")
        mod_h = _monthly_total(df_mod, "Heures_")
        if ann_h.empty:
            st.info("Aucune colonne d'heures (préfixe 'Heures_') détectée.")
        else:
            factu_month_h = pd.DataFrame(columns=["Année","Mois_Num","Total"])
            if not factu_df.empty and "Heures" in factu_df.columns:
                f2 = factu_df.copy()
                f2["Date"] = pd.to_datetime(f2["Date"], errors="coerce")
                f2 = f2.dropna(subset=["Date"])
                f2["Année"] = f2["Date"].dt.year
                f2["Mois_Num"] = f2["Date"].dt.month
                factu_month_h = f2.groupby(["Année","Mois_Num"], as_index=False)["Heures"].sum()
                factu_month_h.rename(columns={"Heures":"Total"}, inplace=True)

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

    # ======================
    # C) Courbes cumulées (journalier → cumul)
    # ======================
    with tabs[2]:
        st.subheader("Courbes cumulées")

        daily_chf_ann = _daily_series(df_annuel, "Coût_")
        daily_chf_mod = _daily_series(df_mod, "Coût_")

        factu_daily = pd.DataFrame(columns=["Date","Montant","Heures"])
        if not factu_df.empty:
            factu_daily = factu_df.copy()
            factu_daily["Date"] = pd.to_datetime(factu_daily["Date"], errors="coerce")
            factu_daily = factu_daily.dropna(subset=["Date"]).sort_values("Date")

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
        st.subheader("Détails Mensuels")

        # options à partir du DF annuel (ou modifié si annuel vide—mais on sait qu'il n'est pas vide)
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
            cols = [c for c in work.columns if isinstance(c, str) and c.startswith(prefix)]
            if not cols:
                return pd.DataFrame()
            for c in cols:
                work[c] = pd.to_numeric(work[c], errors="coerce").fillna(0.0)
            work["Année"] = work["Date"].dt.year
            work["Mois_Num"] = work["Date"].dt.month
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
