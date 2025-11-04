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
from utils.pdf_parser import (
    load_pdf_facturation_data,
    get_category_mapping_for_pdf,
    apply_category_mapping,
    PDF_AVAILABLE
)


def load_facturation_data_for_year(year: int):
    """
    Charge et agrège tous les fichiers de facturation pour une année donnée.
    Supporte à la fois les fichiers Excel (.xlsx) et PDF (.pdf).

    Returns:
        DataFrame avec colonnes: Date, Heures_[CATEGORY], Cout_[CATEGORY], Heures_Total, Cout_Total
    """
    factu_dir = Path(FACTU_AT_DIR)
    if not factu_dir.exists():
        st.error(f"Le répertoire de facturation n'existe pas: {factu_dir}")
        return pd.DataFrame()

    # ==== CHARGER LES FICHIERS EXCEL ====
    excel_data = _load_excel_facturation(year, factu_dir)

    # ==== CHARGER LES FICHIERS PDF ====
    pdf_data = pd.DataFrame()
    if PDF_AVAILABLE:
        try:
            pdf_data = load_pdf_facturation_data(factu_dir, year)

            # Appliquer le mapping des catégories si nécessaire
            if not pdf_data.empty:
                pdf_data = _apply_pdf_category_mapping(pdf_data)
        except Exception as e:
            st.warning(f"Erreur lors du chargement des PDFs: {e}")

    # ==== FUSIONNER EXCEL ET PDF ====
    if excel_data.empty and pdf_data.empty:
        return pd.DataFrame()
    elif excel_data.empty:
        # Normaliser la colonne Date en datetime
        if 'Date' in pdf_data.columns:
            pdf_data['Date'] = pd.to_datetime(pdf_data['Date'])
        return pdf_data
    elif pdf_data.empty:
        # Normaliser la colonne Date en datetime (devrait déjà l'être, mais par sécurité)
        if 'Date' in excel_data.columns:
            excel_data['Date'] = pd.to_datetime(excel_data['Date'])
        return excel_data
    else:
        # Fusionner les deux sources
        # Les Excel ont: Date, Heures, Heures_Coordinateurs, Heures_Total
        # Les PDF ont: Date, Heures_CATEGORY, Cout_CATEGORY, Heures_Total, Cout_Total

        # Normaliser les dates des deux sources
        excel_data['Date'] = pd.to_datetime(excel_data['Date'], errors='coerce')
        pdf_data['Date'] = pd.to_datetime(pdf_data['Date'], errors='coerce')

        # Extraire les mois présents dans chaque source
        excel_months = set(excel_data['Date'].dropna().dt.to_period('M'))
        pdf_months = set(pdf_data['Date'].dropna().dt.to_period('M'))

        # Mois communs = potentiel de duplication
        common_months = excel_months & pdf_months

        if common_months:
            st.warning(
                f"⚠️ Données trouvées à la fois en Excel et PDF pour {len(common_months)} mois. "
                f"Les données PDF (plus récentes) seront privilégiées."
            )
            # Filtrer Excel: ne garder que les mois absents des PDF
            excel_data = excel_data[
                ~excel_data['Date'].dt.to_period('M').isin(pdf_months)
            ].copy()

        # Harmoniser les colonnes Excel pour être compatibles avec PDF
        if 'Heures' in excel_data.columns:
            excel_data.rename(columns={'Heures': 'Heures_AT'}, inplace=True)
        if 'Heures_Coordinateurs' in excel_data.columns:
            excel_data.rename(columns={
                'Heures_Coordinateurs': 'Heures_Coordinateur'
            }, inplace=True)

        # Concaténer (maintenant sans doublons)
        result = pd.concat([excel_data, pdf_data], ignore_index=True)

        # Supprimer les lignes avec Date invalide/NaN
        result = result.dropna(subset=['Date'])

        # Trier par date
        result = result.sort_values('Date', na_position='last').reset_index(drop=True)

        # Remplir les NaN avec 0 (pour les colonnes numériques)
        result = result.fillna(0)

        return result


def _load_excel_facturation(year: int, factu_dir: Path) -> pd.DataFrame:
    """Charge les fichiers Excel de facturation pour une année donnée"""
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


def _apply_pdf_category_mapping(pdf_df: pd.DataFrame) -> pd.DataFrame:
    """Applique le mapping des catégories PDF vers les catégories de l'app"""
    # Extraire les catégories PDF présentes dans les données
    pdf_categories = []
    for col in pdf_df.columns:
        if col.startswith('Heures_') and col != 'Heures_Total':
            cat = col.replace('Heures_', '')
            pdf_categories.append(cat)

    if not pdf_categories:
        return pdf_df

    # Récupérer le mapping depuis session_state
    mapping = st.session_state.get('pdf_category_mapping', {})

    # IMPORTANT: Les catégories de l'app sont les TYPES de Personnel (AT, ATR, Coordinateur, etc.)
    # Pas les périmètres (qui sont les lieux/secteurs)
    app_categories = []
    if 'personnel' in st.session_state and not st.session_state.personnel.empty:
        app_categories = st.session_state.personnel['Type'].unique().tolist()

    # Créer le mapping automatique pour toutes les catégories PDF
    auto_mapping = get_category_mapping_for_pdf(pdf_categories, app_categories)

    # Fusionner: garder le mapping manuel s'il existe, sinon utiliser l'auto
    for pdf_cat in pdf_categories:
        if pdf_cat not in mapping:
            mapping[pdf_cat] = auto_mapping.get(pdf_cat)

    # Mettre à jour session_state
    st.session_state.pdf_category_mapping = mapping

    # Vérifier s'il y a des catégories non mappées (None)
    unmapped_categories = [cat for cat, app_cat in mapping.items() if app_cat is None and cat in pdf_categories]

    if unmapped_categories:
        st.warning(
            f"⚠️ **{len(unmapped_categories)} catégories PDF non mappées:** {', '.join(unmapped_categories)}\n\n"
            f"Ces catégories ne seront pas incluses dans l'analyse. "
            f"Pour les mapper vers des catégories existantes, allez dans **Configuration → "
            f"Bloc 4: Mapping des Catégories PDF**."
        )

        # Afficher les catégories disponibles pour info
        if app_categories:
            st.info(f"📋 Types de personnel disponibles: {', '.join(app_categories)}")

    # Appliquer le mapping
    result = apply_category_mapping(pdf_df, mapping)

    return result


def calculate_budget_modifie(year: int):
    """
    Calcule le budget modifié pour l'année (Budget Annuel + ajustements Besoin Jour).
    IMPORTANT: Cette fonction DOIT utiliser exactement la même logique que besoin_jour.py
    pour garantir la cohérence des résultats.

    Returns:
        dict avec 'heures_total', 'cout_total' et 'calendar_df'
    """
    bs = st.session_state.get('budget_state', {})
    if not bs or bs.get('year') != year or 'calendar_df' not in bs:
        return None

    try:
        # EXACTEMENT comme dans besoin_jour.py ligne 55
        calendar_dyn = bs['calendar_df'].copy()

        # Récupérer le tarif AT (même logique que besoin_jour.py lignes 58-65)
        tarif_at = 0.0
        personnel_type_at = st.session_state.get('cost_mapping', {}).get("AT")
        if personnel_type_at:
            personnel_df = st.session_state.get('personnel', pd.DataFrame())
            if not personnel_df.empty:
                row_tarif = personnel_df[personnel_df['Type'] == personnel_type_at]
                if not row_tarif.empty:
                    tarif_at = float(row_tarif['Coût Horaire'].iloc[0])

        # Préparer les données AT (même logique que besoin_jour.py lignes 67-69)
        perimetres_AT = st.session_state.perimetres.get("AT", [])
        time_slots_default = TIME_SLOTS
        planning_dict_at = st.session_state.planning_data.get("AT", {})

        heures_vals_at_recalc = []
        costs_vals_at_recalc = []

        # Recalculer AT avec les ajustements (EXACTEMENT comme besoin_jour.py lignes 71-82)
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
            heures_vals_at_recalc.append(day_hours)
            costs_vals_at_recalc.append(day_hours * tarif_at)

        # Remplacer DIRECTEMENT les colonnes AT (comme besoin_jour.py lignes 84-85)
        calendar_dyn["Heures_AT"] = heures_vals_at_recalc
        calendar_dyn["Coût_AT"] = costs_vals_at_recalc

        # Recalculer les totaux (EXACTEMENT comme besoin_jour.py lignes 87-97)
        heure_cols_categories = [c for c in calendar_dyn.columns
                                if c.startswith('Heures_') and c != 'Heures_Total_Jour']
        cout_cols_categories = [c for c in calendar_dyn.columns
                               if c.startswith('Coût_') and c != 'Coût_Total_Jour']

        calendar_dyn['Heures_Total_Jour'] = calendar_dyn[heure_cols_categories].sum(
            axis=1
        ) if heure_cols_categories else 0.0
        calendar_dyn['Coût_Total_Jour'] = calendar_dyn[cout_cols_categories].sum(
            axis=1
        ) if cout_cols_categories else 0.0

        # Calculer les totaux annuels (comme besoin_jour.py lignes 99-100)
        cur_hours_recalc = calendar_dyn['Heures_Total_Jour'].sum()
        cur_cost_recalc = calendar_dyn['Coût_Total_Jour'].sum()

        return {
            'heures_total': cur_hours_recalc,
            'cout_total': cur_cost_recalc,
            'calendar_df': calendar_dyn
        }

    except Exception as e:
        st.error(f"Erreur lors du calcul du budget modifié: {e}")
        import traceback
        st.error(traceback.format_exc())
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

            # Récupérer aussi le calendar_df ORIGINAL (Budget Annuel non modifié)
            calendar_annuel = bs.get('calendar_df', pd.DataFrame()).copy()
            calendar_annuel['Date'] = pd.to_datetime(calendar_annuel['Date'])
            calendar_annuel['Mois'] = calendar_annuel['Date'].dt.to_period('M')

            # Agréger par mois - Budget Annuel (original, sans ajustements)
            monthly_annuel = calendar_annuel.groupby('Mois').agg({
                'Heures_Total_Jour': 'sum',
                'Coût_Total_Jour': 'sum'
            }).reset_index()
            monthly_annuel.rename(columns={
                'Heures_Total_Jour': 'Heures_Annuel',
                'Coût_Total_Jour': 'Cout_Annuel'
            }, inplace=True)

            # Agréger par mois - Budget Modifié (avec ajustements)
            # IMPORTANT: calendar_with_modif contient les valeurs modifiées dans
            # Heures_Total_Jour et Coût_Total_Jour (après recalcul avec ajustements)
            monthly_modifie = calendar_with_modif.groupby('Mois').agg({
                'Heures_Total_Jour': 'sum',
                'Coût_Total_Jour': 'sum'
            }).reset_index()
            monthly_modifie.rename(columns={
                'Heures_Total_Jour': 'Heures_Modifie',
                'Coût_Total_Jour': 'Cout_Modifie'
            }, inplace=True)

            # Fusionner Annuel et Modifié
            monthly_budget = monthly_annuel.merge(monthly_modifie, on='Mois', how='outer')

            monthly_budget['Mois_str'] = monthly_budget['Mois'].astype(str)
            monthly_budget['Mois_dt'] = monthly_budget['Mois'].apply(lambda x: x.to_timestamp())

            # Calcul cumulé
            monthly_budget['Heures_Annuel_Cumul'] = monthly_budget['Heures_Annuel'].cumsum()
            monthly_budget['Cout_Annuel_Cumul'] = monthly_budget['Cout_Annuel'].cumsum()
            monthly_budget['Heures_Modifie_Cumul'] = monthly_budget['Heures_Modifie'].cumsum()
            monthly_budget['Cout_Modifie_Cumul'] = monthly_budget['Cout_Modifie'].cumsum()
            
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
                'Heures_Annuel': 'Heures Annuel',
                'Heures_Modifie': 'Heures Modifié',
                'Cout_Annuel': 'Coût Annuel (CHF)',
                'Cout_Modifie': 'Coût Modifié (CHF)'
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
