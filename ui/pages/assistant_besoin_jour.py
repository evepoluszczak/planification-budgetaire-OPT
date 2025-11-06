# ui/pages/assistant_besoin_jour.py
"""
Assistant Besoin Jour
- Construit le ratio AT/PAX par jour en récupérant automatiquement :
  * PAX (forecast, 30' ou daily) via plusieurs clés possibles dans session_state
  * Heures AT Modifié (sinon Annuel)
- Repère automatiquement s'il faut AJOUTER ou RETIRER des heures (via Simulateur d'Objectif)
- Propose des jours cibles (faible ratio pour AJOUTER, ratio élevé pour RETIRER)
- Stocke les suggestions et un mini "ops" JSON dans session_state pour application ultérieure
"""

from __future__ import annotations

import pandas as pd
import numpy as np
import streamlit as st
import calendar
import datetime as dt


# =============== Helpers diagnostics & chargement ===============

def _why_no_ratio():
    msgs = []

    # 1) PAX sources
    pax_sources = [
        ("pax_daily",    st.session_state.get("pax_daily")),
        ("pax_forecast", st.session_state.get("pax_forecast")),
        ("pax_merged",   st.session_state.get("pax_merged")),
        ("pax_data",     st.session_state.get("pax_data")),
        ("pax_df_30min", st.session_state.get("pax_df_30min")),
        ("pax_30min",    st.session_state.get("pax_30min")),
    ]
    pax_ok = any(isinstance(obj, pd.DataFrame) and not obj.empty for _, obj in pax_sources)
    if not pax_ok:
        msgs.append("Aucune source PAX exploitable trouvée (pax_daily / pax_forecast / pax_merged / ...).")

    # 2) Heures (Modifié/Annuel)
    bs = st.session_state.get("budget_state", {}) or {}
    ann = bs.get("calendar_df", pd.DataFrame())
    mod = (st.session_state.get("budget_modifie_state") or {}).get("calendar_df", pd.DataFrame())
    if (not isinstance(mod, pd.DataFrame) or mod.empty) and (not isinstance(ann, pd.DataFrame) or ann.empty):
        msgs.append("Aucun calendar_df (Annuel) ni calendar_df (Modifié) disponible.")

    if msgs:
        return " / ".join(msgs)
    return None


def _daily_pax_from_forecast(flux: str = "Tous") -> pd.DataFrame:
    """
    Retourne un DF [Date, Pax_Total].
    Cherche plusieurs clés de session_state et accepte soit un DF déjà daily,
    soit des séries 15'/30' à agréger par jour.
    """
    candidates = [
        st.session_state.get("pax_daily"),
        st.session_state.get("pax_forecast"),
        st.session_state.get("pax_merged"),
        st.session_state.get("pax_data"),
        st.session_state.get("pax_df_30min"),
        st.session_state.get("pax_30min"),
    ]
    df_src = next((d for d in candidates if isinstance(d, pd.DataFrame) and not d.empty), None)
    if df_src is None:
        return pd.DataFrame()

    df = df_src.copy()

    # CAS 1: déjà daily
    if "Date" in df.columns and any(c in df.columns for c in ["Pax_Total", "PAX", "Pax"]):
        date_col = "Date"
        pax_col = next(c for c in ["Pax_Total", "PAX", "Pax"] if c in df.columns)
        out = df[[date_col, pax_col]].copy()
        out.rename(columns={pax_col: "Pax_Total"}, inplace=True)
        out["Date"] = pd.to_datetime(out["Date"]).dt.normalize()
        out = out.groupby("Date", as_index=False)["Pax_Total"].sum()
        return out

    # CAS 2: granularité 15'/30'
    if "DateTime" in df.columns:
        df["DateTime"] = pd.to_datetime(df["DateTime"])
        df = df.set_index("DateTime")

    if not isinstance(df.index, pd.DatetimeIndex):
        try:
            df.index = pd.to_datetime(df.index)
        except Exception:
            return pd.DataFrame()

    def _sum_cols(cands):
        cols = [c for c in cands if c in df.columns]
        return df[cols].sum(axis=1) if cols else None

    if flux == "Arrivée":
        s = _sum_cols(["Pax_Schengen_A", "Pax_NonSchengen_A", "PAX_A", "Pax_A", "Arrivals"])
    elif flux == "Départ":
        s = _sum_cols(["Pax_Schengen_D", "Pax_NonSchengen_D", "PAX_D", "Pax_D", "Departures"])
    else:
        sA = _sum_cols(["Pax_Schengen_A", "Pax_NonSchengen_A", "PAX_A", "Pax_A", "Arrivals"])
        sD = _sum_cols(["Pax_Schengen_D", "Pax_NonSchengen_D", "PAX_D", "Pax_D", "Departures"])
        if sA is not None and sD is not None:
            s = sA.add(sD, fill_value=0)
        else:
            s = sA or sD

    if s is None or s.empty:
        # dernier recours: toutes colonnes numériques
        num = df.select_dtypes(include=[np.number])
        s = num.sum(axis=1) if not num.empty else None
    if s is None or s.empty:
        return pd.DataFrame()

    daily = s.groupby(s.index.normalize()).sum()
    out = pd.DataFrame({"Date": daily.index, "Pax_Total": daily.values})
    out["Date"] = pd.to_datetime(out["Date"]).dt.normalize()
    return out


def _daily_hours_from_calendar(prefer_modifie: bool = True) -> pd.DataFrame:
    """
    Retourne DF [Date, Heures_AT].
    Cherche d’abord calendar_df du budget_modifie_state (si présent),
    sinon calendar_df de budget_state (Annuel).
    Utilise 'Heures_AT' si présente, sinon 'Heures_Total_Jour'.
    """
    bs = st.session_state.get("budget_state", {}) or {}
    ann = bs.get("calendar_df", pd.DataFrame())
    mod = (st.session_state.get("budget_modifie_state") or {}).get("calendar_df", pd.DataFrame())

    base = mod if (prefer_modifie and isinstance(mod, pd.DataFrame) and not mod.empty) else ann
    if not isinstance(base, pd.DataFrame) or base.empty:
        return pd.DataFrame()

    base = base.copy()
    base["Date"] = pd.to_datetime(base["Date"]).dt.normalize()

    col = None
    for c in ["Heures_AT", "Heures_AT_jour", "Heures_Total_Jour"]:
        if c in base.columns:
            col = c; break
    if col is None:
        return pd.DataFrame()

    h = base.groupby("Date", as_index=False)[col].sum()
    return h.rename(columns={col: "Heures_AT"})


def _build_ratio_df() -> pd.DataFrame:
    """
    Joint PAX/day et Heures AT/day -> ratio AT par 1'000 PAX.
    Colonnes: Date, Pax_Total, Heures_AT, Ratio_AT_par_1000PAX, Jour_FR, Mois_FR, Saison
    (Saison si dispo dans calendar_df)
    """
    pax = _daily_pax_from_forecast()
    hrs = _daily_hours_from_calendar()

    if pax.empty or hrs.empty:
        return pd.DataFrame()

    df = pd.merge(hrs, pax, on="Date", how="inner")
    if df.empty:
        return pd.DataFrame()

    df["Pax_Total"] = pd.to_numeric(df["Pax_Total"], errors="coerce").fillna(0.0)
    df["Heures_AT"] = pd.to_numeric(df["Heures_AT"], errors="coerce").fillna(0.0)
    df = df[df["Pax_Total"] > 0].copy()
    if df.empty:
        return pd.DataFrame()

    df["Ratio_AT_par_1000PAX"] = (df["Heures_AT"] / df["Pax_Total"]) * 1000.0

    # Jour_FR & Mois_FR
    jours_fr = ["Lundi","Mardi","Mercredi","Jeudi","Vendredi","Samedi","Dimanche"]
    df["Jour_FR"] = df["Date"].dt.dayofweek.map(lambda i: jours_fr[i])
    # Mois en français
    mois_fr = {
        1: "Janvier", 2: "Février", 3: "Mars", 4: "Avril", 5: "Mai", 6: "Juin",
        7: "Juillet", 8: "Août", 9: "Septembre", 10: "Octobre", 11: "Novembre", 12: "Décembre"
    }
    df["Mois_FR"] = df["Date"].dt.month.map(mois_fr)

    # Saison si dispo dans calendar_df
    saison_map = {}
    bs = st.session_state.get("budget_state", {}) or {}
    for dsrc in [ (st.session_state.get("budget_modifie_state") or {}).get("calendar_df"),
                  bs.get("calendar_df")]:
        if isinstance(dsrc, pd.DataFrame) and not dsrc.empty and "Date" in dsrc.columns and "Saison" in dsrc.columns:
            tmp = dsrc[["Date","Saison"]].copy()
            tmp["Date"] = pd.to_datetime(tmp["Date"]).dt.normalize()
            for r in tmp.itertuples(index=False):
                saison_map[r.Date] = r.Saison
            break
    df["Saison"] = df["Date"].map(saison_map).fillna("—")

    return df


def _get_simulated_hour_delta_from_simulateur() -> float:
    """
    Va lire la dernière simulation du Simulateur d'Objectif (si présente)
    et récupère la somme des 'Ajustement Heures (h)' pour la catégorie AT uniquement.
    Convention: le Simulateur sauvegarde dans st.session_state['sim_objectif_current'] un dict:
      {
         'results': DataFrame(columns=[Catégorie, Ajustement Heures (h), ...]),
         'target_adjustment': float, 'distribution': dict, ...
      }
    """
    sim = st.session_state.get("sim_objectif_current") or {}
    df = sim.get("results")
    if not isinstance(df, pd.DataFrame) or df.empty:
        return 0.0

    # On ne cible que la catégorie AT (cohérent avec Besoin Jour sur AT)
    if "Catégorie" not in df.columns or "Ajustement Heures (h)" not in df.columns:
        return 0.0

    dff = df[df["Catégorie"].astype(str) == "AT"].copy()
    if dff.empty:
        return 0.0

    try:
        return float(pd.to_numeric(dff["Ajustement Heures (h)"], errors="coerce").fillna(0).sum())
    except Exception:
        return 0.0


def _pick_days(df_ratio: pd.DataFrame, needed_hours: float, per_day_step: float) -> pd.DataFrame:
    """
    Choisit des jours pour ajouter/retirer des heures.
    - needed_hours > 0 => il faut AJOUTER des heures -> on prend d'abord les jours à plus FAIBLE ratio
    - needed_hours < 0 => il faut RETIRER des heures -> on prend d'abord les jours à plus FORT ratio
    Retourne un DF avec colonnes:
      Date, Jour_FR, Mois_FR, Saison, Pax_Total, Heures_AT, Ratio_AT_par_1000PAX, Delta_Heures
    """
    if df_ratio.empty or per_day_step <= 0:
        return pd.DataFrame()

    df = df_ratio.sort_values(
        "Ratio_AT_par_1000PAX",
        ascending=True if needed_hours > 0 else False
    ).copy()

    remain = abs(needed_hours)
    deltas = []
    for _, r in df.iterrows():
        if remain <= 0:
            break
        step = min(per_day_step, remain)
        deltas.append(step)
        remain -= step

    df = df.iloc[:len(deltas)].copy()
    df["Delta_Heures"] = [d if needed_hours > 0 else -d for d in deltas]
    return df


# ============================ UI principale ============================

def render_besoin_jour_assistant_page():
    st.title("Assistant Besoin Jour — Ciblage des jours (AT/PAX)")

    # Debug panel (utile si rien ne s'affiche)
    with st.expander("🧪 Debug AT/PAX (si besoin)"):
        msg = _why_no_ratio()
        if msg:
            st.error("Pourquoi le ratio est indisponible : " + msg)
        else:
            st.success("Sources présentes : PAX + Heures (Annuel/Modifié) OK.")
        # Aperçus
        pax = _daily_pax_from_forecast()
        hrs = _daily_hours_from_calendar()
        c1, c2 = st.columns(2)
        with c1:
            st.caption("Aperçu PAX/jour")
            if isinstance(pax, pd.DataFrame) and not pax.empty:
                st.dataframe(pax.head(10), use_container_width=True, hide_index=True)
            else:
                st.write("—")
        with c2:
            st.caption("Aperçu Heures AT/jour")
            if isinstance(hrs, pd.DataFrame) and not hrs.empty:
                st.dataframe(hrs.head(10), use_container_width=True, hide_index=True)
            else:
                st.write("—")

    # Construire la base ratio
    df_ratio = _build_ratio_df()
    if df_ratio.empty:
        st.warning("Pas de données suffisantes pour calculer le ratio AT/PAX.")
        st.stop()

    # Filtres
    st.markdown("---")
    st.subheader("Filtres")

    # Mois FR uniques dans l'ordre calendrier
    mois_order = ["Janvier","Février","Mars","Avril","Mai","Juin","Juillet","Août","Septembre","Octobre","Novembre","Décembre"]
    mois_dispo = [m for m in mois_order if m in df_ratio["Mois_FR"].unique().tolist()]
    jours_fr = ["Lundi","Mardi","Mercredi","Jeudi","Vendredi","Samedi","Dimanche"]
    jours_dispo = [j for j in jours_fr if j in df_ratio["Jour_FR"].unique().tolist()]
    saisons_dispo = sorted([s for s in df_ratio["Saison"].unique().tolist() if isinstance(s, str)])

    colf1, colf2, colf3 = st.columns(3)
    with colf1:
        sel_mois = st.multiselect("Mois", options=mois_dispo, default=mois_dispo)
    with colf2:
        sel_jour = st.multiselect("Jour de semaine", options=jours_dispo, default=jours_dispo)
    with colf3:
        sel_saison = st.multiselect("Saison", options=saisons_dispo, default=saisons_dispo)

    dff = df_ratio[
        df_ratio["Mois_FR"].isin(sel_mois) &
        df_ratio["Jour_FR"].isin(sel_jour) &
        df_ratio["Saison"].isin(sel_saison)
    ].copy()
    if dff.empty:
        st.warning("Aucune ligne après filtres.")
        st.stop()

    st.markdown("—")
    st.subheader("Paramètres de ciblage")

    # Heures à ajuster : récup depuis Simulateur (catégorie AT)
    sim_delta_h = _get_simulated_hour_delta_from_simulateur()
    if sim_delta_h == 0.0:
        st.info("Aucun ajustement d'heures AT détecté depuis le Simulateur d’Objectif (catégorie AT). "
                "Vous pouvez quand même saisir un objectif manuel ci-dessous.")
    colp1, colp2, colp3 = st.columns([1,1,1])
    with colp1:
        hours_target = st.number_input(
            "Objectif d'ajustement (heures, + pour AJOUTER / − pour RETIRER)",
            value=float(sim_delta_h),
            step=10.0,
            format="%.0f"
        )
    with colp2:
        per_day_step = st.number_input(
            "Pas par jour (h)",
            value=2.0, step=0.5, min_value=0.5, format="%.1f",
            help="Quantité d'heures à proposer par jour sélectionné (sera plafonnée par l’objectif)."
        )
    with colp3:
        max_days = st.number_input(
            "Nombre max. de jours proposés",
            value=20, min_value=1, step=1
        )

    # Rappels KPI
    st.markdown("—")
    c1, c2, c3 = st.columns(3)
    with c1:
        st.metric("Jours filtrés", f"{len(dff):,}".replace(",", " "))
    with c2:
        st.metric("PAX moyen / jour", f"{dff['Pax_Total'].mean():,.0f}".replace(",", " "))
    with c3:
        st.metric("Heures AT moy. / jour", f"{dff['Heures_AT'].mean():,.1f} h".replace(",", " "))

    # Action
    st.markdown("—")
    if st.button("🎯 Proposer des jours cibles (AT/PAX)"):
        if hours_target == 0:
            st.warning("Objectif à 0h — rien à proposer.")
        else:
            # Choisir jours
            ranked = dff.sort_values(
                "Ratio_AT_par_1000PAX",
                ascending=True if hours_target > 0 else False
            ).copy()
            # On sélectionne jusqu’à max_days, mais le delta réel est packé avec _pick_days
            ranked = ranked.head(int(max_days)).copy()

            picked = _pick_days(ranked, hours_target, per_day_step)
            if picked.empty:
                st.warning("Impossible de construire des propositions avec les paramètres actuels.")
            else:
                # Sauvegarde suggestions et mini-ops
                suggestions = picked[[
                    "Date","Jour_FR","Mois_FR","Saison","Pax_Total","Heures_AT","Ratio_AT_par_1000PAX","Delta_Heures"
                ]].copy()

                st.session_state["besoin_jour_assistant_suggestions"] = suggestions.copy()

                # Construire un format d'opérations simple (à consommer par la page Besoin Jour si besoin)
                ops = []
                for r in suggestions.itertuples(index=False):
                    ops.append({
                        "date": pd.to_datetime(r.Date).date().isoformat(),
                        "category": "AT",
                        "delta_hours": float(r.Delta_Heures),
                        "reason": "Assistant AT/PAX",
                        "context": {
                            "pax": float(r.Pax_Total),
                            "heures_at": float(r.Heures_AT),
                            "ratio_at_per_1000pax": float(r.Ratio_AT_par_1000PAX)
                        }
                    })
                st.session_state["besoin_jour_assistant_ops"] = ops

                st.success(f"{len(suggestions)} jours proposés. Voir le tableau ci-dessous.")
                st.dataframe(
                    suggestions,
                    use_container_width=True,
                    hide_index=True,
                    column_config={
                        "Date": st.column_config.DatetimeColumn(format="YYYY-MM-DD"),
                        "Pax_Total": st.column_config.NumberColumn("PAX", format="%.0f"),
                        "Heures_AT": st.column_config.NumberColumn("Heures AT", format="%.1f h"),
                        "Ratio_AT_par_1000PAX": st.column_config.NumberColumn("AT / 1000 PAX", format="%.2f"),
                        "Delta_Heures": st.column_config.NumberColumn("Δ Heures (proposé)", format="%.1f h"),
                    }
                )

                st.download_button(
                    "⬇️ Exporter les suggestions (CSV)",
                    data=suggestions.to_csv(index=False).encode("utf-8"),
                    file_name="assistant_besoin_jour_suggestions.csv",
                    mime="text/csv",
                    use_container_width=True
                )

                st.download_button(
                    "⬇️ Exporter les opérations (JSON)",
                    data=pd.Series(ops).to_json(orient="values").encode("utf-8"),
                    file_name="assistant_besoin_jour_ops.json",
                    mime="application/json",
                    use_container_width=True
                )

    # Afficher dernières suggestions si présentes
    if "besoin_jour_assistant_suggestions" in st.session_state:
        st.markdown("---")
        st.subheader("Dernières suggestions générées")
        s = st.session_state["besoin_jour_assistant_suggestions"]
        st.dataframe(
            s,
            use_container_width=True,
            hide_index=True
        )


if __name__ == "__main__":
    render_besoin_jour_assistant_page()
