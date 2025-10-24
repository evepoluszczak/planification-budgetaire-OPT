"""
Chargement asynchrone des données PAX en arrière-plan
"""
import threading
import datetime as dt
from pathlib import Path
import pandas as pd
import streamlit as st


class PaxLoaderThread(threading.Thread):
    """Thread pour charger les données PAX en arrière-plan"""

    def __init__(self, file_path: Path, session_state_key: str):
        super().__init__(daemon=True)
        self.file_path = file_path
        self.session_state_key = session_state_key
        self.result = None
        self.error = None

    def run(self):
        """Exécute le chargement en arrière-plan"""
        try:
            # Import ici pour éviter les problèmes de circular imports
            from core.data_loader import load_pax_data

            # Charger les données (sans cache pour forcer un rechargement)
            full_pax_data, overall_min_date, overall_max_date = self._load_pax_uncached(
                self.file_path, "Passagers Forecast"
            )

            if not full_pax_data.empty:
                # Séparer historique et forecast
                today = dt.date.today()
                historical_data = full_pax_data[full_pax_data.index.date < today].copy()
                forecast_data = full_pax_data[full_pax_data.index.date >= today].copy()

                self.result = {
                    'full_data': full_pax_data,
                    'overall_min_date': overall_min_date,
                    'overall_max_date': overall_max_date,
                    'historical_data': historical_data,
                    'forecast_data': forecast_data,
                    'status': 'success'
                }
            else:
                self.error = "Le fichier est vide ou n'a pas pu être lu"
                self.result = {'status': 'empty'}

        except Exception as e:
            self.error = str(e)
            self.result = {'status': 'error', 'error': str(e)}

    def _load_pax_uncached(self, file_path: Path, file_description: str):
        """Version non-cachée de load_pax_data pour forcer le rechargement"""
        import numpy as np

        if not file_path.exists():
            raise FileNotFoundError(f"Fichier {file_description} non trouvé : {file_path}")

        # Lecture du fichier (CSV ou Excel)
        if file_path.suffix.lower() == '.csv':
            df = pd.read_csv(file_path, delimiter=";")
        elif file_path.suffix.lower() in ['.xlsx', '.xls']:
            df = pd.read_excel(file_path, engine='openpyxl')
        else:
            raise ValueError(f"Format non supporté: {file_path.suffix}")

        # Conversion DateTime
        time_col_name = 'Local Schedule Time'
        try:
            df['DateTime'] = pd.to_datetime(
                df[time_col_name],
                format='%d.%m.%Y %H:%M',
                errors='coerce'
            )
            if df['DateTime'].isnull().sum() > len(df) / 2:
                df['DateTime'] = pd.to_datetime(df[time_col_name], errors='coerce')
        except (KeyError, ValueError):
            df['DateTime'] = pd.to_datetime(df[time_col_name], errors='coerce')

        # Nettoyage
        pax_col = 'Expected Pax'
        schengen_col = 'Schengen Flight'
        arrdep_col = 'Arrival - Departure Code'

        df[pax_col] = pd.to_numeric(df[pax_col], errors='coerce').fillna(0)

        if not all(col in df.columns for col in [schengen_col, arrdep_col]):
            missing = [col for col in [schengen_col, arrdep_col] if col not in df.columns]
            raise KeyError(f"Colonnes manquantes : {', '.join(missing)}")

        df = df.dropna(subset=['DateTime'])

        if df.empty:
            return pd.DataFrame(), None, None

        # Dates Min/Max
        min_date = df['DateTime'].min().date()
        max_date = df['DateTime'].max().date()

        # Breakdown vectorisé
        schengen_mask = df[schengen_col] == 'Y'
        arrival_mask = df[arrdep_col] == 'A'
        nonschengen_mask = ~schengen_mask
        departure_mask = ~arrival_mask
        pax_values = df[pax_col]

        df['Pax_Schengen_A'] = np.where(schengen_mask & arrival_mask, pax_values, 0)
        df['Pax_Schengen_D'] = np.where(schengen_mask & departure_mask, pax_values, 0)
        df['Pax_NonSchengen_A'] = np.where(nonschengen_mask & arrival_mask, pax_values, 0)
        df['Pax_NonSchengen_D'] = np.where(nonschengen_mask & departure_mask, pax_values, 0)

        # Agrégation
        pax_agg = df.set_index('DateTime').resample('30T').agg({
            'Pax_Schengen_A': 'sum', 'Pax_Schengen_D': 'sum',
            'Pax_NonSchengen_A': 'sum', 'Pax_NonSchengen_D': 'sum'
        })

        return pax_agg, min_date, max_date


def start_pax_loading(file_path: Path):
    """
    Démarre le chargement des données PAX en arrière-plan.
    Met à jour st.session_state pour tracker l'état.
    """
    # Initialiser l'état de chargement
    st.session_state.pax_loading_status = 'loading'
    st.session_state.pax_loading_progress = 0
    st.session_state.pax_loading_error = None

    # Créer et démarrer le thread
    session_key = f'pax_loader_{dt.datetime.now().timestamp()}'
    loader_thread = PaxLoaderThread(file_path, session_key)

    # Stocker la référence au thread
    st.session_state.pax_loader_thread = loader_thread
    st.session_state.pax_loader_start_time = dt.datetime.now()

    # Démarrer le thread
    loader_thread.start()

    return session_key


def check_pax_loading_status():
    """
    Vérifie l'état du chargement PAX et met à jour session_state.
    Retourne: 'loading', 'success', 'error', ou 'idle'
    """
    if 'pax_loader_thread' not in st.session_state:
        return 'idle'

    thread = st.session_state.pax_loader_thread

    # Vérifier si le thread est toujours en cours
    if thread.is_alive():
        # Calculer le temps écoulé
        elapsed = (dt.datetime.now() - st.session_state.pax_loader_start_time).total_seconds()
        st.session_state.pax_loading_elapsed = elapsed
        return 'loading'

    # Le thread est terminé, récupérer les résultats
    if thread.result is not None:
        result = thread.result

        if result.get('status') == 'success':
            # Stocker les données dans session_state
            st.session_state.pax_forecast_data = result['forecast_data']
            st.session_state.pax_historical_data = result['historical_data']
            st.session_state.pax_overall_min_date = result['overall_min_date']
            st.session_state.pax_overall_max_date = result['overall_max_date']

            # Stocker les dates min/max pour forecast et historical
            if not result['forecast_data'].empty:
                st.session_state.pax_forecast_min_date = result['forecast_data'].index.min().date()
                st.session_state.pax_forecast_max_date = result['forecast_data'].index.max().date()
                st.session_state.pax_forecast_status = 'loaded'
            else:
                st.session_state.pax_forecast_status = 'no_data_found'

            if not result['historical_data'].empty:
                st.session_state.pax_historical_min_date = result['historical_data'].index.min().date()
                st.session_state.pax_historical_max_date = result['historical_data'].index.max().date()
                st.session_state.pax_historical_status = 'loaded'
            else:
                st.session_state.pax_historical_status = 'no_data_found'

            st.session_state.pax_loading_status = 'success'
            st.session_state.pax_data_status = 'attempted'

            # Nettoyer la référence au thread
            del st.session_state.pax_loader_thread

            return 'success'
        else:
            # Erreur ou vide
            st.session_state.pax_loading_status = 'error'
            st.session_state.pax_loading_error = result.get('error', 'Données vides')

            # Nettoyer la référence au thread
            del st.session_state.pax_loader_thread

            return 'error'

    # Erreur durant l'exécution
    if thread.error is not None:
        st.session_state.pax_loading_status = 'error'
        st.session_state.pax_loading_error = thread.error

        # Nettoyer la référence au thread
        del st.session_state.pax_loader_thread

        return 'error'

    # État indéterminé (ne devrait pas arriver)
    return 'loading'


def get_pax_loading_info():
    """Retourne les informations d'état du chargement pour l'affichage"""
    status = st.session_state.get('pax_loading_status', 'idle')

    info = {
        'status': status,
        'elapsed': st.session_state.get('pax_loading_elapsed', 0),
        'error': st.session_state.get('pax_loading_error'),
        'forecast_status': st.session_state.get('pax_forecast_status'),
        'historical_status': st.session_state.get('pax_historical_status')
    }

    return info
