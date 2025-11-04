"""
Page Budget Annuel - Génération et analyse du budget
"""
import datetime as dt
import pandas as pd
import streamlit as st
import altair as alt
from core.budget import generate_budget_state, _ensure_adjusted_saisons_for_year, _season_timeline_df
from utils.date_utils import _day_name_fr


def render_budget_annuel_page():
    """Affiche la page Budget Annuel"""
    st.title("Budget Annuel Consolidé")
    st.markdown("Générez une projection annuelle complète basée sur vos planifications et paramètres.")

    year = st.number_input(
        "Année du budget :",
        value=st.session_state.get('adjusted_saisons_year', dt.date.today().year + 1),
        min_value=2024, max_value=2050, key="budget_year_selector"
    )

    tabs_budget = st.tabs([
        "Vue d'Ensemble & Génération",
        "Paramètres du Calendrier",
        "Association des Coûts"
    ])

    # =================== Onglet 1 : Vue d'Ensemble & Génération ===================
    with tabs_budget[0]:
        st.markdown('<div class="ga-card">', unsafe_allow_html=True)
        st.subheader("Génération du Budget")
        st.markdown(
            f"Calculez le budget pour l'année **{year}** à partir des JTs et du calendrier.",
            help="Vérifiez d'abord le personnel et l'association des coûts."
        )

        if 'personnel' in st.session_state and not st.session_state.personnel.empty:
            cols_act = st.columns([1, 1.2])
            with cols_act[0]:
                if st.button("Lancer la génération", type="primary",
                           use_container_width=True, key="generate_budget_button"):
                    with st.spinner("Consolidation en cours…"):
                        generate_budget_state(year)
                    if 'budget_state' in st.session_state and                        st.session_state.budget_state.get('year') == year:
                        st.success("Budget annuel généré avec succès !")
                    else:
                        st.error("La génération a échoué. Consultez les messages précédents.")
            with cols_act[1]:
                st.info(
                    "Regénérez après tout changement de **saisons**, **tarifs** "
                    "ou **mapping des coûts**."
                )
        else:
            st.warning("Définissez d'abord les **types de personnel** dans la page *Configuration*.")
        st.markdown('</div>', unsafe_allow_html=True)

        bs = st.session_state.get('budget_state', {})
        if bs and bs.get('year') == year:
            # ========== TABLES ÉDITABLES D'ABORD (pour capturer les modifications) ==========

            # Formation / Doublure AT (hors planification)
            with st.container(border=True):
                st.subheader("Formation / Doublure AT (hors planification)")
                st.markdown("Gérez les shifts de formation et doublure AT indépendamment de la planification standard.")

                # Récupérer le coût horaire AT
                cout_horaire_at = 45.50  # Valeur par défaut
                if 'personnel' in st.session_state and not st.session_state.personnel.empty:
                    personnel_df = st.session_state.personnel
                    at_row = personnel_df[personnel_df['Type'] == 'AT']
                    if not at_row.empty:
                        try:
                            cout_horaire_at = float(at_row['Coût Horaire'].iloc[0])
                        except Exception:
                            pass

                st.caption(f"📌 Coût horaire AT : **{cout_horaire_at:.2f} CHF**")

                # Initialiser le DataFrame si nécessaire
                if 'budget_formation_at' not in st.session_state:
                    st.session_state.budget_formation_at = pd.DataFrame([
                        {'Dénomination': 'Formation (théorique) AT S26', 'Effectif (pers.)': 20, 'Heures': 17.0, 'Nbre de shifts': 1},
                        {'Dénomination': 'Formation (pratique) AT S26', 'Effectif (pers.)': 20, 'Heures': 6.5, 'Nbre de shifts': 3},
                        {'Dénomination': 'Formation (théorique) AT CHT W26', 'Effectif (pers.)': 20, 'Heures': 17.0, 'Nbre de shifts': 1},
                        {'Dénomination': 'Formation (pratique) AT CHT W26', 'Effectif (pers.)': 20, 'Heures': 6.5, 'Nbre de shifts': 3},
                        {'Dénomination': "Formation Visitor's Center", 'Effectif (pers.)': 20, 'Heures': 4.0, 'Nbre de shifts': 1},
                        {'Dénomination': 'Refresher AT CDI', 'Effectif (pers.)': 0, 'Heures': 0.0, 'Nbre de shifts': 0},
                        {'Dénomination': 'Cours FEU', 'Effectif (pers.)': 40, 'Heures': 3.0, 'Nbre de shifts': 1},
                        {'Dénomination': 'Cours DEFI', 'Effectif (pers.)': 40, 'Heures': 2.0, 'Nbre de shifts': 1}
                    ])

                # Préparer le DataFrame pour l'édition (SANS la colonne Total)
                df_formation = st.session_state.budget_formation_at.copy()

                # S'assurer que seules les 4 colonnes éditables sont présentes
                editable_cols = ['Dénomination', 'Effectif (pers.)', 'Heures', 'Nbre de shifts']
                for col in editable_cols:
                    if col not in df_formation.columns:
                        if col == 'Dénomination':
                            df_formation[col] = ''
                        elif col in ('Effectif (pers.)', 'Nbre de shifts'):
                            df_formation[col] = 0
                        else:  # Heures
                            df_formation[col] = 0.0

                # Ne garder que les colonnes éditables pour le data_editor
                df_formation_edit = df_formation[editable_cols].copy()

                # Normaliser et valider les données
                df_formation_edit['Effectif (pers.)'] = pd.to_numeric(
                    df_formation_edit['Effectif (pers.)'], errors='coerce'
                ).fillna(0).astype(int).clip(lower=0)
                df_formation_edit['Heures'] = df_formation_edit['Heures'].apply(
                    lambda x: float(str(x).replace(',', '.')) if pd.notna(x) else 0.0
                ).clip(lower=0)
                df_formation_edit['Nbre de shifts'] = pd.to_numeric(
                    df_formation_edit['Nbre de shifts'], errors='coerce'
                ).fillna(0).astype(int).clip(lower=0)

                # Configuration des colonnes pour l'éditeur (SANS Total)
                column_config_formation = {
                    'Dénomination': st.column_config.TextColumn(
                        'Dénomination',
                        required=True,
                        help='Description du shift de formation'
                    ),
                    'Effectif (pers.)': st.column_config.NumberColumn(
                        'Effectif (pers.)',
                        min_value=0,
                        step=1,
                        format='%d',
                        required=True
                    ),
                    'Heures': st.column_config.NumberColumn(
                        'Heures',
                        min_value=0.0,
                        step=0.5,
                        format='%.1f',
                        required=True,
                        help='Durée en heures (décimales acceptées)'
                    ),
                    'Nbre de shifts': st.column_config.NumberColumn(
                        'Nbre de shifts',
                        min_value=0,
                        step=1,
                        format='%d',
                        required=True
                    )
                }

                # Éditeur de données (SANS la colonne Total)
                edited_formation = st.data_editor(
                    df_formation_edit,
                    column_config=column_config_formation,
                    num_rows="dynamic",
                    use_container_width=True,
                    hide_index=True,
                    key="editor_formation_at"
                )

                # Recalculer avec les données éditées
                edited_formation['Effectif (pers.)'] = pd.to_numeric(
                    edited_formation['Effectif (pers.)'], errors='coerce'
                ).fillna(0).astype(int).clip(lower=0)
                edited_formation['Heures'] = edited_formation['Heures'].apply(
                    lambda x: float(str(x).replace(',', '.')) if pd.notna(x) else 0.0
                ).clip(lower=0)
                edited_formation['Nbre de shifts'] = pd.to_numeric(
                    edited_formation['Nbre de shifts'], errors='coerce'
                ).fillna(0).astype(int).clip(lower=0)

                # Sauvegarder dans session_state (SANS la colonne Total)
                st.session_state.budget_formation_at = edited_formation

                # Calculer les totaux par ligne APRÈS l'édition
                df_formation_display = edited_formation.copy()
                df_formation_display['Total (heures)'] = (
                    df_formation_display['Effectif (pers.)'] *
                    df_formation_display['Heures'] *
                    df_formation_display['Nbre de shifts']
                )

                # Afficher le tableau avec les totaux calculés (lecture seule) en expandable
                with st.expander("📊 Aperçu avec totaux calculés", expanded=False):
                    st.dataframe(
                        df_formation_display,
                        column_config={
                            'Dénomination': st.column_config.TextColumn('Dénomination'),
                            'Effectif (pers.)': st.column_config.NumberColumn('Effectif (pers.)', format='%d'),
                            'Heures': st.column_config.NumberColumn('Heures', format='%.1f'),
                            'Nbre de shifts': st.column_config.NumberColumn('Nbre de shifts', format='%d'),
                            'Total (heures)': st.column_config.NumberColumn('Total (heures)', format='%.1f')
                        },
                        hide_index=True,
                        use_container_width=True
                    )


                # Boutons de gestion
                col_btn1, col_btn2, col_btn3, col_btn4 = st.columns(4)
                with col_btn1:
                    if st.button("➕ Ajouter une ligne", key="btn_add_formation"):
                        new_row = pd.DataFrame([{
                            'Dénomination': 'Nouvelle formation',
                            'Effectif (pers.)': 0,
                            'Heures': 0.0,
                            'Nbre de shifts': 0
                        }])
                        st.session_state.budget_formation_at = pd.concat(
                            [st.session_state.budget_formation_at, new_row],
                            ignore_index=True
                        )
                        st.rerun()

                with col_btn2:
                    if st.button("🔄 Réinitialiser", key="btn_reset_formation"):
                        st.session_state.budget_formation_at = pd.DataFrame([
                            {'Dénomination': 'Formation (théorique) AT S26', 'Effectif (pers.)': 20, 'Heures': 17.0, 'Nbre de shifts': 1},
                            {'Dénomination': 'Formation (pratique) AT S26', 'Effectif (pers.)': 20, 'Heures': 6.5, 'Nbre de shifts': 3},
                            {'Dénomination': 'Formation (théorique) AT CHT W26', 'Effectif (pers.)': 20, 'Heures': 17.0, 'Nbre de shifts': 1},
                            {'Dénomination': 'Formation (pratique) AT CHT W26', 'Effectif (pers.)': 20, 'Heures': 6.5, 'Nbre de shifts': 3},
                            {'Dénomination': "Formation Visitor's Center", 'Effectif (pers.)': 20, 'Heures': 4.0, 'Nbre de shifts': 1},
                            {'Dénomination': 'Refresher AT CDI', 'Effectif (pers.)': 0, 'Heures': 0.0, 'Nbre de shifts': 0},
                            {'Dénomination': 'Cours FEU', 'Effectif (pers.)': 40, 'Heures': 3.0, 'Nbre de shifts': 1},
                            {'Dénomination': 'Cours DEFI', 'Effectif (pers.)': 40, 'Heures': 2.0, 'Nbre de shifts': 1}
                        ])
                        st.rerun()

                with col_btn3:
                    if st.button("🗑️ Vider la table", key="btn_clear_formation"):
                        st.session_state.budget_formation_at = pd.DataFrame(columns=[
                            'Dénomination', 'Effectif (pers.)', 'Heures', 'Nbre de shifts'
                        ])
                        st.rerun()

                # Calcul des totaux (utiliser df_formation_display qui a la colonne Total calculée)
                total_heures_formation = df_formation_display['Total (heures)'].sum()
                cout_total_formation = total_heures_formation * cout_horaire_at

                # Afficher les totaux
                st.markdown("---")
                col_tot1, col_tot2 = st.columns(2)
                with col_tot1:
                    st.metric("Total (HEURES)", f"{total_heures_formation:,.1f} h")
                with col_tot2:
                    st.metric("Coût total (CHF)", f"{cout_total_formation:,.0f} CHF")

            # Shift AT Formateurs planifiés
            with st.container(border=True):
                st.subheader("Shift AT Formateurs planifiés")
                st.markdown("Gérez les shifts des formateurs AT avec coût horaire ATF.")

                # Récupérer le coût horaire ATF
                cout_horaire_atf = 54.00  # Valeur par défaut
                if 'personnel' in st.session_state and not st.session_state.personnel.empty:
                    personnel_df = st.session_state.personnel
                    atf_row = personnel_df[personnel_df['Type'] == 'ATF']
                    if not atf_row.empty:
                        try:
                            cout_horaire_atf = float(atf_row['Coût Horaire'].iloc[0])
                        except Exception:
                            pass

                st.caption(f"📌 Coût horaire ATF : **{cout_horaire_atf:.2f} CHF**")

                # Initialiser le DataFrame si nécessaire
                if 'budget_formateurs_at' not in st.session_state:
                    st.session_state.budget_formateurs_at = pd.DataFrame([
                        {'Dénomination': 'Formation (théorique) AT S26', 'Effectif (pers.)': 2, 'Heures': 17.0, 'Nbre de shifts': 1},
                        {'Dénomination': 'Doublure formation (pratique) AT S26', 'Effectif (pers.)': 20, 'Heures': 6.5, 'Nbre de shifts': 4},
                        {'Dénomination': 'Formation (théorique) AT CHT W26', 'Effectif (pers.)': 2, 'Heures': 17.0, 'Nbre de shifts': 1},
                        {'Dénomination': 'Doublure formation (pratique) AT CHT W26', 'Effectif (pers.)': 20, 'Heures': 6.5, 'Nbre de shifts': 4},
                        {'Dénomination': "Doublure Visitor's Center", 'Effectif (pers.)': 20, 'Heures': 4.0, 'Nbre de shifts': 1}
                    ])

                # Préparer le DataFrame pour l'édition (SANS la colonne Total)
                df_formateurs = st.session_state.budget_formateurs_at.copy()

                # S'assurer que seules les 4 colonnes éditables sont présentes
                editable_cols = ['Dénomination', 'Effectif (pers.)', 'Heures', 'Nbre de shifts']
                for col in editable_cols:
                    if col not in df_formateurs.columns:
                        if col == 'Dénomination':
                            df_formateurs[col] = ''
                        elif col in ('Effectif (pers.)', 'Nbre de shifts'):
                            df_formateurs[col] = 0
                        else:  # Heures
                            df_formateurs[col] = 0.0

                # Ne garder que les colonnes éditables pour le data_editor
                df_formateurs_edit = df_formateurs[editable_cols].copy()

                # Normaliser et valider les données
                df_formateurs_edit['Effectif (pers.)'] = pd.to_numeric(
                    df_formateurs_edit['Effectif (pers.)'], errors='coerce'
                ).fillna(0).astype(int).clip(lower=0)
                df_formateurs_edit['Heures'] = df_formateurs_edit['Heures'].apply(
                    lambda x: float(str(x).replace(',', '.')) if pd.notna(x) else 0.0
                ).clip(lower=0)
                df_formateurs_edit['Nbre de shifts'] = pd.to_numeric(
                    df_formateurs_edit['Nbre de shifts'], errors='coerce'
                ).fillna(0).astype(int).clip(lower=0)

                # Configuration des colonnes pour l'éditeur (SANS Total)
                column_config_formateurs = {
                    'Dénomination': st.column_config.TextColumn(
                        'Dénomination',
                        required=True,
                        help='Description du shift formateur'
                    ),
                    'Effectif (pers.)': st.column_config.NumberColumn(
                        'Effectif (pers.)',
                        min_value=0,
                        step=1,
                        format='%d',
                        required=True
                    ),
                    'Heures': st.column_config.NumberColumn(
                        'Heures',
                        min_value=0.0,
                        step=0.5,
                        format='%.1f',
                        required=True,
                        help='Durée en heures (décimales acceptées)'
                    ),
                    'Nbre de shifts': st.column_config.NumberColumn(
                        'Nbre de shifts',
                        min_value=0,
                        step=1,
                        format='%d',
                        required=True
                    )
                }

                # Éditeur de données (SANS la colonne Total)
                edited_formateurs = st.data_editor(
                    df_formateurs_edit,
                    column_config=column_config_formateurs,
                    num_rows="dynamic",
                    use_container_width=True,
                    hide_index=True,
                    key="editor_formateurs_at"
                )

                # Recalculer avec les données éditées
                edited_formateurs['Effectif (pers.)'] = pd.to_numeric(
                    edited_formateurs['Effectif (pers.)'], errors='coerce'
                ).fillna(0).astype(int).clip(lower=0)
                edited_formateurs['Heures'] = edited_formateurs['Heures'].apply(
                    lambda x: float(str(x).replace(',', '.')) if pd.notna(x) else 0.0
                ).clip(lower=0)
                edited_formateurs['Nbre de shifts'] = pd.to_numeric(
                    edited_formateurs['Nbre de shifts'], errors='coerce'
                ).fillna(0).astype(int).clip(lower=0)

                # Sauvegarder dans session_state (SANS la colonne Total)
                st.session_state.budget_formateurs_at = edited_formateurs

                # Calculer les totaux par ligne APRÈS l'édition
                df_formateurs_display = edited_formateurs.copy()
                df_formateurs_display['Total (heures)'] = (
                    df_formateurs_display['Effectif (pers.)'] *
                    df_formateurs_display['Heures'] *
                    df_formateurs_display['Nbre de shifts']
                )

                # Afficher le tableau avec les totaux calculés (lecture seule) en expandable
                with st.expander("📊 Aperçu avec totaux calculés", expanded=False):
                    st.dataframe(
                        df_formateurs_display,
                        column_config={
                            'Dénomination': st.column_config.TextColumn('Dénomination'),
                            'Effectif (pers.)': st.column_config.NumberColumn('Effectif (pers.)', format='%d'),
                            'Heures': st.column_config.NumberColumn('Heures', format='%.1f'),
                            'Nbre de shifts': st.column_config.NumberColumn('Nbre de shifts', format='%d'),
                            'Total (heures)': st.column_config.NumberColumn('Total (heures)', format='%.1f')
                        },
                        hide_index=True,
                        use_container_width=True
                    )

                # Boutons de gestion
                col_btn1, col_btn2, col_btn3, col_btn4 = st.columns(4)
                with col_btn1:
                    if st.button("➕ Ajouter une ligne", key="btn_add_formateurs"):
                        new_row = pd.DataFrame([{
                            'Dénomination': 'Nouveau shift formateur',
                            'Effectif (pers.)': 0,
                            'Heures': 0.0,
                            'Nbre de shifts': 0
                        }])
                        st.session_state.budget_formateurs_at = pd.concat(
                            [st.session_state.budget_formateurs_at, new_row],
                            ignore_index=True
                        )
                        st.rerun()

                with col_btn2:
                    if st.button("🔄 Réinitialiser", key="btn_reset_formateurs"):
                        st.session_state.budget_formateurs_at = pd.DataFrame([
                            {'Dénomination': 'Formation (théorique) AT S26', 'Effectif (pers.)': 2, 'Heures': 17.0, 'Nbre de shifts': 1},
                            {'Dénomination': 'Doublure formation (pratique) AT S26', 'Effectif (pers.)': 20, 'Heures': 6.5, 'Nbre de shifts': 4},
                            {'Dénomination': 'Formation (théorique) AT CHT W26', 'Effectif (pers.)': 2, 'Heures': 17.0, 'Nbre de shifts': 1},
                            {'Dénomination': 'Doublure formation (pratique) AT CHT W26', 'Effectif (pers.)': 20, 'Heures': 6.5, 'Nbre de shifts': 4},
                            {'Dénomination': "Doublure Visitor's Center", 'Effectif (pers.)': 20, 'Heures': 4.0, 'Nbre de shifts': 1}
                        ])
                        st.rerun()

                with col_btn3:
                    if st.button("🗑️ Vider la table", key="btn_clear_formateurs"):
                        st.session_state.budget_formateurs_at = pd.DataFrame(columns=[
                            'Dénomination', 'Effectif (pers.)', 'Heures', 'Nbre de shifts'
                        ])
                        st.rerun()

                # Calcul des totaux (utiliser df_formateurs_display qui a la colonne Total calculée)
                total_heures_formateurs = df_formateurs_display['Total (heures)'].sum()
                cout_total_formateurs = total_heures_formateurs * cout_horaire_atf

                # Afficher les totaux
                st.markdown("---")
                col_tot1, col_tot2 = st.columns(2)
                with col_tot1:
                    st.metric("Total (HEURES)", f"{total_heures_formateurs:,.1f} h")
                with col_tot2:
                    st.metric("Coût total (CHF)", f"{cout_total_formateurs:,.0f} CHF")

            # ========== SYNTHÈSE ANNUELLE (affichée après les tables pour refléter les modifications) ==========
            with st.container(border=True):
                st.subheader("Synthèse Annuelle")
                totals = bs.get('totals', {})
                total_heures_planif = totals.get('heures_annuel', 0.0)
                total_cout_planif = totals.get('cout_annuel', 0.0)

                # Calcul des heures/coûts de formation (depuis session_state mis à jour)
                total_heures_formation = 0.0
                total_cout_formation = 0.0
                cout_horaire_at = 45.50
                if 'personnel' in st.session_state and not st.session_state.personnel.empty:
                    at_row = st.session_state.personnel[st.session_state.personnel['Type'] == 'AT']
                    if not at_row.empty:
                        try:
                            cout_horaire_at = float(at_row['Coût Horaire'].iloc[0])
                        except Exception:
                            pass

                if 'budget_formation_at' in st.session_state:
                    df_formation = st.session_state.budget_formation_at.copy()
                    # Normaliser les données
                    df_formation['Effectif (pers.)'] = pd.to_numeric(df_formation.get('Effectif (pers.)', 0), errors='coerce').fillna(0).astype(int).clip(lower=0)
                    df_formation['Heures'] = df_formation.get('Heures', 0).apply(
                        lambda x: float(str(x).replace(',', '.')) if pd.notna(x) else 0.0
                    ).clip(lower=0)
                    df_formation['Nbre de shifts'] = pd.to_numeric(df_formation.get('Nbre de shifts', 0), errors='coerce').fillna(0).astype(int).clip(lower=0)
                    df_formation['Total (heures)'] = (
                        df_formation['Effectif (pers.)'] *
                        df_formation['Heures'] *
                        df_formation['Nbre de shifts']
                    )
                    total_heures_formation = df_formation['Total (heures)'].sum()
                    total_cout_formation = total_heures_formation * cout_horaire_at

                # Calcul des heures/coûts formateurs (depuis session_state mis à jour)
                total_heures_formateurs = 0.0
                total_cout_formateurs = 0.0
                cout_horaire_atf = 52.00
                if 'personnel' in st.session_state and not st.session_state.personnel.empty:
                    atf_row = st.session_state.personnel[st.session_state.personnel['Type'] == 'ATF']
                    if not atf_row.empty:
                        try:
                            cout_horaire_atf = float(atf_row['Coût Horaire'].iloc[0])
                        except Exception:
                            pass

                if 'budget_formateurs_at' in st.session_state:
                    df_formateurs = st.session_state.budget_formateurs_at.copy()
                    # Normaliser les données
                    df_formateurs['Effectif (pers.)'] = pd.to_numeric(df_formateurs.get('Effectif (pers.)', 0), errors='coerce').fillna(0).astype(int).clip(lower=0)
                    df_formateurs['Heures'] = df_formateurs.get('Heures', 0).apply(
                        lambda x: float(str(x).replace(',', '.')) if pd.notna(x) else 0.0
                    ).clip(lower=0)
                    df_formateurs['Nbre de shifts'] = pd.to_numeric(df_formateurs.get('Nbre de shifts', 0), errors='coerce').fillna(0).astype(int).clip(lower=0)
                    df_formateurs['Total (heures)'] = (
                        df_formateurs['Effectif (pers.)'] *
                        df_formateurs['Heures'] *
                        df_formateurs['Nbre de shifts']
                    )
                    total_heures_formateurs = df_formateurs['Total (heures)'].sum()
                    total_cout_formateurs = total_heures_formateurs * cout_horaire_atf

                # Totaux globaux
                total_heures_global = total_heures_planif + total_heures_formation + total_heures_formateurs
                total_cout_global = total_cout_planif + total_cout_formation + total_cout_formateurs

                st.markdown(
                    f"""<div class="kpi-cards">
                    <div class="kpi-card kpi-blue">
                        <div class="label">Volume Heures Annuel (Planification)</div>
                        <div class="value">{total_heures_planif:,.0f} h</div>
                    </div>
                    <div class="kpi-card kpi-amber">
                        <div class="label">Coût Annuel (Planification)</div>
                        <div class="value">{total_cout_planif:,.0f} CHF</div>
                    </div>
                    </div>""",
                    unsafe_allow_html=True
                )

                # --- (remplace l'ancien bloc 'if total_heures_formation > 0 or total_heures_formateurs > 0: ...') ---
                if total_heures_formation > 0 or total_heures_formateurs > 0:
                    # Petit style pour la sous-ligne
                    st.markdown("""
                    <style>
                    .kpi-card .sub {
                        margin-top: .25rem;
                        font-size: .85em;
                        color: #6b7280;
                        line-height: 1.25;/* gris neutre */
                    }
                    </style>
                    """, unsafe_allow_html=True)
                
                    # Sous-lignes (heures et coût)
                    breakdown_heures = (
                        "<div class='sub'>"
                        "dont<br>"
                        f"{total_heures_formation:,.1f} heure"
                        f"{'' if abs(total_heures_formation - 1) < 1e-9 else 's'} Formation<br> "
                        f"et {total_heures_formateurs:,.1f} heure"
                        f"{'' if abs(total_heures_formateurs - 1) < 1e-9 else 's'} de shifts ATF</div>"
                    )
                    breakdown_cout = (
                        "<div class='sub'>"
                        "dont<br>"
                        f"{total_cout_formation:,.0f} CHF Formation<br> "
                        f"et {total_cout_formateurs:,.0f} CHF de shifts ATF</div>"
                    )
                
                    # KPI Totaux (une seule rangée, avec sous-lignes)
                    st.markdown(f'''
                        <div class="kpi-cards">
                            <div class="kpi-card kpi-blue">
                                <div class="label">Total Heures (avec formation)</div>
                                <div class="value">{total_heures_global:,.0f} h</div>
                                {breakdown_heures}
                            </div>
                            <div class="kpi-card kpi-amber">
                                <div class="label">Total Coût (avec formation)</div>
                                <div class="value">{total_cout_global:,.0f} CHF</div>
                                {breakdown_cout}
                            </div>
                        </div>
                    ''', unsafe_allow_html=True)


                # --- Répartition Coût et Heure par Catégorie ---
                st.markdown("---")
                st.subheader("Répartition Coût et Heure par Catégorie")

                # Onglets sous le titre
                tab_cost, tab_hours = st.tabs(["Coût", "Heure"])

                # ===================== ONGLET COÛT =====================
                with tab_cost:
                    # Récupération du résumé tel que calculé par generate_budget_state
                    summary = bs.get('summary', pd.DataFrame()).copy()

                    def _ensure_numeric_cost(df: pd.DataFrame) -> pd.DataFrame:
                        if 'Coût' in df.columns:
                            df['Coût'] = pd.to_numeric(df['Coût'], errors='coerce').fillna(0.0).astype(float)
                        return df

                    summary = _ensure_numeric_cost(summary)

                    # Ajouter Formation/Doublure AT & ATF depuis les calculs de synthèse
                    extra_rows = pd.DataFrame([
                        {'Catégorie': 'Formation/Doublure AT', 'Coût': float(total_cout_formation if "total_cout_formation" in locals() else 0.0)},
                        {'Catégorie': 'ATF',                   'Coût': float(total_cout_formateurs if "total_cout_formateurs" in locals() else 0.0)}
                    ])

                    if summary.empty:
                        summary = extra_rows.copy()
                    else:
                        summary = pd.concat([summary, extra_rows], ignore_index=True)
                        summary = summary.groupby('Catégorie', as_index=False)['Coût'].sum()

                    if not summary.empty:
                        # Prépare données en millions de CHF
                        summary_m = summary.copy()
                        summary_m['Coût_M'] = summary_m['Coût'] / 1_000_000

                        col1, col2 = st.columns([0.44, 0.56])

                        with col1:
                            st.dataframe(
                                summary.set_index('Catégorie').style.format({'Coût': '{:,.0f} CHF'}),
                                use_container_width=True
                            )

                        with col2:
                            # Sélection multi par clic
                            sel = alt.selection_point(
                                fields=['Catégorie'],
                                on='click',
                                toggle=True,
                                empty='none'
                            )

                            bars = alt.Chart(summary_m).mark_bar().encode(
                                x=alt.X(
                                    'Catégorie:N',
                                    sort='-y',
                                    title=None,
                                    axis=alt.Axis(
                                        labelFontSize=10,
                                        labelAngle=-30,
                                        labelLimit=220,
                                        labelOverlap=False
                                    )
                                ),
                                y=alt.Y('Coût_M:Q', title='Coût (M CHF)'),
                                tooltip=[
                                    alt.Tooltip('Catégorie:N', title='Catégorie'),
                                    alt.Tooltip('Coût_M:Q', title='Coût (M CHF)', format=',.2f'),
                                    alt.Tooltip('Coût:Q',   title='Coût (CHF)',  format=',.0f')
                                ],
                                opacity=alt.condition(sel, alt.value(1), alt.value(0.6))
                            ).add_params(sel)

                            rule = alt.Chart(summary_m).transform_filter(
                                sel
                            ).transform_aggregate(
                                total_sel='sum(Coût_M)'
                            ).mark_rule(
                                strokeDash=[6,4],
                                size=2
                            ).encode(
                                y='total_sel:Q',
                                tooltip=[alt.Tooltip('total_sel:Q', title='Total sélection (M CHF)', format=',.2f')]
                            )

                            label = alt.Chart(summary_m).transform_filter(
                                sel
                            ).transform_aggregate(
                                total_sel='sum(Coût_M)'
                            ).mark_text(
                                dy=-6
                            ).encode(
                                y='total_sel:Q',
                                x=alt.value(5),
                                text=alt.Text('total_sel:Q', format=',.2f')
                            )

                            chart_cost = (bars + rule + label).properties(height=350)

                            # Astuce (petite police + italique)
                            st.markdown(
                                "<span style='font-size:0.85em; font-style:italic; color:#555;'>💡 Astuce : "
                                "Shift+Click pour sélectionner plusieurs barres ou en retirer.</span>",
                                unsafe_allow_html=True
                            )
                            st.altair_chart(chart_cost, use_container_width=True)
                    else:
                        st.info("Aucun coût calculé (vérifiez l'association des coûts et les tarifs).")

                # ===================== ONGLET HEURE =====================
                with tab_hours:
                    calendar_df = bs.get('calendar_df', pd.DataFrame()).copy()
                    if not calendar_df.empty:
                        # Construire la table Heures par Catégorie depuis les colonnes Heures_*
                        hour_cols = [c for c in calendar_df.columns if c.startswith('Heures_') and c != 'Heures_Total_Jour']
                        heures_rows = []
                        for c in hour_cols:
                            cat = c.replace('Heures_', '')
                            total_h = pd.to_numeric(calendar_df[c], errors='coerce').fillna(0.0).sum()
                            heures_rows.append({'Catégorie': cat, 'Heures': float(total_h)})

                        heures_df = pd.DataFrame(heures_rows)

                        # Ajouter la Formation/Doublure AT (heures hors planif) et ATF (heures formateurs)
                        if 'total_heures_formation' in locals():
                            heures_df = pd.concat(
                                [heures_df, pd.DataFrame([{'Catégorie': 'Formation/Doublure AT', 'Heures': float(total_heures_formation)}])],
                                ignore_index=True
                            )
                        if 'total_heures_formateurs' in locals():
                            heures_df = pd.concat(
                                [heures_df, pd.DataFrame([{'Catégorie': 'ATF', 'Heures': float(total_heures_formateurs)}])],
                                ignore_index=True
                            )

                        heures_df = heures_df.groupby('Catégorie', as_index=False)['Heures'].sum()

                        col1h, col2h = st.columns([0.44, 0.56])
                        with col1h:
                            st.dataframe(
                                heures_df.set_index('Catégorie').style.format({'Heures': '{:,.1f} h'}),
                                use_container_width=True
                            )

                        with col2h:
                            sel_h = alt.selection_point(
                                fields=['Catégorie'],
                                on='click',
                                toggle=True,
                                empty='none'
                            )

                            bars_h = alt.Chart(heures_df).mark_bar().encode(
                                x=alt.X(
                                    'Catégorie:N',
                                    sort='-y',
                                    title=None,
                                    axis=alt.Axis(
                                        labelFontSize=10,
                                        labelAngle=-30,
                                        labelLimit=220,
                                        labelOverlap=False
                                    )
                                ),
                                y=alt.Y('Heures:Q', title='Heures', axis=alt.Axis(format='.2s')),
                                tooltip=[
                                    alt.Tooltip('Catégorie:N', title='Catégorie'),
                                    alt.Tooltip('Heures:Q', title='Heures', format=',.1f')
                                ],
                                opacity=alt.condition(sel_h, alt.value(1), alt.value(0.6))
                            ).add_params(sel_h)

                            rule_h = alt.Chart(heures_df).transform_filter(
                                sel_h
                            ).transform_aggregate(
                                total_sel='sum(Heures)'
                            ).mark_rule(
                                strokeDash=[6,4],
                                size=2
                            ).encode(
                                y='total_sel:Q',
                                tooltip=[alt.Tooltip('total_sel:Q', title='Total sélection (h)', format=',.1f')]
                            )

                            label_h = alt.Chart(heures_df).transform_filter(
                                sel_h
                            ).transform_aggregate(
                                total_sel='sum(Heures)'
                            ).mark_text(
                                dy=-6
                            ).encode(
                                y='total_sel:Q',
                                x=alt.value(5),
                                text=alt.Text('total_sel:Q', format=',.1f')
                            )

                            chart_hours = (bars_h + rule_h + label_h).properties(height=350)

                            st.markdown(
                                "<span style='font-size:0.85em; font-style:italic; color:#555;'>💡 Astuce : "
                                "Shift+Click pour sélectionner plusieurs barres ou en retirer.</span>",
                                unsafe_allow_html=True
                            )
                            st.altair_chart(chart_hours, use_container_width=True)
                    else:
                        st.info("Le détail des heures n'est pas disponible.")

                # --- Information additionnelle : DA OPT AT ---
                # DA OPT AT = Heures_AT + Heures_CSC + Heures_EES + Heures_Formation/Doublure AT
                da_opt_at_heures = 0.0

                calendar_df_all = bs.get('calendar_df', pd.DataFrame())
                if not calendar_df_all.empty:
                    for col in ['Heures_AT', 'Heures_CSC', 'Heures_EES']:
                        if col in calendar_df_all.columns:
                            da_opt_at_heures += pd.to_numeric(calendar_df_all[col], errors='coerce').fillna(0.0).sum()

                # Ajoute la formation/doublure (calculée plus haut)
                if 'total_heures_formation' in locals():
                    da_opt_at_heures += float(total_heures_formation)

                # Calcul du coût total associé aux heures DA OPT AT
                da_opt_at_cout = 0.0
                if not calendar_df_all.empty:
                    for col in ['Coût_AT', 'Coût_CSC', 'Coût_EES']:
                        if col in calendar_df_all.columns:
                            da_opt_at_cout += pd.to_numeric(calendar_df_all[col], errors='coerce').fillna(0.0).sum()
                if 'cout_total_formation' in locals():
                    da_opt_at_cout += float(cout_total_formation)

                # ✅ Affichage sur deux lignes (titre + italique dessous)
                st.markdown(
                    f"""
                    **DA OPT AT** : {da_opt_at_heures:,.1f} h / {da_opt_at_cout:,.0f} CHF  
                    *AT + CSC + EES + Formation/Doublure AT*
                    """,
                    unsafe_allow_html=True
                )

            # Détail Mensuel et Journalier
            with st.container(border=True):
                st.subheader("Budget Détaillé par Période")
                calendar_df = bs.get('calendar_df', pd.DataFrame())

                if not calendar_df.empty:
                    try:
                        # Préparation des données mensuelles
                        calendar_df['Date'] = pd.to_datetime(calendar_df['Date'])
                        calendar_df['Mois_Str'] = calendar_df['Date'].dt.strftime('%m.%Y')
                        calendar_df['Month_Obj'] = calendar_df['Date'].dt.to_period('M')
                        calendar_df = calendar_df.sort_values('Date')

                        cost_cols = [c for c in calendar_df.columns
                                   if c.startswith('Coût_') and c != 'Coût_Total_Jour']
                        hour_cols = [c for c in calendar_df.columns
                                   if c.startswith('Heures_') and c != 'Heures_Total_Jour']
                        cols_to_group = ['Mois_Str', 'Month_Obj'] + cost_cols + hour_cols

                        # Grouper par mois
                        monthly_summary = calendar_df[cols_to_group].groupby(
                            ['Month_Obj', 'Mois_Str'], sort=True
                        ).sum(numeric_only=True).reset_index()
                        monthly_summary = monthly_summary.drop(columns=['Month_Obj'])
                        monthly_summary = monthly_summary.fillna(0)

                        # Tableaux Mensuels
                        tab_monthly_cost, tab_monthly_hour = st.tabs([
                            "Détail Mensuel (CHF)",
                            "Détail Mensuel (Heures)"
                        ])

                        with tab_monthly_cost:
                            df_costs = monthly_summary[['Mois_Str'] + cost_cols].copy()
                            category_cost_cols = [c.replace('Coût_', '') for c in cost_cols]
                            df_costs.columns = ['Mois'] + category_cost_cols
                            if category_cost_cols:
                                for col in category_cost_cols:
                                    df_costs[col] = pd.to_numeric(
                                        df_costs[col], errors='coerce'
                                    ).fillna(0.0).astype(float)
                                df_costs['Total'] = df_costs[category_cost_cols].sum(axis=1).astype(float)
                            else:
                                df_costs['Total'] = 0.0

                            col_config_costs = {"Mois": st.column_config.TextColumn("Mois")}
                            for cat in category_cost_cols:
                                col_config_costs[cat] = st.column_config.NumberColumn(
                                    f"{cat} (CHF)", format="%.0f"
                                )
                            col_config_costs["Total"] = st.column_config.NumberColumn(
                                "Total (CHF)", format="%.0f"
                            )

                            st.dataframe(
                                df_costs, column_config=col_config_costs,
                                hide_index=True, use_container_width=True
                            )

                        with tab_monthly_hour:
                            df_hours = monthly_summary[['Mois_Str'] + hour_cols].copy()
                            category_hour_cols = [c.replace('Heures_', '') for c in hour_cols]
                            df_hours.columns = ['Mois'] + category_hour_cols
                            if category_hour_cols:
                                for col in category_hour_cols:
                                    df_hours[col] = pd.to_numeric(
                                        df_hours[col], errors='coerce'
                                    ).fillna(0.0).astype(float)
                                df_hours['Total'] = df_hours[category_hour_cols].sum(axis=1).astype(float)
                            else:
                                df_hours['Total'] = 0.0

                            col_config_hours = {"Mois": st.column_config.TextColumn("Mois")}
                            for cat in category_hour_cols:
                                col_config_hours[cat] = st.column_config.NumberColumn(
                                    f"{cat} (h)", format="%.1f"
                                )
                            col_config_hours["Total"] = st.column_config.NumberColumn(
                                "Total (h)", format="%.1f"
                            )

                            st.dataframe(
                                df_hours, column_config=col_config_hours,
                                hide_index=True, use_container_width=True
                            )

                        # Section Détail Journalier
                        st.divider()
                        st.markdown("##### Explorer le Détail Journalier")
                        available_months = monthly_summary['Mois_Str'].unique().tolist()
                        selected_month = st.selectbox(
                            "Sélectionner un mois pour voir les jours :",
                            available_months, key="budget_detail_month_select"
                        )

                        if selected_month:
                            df_daily_detail = calendar_df[
                                calendar_df['Mois_Str'] == selected_month
                            ].copy()
                            df_daily_detail['Jour_Semaine'] = _day_name_fr(df_daily_detail['Date'])

                            tab_daily_cost, tab_daily_hour = st.tabs([
                                f"Détail Jours {selected_month} (CHF)",
                                f"Détail Jours {selected_month} (Heures)"
                            ])

                            with tab_daily_cost:
                                cols_to_show_cost = ['Date', 'Jour_Semaine'] + cost_cols + ['Coût_Total_Jour']
                                df_daily_costs_view = df_daily_detail[cols_to_show_cost].copy()
                                cost_view_cols_rename = {c: c.replace('Coût_', '') for c in cost_cols}
                                cost_view_cols_rename['Coût_Total_Jour'] = 'Total'
                                cost_view_cols_rename['Jour_Semaine'] = 'Jour'
                                df_daily_costs_view = df_daily_costs_view.rename(columns=cost_view_cols_rename)

                                numeric_cost_cols_daily = list(cost_view_cols_rename.values())
                                for col in ('Date', 'Jour'):
                                    if col in numeric_cost_cols_daily:
                                        numeric_cost_cols_daily.remove(col)
                                if numeric_cost_cols_daily:
                                    df_daily_costs_view[numeric_cost_cols_daily] =                                         df_daily_costs_view[numeric_cost_cols_daily].apply(
                                            pd.to_numeric, errors='coerce'
                                        ).fillna(0.0).astype(float)

                                daily_cost_config = {
                                    "Date": st.column_config.DateColumn("Date", format="DD/MM/YYYY"),
                                    "Jour": st.column_config.TextColumn("Jour")
                                }
                                for cat_col in cost_view_cols_rename.values():
                                    if cat_col not in ["Date", "Jour"]:
                                        daily_cost_config[cat_col] = st.column_config.NumberColumn(
                                            f"{cat_col} (CHF)", format="%.0f"
                                        )

                                st.dataframe(
                                    df_daily_costs_view, column_config=daily_cost_config,
                                    hide_index=True, use_container_width=True
                                )

                            with tab_daily_hour:
                                cols_to_show_hour = ['Date', 'Jour_Semaine'] + hour_cols + ['Heures_Total_Jour']
                                df_daily_hours_view = df_daily_detail[cols_to_show_hour].copy()
                                hour_view_cols_rename = {c: c.replace('Heures_', '') for c in hour_cols}
                                hour_view_cols_rename['Heures_Total_Jour'] = 'Total'
                                hour_view_cols_rename['Jour_Semaine'] = 'Jour'
                                df_daily_hours_view = df_daily_hours_view.rename(columns=hour_view_cols_rename)

                                numeric_hour_cols_daily = list(hour_view_cols_rename.values())
                                for col in ('Date', 'Jour'):
                                    if col in numeric_hour_cols_daily:
                                        numeric_hour_cols_daily.remove(col)
                                if numeric_hour_cols_daily:
                                    df_daily_hours_view[numeric_hour_cols_daily] =                                         df_daily_hours_view[numeric_hour_cols_daily].apply(
                                            pd.to_numeric, errors='coerce'
                                        ).fillna(0.0).astype(float)

                                daily_hour_config = {
                                    "Date": st.column_config.DateColumn("Date", format="DD/MM/YYYY"),
                                    "Jour": st.column_config.TextColumn("Jour")
                                }
                                for cat_col in hour_view_cols_rename.values():
                                    if cat_col not in ["Date", "Jour"]:
                                        daily_hour_config[cat_col] = st.column_config.NumberColumn(
                                            f"{cat_col} (h)", format="%.1f"
                                        )

                                st.dataframe(
                                    df_daily_hours_view, column_config=daily_hour_config,
                                    hide_index=True, use_container_width=True
                                )

                    except Exception as e:
                        st.error(f"Erreur lors de la préparation du détail mensuel/journalier : {e}")
                        import traceback
                        st.error(traceback.format_exc())

                else:
                    st.info("Le détail mensuel/journalier n'est pas disponible.")

    # =================== Onglet 2 : Paramètres du Calendrier ===================
    with tabs_budget[1]:
        with st.container(border=True):
            st.subheader(f"Calendrier des Saisons pour {year}")
            st.markdown("Les dates sont calculées automatiquement. Ajustez si nécessaire.")

            _ensure_adjusted_saisons_for_year(year)

            if 'adjusted_saisons' not in st.session_state or                st.session_state.adjusted_saisons.empty:
                st.warning(f"Impossible de déterminer le calendrier des saisons pour {year}.")
            else:
                col_edit, col_viz = st.columns([0.4, 0.6])
                with col_edit:
                    current_adjusted_saisons = st.session_state.adjusted_saisons.copy()
                    edited_adjusted_saisons = st.data_editor(
                        current_adjusted_saisons,
                        column_config={
                            "Saison": st.column_config.TextColumn(
                                "Nom Saison", required=True
                            ),
                            "Date Début": st.column_config.DateColumn(
                                "Date Début", format="DD/MM/YYYY", required=True
                            ),
                            "Date Fin": st.column_config.DateColumn(
                                "Date Fin", format="DD/MM/YYYY", required=True
                            )
                        },
                        num_rows="dynamic",
                        key="editor_adjusted_saisons",
                        use_container_width=True,
                        hide_index=True
                    )
                    if not edited_adjusted_saisons.equals(current_adjusted_saisons):
                        st.session_state.adjusted_saisons = edited_adjusted_saisons
                        st.info("Calendrier ajusté. Regénérez le budget pour appliquer.")
                        st.rerun()

                with col_viz:
                    try:
                        timeline_df = _season_timeline_df()
                        if not timeline_df.empty:
                            # Color mapping
                            base_map = {
                                "Hiver": "#0076aa",
                                "Standard": "#C2C3CB",
                                "Été": "#68813B",
                                "Ete": "#68813B"
                            }
                            fallback_palette = ["#C0A192", "#E5D8D1", "#E0E1D4"]
                            seasons = list(pd.unique(timeline_df["Saison"]))
                            colors, fp_idx = [], 0
                            for s in seasons:
                                colors.append(base_map.get(
                                    s, fallback_palette[fp_idx % len(fallback_palette)]
                                ))
                                if s not in base_map:
                                    fp_idx += 1

                            # Altair chart
                            timeline = alt.Chart(timeline_df).mark_bar(
                                cornerRadius=3, height=50
                            ).encode(
                                x=alt.X("start:T", title="", axis=alt.Axis(format="%b")),
                                x2="end:T",
                                y=alt.Y("Saison:N", sort=None, title=None,
                                       axis=alt.Axis(labels=True, ticks=False, domain=False)),
                                tooltip=["Saison", "start:T", "end:T",
                                        alt.Tooltip("days", title="Durée (j)")],
                                color=alt.Color("Saison:N", legend=alt.Legend(title="Saison"),
                                              scale=alt.Scale(domain=seasons, range=colors)),
                                order=alt.Order("start:T")
                            ).properties(height=max(100, len(seasons) * 75))
                            st.altair_chart(timeline, use_container_width=True)
                        else:
                            st.info("Aucune donnée de saison à visualiser.")
                    except Exception as e:
                        st.warning(f"Impossible d'afficher la frise chronologique: {e}")

    # =================== Onglet 3 : Association des Coûts ===================
    with tabs_budget[2]:
        with st.container(border=True):
            st.subheader("Association Personnel-Coût par Catégorie")
            st.markdown("Associez chaque catégorie à un type de personnel pour le calcul des coûts.")

            if 'personnel' not in st.session_state or st.session_state.personnel.empty:
                st.warning("Définissez d'abord les types de personnel dans 'Configuration'.")
            elif 'perimetres' not in st.session_state or not st.session_state.perimetres:
                st.warning("Définissez d'abord les catégories/périmètres dans 'Configuration'.")
            else:
                personnel_list = st.session_state.personnel['Type'].tolist()
                cost_mapping = st.session_state.get('cost_mapping', {})
                # Assurer que le mapping existe pour toutes les catégories
                for cat in st.session_state.perimetres.keys():
                    if cat not in cost_mapping:
                        cost_mapping[cat] = personnel_list[0] if personnel_list else None

                cols = st.columns(3)
                sorted_categories = sorted(list(st.session_state.perimetres.keys()))
                changed = False
                for i, key in enumerate(sorted_categories):
                    with cols[i % 3]:
                        current_personnel = cost_mapping.get(key)
                        try:
                            default_idx = personnel_list.index(current_personnel)                                          if current_personnel in personnel_list else 0
                        except ValueError:
                            default_idx = 0

                        new_personnel = st.selectbox(
                            f"**{key}** :",
                            personnel_list,
                            index=default_idx,
                            key=f"map_{key}"
                        )
                        if new_personnel != current_personnel:
                            cost_mapping[key] = new_personnel
                            changed = True

                if changed:
                    st.session_state.cost_mapping = cost_mapping
                    st.info("Association mise à jour. Regénérez le budget pour appliquer.")
                    st.rerun()
