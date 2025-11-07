"""
Page Besoin Jour - Ajustements ponctuels
"""
import datetime as dt
from datetime import timedelta
import pandas as pd
import streamlit as st
import altair as alt
from config.constants import RULES_BESOIN_JOUR_PATH, PAX_DATA_FILE_PATH, TIME_SLOTS
from core.planning import _ensure_grid, _apply_ops_to_grid
from core.rules import save_rules_to_json
from utils.date_utils import _day_name_fr, _date_to_str
from ui.components import _render_grid_for_edit


def render_besoin_jour_page():
    """Affiche la page Besoin Jour"""
    st.title("Ajustement du Besoin Journalier")
    st.markdown(
        "Appliquez des modifications temporaires (ex: événements) "
        "sans altérer vos jours-types de base."
    )

    bs = st.session_state.get('budget_state', {})
    if not bs or 'year' not in bs or 'calendar_df' not in bs or bs['calendar_df'].empty:
        st.warning(
            "⚠️ Aucun budget annuel valide en mémoire. "
            "Veuillez d'abord en générer un via la page **Budget Annuel**."
        )
        st.stop()

    year = bs['year']

    # Sélection de la catégorie
    with st.container(border=True):
        st.subheader("Catégorie de Personnel")
        available_categories = list(st.session_state.get('perimetres', {}).keys())
        if not available_categories:
            st.error("Aucune catégorie de personnel définie dans la Configuration.")
            st.stop()

        selected_category = st.selectbox(
            "Sélectionnez la catégorie à ajuster",
            options=available_categories,
            index=0 if 'AT' not in available_categories else available_categories.index('AT'),
            key="besoin_jour_category_select",
            help="Choisissez la catégorie de personnel pour laquelle vous souhaitez définir des ajustements journaliers."
        )

    def assign_season(d: dt.date) -> str:
        """Assigne la saison pour une date donnée"""
        if 'adjusted_saisons' not in st.session_state or \
           st.session_state.adjusted_saisons.empty:
            return "Standard"
        try:
            for _, r in st.session_state.adjusted_saisons.iterrows():
                start_date = pd.to_datetime(r['Date Début']).date()
                end_date = pd.to_datetime(r['Date Fin']).date()
                if start_date <= d <= end_date:
                    return r['Saison']
            return "Standard"
        except Exception as e:
            st.error(f"Erreur dans assign_season : {e}")
            return "Standard"

    # Impact Annuel Recalculé
    with st.container(border=True):
        st.subheader("Impact Annuel Recalculé")

        # Calculer un hash des règles pour détecter les changements
        import hashlib
        import json
        rules_hash = hashlib.md5(json.dumps(st.session_state.besoin_jour_ops, sort_keys=True, default=str).encode()).hexdigest()

        # Vérifier si le cache est valide
        cache_valid = (
            'besoin_jour_impact_cache' in st.session_state and
            st.session_state.get('besoin_jour_rules_hash') == rules_hash and
            st.session_state.get('besoin_jour_cache_year') == year
        )

        if cache_valid:
            # Utiliser le cache
            cached_data = st.session_state.besoin_jour_impact_cache
            cur_hours_recalc = cached_data['cur_hours_recalc']
            cur_cost_recalc = cached_data['cur_cost_recalc']
            base_hours = cached_data['base_hours']
            base_cost = cached_data['base_cost']
        else:
            # Recalculer
            with st.spinner("Recalcul du budget annuel avec tous les ajustements..."):
                try:
                    calendar_dyn = bs['calendar_df'].copy()
                    time_slots_default = TIME_SLOTS

                    # Récupérer toutes les catégories définies
                    all_categories = list(st.session_state.get('perimetres', {}).keys())

                    # Dictionnaire pour stocker les tarifs horaires par catégorie
                    tarifs = {}
                    for category in all_categories:
                        tarif = 0.0
                        personnel_type = st.session_state.get('cost_mapping', {}).get(category)
                        if personnel_type:
                            personnel_df = st.session_state.get('personnel', pd.DataFrame())
                            if not personnel_df.empty:
                                row_tarif = personnel_df[personnel_df['Type'] == personnel_type]
                                if not row_tarif.empty:
                                    try:
                                        tarif = float(row_tarif['Coût Horaire'].iloc[0])
                                    except Exception:
                                        pass
                        tarifs[category] = tarif

                    # Recalculer pour chaque catégorie
                    for category in all_categories:
                        heures_vals_recalc = []
                        costs_vals_recalc = []

                        perimetres_cat = st.session_state.perimetres.get(category, [])
                        planning_dict_cat = st.session_state.planning_data.get(category, {})
                        tarif_cat = tarifs.get(category, 0.0)

                        for _, r in calendar_dyn.iterrows():
                            jour, saison, date_ = r['Jour'], r['Saison'], r['Date'].date()
                            jtg = r['Jour_Type_Global']

                            # Pour catégories non-AT, utiliser "Default" comme jour-type
                            jt_key = jtg if category == 'AT' else 'Default'

                            _, base_df_cat = _ensure_grid(
                                planning_dict_cat, jt_key, perimetres_cat, time_slots_default
                            )
                            eff_df_cat = _apply_ops_to_grid(
                                base_df_cat, date_, jour, saison, category=category
                            )
                            day_hours = eff_df_cat.values.sum() * 0.5
                            heures_vals_recalc.append(day_hours)
                            costs_vals_recalc.append(day_hours * tarif_cat)

                        calendar_dyn[f"Heures_{category}"] = heures_vals_recalc
                        calendar_dyn[f"Coût_{category}"] = costs_vals_recalc

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

                    cur_hours_recalc_planif = calendar_dyn['Heures_Total_Jour'].sum()
                    cur_cost_recalc_planif = calendar_dyn['Coût_Total_Jour'].sum()

                    # Calculer les totaux de base (planification uniquement)
                    base_totals = bs.get('totals', {})
                    base_hours_planif = float(base_totals.get('heures_annuel', 0.0))
                    base_cost_planif = float(base_totals.get('cout_annuel', 0.0))

                    # Calculer les heures/coûts de formation (même logique que Budget Annuel)
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
                        df_formation['Effectif (pers.)'] = pd.to_numeric(df_formation.get('Effectif (pers.)', 0), errors='coerce').fillna(0).astype(int).clip(lower=0)
                        df_formation['Heures'] = df_formation.get('Heures', 0).apply(lambda x: float(str(x).replace(',', '.')) if pd.notna(x) else 0.0).clip(lower=0)
                        df_formation['Nbre de shifts'] = pd.to_numeric(df_formation.get('Nbre de shifts', 0), errors='coerce').fillna(0).astype(int).clip(lower=0)
                        df_formation['Total (heures)'] = (
                            df_formation['Effectif (pers.)'] *
                            df_formation['Heures'] *
                            df_formation['Nbre de shifts']
                        )
                        total_heures_formation = df_formation['Total (heures)'].sum()
                        total_cout_formation = total_heures_formation * cout_horaire_at

                    # Calculer les heures/coûts des formateurs (ATF)
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
                        df_formateurs['Effectif (pers.)'] = pd.to_numeric(df_formateurs.get('Effectif (pers.)', 0), errors='coerce').fillna(0).astype(int).clip(lower=0)
                        df_formateurs['Heures'] = df_formateurs.get('Heures', 0).apply(lambda x: float(str(x).replace(',', '.')) if pd.notna(x) else 0.0).clip(lower=0)
                        df_formateurs['Nbre de shifts'] = pd.to_numeric(df_formateurs.get('Nbre de shifts', 0), errors='coerce').fillna(0).astype(int).clip(lower=0)
                        df_formateurs['Total (heures)'] = (
                            df_formateurs['Effectif (pers.)'] *
                            df_formateurs['Heures'] *
                            df_formateurs['Nbre de shifts']
                        )
                        total_heures_formateurs = df_formateurs['Total (heures)'].sum()
                        total_cout_formateurs = total_heures_formateurs * cout_horaire_atf

                    # Totaux globaux avec formation (référence Budget Annuel)
                    base_hours = base_hours_planif + total_heures_formation + total_heures_formateurs
                    base_cost = base_cost_planif + total_cout_formation + total_cout_formateurs

                    # Ajouter formation et formateurs aux valeurs recalculées pour comparaison correcte
                    cur_hours_recalc = cur_hours_recalc_planif + total_heures_formation + total_heures_formateurs
                    cur_cost_recalc = cur_cost_recalc_planif + total_cout_formation + total_cout_formateurs

                    # Sauvegarder dans le cache
                    st.session_state.besoin_jour_impact_cache = {
                        'cur_hours_recalc': cur_hours_recalc,
                        'cur_cost_recalc': cur_cost_recalc,
                        'base_hours': base_hours,
                        'base_cost': base_cost
                    }
                    st.session_state.besoin_jour_rules_hash = rules_hash
                    st.session_state.besoin_jour_cache_year = year

                except Exception as e:
                    st.error(f"Erreur lors du recalcul de l'impact annuel: {e}")
                    cur_hours_recalc = 0.0
                    cur_cost_recalc = 0.0
                    base_hours = 0.0
                    base_cost = 0.0

        # Afficher les résultats (que ce soit depuis le cache ou recalculé)
        if cache_valid:
            st.caption("✓ Résultats depuis le cache (aucune règle modifiée)")
        else:
            st.caption("🔄 Recalcul effectué (nouvelles règles détectées)")

        def _delta_str(cur, base, unit):
            if base == 0:
                pct_str = "N/A" if cur == 0 else "+Inf%"
                diff = cur
            else:
                diff = cur - base
                pct = (diff / base) * 100.0
                pct_str = f"{pct:+.1f}%"
            sign = "+" if diff >= 0 else ""
            return f"{sign}{diff:,.0f} {unit} ({pct_str})"

        st.markdown(
            f"""<div class="kpi-cards">
            <div class="kpi-card kpi-blue">
                <div class="label">Nouveau Total Heures Annuel</div>
                <div class="value">{cur_hours_recalc:,.0f} h</div>
                <div class="delta">{_delta_str(cur_hours_recalc, base_hours, "h")} vs Budget</div>
            </div>
            <div class="kpi-card kpi-amber">
                <div class="label">Nouveau Coût Annuel</div>
                <div class="value">{cur_cost_recalc:,.0f} CHF</div>
                <div class="delta">{_delta_str(cur_cost_recalc, base_cost, "CHF")} vs Budget</div>
            </div>
            </div>""",
            unsafe_allow_html=True
        )

    # Périmètre de l'Ajustement
    with st.container(border=True):
        st.subheader("Périmètre de l'Ajustement")
        mode = st.radio(
            "Portée", ["Date unique", "Plage de dates"],
            index=1, horizontal=True, key="bj_mode_select"
        )
        min_d = dt.date(year, 1, 1)
        max_d = dt.date(year, 12, 31)
        default_start = bs.get('selected_date', min_d)
        if not (min_d <= default_start <= max_d):
            default_start = min_d
        default_end = min(default_start + timedelta(days=6), max_d)

        date_range_selected = []
        if mode == "Date unique":
            picked_date = st.date_input(
                "Date cible", value=default_start,
                min_value=min_d, max_value=max_d, key="bj_single_date"
            )
            date_range_selected = [picked_date] if picked_date else []
        else:
            date_range_output = st.date_input(
                "Plage de dates cible", value=(default_start, default_end),
                min_value=min_d, max_value=max_d, key="bj_date_range"
            )
            if isinstance(date_range_output, (tuple, list)) and len(date_range_output) == 2:
                start_d, end_d = date_range_output
                if start_d and end_d:
                    if start_d > end_d:
                        start_d, end_d = end_d, start_d
                    date_range_selected = pd.date_range(
                        start=start_d, end=end_d, freq='D'
                    ).date.tolist()
                else:
                    date_range_selected = []
            else:
                st.warning("Sélection de plage invalide. Réinitialisation.")
                start_d, end_d = default_start, default_end
                date_range_selected = pd.date_range(
                    start=start_d, end=end_d, freq='D'
                ).date.tolist()

        date_range_final = []
        jt_set = []
        jours_filter = []
        saisons_filter = []

        if date_range_selected:
            try:
                temp_df = pd.DataFrame({'Date': pd.to_datetime(date_range_selected)})
                temp_df['Jour'] = _day_name_fr(temp_df['Date'])
                temp_df['Saison'] = temp_df['Date'].apply(lambda dt: assign_season(dt.date()))
                WEEK_ORDER = ["Lundi", "Mardi", "Mercredi", "Jeudi", "Vendredi",
                             "Samedi", "Dimanche"]
                jours_present = temp_df['Jour'].unique().tolist()
                jours_in_range = [j for j in WEEK_ORDER if j in jours_present]
                saisons_in_range = sorted(temp_df['Saison'].unique().tolist())

                col_f1, col_f2 = st.columns(2)
                with col_f1:
                    jours_filter = st.multiselect(
                        "Filtrer par Jours (optionnel)", options=jours_in_range,
                        default=[], key="bj_jours_filter"
                    )
                with col_f2:
                    saisons_filter = st.multiselect(
                        "Filtrer par Saisons (optionnel)", options=saisons_in_range,
                        default=[], key="bj_saisons_filter"
                    )

                filtered_dates_df = temp_df[
                    temp_df['Jour'].isin(jours_filter if jours_filter else jours_in_range) &
                    temp_df['Saison'].isin(saisons_filter if saisons_filter else saisons_in_range)
                ]
                date_range_final = filtered_dates_df['Date'].dt.date.tolist()
                jt_set = sorted(filtered_dates_df.apply(
                    lambda row: f"{row['Jour']} {row['Saison']}", axis=1
                ).unique().tolist())

                st.caption(
                    f"{len(date_range_final)} jour(s) sélectionné(s) correspondant aux filtres. "
                    f"Jour-types (AT) impactés: {', '.join(jt_set) if jt_set else 'Aucun'}"
                )
            except Exception as e:
                st.error(f"Erreur lors de l'application des filtres: {e}")
                date_range_final = []
                jt_set = []
        else:
            st.warning("Veuillez sélectionner une date ou une plage valide.")

    # Tabs Besoin
    tabs_besoin = st.tabs([
        "Vue & Analyse (Après Règles)",
        f"Gérer les Règles d'Ajustement ({selected_category})"
    ])

    with tabs_besoin[0]:
        if not date_range_final:
            st.info(
                "Sélectionnez une date ou une plage valide et appliquez des filtres "
                "pour voir l'aperçu et l'impact."
            )
        else:
            with st.container(border=True):
                st.subheader(f"Aperçu de la Grille {selected_category} (lecture seule)")
                preview_date = date_range_final[0]
                if len(date_range_final) > 1:
                    preview_date = st.selectbox(
                        "Choisir une date pour l'aperçu", options=date_range_final,
                        format_func=lambda d: f"{_day_name_fr(pd.Series([pd.to_datetime(d)])).iloc[0]} {d.strftime('%d.%m.%Y')}",
                        key="bj_preview_date_selector"
                    )

                preview_jour = _day_name_fr(pd.Series(pd.to_datetime([preview_date]))).iloc[0]
                preview_saison = assign_season(preview_date)
                preview_jt = f"{preview_jour} {preview_saison}"

                perimetres_cat = st.session_state.perimetres.get(selected_category, [])
                time_slots_default = TIME_SLOTS
                planning_dict_cat = st.session_state.planning_data.get(selected_category, {})

                # Pour les catégories non-AT, utiliser "Default" comme jour-type
                jt_key = preview_jt if selected_category == 'AT' else 'Default'

                _, base_df = _ensure_grid(
                    planning_dict_cat, jt_key, perimetres_cat, time_slots_default
                )
                eff_df = _apply_ops_to_grid(
                    base_df, preview_date, preview_jour, preview_saison, category=selected_category
                )

                view_choice = st.radio(
                    "Afficher grille:", ("Après règles (effective)", "Base (avant règles)"),
                    horizontal=True, key="bj_grid_view_toggle"
                )
                grid_to_show = eff_df if view_choice.startswith("Après") else base_df

                def highlight_zero_rows(row):
                    is_zero = (row == 0).all()
                    return ['background-color: #f0f0f0'] * len(row) if is_zero else [''] * len(row)

                styled_grid = grid_to_show.style.apply(highlight_zero_rows, axis=1)
                st.dataframe(
                    styled_grid, use_container_width=True,
                    height=(len(grid_to_show.index) + 1) * 35 + 3
                )

                day_total_hours = grid_to_show.values.sum() * 0.5
                tarif_cat_day = 0.0
                personnel_type_cat_day = st.session_state.get('cost_mapping', {}).get(selected_category)
                if personnel_type_cat_day:
                    personnel_df_day = st.session_state.get('personnel', pd.DataFrame())
                    if not personnel_df_day.empty:
                        row_tarif_day = personnel_df_day[
                            personnel_df_day['Type'] == personnel_type_cat_day
                        ]
                        if not row_tarif_day.empty:
                            try:
                                tarif_cat_day = float(row_tarif_day['Coût Horaire'].iloc[0])
                            except (ValueError, TypeError):
                                tarif_cat_day = 0.0

                day_total_cost = day_total_hours * tarif_cat_day
                st.caption(
                    f"**Total pour le {preview_date.strftime('%d.%m.%Y')} ({view_choice}):** "
                    f"{day_total_hours:,.1f} h / {day_total_cost:,.0f} CHF"
                )

                # Bloc PAX (uniquement pour AT)
                if selected_category == 'AT':
                    st.divider()
                    st.subheader(f"Prévisions Passagers - {preview_date.strftime('%d.%m.%Y')}")

                    if 'pax_forecast_data' in st.session_state and \
                       not st.session_state.pax_forecast_data.empty:
                        pax_agg_full = st.session_state.pax_forecast_data

                        pax_filter = st.radio(
                            "Filtrer le flux de passagers :", ('Tous', 'Arrivée', 'Départ'),
                            horizontal=True, key="pax_flow_filter"
                        )

                        df_day_raw = pax_agg_full[pax_agg_full.index.date == preview_date].copy()

                        if not df_day_raw.empty:
                            df_day = pd.DataFrame(index=df_day_raw.index)
                            if pax_filter == 'Tous':
                                df_day['Pax Schengen'] = df_day_raw['Pax_Schengen_A'] + \
                                                         df_day_raw['Pax_Schengen_D']
                                df_day['Pax Non-Schengen'] = df_day_raw['Pax_NonSchengen_A'] + \
                                                              df_day_raw['Pax_NonSchengen_D']
                            elif pax_filter == 'Arrivée':
                                df_day['Pax Schengen'] = df_day_raw['Pax_Schengen_A']
                                df_day['Pax Non-Schengen'] = df_day_raw['Pax_NonSchengen_A']
                            elif pax_filter == 'Départ':
                                df_day['Pax Schengen'] = df_day_raw['Pax_Schengen_D']
                                df_day['Pax Non-Schengen'] = df_day_raw['Pax_NonSchengen_D']

                            df_day['Pax Total'] = df_day['Pax Schengen'] + df_day['Pax Non-Schengen']

                            total_pax_jour = df_day['Pax Total'].sum()
                            total_schengen = df_day['Pax Schengen'].sum()
                            total_non_schengen = df_day['Pax Non-Schengen'].sum()

                            st.markdown(
                                f"""<div class="kpi-cards">
                                <div class="kpi-card kpi-blue">
                                    <div class="label">Total Passagers ({pax_filter})</div>
                                    <div class="value">{total_pax_jour:,.0f}</div>
                                </div>
                                <div class="kpi-card kpi-green">
                                    <div class="label">Total Schengen ({pax_filter})</div>
                                    <div class="value">{total_schengen:,.0f}</div>
                                </div>
                                <div class="kpi-card kpi-amber">
                                    <div class="label">Total Non-Schengen ({pax_filter})</div>
                                    <div class="value">{total_non_schengen:,.0f}</div>
                                </div>
                                </div>""",
                                unsafe_allow_html=True
                            )
                            st.markdown("---")

                            if total_pax_jour > 0:
                                df_day['Heure'] = df_day.index.strftime('%H:%M')
                                df_chart_to_melt = df_day[['Heure', 'Pax Schengen', 'Pax Non-Schengen']]
                                df_chart_long = df_chart_to_melt.melt(
                                    'Heure', var_name='Zone', value_name='Passagers'
                                )

                                chart = alt.Chart(df_chart_long).mark_bar().encode(
                                    x=alt.X('Heure:O', sort=None, title='Heure'),
                                    y=alt.Y('Passagers:Q', title=f'Nombre de Passagers ({pax_filter})'),
                                    color=alt.Color('Zone:N', title='Zone'),
                                    xOffset=alt.XOffset('Zone:N', title='Zone'),
                                    tooltip=['Heure', 'Zone', 'Passagers']
                                ).properties().interactive()

                                st.altair_chart(chart, use_container_width=True)
                            else:
                                st.info(
                                    f"Aucune prévision passager ({pax_filter}) trouvée pour "
                                    f"le {preview_date.strftime('%d.%m.%Y')}."
                                )
                        else:
                            st.info(
                                f"Aucune prévision passager trouvée dans le fichier pour "
                                f"le {preview_date.strftime('%d.%m.%Y')}."
                            )
                    else:
                        st.info(
                            f"Données prévisionnelles non chargées ou non trouvées dans "
                            f"'{PAX_DATA_FILE_PATH.name}'."
                        )

    # Tab Gestion des Règles
    with tabs_besoin[1]:
        with st.container(border=True):
            st.subheader(f"Définir une Nouvelle Règle ({selected_category})")
            if not date_range_final:
                st.warning("Veuillez d'abord sélectionner une plage de dates et des filtres valides.")
            elif selected_category == 'AT' and not jt_set:
                st.info("La sélection de dates/filtres actuelle n'impacte aucun jour-type AT connu.")
            else:
                perimetres_cat = st.session_state.perimetres.get(selected_category, [])
                if not perimetres_cat:
                    st.error(f"Aucun périmètre défini pour {selected_category} dans la Configuration.")
                else:
                    time_slots_default = TIME_SLOTS

                    with st.form(key="add_rule_form"):
                        st.caption(
                            f"Cette règle s'appliquera aux {len(date_range_final)} jours "
                            f"sélectionnés via les filtres actifs."
                        )
                        c1, c2, c3 = st.columns([0.5, 0.3, 0.2])
                        with c1:
                            rows_sel = st.multiselect(
                                f"Périmètre(s) {selected_category} à modifier", options=perimetres_cat,
                                key="rule_rows_sel"
                            )
                        with c2:
                            start_col, end_col = st.select_slider(
                                "Plage horaire à modifier", options=time_slots_default,
                                value=(time_slots_default[0], time_slots_default[-1]),
                                key="rule_range_cols"
                            )
                        with c3:
                            val_set = st.radio(
                                "Valeur", [1, 0], index=0, key="rule_value", horizontal=True
                            )

                        submitted = st.form_submit_button("Ajouter la Règle")
                        if submitted:
                            if not rows_sel:
                                st.error("Sélectionnez au moins un périmètre.")
                            elif not date_range_final:
                                st.error("La plage de dates filtrée est vide.")
                            else:
                                new_rule = {
                                    'category': selected_category,
                                    'start': min(date_range_final),
                                    'end': max(date_range_final),
                                    'jours': jours_filter.copy(),
                                    'saisons': saisons_filter.copy(),
                                    'rows': rows_sel,
                                    'start_col': start_col,
                                    'end_col': end_col,
                                    'value': int(val_set)
                                }
                                st.session_state.besoin_jour_ops.append(new_rule)
                                save_rules_to_json(
                                    st.session_state.besoin_jour_ops, RULES_BESOIN_JOUR_PATH
                                )
                                st.success(
                                    f"Règle {selected_category} ajoutée. Elle affectera les jours correspondants "
                                    f"aux filtres dans la plage {min(date_range_final)} - "
                                    f"{max(date_range_final)}."
                                )
                                st.rerun()

        # Affichage des règles enregistrées
        with st.container(border=True):
            st.subheader(f"Règles Enregistrées ({selected_category})")
            all_ops_with_indices = list(enumerate(st.session_state.besoin_jour_ops))
            ops_cat_with_indices = [(i, op) for i, op in all_ops_with_indices
                                    if op.get('category') == selected_category]

            if not ops_cat_with_indices:
                st.info(f"Aucune règle d'ajustement définie pour la catégorie {selected_category}.")
            else:
                if st.button(f"Supprimer Toutes les Règles {selected_category}", type="secondary",
                           key=f"delete_all_{selected_category}_rules"):
                    st.session_state.besoin_jour_ops = [
                        op for op in st.session_state.besoin_jour_ops
                        if op.get('category') != selected_category
                    ]
                    save_rules_to_json(
                        st.session_state.besoin_jour_ops, RULES_BESOIN_JOUR_PATH
                    )
                    st.success(f"Toutes les règles {selected_category} ont été supprimées.")
                    st.rerun()
                st.divider()

                indices_to_delete = []
                for original_index, op in ops_cat_with_indices:
                    col1, col2 = st.columns([0.9, 0.1])
                    with col1:
                        jours_str = ", ".join(op.get('jours', [])) or 'Tous'
                        saisons_str = ", ".join(op.get('saisons', [])) or 'Toutes'
                        rows_str = ", ".join(op.get('rows', []))
                        start_str = _date_to_str(op.get('start', 'N/A'))
                        end_str = _date_to_str(op.get('end', 'N/A'))
                        rule_color = '#28a745' if op.get('value', 0) == 1 else '#dc3545'
                        st.markdown(
                            f"""
                            <div class="rule-card" style="--rule-color:{rule_color};">
                                <p><strong>Période:</strong> {start_str} au {end_str}</p>
                                <p><strong>Filtres:</strong> Jours: [{jours_str}] / Saisons: [{saisons_str}]</p>
                                <p><strong>Action:</strong> Mettre à <strong>{op.get('value', 'N/A')}</strong> de {op.get('start_col', 'N/A')} à {op.get('end_col', 'N/A')} pour : <i>{rows_str}</i></p>
                            </div>
                            """,
                            unsafe_allow_html=True
                        )
                    with col2:
                        if st.button("❌", key=f"del_rule_{original_index}",
                                   help="Supprimer cette règle", use_container_width=True):
                            indices_to_delete.append(original_index)

                if indices_to_delete:
                    indices_to_delete.sort(reverse=True)
                    deleted_count = 0
                    try:
                        for index_to_del in indices_to_delete:
                            if 0 <= index_to_del < len(st.session_state.besoin_jour_ops):
                                if st.session_state.besoin_jour_ops[index_to_del].get('category') == selected_category:
                                    st.session_state.besoin_jour_ops.pop(index_to_del)
                                    deleted_count += 1
                                else:
                                    st.warning(f"Tentative de suppression d'une règle d'une autre catégorie. Ignoré.")
                            else:
                                st.error(f"Erreur: Index {index_to_del} hors limites.")
                        if deleted_count > 0:
                            save_rules_to_json(
                                st.session_state.besoin_jour_ops, RULES_BESOIN_JOUR_PATH
                            )
                            st.success(f"{deleted_count} règle(s) supprimée(s).")
                            st.rerun()
                    except Exception as e:
                        st.error(f"Erreur inattendue lors de la suppression: {e}")
