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
                    if 'budget_state' in st.session_state and \
                       st.session_state.budget_state.get('year') == year:
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
            # Synthèse Annuelle
            with st.container(border=True):
                st.subheader("Synthèse Annuelle")
                totals = bs.get('totals', {})
                total_heures_annuel = totals.get('heures_annuel', 0.0)
                total_cout_annuel = totals.get('cout_annuel', 0.0)
                st.markdown(
                    f"""<div class="kpi-cards">
                    <div class="kpi-card kpi-blue">
                        <div class="label">Volume Heures Annuel TOTAL</div>
                        <div class="value">{total_heures_annuel:,.0f} h</div>
                    </div>
                    <div class="kpi-card kpi-amber">
                        <div class="label">Coût Annuel TOTAL</div>
                        <div class="value">{total_cout_annuel:,.0f} CHF</div>
                    </div>
                    </div>""",
                    unsafe_allow_html=True
                )
                st.markdown("---")
                st.subheader("Répartition du Coût par Catégorie")
                summary = bs.get('summary', pd.DataFrame())
                if not summary.empty:
                    col1, col2 = st.columns([0.4, 0.6])
                    with col1:
                        st.dataframe(
                            summary.set_index('Catégorie').style.format({'Coût': '{:,.0f} CHF'}),
                            use_container_width=True
                        )
                    with col2:
                        try:
                            chart = alt.Chart(summary).mark_bar().encode(
                                x=alt.X('Catégorie:N', sort='-y', title=None),
                                y=alt.Y('Coût:Q', title="Coût (CHF)"),
                                tooltip=['Catégorie', alt.Tooltip('Coût:Q', format=',.0f')]
                            ).properties(height=250)
                            st.altair_chart(chart, use_container_width=True)
                        except Exception as e:
                            st.warning(f"Impossible d'afficher le graphique : {e}")
                            st.bar_chart(summary.set_index('Catégorie'))
                else:
                    st.info("Aucun coût calculé (vérifiez l'association des coûts et les tarifs).")

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
                            "📊 Détail Mensuel (CHF)",
                            "🕒 Détail Mensuel (Heures)"
                        ])

                        with tab_monthly_cost:
                            df_costs = monthly_summary[['Mois_Str'] + cost_cols].copy()
                            category_cost_cols = [c.replace('Coût_', '') for c in cost_cols]
                            df_costs.columns = ['Mois'] + category_cost_cols
                            if category_cost_cols:
                                # Convertir toutes les colonnes numériques en float et remplacer NaN
                                for col in category_cost_cols:
                                    df_costs[col] = pd.to_numeric(
                                        df_costs[col], errors='coerce'
                                    ).fillna(0.0).astype(float)
                                # Calculer le Total
                                df_costs['Total'] = df_costs[category_cost_cols].sum(axis=1).astype(float)
                            else:
                                df_costs['Total'] = 0.0

                            col_config_costs = {"Mois": st.column_config.TextColumn("Mois")}
                            for cat in category_cost_cols:
                                col_config_costs[cat] = st.column_config.NumberColumn(
                                    f"{cat}", format="%,.0f CHF"
                                )
                            col_config_costs["Total"] = st.column_config.NumberColumn(
                                "Total", format="%,.0f CHF"
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
                                # Convertir toutes les colonnes numériques en float et remplacer NaN
                                for col in category_hour_cols:
                                    df_hours[col] = pd.to_numeric(
                                        df_hours[col], errors='coerce'
                                    ).fillna(0.0).astype(float)
                                # Calculer le Total
                                df_hours['Total'] = df_hours[category_hour_cols].sum(axis=1).astype(float)
                            else:
                                df_hours['Total'] = 0.0

                            col_config_hours = {"Mois": st.column_config.TextColumn("Mois")}
                            for cat in category_hour_cols:
                                col_config_hours[cat] = st.column_config.NumberColumn(
                                    f"{cat}", format="%.1f h"
                                )
                            col_config_hours["Total"] = st.column_config.NumberColumn(
                                "Total", format="%.1f h"
                            )

                            st.dataframe(
                                df_hours, column_config=col_config_hours,
                                hide_index=True, use_container_width=True
                            )

                        # Section Détail Journalier
                        st.divider()
                        st.markdown("##### 🗓️ Explorer le Détail Journalier")
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
                                cols_to_show_cost = ['Date', 'Jour_Semaine'] + cost_cols + \
                                                   ['Coût_Total_Jour']
                                df_daily_costs_view = df_daily_detail[cols_to_show_cost].copy()
                                cost_view_cols_rename = {
                                    c: c.replace('Coût_', '') for c in cost_cols
                                }
                                cost_view_cols_rename['Coût_Total_Jour'] = 'Total'
                                cost_view_cols_rename['Jour_Semaine'] = 'Jour'
                                df_daily_costs_view = df_daily_costs_view.rename(
                                    columns=cost_view_cols_rename
                                )

                                numeric_cost_cols_daily = list(cost_view_cols_rename.values())
                                if 'Date' in numeric_cost_cols_daily:
                                    numeric_cost_cols_daily.remove('Date')
                                if 'Jour' in numeric_cost_cols_daily:
                                    numeric_cost_cols_daily.remove('Jour')
                                if numeric_cost_cols_daily:
                                    df_daily_costs_view[numeric_cost_cols_daily] = \
                                        df_daily_costs_view[numeric_cost_cols_daily].apply(
                                            pd.to_numeric, errors='coerce'
                                        ).fillna(0.0).astype(float)

                                daily_cost_config = {
                                    "Date": st.column_config.DateColumn(
                                        "Date", format="DD/MM/YYYY"
                                    ),
                                    "Jour": st.column_config.TextColumn("Jour")
                                }
                                for cat_col in cost_view_cols_rename.values():
                                    if cat_col not in ["Date", "Jour"]:
                                        daily_cost_config[cat_col] = st.column_config.NumberColumn(
                                            f"{cat_col} (CHF)", format="%,.0f"
                                        )

                                st.dataframe(
                                    df_daily_costs_view, column_config=daily_cost_config,
                                    hide_index=True, use_container_width=True
                                )

                            with tab_daily_hour:
                                cols_to_show_hour = ['Date', 'Jour_Semaine'] + hour_cols + \
                                                   ['Heures_Total_Jour']
                                df_daily_hours_view = df_daily_detail[cols_to_show_hour].copy()
                                hour_view_cols_rename = {
                                    c: c.replace('Heures_', '') for c in hour_cols
                                }
                                hour_view_cols_rename['Heures_Total_Jour'] = 'Total'
                                hour_view_cols_rename['Jour_Semaine'] = 'Jour'
                                df_daily_hours_view = df_daily_hours_view.rename(
                                    columns=hour_view_cols_rename
                                )

                                numeric_hour_cols_daily = list(hour_view_cols_rename.values())
                                if 'Date' in numeric_hour_cols_daily:
                                    numeric_hour_cols_daily.remove('Date')
                                if 'Jour' in numeric_hour_cols_daily:
                                    numeric_hour_cols_daily.remove('Jour')
                                if numeric_hour_cols_daily:
                                    df_daily_hours_view[numeric_hour_cols_daily] = \
                                        df_daily_hours_view[numeric_hour_cols_daily].apply(
                                            pd.to_numeric, errors='coerce'
                                        ).fillna(0.0).astype(float)

                                daily_hour_config = {
                                    "Date": st.column_config.DateColumn(
                                        "Date", format="DD/MM/YYYY"
                                    ),
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

            if 'adjusted_saisons' not in st.session_state or \
               st.session_state.adjusted_saisons.empty:
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
                            default_idx = personnel_list.index(current_personnel) \
                                         if current_personnel in personnel_list else 0
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
