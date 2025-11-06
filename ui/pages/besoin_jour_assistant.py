# ui/pages/besoin_jour_assistant.py
from __future__ import annotations
import datetime as dt
import pandas as pd
import numpy as np
import streamlit as st
import altair as alt

from core.assistant_engine import (
    AssistantParams, Locks, Suggestion,
    generate_suggestions, apply_suggestions, undo_last_apply
)
from core.assistant_utils import month_name_fr, day_name_fr


def _year_default() -> int:
    bs = st.session_state.get('budget_state', {})
    return int(bs.get('year', dt.date.today().year))


def _delta_from_simulator() -> dict:
    """
    Récupère un delta heures par catégorie depuis st.session_state.ajustements_proposes
    Si absent, retourne {}.
    """
    adj = st.session_state.get('ajustements_proposes')
    if not adj or not isinstance(adj, dict):
        return {}
    # priorité aux heures si présentes
    out = {}
    by_cat = adj.get("by_category", {})
    for cat, payload in by_cat.items():
        dh = payload.get("delta_hours")
        if dh is not None:
            out[cat] = float(dh)
        else:
            # fallback: à partir du delta_chf / tarif
            dchf = float(payload.get("delta_chf", 0.0) or 0.0)
            if dchf != 0:
                out[cat] = dchf / _hourly_rate_for_category(cat)
    return out


def _hourly_rate_for_category(category: str) -> float:
    cm = st.session_state.get('cost_mapping', {})
    perso = st.session_state.get('personnel', pd.DataFrame())
    ptype = cm.get(category, category)
    if isinstance(perso, pd.DataFrame) and not perso.empty:
        row = perso[ perso['Type'] == ptype ]
        if not row.empty:
            try:
                return float(row['Coût Horaire'].iloc[0])
            except Exception:
                pass
    return 45.0


def _suggestions_to_df(items: list[Suggestion]) -> pd.DataFrame:
    if not items:
        return pd.DataFrame(columns=[
            "Date","Jour","Période","Périmètre","Catégorie","Δ Heures","Δ Coût (CHF)","Score","Motifs"
        ])
    rows = []
    for s in items:
        rows.append({
            "Date": pd.to_datetime(s.date),
            "Jour": day_name_fr(pd.to_datetime(s.date).weekday()),
            "Période": f"{s.slot_start}–{s.slot_end}",
            "Périmètre": s.perimetre,
            "Catégorie": s.categorie,
            "Δ Heures": float(s.delta_hours),
            "Δ Coût (CHF)": float(s.delta_chf),
            "Score": float(s.score),
            "Motifs": " · ".join(s.motifs or []),
        })
    df = pd.DataFrame(rows).sort_values(["Date","Périmètre","Catégorie","Période"]).reset_index(drop=True)
    return df


def render_besoin_jour_assistant_page():
    st.title("Assistant Besoin Jour")
    st.markdown(
        "Propose automatiquement **où** ajouter/retirer des heures en s’appuyant sur "
        "les **PAX**, la **grille effective** et des **contraintes opérationnelles**. "
        "Vous pouvez importer un objectif depuis le *Simulateur d’Objectif*, affiner les paramètres, "
        "puis **appliquer** tout ou partie des suggestions."
    )

    # Vérifs de base
    bs = st.session_state.get('budget_state', {})
    if not bs or 'calendar_df' not in bs or bs['calendar_df'].empty:
        st.warning("⚠️ Aucun budget annuel valide en mémoire. Générez d’abord un budget.")
        st.stop()

    # Choix année
    year = st.number_input("Année d’analyse", value=_year_default(), min_value=2023, max_value=2050, step=1)

    with st.expander("⚙️ Paramètres de génération", expanded=True):
        cols = st.columns(2)
        with cols[0]:
            use_sim = st.toggle("Importer l’objectif du *Simulateur d’Objectif*", value=True)
            if use_sim:
                delta_hours = _delta_from_simulator()
            else:
                # entrée manuelle (simple):  AT / ATR / ATF visibles si existants dans perimetres
                cats = sorted(list(st.session_state.get('perimetres', {}).keys()))
                delta_hours = {}
                for cat in cats:
                    delta_hours[cat] = st.number_input(f"Δ heures {cat}", value=0.0, step=1.0, format="%.1f", key=f"manual_{cat}")
        with cols[1]:
            st.caption("Pondérations du score")
            w_int = st.slider("Poids Intensité PAX", 0.0, 1.0, 0.35, 0.05)
            w_rat = st.slider("Poids Ratio PAX/heure", 0.0, 1.0, 0.25, 0.05)
            w_sta = st.slider("Poids Stabilité", 0.0, 1.0, 0.15, 0.05)
            w_his = st.slider("Poids Historique", 0.0, 1.0, 0.15, 0.05)
            w_eve = st.slider("Pénalité Évènements", 0.0, 1.0, 0.10, 0.05)

        params = AssistantParams(
            w_intensity=w_int, w_ratio=w_rat, w_stability=w_sta, w_history=w_his, w_events=w_eve,
            min_block_hours=st.number_input("Taille minimale d’une suggestion (h)", value=1.0, step=0.5),
            unit=st.number_input("Granularité d’allocation (h)", value=0.5, step=0.5),
            honor_min_agents=st.toggle("Respecter le plancher agents (ne pas descendre sous l’actuel)", value=True)
        )

        st.divider()
        st.caption("🔒 Verrous (exclus)")
        cats_all = sorted(list(st.session_state.get('perimetres', {}).keys()))
        perims_all = sorted({p for lst in st.session_state.get('perimetres', {}).values() for p in lst})

        c1, c2 = st.columns(2)
        with c1:
            locked_cats = st.multiselect("Catégories verrouillées", cats_all, default=[])
        with c2:
            locked_perims = st.multiselect("Périmètres verrouillés", perims_all, default=[])

        lock_dates = st.date_input("Dates verrouillées", value=[], format="DD/MM/YYYY")

        locks = Locks(
            categories=locked_cats,
            perimetres=locked_perims,
            dates=[d for d in lock_dates] if isinstance(lock_dates, list) else [lock_dates]
        )

        st.divider()
        gen = st.button("⚡ Générer des suggestions", type="primary", use_container_width=True)

    if gen:
        suggs = generate_suggestions(year=int(year), delta_by_category_hours=delta_hours, locks=locks, params=params)
        if not suggs:
            st.info("Aucune suggestion n’a pu être générée (verrous trop stricts ou pas de delta à couvrir).")

    # Liste des suggestions courantes (en mémoire)
    suggestions = st.session_state.get("assistant_suggestions", [])
    df_sugg = _suggestions_to_df(suggestions)

    st.markdown("---")
    st.subheader("📋 Suggestions proposées")
    if df_sugg.empty:
        st.info("Générez des suggestions pour les voir apparaître ici.")
    else:
        # Heatmap par mois
        df_hm = df_sugg.copy()
        df_hm['Date'] = pd.to_datetime(df_hm['Date'])
        df_hm['Mois'] = df_hm['Date'].dt.month.map(lambda m: month_name_fr(m))
        df_hm['Δh_abs'] = df_hm['Δ Heures'].abs()

        with st.container():
            st.caption("Distribution des ajustements par mois et catégorie (aire ∝ |Δh|)")
            chart = alt.Chart(df_hm).mark_circle().encode(
                x=alt.X("Mois:N", sort=list(map(month_name_fr, range(1,13)))),
                y=alt.Y("Catégorie:N"),
                size=alt.Size("Δh_abs:Q", title="|Δ Heures|"),
                color=alt.Color("Δ Heures:Q", scale=alt.Scale(scheme="redblue"), title="Δ Heures"),
                tooltip=["Mois","Catégorie","Périmètre","Période","Δ Heures","Δ Coût (CHF)","Score"]
            ).properties(height=300)
            st.altair_chart(chart, use_container_width=True)

        st.dataframe(
            df_sugg,
            hide_index=True,
            use_container_width=True,
            column_config={
                "Date": st.column_config.DatetimeColumn("Date", format="DD/MM/YYYY"),
                "Δ Heures": st.column_config.NumberColumn("Δ Heures", format="%.1f h"),
                "Δ Coût (CHF)": st.column_config.NumberColumn("Δ Coût (CHF)", format="%.0f"),
                "Score": st.column_config.NumberColumn("Score", format="%.2f"),
            }
        )

        cA, cB, cC = st.columns(3)
        with cA:
            if st.button("✅ Appliquer toutes les suggestions", type="primary", use_container_width=True):
                apply_suggestions(suggestions)
                st.success("Suggestions appliquées (journal créé pour annulation).")
        with cB:
            if st.button("↩️ Annuler la dernière application", use_container_width=True):
                undo_last_apply()
                st.info("Dernière application annulée.")
        with cC:
            if st.button("🗑️ Effacer les suggestions", use_container_width=True):
                st.session_state.assistant_suggestions = []
                st.experimental_rerun()
