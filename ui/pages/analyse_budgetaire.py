"""
Page Analyse Budgétaire - Comparaison Budget Annuel vs Modifié vs Réalisé
"""
import datetime as dt
from pathlib import Path
import re
import pandas as pd
import streamlit as st
import altair as alt
from config.constants import FACTU_AT_DIR, FACTU_AT_GLOB, TIME_SLOTS
from core.planning import _ensure_grid, _apply_ops_to_grid


def load_facturation_data_for_year(year: int):
    """
    Charge et agrège tous les fichiers de facturation pour une année donnée.
    
    Returns:
        DataFrame avec colonnes: Date, Heures, Coordinateurs
    """
    factu_dir = Path(FACTU_AT_DIR)
    if not factu_dir.exists():
        st.error(f"Le répertoire de facturation n'existe pas: {factu_dir}")
        return pd.DataFrame()
    
    # Pattern pour les fichiers de facturation avec année
    pattern = re.compile(r'Facturation Lot A (\d{2})\.(\d{4})\.xlsx')
    
    all_data = []
    
    for file_path in factu_dir.glob(FACTU_AT_GLOB):
        match = pattern.match(file_path.name)
        if match:
            month_str, year_str = match.groups()
            file_year = int(year_str)
            
            # Ne charger que les fichiers de l'année sélectionnée
            if file_year != year:
                continue
            
            try:
                # Lire le fichier Excel sans header pour analyser la structure
                df_raw = pd.read_excel(file_path, header=None)
                
                # Trouver la ligne d'en-tête (qui contient "Date ouvrable", "Heures", etc.)
                header_row = None
                for idx, row in df_raw.iterrows():
                    if 'Date ouvrable' in str(row.values):
                        header_row = idx
                        break
                
                if header_row is None:
                    st.warning(f"Structure non reconnue dans {file_path.name}")
                    continue
                
                # Lire à partir de la ligne suivante avec les bonnes colonnes
                df = pd.read_excel(file_path, header=header_row)
                
                # Vérifier les colonnes nécessaires
                if 'Date ouvrable' not in df.columns or 'Heures' not in df.columns:
                    st.warning(f"Colonnes manquantes dans {file_path.name}")
                    continue
                
                # Filtrer les lignes valides (qui contiennent "Total")
                df = df[df['Date ouvrable'].astype(str).str.contains('Total', na=False)].copy()
                
                # Extraire la date du format "Total DD.MM.YYYY"
                df['Date_str'] = df['Date ouvrable'].astype(str).str.extract(r'(\d{2}\.\d{2}\.\d{4})')
                df['Date'] = pd.to_datetime(df['Date_str'], format='%d.%m.%Y', errors='coerce')
                
                # Nettoyer les données
                df = df.dropna(subset=['Date'])
                df['Heures'] = pd.to_numeric(df['Heures'], errors='coerce').fillna(0)
                
                # Ajouter les heures de coordination si disponible
                if 'Coordinateurs' in df.columns:
                    df['Heures_Coordinateurs'] = pd.to_numeric(
                        df['Coordinateurs'], errors='coerce'
                    ).fillna(0)
                else:
                    df['Heures_Coordinateurs'] = 0
                
                # Calculer le total des heures (AT + Coordinateurs)
                df['Heures_Total'] = df['Heures'] + df['Heures_Coordinateurs']
                
                # Sélectionner les colonnes finales
                df_clean = df[['Date', 'Heures', 'Heures_Coordinateurs', 'Heures_Total']].copy()
                all_data.append(df_clean)
                
            except Exception as e:
                st.warning(f"Erreur lors du chargement de {file_path.name}: {e}")
                continue
    
    if not all_data:
        return pd.DataFrame()
    
    # Concaténer tous les mois
    result = pd.concat(all_data, ignore_index=True)
    result = result.sort_values('Date').reset_index(drop=True)
    
    return result


def calculate_budget_modifie(year: int):
    """
    Calcule le budget modifié pour l'année (Budget Annuel + ajustements Besoin Jour).
    
    Returns:
        dict avec 'heures_total' et 'cout_total'
    """
    bs = st.session_state.get('budget_state', {})
    if not bs or bs.get('year') != year or 'calendar_df' not in bs:
        return None
    
    try:
        calendar_dyn = bs['calendar_df'].copy()
        
        # Récupérer le tarif AT
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
        
        heures_vals_at_modifie = []
        costs_vals_at_modifie = []
        
        # Recalculer avec les ajustements Besoin Jour
        for _, r in calendar_dyn.iterrows():
            jour, saison, date_ = r['Jour'], r['Saison'], r['Date'].date()
            jtg = r['Jour_Type_Global']
            
            _, base_df_at = _ensure_grid(
                planning_dict_at, jtg, perimetres_AT, time_slots_default
            )
            
            # Appliquer les ajustements Besoin Jour
            eff_df_at = _apply_ops_to_grid(
                base_df_at, date_, jour, saison, category="AT"
            )
            
            day_hours = eff_df_at.values.sum() * 0.5
            heures_vals_at_modifie.append(day_hours)
            costs_vals_at_modifie.append(day_hours * tarif_at)
        
        calendar_dyn["Heures_AT_Modifie"] = heures_vals_at_modifie
        calendar_dyn["Coût_AT_Modifie"] = costs_vals_at_modifie
        
        # Recalculer les totaux pour toutes les catégories avec ajustements
        heure_cols_categories = [c for c in calendar_dyn.columns
                                if c.startswith('Heures_') and c != 'Heures_Total_Jour']
        cout_cols_categories = [c for c in calendar_dyn.columns
                               if c.startswith('Coût_') and c != 'Coût_Total_Jour']
        
        # Remplacer les valeurs AT par les valeurs modifiées
        if 'Heures_AT' in calendar_dyn.columns:
            calendar_dyn['Heures_AT'] = calendar_dyn['Heures_AT_Modifie']
        if 'Coût_AT' in calendar_dyn.columns:
            calendar_dyn['Coût_AT'] = calendar_dyn['Coût_AT_Modifie']
        
        # Recalculer les totaux
        calendar_dyn['Heures_Total_Modifie'] = calendar_dyn[heure_cols_categories].sum(
            axis=1
        ) if heure_cols_categories else 0.0
        calendar_dyn['Coût_Total_Modifie'] = calendar_dyn[cout_cols_categories].sum(
            axis=1
        ) if cout_cols_categories else 0.0
        
        return {
            'heures_total': calendar_dyn['Heures_Total_Modifie'].sum(),
            'cout_total': calendar_dyn['Coût_Total_Modifie'].sum(),
            'calendar_df': calendar_dyn
        }
        
    except Exception as e:
        st.error(f"Erreur lors du calcul du budget modifié: {e}")
        return None


def render_analyse_budgetaire_page():
    """Affiche la page d'Analyse Budgétaire"""
    st.title("Analyse Budgétaire")
    st.markdown(
        "Comparaison entre le **Budget Annuel** (prévision initiale), "
        "le **Budget Modifié** (après ajustements Besoin Jour) et "
        "le **Réalisé** (facturation effective)."
    )
    
    # Sélection de l'année
    bs = st.session_state.get('budget_state', {})
    default_year = bs.get('year', dt.date.today().year)
    
    year = st.number_input(
        "Année d'analyse :",
        value=default_year,
        min_value=2023,
        max_value=2050,
        key="analyse_budget_year"
    )
    
    # Vérifier que le budget existe pour cette année
    if not bs or bs.get('year') != year:
        st.warning(
            f"⚠️ Aucun budget annuel généré pour l'année {year}. "
            f"Veuillez d'abord générer le budget dans la page **Budget Annuel**."
        )
        st.stop()
    
    # =================== Chargement des données ===================
    
    with st.spinner("Chargement des données de facturation..."):
        df_factu = load_facturation_data_for_year(year)
    
    with st.spinner("Calcul du budget modifié avec ajustements..."):
        budget_modifie = calculate_budget_modifie(year)
    
    if budget_modifie is None:
        st.error("Impossible de calculer le budget modifié.")
        st.stop()
    
    # =================== Extraction des données Budget Annuel ===================
    
    calendar_df = bs.get('calendar_df', pd.DataFrame())
    totals_annuel = bs.get('totals', {})
    heures_annuel = totals_annuel.get('heures_annuel', 0.0)
    cout_annuel = totals_annuel.get('cout_annuel', 0.0)
    
    # =================== Extraction des données Budget Modifié ===================
    
    heures_modifie = budget_modifie.get('heures_total', 0.0)
    cout_modifie = budget_modifie.get('cout_total', 0.0)
    
    # =================== Extraction des données Réalisé ===================
    
    heures_realise = 0.0
    cout_realise = 0.0
    
    if not df_factu.empty:
        heures_realise = df_factu['Heures_Total'].sum()
        
        # Calculer le coût réalisé en utilisant le tarif AT
        tarif_at = 0.0
        personnel_type_at = st.session_state.get('cost_mapping', {}).get("AT")
        if personnel_type_at:
            personnel_df = st.session_state.get('personnel', pd.DataFrame())
            if not personnel_df.empty:
                row_tarif = personnel_df[personnel_df['Type'] == personnel_type_at]
                if not row_tarif.empty:
                    tarif_at = float(row_tarif['Coût Horaire'].iloc[0])
        
        cout_realise = heures_realise * tarif_at
    
    # =================== Calcul des écarts ===================
    
    # Écarts Modifié vs Annuel
    ecart_heures_mod_ann = heures_modifie - heures_annuel
    ecart_heures_mod_ann_pct = (ecart_heures_mod_ann / heures_annuel * 100) if heures_annuel != 0 else 0
    ecart_cout_mod_ann = cout_modifie - cout_annuel
    ecart_cout_mod_ann_pct = (ecart_cout_mod_ann / cout_annuel * 100) if cout_annuel != 0 else 0
    
    # Écarts Réalisé vs Modifié
    ecart_heures_real_mod = heures_realise - heures_modifie
    ecart_heures_real_mod_pct = (ecart_heures_real_mod / heures_modifie * 100) if heures_modifie != 0 else 0
    ecart_cout_real_mod = cout_realise - cout_modifie
    ecart_cout_real_mod_pct = (ecart_cout_real_mod / cout_modifie * 100) if cout_modifie != 0 else 0
    
    # =================== Affichage : Synthèse CHF ===================
    
    st.markdown("---")
    st.subheader(f"📊 Synthèse {year} - Coûts (CHF)")
    
    col1, col2, col3 = st.columns(3)
    
    with col1:
        st.markdown(
            f"""<div class="kpi-card kpi-blue">
            <div class="label">Budget Annuel</div>
            <div class="value">{cout_annuel:,.0f} CHF</div>
            <div class="delta">Prévision initiale</div>
            </div>""",
            unsafe_allow_html=True
        )
    
    with col2:
        ecart_color = "kpi-green" if ecart_cout_mod_ann <= 0 else "kpi-amber"
        ecart_symbol = "▼" if ecart_cout_mod_ann < 0 else "▲"
        st.markdown(
            f"""<div class="kpi-card {ecart_color}">
            <div class="label">Budget Modifié</div>
            <div class="value">{cout_modifie:,.0f} CHF</div>
            <div class="delta">{ecart_symbol} {abs(ecart_cout_mod_ann):,.0f} CHF ({ecart_cout_mod_ann_pct:+.1f}%)</div>
            </div>""",
            unsafe_allow_html=True
        )
    
    with col3:
        ecart_color_real = "kpi-green" if ecart_cout_real_mod <= 0 else "kpi-red"
        ecart_symbol_real = "▼" if ecart_cout_real_mod < 0 else "▲"
        
        if df_factu.empty:
            st.markdown(
                f"""<div class="kpi-card kpi-amber">
                <div class="label">Réalisé</div>
                <div class="value">— CHF</div>
                <div class="delta">Aucune donnée de facturation pour {year}</div>
                </div>""",
                unsafe_allow_html=True
            )
        else:
            st.markdown(
                f"""<div class="kpi-card {ecart_color_real}">
                <div class="label">Réalisé</div>
                <div class="value">{cout_realise:,.0f} CHF</div>
                <div class="delta">{ecart_symbol_real} {abs(ecart_cout_real_mod):,.0f} CHF ({ecart_cout_real_mod_pct:+.1f}%)</div>
                </div>""",
                unsafe_allow_html=True
            )
    
    # =================== Affichage : Synthèse Heures ===================
    
    st.markdown("---")
    st.subheader(f"⏱️ Synthèse {year} - Heures")
    
    col1, col2, col3 = st.columns(3)
    
    with col1:
        st.markdown(
            f"""<div class="kpi-card kpi-blue">
            <div class="label">Budget Annuel</div>
            <div class="value">{heures_annuel:,.0f} h</div>
            <div class="delta">Prévision initiale</div>
            </div>""",
            unsafe_allow_html=True
        )
    
    with col2:
        ecart_color = "kpi-green" if ecart_heures_mod_ann <= 0 else "kpi-amber"
        ecart_symbol = "▼" if ecart_heures_mod_ann < 0 else "▲"
        st.markdown(
            f"""<div class="kpi-card {ecart_color}">
            <div class="label">Budget Modifié</div>
            <div class="value">{heures_modifie:,.0f} h</div>
            <div class="delta">{ecart_symbol} {abs(ecart_heures_mod_ann):,.0f} h ({ecart_heures_mod_ann_pct:+.1f}%)</div>
            </div>""",
            unsafe_allow_html=True
        )
    
    with col3:
        ecart_color_real = "kpi-green" if ecart_heures_real_mod <= 0 else "kpi-red"
        ecart_symbol_real = "▼" if ecart_heures_real_mod < 0 else "▲"
        
        if df_factu.empty:
            st.markdown(
                f"""<div class="kpi-card kpi-amber">
                <div class="label">Réalisé</div>
                <div class="value">— h</div>
                <div class="delta">Aucune donnée de facturation pour {year}</div>
                </div>""",
                unsafe_allow_html=True
            )
        else:
            st.markdown(
                f"""<div class="kpi-card {ecart_color_real}">
                <div class="label">Réalisé</div>
                <div class="value">{heures_realise:,.0f} h</div>
                <div class="delta">{ecart_symbol_real} {abs(ecart_heures_real_mod):,.0f} h ({ecart_heures_real_mod_pct:+.1f}%)</div>
                </div>""",
                unsafe_allow_html=True
            )
    
    # =================== Affichage : Courbes Cumulées ===================
    
    st.markdown("---")
    st.subheader(f"📈 Évolution Cumulée {year}")
    
    # Préparer les données mensuelles
    calendar_with_modif = budget_modifie.get('calendar_df', pd.DataFrame())
    
    if not calendar_with_modif.empty:
        try:
            # S'assurer que Date est au bon format
            calendar_with_modif['Date'] = pd.to_datetime(calendar_with_modif['Date'])
            calendar_with_modif['Mois'] = calendar_with_modif['Date'].dt.to_period('M')
            
            # Agréger par mois pour Budget Annuel et Modifié
            monthly_budget = calendar_with_modif.groupby('Mois').agg({
                'Heures_Total_Jour': 'sum',
                'Coût_Total_Jour': 'sum',
                'Heures_Total_Modifie': 'sum',
                'Coût_Total_Modifie': 'sum'
            }).reset_index()
            
            monthly_budget['Mois_str'] = monthly_budget['Mois'].astype(str)
            monthly_budget['Mois_dt'] = monthly_budget['Mois'].apply(lambda x: x.to_timestamp())
            
            # Calcul cumulé
            monthly_budget['Heures_Annuel_Cumul'] = monthly_budget['Heures_Total_Jour'].cumsum()
            monthly_budget['Cout_Annuel_Cumul'] = monthly_budget['Coût_Total_Jour'].cumsum()
            monthly_budget['Heures_Modifie_Cumul'] = monthly_budget['Heures_Total_Modifie'].cumsum()
            monthly_budget['Cout_Modifie_Cumul'] = monthly_budget['Coût_Total_Modifie'].cumsum()
            
            # Agréger les données de facturation par mois si disponibles
            if not df_factu.empty:
                df_factu['Mois'] = pd.to_datetime(df_factu['Date']).dt.to_period('M')
                monthly_factu = df_factu.groupby('Mois').agg({
                    'Heures_Total': 'sum'
                }).reset_index()
                monthly_factu['Mois_str'] = monthly_factu['Mois'].astype(str)
                monthly_factu['Mois_dt'] = monthly_factu['Mois'].apply(lambda x: x.to_timestamp())
                monthly_factu['Heures_Realise_Cumul'] = monthly_factu['Heures_Total'].cumsum()
                
                # Calculer le coût réalisé cumulé
                tarif_at = 0.0
                personnel_type_at = st.session_state.get('cost_mapping', {}).get("AT")
                if personnel_type_at:
                    personnel_df = st.session_state.get('personnel', pd.DataFrame())
                    if not personnel_df.empty:
                        row_tarif = personnel_df[personnel_df['Type'] == personnel_type_at]
                        if not row_tarif.empty:
                            tarif_at = float(row_tarif['Coût Horaire'].iloc[0])
                
                monthly_factu['Cout_Realise'] = monthly_factu['Heures_Total'] * tarif_at
                monthly_factu['Cout_Realise_Cumul'] = monthly_factu['Cout_Realise'].cumsum()
                
                # Fusionner les données
                monthly_combined = monthly_budget.merge(
                    monthly_factu[['Mois_str', 'Heures_Realise_Cumul', 'Cout_Realise_Cumul']],
                    on='Mois_str',
                    how='left'
                )
            else:
                monthly_combined = monthly_budget.copy()
                monthly_combined['Heures_Realise_Cumul'] = None
                monthly_combined['Cout_Realise_Cumul'] = None
            
            # Préparer les données pour Altair (format long)
            # Pour les Heures
            df_heures_plot = pd.DataFrame({
                'Mois': monthly_combined['Mois_dt'].tolist() * 3,
                'Type': (
                    ['Budget Annuel'] * len(monthly_combined) +
                    ['Budget Modifié'] * len(monthly_combined) +
                    ['Réalisé'] * len(monthly_combined)
                ),
                'Heures_Cumul': (
                    monthly_combined['Heures_Annuel_Cumul'].tolist() +
                    monthly_combined['Heures_Modifie_Cumul'].tolist() +
                    monthly_combined['Heures_Realise_Cumul'].tolist()
                )
            })
            
            # Pour les Coûts
            df_cout_plot = pd.DataFrame({
                'Mois': monthly_combined['Mois_dt'].tolist() * 3,
                'Type': (
                    ['Budget Annuel'] * len(monthly_combined) +
                    ['Budget Modifié'] * len(monthly_combined) +
                    ['Réalisé'] * len(monthly_combined)
                ),
                'Cout_Cumul': (
                    monthly_combined['Cout_Annuel_Cumul'].tolist() +
                    monthly_combined['Cout_Modifie_Cumul'].tolist() +
                    monthly_combined['Cout_Realise_Cumul'].tolist()
                )
            })
            
            # Supprimer les lignes avec NaN pour le Réalisé
            df_heures_plot = df_heures_plot.dropna(subset=['Heures_Cumul'])
            df_cout_plot = df_cout_plot.dropna(subset=['Cout_Cumul'])
            
            # Créer les graphiques
            tab_cout, tab_heures = st.tabs(["💰 Coûts Cumulés (CHF)", "⏱️ Heures Cumulées"])
            
            with tab_cout:
                if not df_cout_plot.empty:
                    chart_cout = alt.Chart(df_cout_plot).mark_line(
                        point=True, strokeWidth=3
                    ).encode(
                        x=alt.X('Mois:T', title='Mois', axis=alt.Axis(format='%b %Y')),
                        y=alt.Y('Cout_Cumul:Q', title='Coût Cumulé (CHF)'),
                        color=alt.Color(
                            'Type:N',
                            scale=alt.Scale(
                                domain=['Budget Annuel', 'Budget Modifié', 'Réalisé'],
                                range=['#0076aa', '#ffa500', '#dc143c']
                            ),
                            legend=alt.Legend(title='Type de Budget')
                        ),
                        tooltip=[
                            alt.Tooltip('Mois:T', title='Mois', format='%B %Y'),
                            alt.Tooltip('Type:N', title='Type'),
                            alt.Tooltip('Cout_Cumul:Q', title='Coût Cumulé', format=',.0f')
                        ]
                    ).properties(
                        height=400
                    ).interactive()
                    
                    st.altair_chart(chart_cout, use_container_width=True)
                else:
                    st.info("Pas de données disponibles pour tracer la courbe des coûts.")
            
            with tab_heures:
                if not df_heures_plot.empty:
                    chart_heures = alt.Chart(df_heures_plot).mark_line(
                        point=True, strokeWidth=3
                    ).encode(
                        x=alt.X('Mois:T', title='Mois', axis=alt.Axis(format='%b %Y')),
                        y=alt.Y('Heures_Cumul:Q', title='Heures Cumulées'),
                        color=alt.Color(
                            'Type:N',
                            scale=alt.Scale(
                                domain=['Budget Annuel', 'Budget Modifié', 'Réalisé'],
                                range=['#0076aa', '#ffa500', '#dc143c']
                            ),
                            legend=alt.Legend(title='Type de Budget')
                        ),
                        tooltip=[
                            alt.Tooltip('Mois:T', title='Mois', format='%B %Y'),
                            alt.Tooltip('Type:N', title='Type'),
                            alt.Tooltip('Heures_Cumul:Q', title='Heures Cumulées', format=',.0f')
                        ]
                    ).properties(
                        height=400
                    ).interactive()
                    
                    st.altair_chart(chart_heures, use_container_width=True)
                else:
                    st.info("Pas de données disponibles pour tracer la courbe des heures.")
            
        except Exception as e:
            st.error(f"Erreur lors de la création des graphiques cumulés: {e}")
            import traceback
            st.error(traceback.format_exc())
    
    # =================== Tableau Détaillé Mensuel ===================
    
    st.markdown("---")
    st.subheader("📋 Détail Mensuel")
    
    if not calendar_with_modif.empty and 'monthly_combined' in locals():
        try:
            # Préparer un tableau récapitulatif mensuel
            monthly_table = monthly_combined.copy()
            monthly_table['Mois'] = monthly_table['Mois_str']
            
            # Sélectionner et renommer les colonnes
            columns_to_show = {
                'Mois': 'Mois',
                'Heures_Total_Jour': 'Heures Annuel',
                'Heures_Total_Modifie': 'Heures Modifié',
                'Coût_Total_Jour': 'Coût Annuel (CHF)',
                'Coût_Total_Modifie': 'Coût Modifié (CHF)'
            }
            
            if 'Heures_Total' in monthly_table.columns:
                # Recalculer depuis df_factu pour avoir les valeurs mensuelles (non cumulées)
                if not df_factu.empty:
                    monthly_factu_raw = df_factu.groupby('Mois').agg({
                        'Heures_Total': 'sum'
                    }).reset_index()
                    monthly_factu_raw['Mois_str'] = monthly_factu_raw['Mois'].astype(str)
                    
                    tarif_at = 0.0
                    personnel_type_at = st.session_state.get('cost_mapping', {}).get("AT")
                    if personnel_type_at:
                        personnel_df = st.session_state.get('personnel', pd.DataFrame())
                        if not personnel_df.empty:
                            row_tarif = personnel_df[personnel_df['Type'] == personnel_type_at]
                            if not row_tarif.empty:
                                tarif_at = float(row_tarif['Coût Horaire'].iloc[0])
                    
                    monthly_factu_raw['Cout_Realise'] = monthly_factu_raw['Heures_Total'] * tarif_at
                    
                    monthly_table = monthly_table.merge(
                        monthly_factu_raw[['Mois_str', 'Heures_Total', 'Cout_Realise']],
                        left_on='Mois',
                        right_on='Mois_str',
                        how='left'
                    )
                    
                    columns_to_show['Heures_Total'] = 'Heures Réalisé'
                    columns_to_show['Cout_Realise'] = 'Coût Réalisé (CHF)'
            
            # Créer le DataFrame final
            df_monthly_display = monthly_table[list(columns_to_show.keys())].copy()
            df_monthly_display.columns = list(columns_to_show.values())
            
            # Configuration des colonnes
            col_config = {
                'Mois': st.column_config.TextColumn('Mois'),
                'Heures Annuel': st.column_config.NumberColumn(
                    'Heures Annuel', format='%.0f h'
                ),
                'Heures Modifié': st.column_config.NumberColumn(
                    'Heures Modifié', format='%.0f h'
                ),
                'Coût Annuel (CHF)': st.column_config.NumberColumn(
                    'Coût Annuel', format='%.0f CHF'
                ),
                'Coût Modifié (CHF)': st.column_config.NumberColumn(
                    'Coût Modifié', format='%.0f CHF'
                )
            }
            
            if 'Heures Réalisé' in df_monthly_display.columns:
                col_config['Heures Réalisé'] = st.column_config.NumberColumn(
                    'Heures Réalisé', format='%.0f h'
                )
                col_config['Coût Réalisé (CHF)'] = st.column_config.NumberColumn(
                    'Coût Réalisé', format='%.0f CHF'
                )
            
            st.dataframe(
                df_monthly_display,
                column_config=col_config,
                hide_index=True,
                use_container_width=True
            )
            
        except Exception as e:
            st.error(f"Erreur lors de la création du tableau mensuel: {e}")
            import traceback
            st.error(traceback.format_exc())
    
    # =================== Notes et Informations ===================
    
    with st.expander("ℹ️ Informations sur l'Analyse Budgétaire"):
        st.markdown("""
        ### Définitions
        
        - **Budget Annuel** : Budget prévisionnel initial basé sur les jours-types et le calendrier des saisons.
        
        - **Budget Modifié** : Budget ajusté intégrant tous les ajustements ponctuels définis dans 
          la page "Besoin Jour" (événements, modifications temporaires, etc.).
        
        - **Réalisé** : Heures et coûts effectifs basés sur les fichiers de facturation 
          (dossier `input_files/facturation/`).
        
        ### Calcul des écarts
        
        - **Modifié vs Annuel** : Mesure l'impact des ajustements ponctuels sur le budget initial.
        
        - **Réalisé vs Modifié** : Mesure l'écart entre ce qui était prévu (après ajustements) 
          et ce qui a été effectivement réalisé.
        
        ### Sources de données
        
        - **Budget Annuel** : Généré dans la page "Budget Annuel"
        - **Ajustements** : Définis dans la page "Besoin Jour"
        - **Facturation** : Fichiers Excel dans `input_files/facturation/`
          (format: `Facturation Lot A MM.YYYY.xlsx`)
        """)
