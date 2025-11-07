"""
Logique métier pour la génération du budget annuel
"""
import datetime as dt
from datetime import timedelta
import pandas as pd
import streamlit as st
from utils.helpers import sync_all_planning_grids_from_widgets
from utils.date_utils import find_closest_weekday, _day_name_fr
from core.planning import _ensure_grid


def _ensure_adjusted_saisons_for_year(year: int):
    """
    S'assure que les saisons ajustées pour l'année cible existent.
    Calcule automatiquement à partir des saisons de référence.
    """
    ref = st.session_state.get('saisons', pd.DataFrame())
    if ref.empty or 'Date Début' not in ref.columns or 'Date Fin' not in ref.columns:
        st.warning("Saisons de référence non définies ou invalides.")
        st.session_state.adjusted_saisons = pd.DataFrame(
            columns=['Saison', 'Date Début', 'Date Fin']
        )
        st.session_state.adjusted_saisons_year = year
        return

    # Vérifier si déjà calculé pour cette année
    if 'adjusted_saisons' in st.session_state and \
       isinstance(st.session_state.adjusted_saisons, pd.DataFrame) and \
       not st.session_state.adjusted_saisons.empty and \
       st.session_state.get('adjusted_saisons_year') == year:
        return  # Déjà calculé

    adjusted_data = []
    has_error = False

    for _, row in ref.iterrows():
        try:
            start_ref_date = pd.to_datetime(row['Date Début']).date()
            end_ref_date = pd.to_datetime(row['Date Fin']).date()
            target_start = start_ref_date.replace(year=year)
            target_end = end_ref_date.replace(year=year)
            new_start_date = find_closest_weekday(target_start, start_ref_date.weekday())
            new_end_date = find_closest_weekday(target_end, end_ref_date.weekday())
            adjusted_data.append({
                'Saison': row['Saison'],
                'Date Début': new_start_date,
                'Date Fin': new_end_date
            })
        except Exception as e:
            st.error(f"Erreur ajustement saison '{row.get('Saison', 'Inconnue')}': {e}")
            has_error = True
            break

    if has_error:
        st.session_state.adjusted_saisons = pd.DataFrame(
            columns=['Saison', 'Date Début', 'Date Fin']
        )
        st.session_state.adjusted_saisons_year = year
        return

    if adjusted_data:
        try:
            # Assurer que l'année commence le 1er janvier et finit le 31 décembre
            adjusted_data[0]['Date Début'] = dt.date(year, 1, 1)
            adjusted_data[-1]['Date Fin'] = dt.date(year, 12, 31)

            # Ajuster les dates pour éviter les chevauchements
            for i in range(len(adjusted_data) - 1):
                adjusted_data[i+1]['Date Début'] = adjusted_data[i]['Date Fin'] + timedelta(days=1)
                if adjusted_data[i+1]['Date Début'] > adjusted_data[i+1]['Date Fin']:
                    st.warning(
                        f"Chevauchement détecté pour {adjusted_data[i+1]['Saison']}. "
                        "Ajustement forcé."
                    )
                    adjusted_data[i+1]['Date Fin'] = adjusted_data[i+1]['Date Début']
        except IndexError:
            st.error("Erreur lors de l'ajustement des dates de début/fin d'année.")
            st.session_state.adjusted_saisons = pd.DataFrame(
                columns=['Saison', 'Date Début', 'Date Fin']
            )
            st.session_state.adjusted_saisons_year = year
            return

    st.session_state.adjusted_saisons = pd.DataFrame(adjusted_data)
    st.session_state.adjusted_saisons_year = year


def generate_budget_state(year: int):
    """
    Génère le budget annuel pour une année donnée.
    Stocke le résultat dans st.session_state.budget_state
    """
    sync_all_planning_grids_from_widgets()

    # Synchroniser l'état du budget
    if 'adjusted_saisons' in st.session_state:
        df = st.session_state.adjusted_saisons
        if isinstance(df, pd.DataFrame) and not df.empty:
            if 'Date Début' in df.columns:
                df['Date Début'] = pd.to_datetime(df['Date Début']).dt.date
            if 'Date Fin' in df.columns:
                df['Date Fin'] = pd.to_datetime(df['Date Fin']).dt.date
            st.session_state.adjusted_saisons = df

    _ensure_adjusted_saisons_for_year(year)

    # Valider les données essentielles
    if 'perimetres' not in st.session_state or not st.session_state.perimetres:
        st.error("Aucun périmètre défini. Vérifiez la configuration.")
        return
    if 'personnel' not in st.session_state or st.session_state.personnel.empty:
        st.error("Aucun type de personnel défini. Vérifiez la configuration.")
        return
    if 'adjusted_saisons' not in st.session_state or st.session_state.adjusted_saisons.empty:
        st.error(f"Calendrier des saisons {year} non généré. Vérifiez les saisons de référence.")
        return

    try:
        days = pd.date_range(start=f"{year}-01-01", end=f"{year}-12-31", freq='D')
        calendar_df = pd.DataFrame({'Date': days})
        calendar_df['Jour'] = _day_name_fr(calendar_df['Date'])

        # Assignation des saisons
        def assign_season(date_):
            d = date_.date()
            for _, r in st.session_state.adjusted_saisons.iterrows():
                start_date = pd.to_datetime(r['Date Début']).date()
                end_date = pd.to_datetime(r['Date Fin']).date()
                if start_date <= d <= end_date:
                    return r['Saison']
            st.warning(f"Date {d} n'appartient à aucune saison. Utilisation de 'Standard'.")
            return "Standard"

        calendar_df['Saison'] = calendar_df['Date'].apply(assign_season)
        calendar_df['Jour_Type_Global'] = calendar_df['Jour'] + " " + calendar_df['Saison']

        # Enrichir avec les événements spéciaux
        from models.event import EventManager
        try:
            def get_event_info(date_):
                """Récupère les informations d'événement pour une date"""
                d = date_.date()
                event = EventManager.get_event(d)
                if event:
                    return pd.Series({
                        'Event_Name': event.name,
                        'Event_Type': event.event_type,
                        'Event_Penalty': event.penalty_factor
                    })
                else:
                    return pd.Series({
                        'Event_Name': None,
                        'Event_Type': None,
                        'Event_Penalty': 0.0
                    })

            event_info = calendar_df['Date'].apply(get_event_info)
            calendar_df['Event_Name'] = event_info['Event_Name']
            calendar_df['Event_Type'] = event_info['Event_Type']
            calendar_df['Event_Penalty'] = event_info['Event_Penalty']
        except Exception as e:
            # Si erreur chargement événements, mettre valeurs par défaut
            calendar_df['Event_Name'] = None
            calendar_df['Event_Type'] = None
            calendar_df['Event_Penalty'] = 0.0

        from config.constants import TIME_SLOTS
        time_slots_default = TIME_SLOTS

        # Calculer heures et coûts par catégorie
        for category_key, perimetres_list in st.session_state.perimetres.items():
            planning_dict = st.session_state.planning_data.get(category_key, {})
            heures_col = f"Heures_{category_key}"
            cout_col = f"Coût_{category_key}"
            calendar_df[heures_col] = 0.0

            if category_key == "AT":
                heures_list = []
                for jtg in calendar_df['Jour_Type_Global']:
                    _, grid_df = _ensure_grid(planning_dict, jtg, perimetres_list, time_slots_default)
                    heures_list.append(grid_df.values.sum() * 0.5)
                calendar_df[heures_col] = heures_list
            else:
                _, default_grid = _ensure_grid(planning_dict, "Default", perimetres_list, time_slots_default)
                daily_hours = default_grid.values.sum() * 0.5
                calendar_df[heures_col] = daily_hours

            # Calculer le coût
            personnel_type = st.session_state.get('cost_mapping', {}).get(category_key)
            calendar_df[cout_col] = 0.0
            if personnel_type:
                tarif_row = st.session_state.personnel[
                    st.session_state.personnel['Type'] == personnel_type
                ]
                if not tarif_row.empty:
                    try:
                        tarif = float(tarif_row['Coût Horaire'].iloc[0])
                        calendar_df[cout_col] = calendar_df[heures_col] * tarif
                    except (ValueError, TypeError):
                        st.warning(
                            f"Tarif invalide pour '{personnel_type}'. "
                            f"Coût '{category_key}' mis à 0."
                        )

        # Calculer les totaux
        heure_cols = [c for c in calendar_df.columns
                     if c.startswith('Heures_') and c != 'Heures_Total_Jour']
        cout_cols = [c for c in calendar_df.columns
                    if c.startswith('Coût_') and c != 'Coût_Total_Jour']
        calendar_df['Heures_Total_Jour'] = calendar_df[heure_cols].sum(axis=1)
        calendar_df['Coût_Total_Jour'] = calendar_df[cout_cols].sum(axis=1)

        # Créer le résumé
        summary = pd.DataFrame()
        if cout_cols:
            summary_data = calendar_df[cout_cols].sum()
            summary = pd.DataFrame({
                'Catégorie': summary_data.index,
                'Coût': summary_data.values
            })
            summary['Catégorie'] = summary['Catégorie'].str.replace('Coût_', '', regex=False)

        # Mettre à jour le state du budget
        st.session_state.budget_state = {
            'year': year,
            'calendar_df': calendar_df,
            'cout_cols': cout_cols,
            'summary': summary,
            'totals': {
                'heures_annuel': calendar_df['Heures_Total_Jour'].sum(),
                'cout_annuel': calendar_df['Coût_Total_Jour'].sum()
            },
            'selected_date': st.session_state.get('budget_state', {}).get(
                'selected_date', dt.date(year, 1, 1)
            )
        }
    except Exception as e:
        st.error(f"Erreur lors de la génération du budget : {e}")
        st.session_state.budget_state = {}


def _season_timeline_df():
    """Crée un DataFrame pour la timeline des saisons (visualisation)"""
    if 'adjusted_saisons' not in st.session_state or \
       not isinstance(st.session_state.adjusted_saisons, pd.DataFrame):
        return pd.DataFrame(columns=['Saison', 'Date Début', 'Date Fin', 'start', 'end', 'days'])

    df = st.session_state.adjusted_saisons.copy()

    try:
        df['Date Début'] = pd.to_datetime(df['Date Début'])
        df['Date Fin'] = pd.to_datetime(df['Date Fin'])
    except Exception as e:
        st.error(f"Erreur conversion dates des saisons: {e}")
        return pd.DataFrame(columns=['Saison', 'Date Début', 'Date Fin', 'start', 'end', 'days'])

    df = df.sort_values('Date Début').reset_index(drop=True)
    df = df.assign(
        start=lambda d: d['Date Début'],
        end=lambda d: d['Date Fin'],
        days=lambda d: (d['Date Fin'] - d['Date Début']).dt.days + 1
    )
    return df
