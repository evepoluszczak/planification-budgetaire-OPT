"""
Page Comparaison Historique - Comparaison PAX historique vs prévisions
"""
import pandas as pd
import streamlit as st
import altair as alt
from config.constants import PAX_DATA_FILE_PATH, FACTU_AT_DIR
from utils.date_utils import find_closest_weekday
from core.data_loader import estimate_at_hours_from_pax_variation


def render_comparaison_historique_page():
    """Affiche la page Comparaison Historique"""
    st.title("Comparaison Historique vs Prévisions Passagers")
    st.markdown("Comparez les volumes de passagers entre une date passée et une date future.")

    # Vérifier les statuts séparés
    hist_loaded = st.session_state.get('pax_historical_status') == "loaded"
    fc_loaded = st.session_state.get('pax_forecast_status') == "loaded"

    if not hist_loaded or not fc_loaded:
        messages = []
        if not hist_loaded:
            messages.append("historiques")
        if not fc_loaded:
            messages.append("prévisionnelles")
        st.warning(
            f"Données passagers {' et '.join(messages)} non disponibles. "
            f"Vérifiez le fichier '{PAX_DATA_FILE_PATH.name}'."
        )
        st.stop()

    # Récupérer les données et les plages de dates spécifiques
    hist_data = st.session_state.pax_historical_data
    hist_min = st.session_state.pax_historical_min_date
    hist_max = st.session_state.pax_historical_max_date

    fc_data = st.session_state.pax_forecast_data
    fc_min = st.session_state.pax_forecast_min_date
    fc_max = st.session_state.pax_forecast_max_date

    # Calcul de la date historique par défaut
    default_forecast_date = fc_min
    default_historical_date = hist_max

    try:
        # Date cible approximative (même jour/mois, année N-1)
        target_hist_date_approx = default_forecast_date.replace(
            year=default_forecast_date.year - 1
        )

        # Jour de la semaine de la date prévisionnelle
        target_weekday = default_forecast_date.weekday()

        # Trouver la date N-1 la plus proche ayant le même jour de la semaine
        calculated_hist_date = find_closest_weekday(target_hist_date_approx, target_weekday)

        # Vérifier si cette date est dans la plage historique disponible
        if hist_min <= calculated_hist_date <= hist_max:
            default_historical_date = calculated_hist_date
        else:
            st.caption(
                f"Note: La date historique correspondante "
                f"({calculated_hist_date.strftime('%d.%m.%Y')}) est hors plage disponible "
                f"({hist_min.strftime('%d.%m.%Y')} - {hist_max.strftime('%d.%m.%Y')}). "
                f"Utilisation de la date la plus récente ({hist_max.strftime('%d.%m.%Y')})."
            )
            default_historical_date = hist_max

    except Exception as e:
        st.warning(
            f"Erreur lors du calcul de la date historique par défaut: {e}. "
            f"Utilisation de {hist_max.strftime('%d.%m.%Y')}."
        )
        default_historical_date = hist_max

    # Sélecteurs de date
    col1, col2 = st.columns(2)
    with col1:
        historical_date = st.date_input(
            "Choisir la date historique de référence", value=default_historical_date,
            min_value=hist_min, max_value=hist_max, key="hist_date_compare"
        )
    with col2:
        forecast_date = st.date_input(
            "Choisir la date prévisionnelle à comparer", value=default_forecast_date,
            min_value=fc_min, max_value=fc_max, key="fc_date_compare"
        )

    pax_filter_compare = st.radio(
        "Filtrer le flux :", ('Tous', 'Arrivée', 'Départ'),
        horizontal=True, key="pax_flow_filter_compare"
    )

    if historical_date and forecast_date:

        def get_filtered_daily_pax(data, selected_date, pax_filter):
            """Filtre les données PAX pour une date et un flux donnés"""
            df_day_raw = data[data.index.date == selected_date].copy()
            if df_day_raw.empty:
                return pd.DataFrame(columns=['Pax Schengen', 'Pax Non-Schengen', 'Pax Total'])

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
            return df_day

        hist_day_pax = get_filtered_daily_pax(hist_data, historical_date, pax_filter_compare)
        fc_day_pax = get_filtered_daily_pax(fc_data, forecast_date, pax_filter_compare)

        hist_total = hist_day_pax['Pax Total'].sum()
        fc_total = fc_day_pax['Pax Total'].sum()
        delta_total = fc_total - hist_total
        delta_pct = (delta_total / hist_total * 100) if hist_total != 0 else 0.0

        st.markdown("---")
        st.subheader(f"Comparaison Passagers ({pax_filter_compare})")

        col_kpi1, col_kpi2, col_kpi3 = st.columns(3)
        with col_kpi1:
            st.metric(
                f"Historique ({historical_date.strftime('%d.%m')})",
                f"{hist_total:,.0f}"
            )
        with col_kpi2:
            st.metric(
                f"Prévisions ({forecast_date.strftime('%d.%m')})",
                f"{fc_total:,.0f}"
            )
        with col_kpi3:
            delta_sign = "+" if delta_total >= 0 else ""
            delta_pct_str = f"{delta_pct:+.1f}%" if abs(delta_pct) < 1e10 else "N/A"
            st.metric("Delta vs Historique", f"{delta_sign}{delta_total:,.0f}", f"{delta_pct_str}")

        # AT à partir des fichiers facturation
        st.markdown("---")
        st.subheader("AT – Heures facturées (historique) & estimation (variation PAX)")

        try:
            res = estimate_at_hours_from_pax_variation(
                historical_date, forecast_date, FACTU_AT_DIR
            )

            c1, c2, c3, c4 = st.columns(4)
            with c1:
                st.metric("AT facturé (jour hist.)", f"{res['heures_hist']:.1f} h")
            with c2:
                fact_txt = "N/A" if res["facteur"] is None else f"{res['facteur']:.2f}×"
                st.metric("Facteur PAX (fc/hist)", fact_txt)
            with c3:
                st.metric("AT estimé (jour fc)", f"{res['heures_estimees']:.1f} h")
            with c4:
                st.caption(f"PAX hist: {res['pax_hist']:.0f} | PAX fc: {res['pax_fc']:.0f}")

            st.info("Règle : AT_est = AT_hist × (PAX_forecast / PAX_hist). Arrondi au pas de 0,5 h.")
        except Exception as e:
            st.warning(f"Calcul AT indisponible : {e}")

        # Graphique comparatif
        hist_day_pax['Type'] = 'Historique'
        fc_day_pax['Type'] = 'Prévisions'

        combined_pax = pd.concat([
            hist_day_pax[['Pax Schengen', 'Pax Non-Schengen', 'Type']],
            fc_day_pax[['Pax Schengen', 'Pax Non-Schengen', 'Type']]
        ], sort=True).fillna(0)
        combined_pax['Heure'] = combined_pax.index.strftime('%H:%M')

        pax_long = combined_pax.melt(
            id_vars=['Heure', 'Type'],
            value_vars=['Pax Schengen', 'Pax Non-Schengen'],
            var_name='Zone', value_name='Passagers'
        )

        # --- Graphique Altair comparatif avec couleurs différenciées ---
        # Historique : gris clair/foncé ; Prévisions : couleurs brand
        gray_scale = alt.Scale(
            domain=['Pax Schengen', 'Pax Non-Schengen'],
            range=['#E0E0E0', '#A0A0A0']  # gris clair / gris foncé
        )
        brand_scale = alt.Scale(
            domain=['Pax Schengen', 'Pax Non-Schengen'],
            range=['#2E86C1', '#17A589']  # adapte à ta charte si besoin
        )
        
        # Fusion Historique / Prévisions
        pax_long['Zone_Type'] = pax_long['Zone'] + ' (' + pax_long['Type'] + ')'
        
        # Palette personnalisée : gris pour Historique, bleu/vert pour Prévisions
        custom_scale = alt.Scale(
            domain=[
                'Pax Schengen (Historique)',
                'Pax Non-Schengen (Historique)',
                'Pax Schengen (Prévisions)',
                'Pax Non-Schengen (Prévisions)'
            ],
            range=['#E0E0E0', '#A0A0A0', '#2E86C1', '#17A589']
        )
        
        chart_compare = (
            alt.Chart(pax_long)
            .mark_bar()
            .encode(
                x=alt.X('Heure:O', sort=None, title=''),
                y=alt.Y('Passagers:Q', title=f'Passagers ({pax_filter_compare})'),
                xOffset='Type:N',
                color=alt.Color(
                    
                    'Zone_Type:N',
                    title='',
                    scale=custom_scale,
                    legend=alt.Legend(
                        orient='bottom',          # Légende sous le graphe
                        direction='horizontal',   # Alignée horizontalement
                        anchor='middle',          # Centrée sous le graphique
                        titleAnchor='middle',     # Centre le titre aussi
                        titleAlign='center',
                        labelFontSize=11,
                        symbolSize=120,
                        padding=10
                    )
                ),
                tooltip=['Heure', 'Type', 'Zone', 'Passagers']
            )
            .properties(height=400)
            .interactive()
        )
        
        st.altair_chart(chart_compare, use_container_width=True)


    else:
        st.info("Veuillez sélectionner une date historique et une date prévisionnelle.")
