"""
Page Analyse Budgétaire - Comparaison Budget vs Réalisé
"""
import datetime as dt
import pandas as pd
import numpy as np
import streamlit as st
import altair as alt
from pathlib import Path
from config.constants import FACTU_AT_DIR, TIME_SLOTS
from core.planning import _ensure_grid, _apply_ops_to_grid
from core.data_loader import load_facturation_at_month


def _load_facturation_year(year: int, factu_dir: Path) -> pd.DataFrame:
    """
    Charge toutes les données de facturation pour une année donnée.
    Retourne un DataFrame avec Date, Heures, Coût
    """
    monthly_data = []

    for month in range(1, 13):
        df = load_facturation_at_month(year, month, factu_dir)
        if df.empty:
            continue

        # Parser les lignes de total par date
        for _, row in df.iterrows():
            date_val = row.get('Date ouvrable', '')
            if not isinstance(date_val, str) or not date_val.startswith('Total '):
                continue

            # Extraire la date
            try:
                date_str = date_val.replace('Total ', '').strip()
                date_obj = pd.to_datetime(date_str, format='%d.%m.%Y', errors='coerce')
                if pd.isna(date_obj):
                    continue

                # Extraire les heures
                heures_val = row.get('Heures', 0)
                if isinstance(heures_val, str):
                    # Format "hh:mm" ou nombre
                    if ':' in heures_val:
                        parts = heures_val.split(':')
                        heures = float(parts[0]) + float(parts[1]) / 60
                    else:
                        heures = float(heures_val.replace(',', '.'))
                else:
                    heures = float(heures_val)

                monthly_data.append({
                    'Date': date_obj.date(),
                    'Heures': heures
                })
            except Exception:
                continue

    if not monthly_data:
        return pd.DataFrame(columns=['Date', 'Heures', 'Coût'])

    result_df = pd.DataFrame(monthly_data)

    # Calculer le coût avec le tarif AT
    tarif_at = 0.0
    personnel_type_at = st.session_state.get('cost_mapping', {}).get("AT")
    if personnel_type_at:
        personnel_df = st.session_state.get('personnel', pd.DataFrame())
        if not personnel_df.empty:
            row_tarif = personnel_df[personnel_df['Type'] == personnel_type_at]
            if not row_tarif.empty:
                tarif_at = float(row_tarif['Coût Horaire'].iloc[0])

    result_df['Coût'] = result_df['Heures'] * tarif_at

    return result_df


def _calculate_modified_budget(bs: dict) -> tuple:
    """
    Calcule le budget modifié avec les ajustements Besoin Jour.
    Retourne (calendar_dyn, total_heures, total_cout)
    """
    calendar_dyn = bs['calendar_df'].copy()

    heures_vals_at_recalc = []
    costs_vals_at_recalc = []

    tarif_at = 0.0
    personnel_type_at = st.session_state.get('cost_mapping', {}).get("AT")
    if personnel_type_at:
        personnel_df = st.session_state.get('personnel', pd.DataFrame())
        if not personnel_df.empty:
            row_tarif = personnel_df[personnel_df['Type'] == personnel_type_at]
            if not row_tarif.empty:
                tarif_at = float(row_tarif['Coût Horaire'].iloc[0])

    perimetres_AT = st.session_state.perimetres.get("AT", [])
    time_slots_default = TIME_SLOTS
    planning_dict_at = st.session_state.planning_data.get("AT", {})

    for _, r in calendar_dyn.iterrows():
        jour, saison, date_ = r['Jour'], r['Saison'], r['Date'].date()
        jtg = r['Jour_Type_Global']
        _, base_df_at = _ensure_grid(
            planning_dict_at, jtg, perimetres_AT, time_slots_default
        )
        eff_df_at = _apply_ops_to_grid(
            base_df_at, date_, jour, saison, category="AT"
        )
        day_hours = eff_df_at.values.sum() * 0.5
        heures_vals_at_recalc.append(day_hours)
        costs_vals_at_recalc.append(day_hours * tarif_at)

    calendar_dyn["Heures_AT_Modif"] = heures_vals_at_recalc
    calendar_dyn["Coût_AT_Modif"] = costs_vals_at_recalc

    # Recalculer les totaux avec toutes les catégories
    heure_cols_categories = [c for c in calendar_dyn.columns
                            if c.startswith('Heures_') and c != 'Heures_Total_Jour' and c != 'Heures_AT_Modif']
    cout_cols_categories = [c for c in calendar_dyn.columns
                           if c.startswith('Coût_') and c != 'Coût_Total_Jour' and c != 'Coût_AT_Modif']

    # Remplacer les heures/coûts AT par les valeurs modifiées
    if 'Heures_AT' in calendar_dyn.columns:
        heure_cols_categories = [c for c in heure_cols_categories if c != 'Heures_AT']
        heure_cols_categories.append('Heures_AT_Modif')

    if 'Coût_AT' in calendar_dyn.columns:
        cout_cols_categories = [c for c in cout_cols_categories if c != 'Coût_AT']
        cout_cols_categories.append('Coût_AT_Modif')

    calendar_dyn['Heures_Total_Modif'] = calendar_dyn[heure_cols_categories].sum(axis=1)
    calendar_dyn['Coût_Total_Modif'] = calendar_dyn[cout_cols_categories].sum(axis=1)

    total_heures = calendar_dyn['Heures_Total_Modif'].sum()
    total_cout = calendar_dyn['Coût_Total_Modif'].sum()

    return calendar_dyn, total_heures, total_cout


def render_analyse_budgetaire_page():
    """Affiche la page Analyse Budgétaire"""
    st.title("Analyse Budgétaire")
    st.markdown(
        "Comparaison entre le **Budget Annuel** (prévision), "
        "le **Budget Modifié** (avec ajustements Besoin Jour), "
        "et le **Réalisé** (facturation)."
    )

    bs = st.session_state.get('budget_state', {})
    if not bs or 'year' not in bs or 'calendar_df' not in bs or bs['calendar_df'].empty:
        st.warning(
            "⚠️ Aucun budget annuel valide en mémoire. "
            "Veuillez d'abord en générer un via la page **Budget Annuel**."
        )
        st.stop()

    year = bs['year']

    # =================== CALCULS ===================

    with st.spinner("Chargement des données..."):
        # 1. Budget Annuel (prévision de base)
        budget_annuel_heures = bs.get('totals', {}).get('heures_annuelles', 0)
        budget_annuel_cout = bs.get('totals', {}).get('cout_annuel', 0)

        # 2. Budget Modifié (avec ajustements)
        calendar_modif, budget_modif_heures, budget_modif_cout = _calculate_modified_budget(bs)

        # 3. Réalisé (facturation)
        facturation_df = _load_facturation_year(year, FACTU_AT_DIR)

        if facturation_df.empty:
            realise_heures = 0
            realise_cout = 0
            st.info(f"ℹ️ Aucune donnée de facturation trouvée pour {year}")
        else:
            realise_heures = facturation_df['Heures'].sum()
            realise_cout = facturation_df['Coût'].sum()

    # =================== SYNTHÈSE CHF ===================

    st.subheader("💰 Synthèse Coût (CHF)")

    col1, col2, col3 = st.columns(3)

    with col1:
        st.metric(
            "Budget Annuel",
            f"{budget_annuel_cout:,.0f} CHF"
        )

    with col2:
        ecart_modif_annuel = budget_modif_cout - budget_annuel_cout
        pct_modif_annuel = (ecart_modif_annuel / budget_annuel_cout * 100) if budget_annuel_cout > 0 else 0
        st.metric(
            "Budget Modifié",
            f"{budget_modif_cout:,.0f} CHF",
            f"{ecart_modif_annuel:+,.0f} CHF ({pct_modif_annuel:+.1f}%)"
        )

    with col3:
        ecart_realise_modif = realise_cout - budget_modif_cout
        pct_realise_modif = (ecart_realise_modif / budget_modif_cout * 100) if budget_modif_cout > 0 else 0
        st.metric(
            "Réalisé",
            f"{realise_cout:,.0f} CHF",
            f"{ecart_realise_modif:+,.0f} CHF ({pct_realise_modif:+.1f}%)"
        )

    # Tableau détaillé CHF
    with st.expander("📊 Détails des écarts (CHF)"):
        ecarts_df = pd.DataFrame({
            'Indicateur': ['Budget Annuel', 'Budget Modifié', 'Réalisé'],
            'Montant (CHF)': [budget_annuel_cout, budget_modif_cout, realise_cout],
            'Écart vs Précédent (CHF)': [0, ecart_modif_annuel, ecart_realise_modif],
            'Écart vs Précédent (%)': [0, pct_modif_annuel, pct_realise_modif]
        })

        st.dataframe(
            ecarts_df,
            column_config={
                'Montant (CHF)': st.column_config.NumberColumn(format="%.0f"),
                'Écart vs Précédent (CHF)': st.column_config.NumberColumn(format="%+.0f"),
                'Écart vs Précédent (%)': st.column_config.NumberColumn(format="%+.1f%%")
            },
            hide_index=True,
            use_container_width=True
        )

    st.divider()

    # =================== SYNTHÈSE HEURES ===================

    st.subheader("⏱️ Synthèse Heures")

    col1, col2, col3 = st.columns(3)

    with col1:
        st.metric(
            "Budget Annuel",
            f"{budget_annuel_heures:,.0f} h"
        )

    with col2:
        ecart_modif_annuel_h = budget_modif_heures - budget_annuel_heures
        pct_modif_annuel_h = (ecart_modif_annuel_h / budget_annuel_heures * 100) if budget_annuel_heures > 0 else 0
        st.metric(
            "Budget Modifié",
            f"{budget_modif_heures:,.0f} h",
            f"{ecart_modif_annuel_h:+,.0f} h ({pct_modif_annuel_h:+.1f}%)"
        )

    with col3:
        ecart_realise_modif_h = realise_heures - budget_modif_heures
        pct_realise_modif_h = (ecart_realise_modif_h / budget_modif_heures * 100) if budget_modif_heures > 0 else 0
        st.metric(
            "Réalisé",
            f"{realise_heures:,.0f} h",
            f"{ecart_realise_modif_h:+,.0f} h ({pct_realise_modif_h:+.1f}%)"
        )

    # Tableau détaillé Heures
    with st.expander("📊 Détails des écarts (Heures)"):
        ecarts_h_df = pd.DataFrame({
            'Indicateur': ['Budget Annuel', 'Budget Modifié', 'Réalisé'],
            'Heures': [budget_annuel_heures, budget_modif_heures, realise_heures],
            'Écart vs Précédent (h)': [0, ecart_modif_annuel_h, ecart_realise_modif_h],
            'Écart vs Précédent (%)': [0, pct_modif_annuel_h, pct_realise_modif_h]
        })

        st.dataframe(
            ecarts_h_df,
            column_config={
                'Heures': st.column_config.NumberColumn(format="%.0f"),
                'Écart vs Précédent (h)': st.column_config.NumberColumn(format="%+.0f"),
                'Écart vs Précédent (%)': st.column_config.NumberColumn(format="%+.1f%%")
            },
            hide_index=True,
            use_container_width=True
        )

    st.divider()

    # =================== COURBES CUMULÉES ===================

    st.subheader("📈 Évolution Cumulée Mensuelle")

    # Préparer les données mensuelles
    calendar_base = bs['calendar_df'].copy()
    calendar_base['Mois'] = pd.to_datetime(calendar_base['Date']).dt.to_period('M')

    # Budget Annuel (mensuel)
    monthly_annuel = calendar_base.groupby('Mois').agg({
        'Heures_Total_Jour': 'sum',
        'Coût_Total_Jour': 'sum'
    }).reset_index()
    monthly_annuel['Mois'] = monthly_annuel['Mois'].astype(str)
    monthly_annuel['Heures_Cumul'] = monthly_annuel['Heures_Total_Jour'].cumsum()
    monthly_annuel['Coût_Cumul'] = monthly_annuel['Coût_Total_Jour'].cumsum()
    monthly_annuel['Type'] = 'Budget Annuel'

    # Budget Modifié (mensuel)
    calendar_modif['Mois'] = pd.to_datetime(calendar_modif['Date']).dt.to_period('M')
    monthly_modif = calendar_modif.groupby('Mois').agg({
        'Heures_Total_Modif': 'sum',
        'Coût_Total_Modif': 'sum'
    }).reset_index()
    monthly_modif['Mois'] = monthly_modif['Mois'].astype(str)
    monthly_modif['Heures_Cumul'] = monthly_modif['Heures_Total_Modif'].cumsum()
    monthly_modif['Coût_Cumul'] = monthly_modif['Coût_Total_Modif'].cumsum()
    monthly_modif['Type'] = 'Budget Modifié'

    # Réalisé (mensuel)
    if not facturation_df.empty:
        facturation_df['Mois'] = pd.to_datetime(facturation_df['Date']).dt.to_period('M')
        monthly_realise = facturation_df.groupby('Mois').agg({
            'Heures': 'sum',
            'Coût': 'sum'
        }).reset_index()
        monthly_realise['Mois'] = monthly_realise['Mois'].astype(str)
        monthly_realise['Heures_Cumul'] = monthly_realise['Heures'].cumsum()
        monthly_realise['Coût_Cumul'] = monthly_realise['Coût'].cumsum()
        monthly_realise['Type'] = 'Réalisé'

        # Combiner
        combined_cout = pd.concat([
            monthly_annuel[['Mois', 'Coût_Cumul', 'Type']].rename(columns={'Coût_Cumul': 'Montant'}),
            monthly_modif[['Mois', 'Coût_Cumul', 'Type']].rename(columns={'Coût_Cumul': 'Montant'}),
            monthly_realise[['Mois', 'Coût_Cumul', 'Type']].rename(columns={'Coût_Cumul': 'Montant'})
        ])

        combined_heures = pd.concat([
            monthly_annuel[['Mois', 'Heures_Cumul', 'Type']].rename(columns={'Heures_Cumul': 'Heures'}),
            monthly_modif[['Mois', 'Heures_Cumul', 'Type']].rename(columns={'Heures_Cumul': 'Heures'}),
            monthly_realise[['Mois', 'Heures_Cumul', 'Type']].rename(columns={'Heures_Cumul': 'Heures'})
        ])
    else:
        # Sans réalisé
        combined_cout = pd.concat([
            monthly_annuel[['Mois', 'Coût_Cumul', 'Type']].rename(columns={'Coût_Cumul': 'Montant'}),
            monthly_modif[['Mois', 'Coût_Cumul', 'Type']].rename(columns={'Coût_Cumul': 'Montant'})
        ])

        combined_heures = pd.concat([
            monthly_annuel[['Mois', 'Heures_Cumul', 'Type']].rename(columns={'Heures_Cumul': 'Heures'}),
            monthly_modif[['Mois', 'Heures_Cumul', 'Type']].rename(columns={'Heures_Cumul': 'Heures'})
        ])

    # Graphique Coût
    chart_cout = alt.Chart(combined_cout).mark_line(point=True).encode(
        x=alt.X('Mois:N', title='Mois', sort=None),
        y=alt.Y('Montant:Q', title='Coût Cumulé (CHF)', axis=alt.Axis(format=',.0f')),
        color=alt.Color('Type:N',
                       scale=alt.Scale(domain=['Budget Annuel', 'Budget Modifié', 'Réalisé'],
                                     range=['#1f77b4', '#ff7f0e', '#2ca02c']),
                       legend=alt.Legend(title='Type')),
        tooltip=['Mois', 'Type', alt.Tooltip('Montant:Q', format=',.0f', title='Coût Cumulé (CHF)')]
    ).properties(
        height=400,
        title='Évolution du Coût Cumulé (CHF)'
    )

    st.altair_chart(chart_cout, use_container_width=True)

    # Graphique Heures
    chart_heures = alt.Chart(combined_heures).mark_line(point=True).encode(
        x=alt.X('Mois:N', title='Mois', sort=None),
        y=alt.Y('Heures:Q', title='Heures Cumulées', axis=alt.Axis(format=',.0f')),
        color=alt.Color('Type:N',
                       scale=alt.Scale(domain=['Budget Annuel', 'Budget Modifié', 'Réalisé'],
                                     range=['#1f77b4', '#ff7f0e', '#2ca02c']),
                       legend=alt.Legend(title='Type')),
        tooltip=['Mois', 'Type', alt.Tooltip('Heures:Q', format=',.0f', title='Heures Cumulées')]
    ).properties(
        height=400,
        title='Évolution des Heures Cumulées'
    )

    st.altair_chart(chart_heures, use_container_width=True)
