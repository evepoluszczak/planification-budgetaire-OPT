"""
Chargement asynchrone des données PAX en arrière-plan
"""
import threading
import datetime as dt
from pathlib import Path
import pandas as pd
import streamlit as st
import json
import pickle
from zoneinfo import ZoneInfo


class PaxLoaderThread(threading.Thread):
    """Thread pour charger les données PAX (Forecast + Historic) en arrière-plan"""

    def __init__(self, forecast_path: Path, historical_path: Path, session_state_key: str):
        super().__init__(daemon=True)
        self.forecast_path = forecast_path
        self.historical_path = historical_path
        self.session_state_key = session_state_key
        self.result = None
        self.error = None
        self.progress = {'current_file': None, 'percent': 0}

    def run(self):
        """Exécute le chargement en arrière-plan"""
        try:
            results = {
                'forecast': None,
                'historical': None,
                'status': 'success',
                'errors': []
            }

            # Charger Forecast
            self.progress = {'current_file': 'Forecast', 'percent': 0}
            try:
                forecast_data, fc_min, fc_max = self._load_pax_uncached(
                    self.forecast_path, "Forecast PAX"
                )
                if not forecast_data.empty:
                    results['forecast'] = {
                        'data': forecast_data,
                        'min_date': fc_min,
                        'max_date': fc_max,
                        'status': 'loaded'
                    }
                else:
                    results['forecast'] = {'status': 'empty'}
                    results['errors'].append('Forecast: Fichier vide')
            except Exception as e:
                results['forecast'] = {'status': 'error', 'error': str(e)}
                results['errors'].append(f'Forecast: {str(e)}')

            self.progress = {'current_file': 'Forecast', 'percent': 50}

            # Charger Historic
            self.progress = {'current_file': 'Historic', 'percent': 50}
            try:
                historical_data, hist_min, hist_max = self._load_pax_uncached(
                    self.historical_path, "Historic PAX"
                )
                if not historical_data.empty:
                    results['historical'] = {
                        'data': historical_data,
                        'min_date': hist_min,
                        'max_date': hist_max,
                        'status': 'loaded'
                    }
                else:
                    results['historical'] = {'status': 'empty'}
                    results['errors'].append('Historic: Fichier vide')
            except Exception as e:
                results['historical'] = {'status': 'error', 'error': str(e)}
                results['errors'].append(f'Historic: {str(e)}')

            self.progress = {'current_file': 'Historic', 'percent': 100}

            # Déterminer le statut global
            if results['forecast'] and results['forecast'].get('status') == 'loaded':
                if results['historical'] and results['historical'].get('status') == 'loaded':
                    results['status'] = 'success'
                else:
                    results['status'] = 'partial'  # Seulement Forecast chargé
            elif results['historical'] and results['historical'].get('status') == 'loaded':
                results['status'] = 'partial'  # Seulement Historic chargé
            else:
                results['status'] = 'error'  # Aucun fichier chargé

            self.result = results

        except Exception as e:
            self.error = str(e)
            self.result = {'status': 'error', 'error': str(e), 'errors': [str(e)]}

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


PAX_CACHE_FILE = Path("input_files/.pax_cache_info.json")
PAX_FORECAST_CACHE = Path("input_files/.pax_forecast_cache.pkl")
PAX_HISTORICAL_CACHE = Path("input_files/.pax_historical_cache.pkl")


def clear_pax_cache():
    """
    Supprime le fichier de cache PAX pour forcer un rechargement.
    """
    try:
        if PAX_CACHE_FILE.exists():
            PAX_CACHE_FILE.unlink()
        if PAX_FORECAST_CACHE.exists():
            PAX_FORECAST_CACHE.unlink()
        if PAX_HISTORICAL_CACHE.exists():
            PAX_HISTORICAL_CACHE.unlink()
    except Exception:
        pass


def _save_pax_data_to_disk(forecast_data=None, historical_data=None):
    """
    Sauvegarde les DataFrames PAX sur disque pour réutilisation.
    """
    try:
        if forecast_data is not None:
            with open(PAX_FORECAST_CACHE, 'wb') as f:
                pickle.dump(forecast_data, f)
        if historical_data is not None:
            with open(PAX_HISTORICAL_CACHE, 'wb') as f:
                pickle.dump(historical_data, f)
    except Exception:
        pass


def load_pax_data_from_cache() -> bool:
    """
    Charge les données PAX depuis le cache disque si disponible et valide.
    Retourne True si les données ont été chargées avec succès.
    """
    try:
        cache_info = _read_pax_cache_file()
        if not cache_info:
            return False

        # Vérifier que c'est aujourd'hui
        loaded_date = cache_info.get('loaded_date')
        if loaded_date != dt.date.today():
            return False

        # Charger Forecast si disponible
        if PAX_FORECAST_CACHE.exists():
            with open(PAX_FORECAST_CACHE, 'rb') as f:
                forecast_data = pickle.load(f)
                st.session_state.pax_forecast_data = forecast_data
                st.session_state.pax_forecast_min_date = forecast_data.index.min().date()
                st.session_state.pax_forecast_max_date = forecast_data.index.max().date()
                st.session_state.pax_forecast_status = 'loaded'

        # Charger Historical si disponible
        if PAX_HISTORICAL_CACHE.exists():
            with open(PAX_HISTORICAL_CACHE, 'rb') as f:
                historical_data = pickle.load(f)
                st.session_state.pax_historical_data = historical_data
                st.session_state.pax_historical_min_date = historical_data.index.min().date()
                st.session_state.pax_historical_max_date = historical_data.index.max().date()
                st.session_state.pax_historical_status = 'loaded'

        # Restaurer les métadonnées
        st.session_state.pax_loaded_date = loaded_date
        st.session_state.pax_loaded_datetime = cache_info.get('loaded_datetime')
        st.session_state.pax_loading_status = cache_info.get('status', 'success')

        return True
    except Exception:
        return False


def _read_pax_cache_file() -> dict | None:
    """
    Lit le fichier de cache PAX local.
    Retourne None si le fichier n'existe pas ou est invalide.
    """
    try:
        if PAX_CACHE_FILE.exists():
            with open(PAX_CACHE_FILE, 'r') as f:
                data = json.load(f)
                # Convertir la date string en date object
                if 'loaded_date' in data:
                    data['loaded_date'] = dt.datetime.fromisoformat(data['loaded_date']).date()
                if 'loaded_datetime' in data:
                    data['loaded_datetime'] = dt.datetime.fromisoformat(data['loaded_datetime'])
                return data
    except Exception:
        pass
    return None


def _write_pax_cache_file(cache_data: dict) -> None:
    """
    Écrit les informations de cache dans le fichier local.
    """
    try:
        # Convertir les dates en strings pour JSON
        data_to_save = cache_data.copy()
        if 'loaded_date' in data_to_save and isinstance(data_to_save['loaded_date'], dt.date):
            data_to_save['loaded_date'] = data_to_save['loaded_date'].isoformat()
        if 'loaded_datetime' in data_to_save and isinstance(data_to_save['loaded_datetime'], dt.datetime):
            data_to_save['loaded_datetime'] = data_to_save['loaded_datetime'].isoformat()

        PAX_CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
        with open(PAX_CACHE_FILE, 'w') as f:
            json.dump(data_to_save, f, indent=2)
    except Exception:
        pass


def is_pax_data_cached_today() -> bool:
    """
    Vérifie si les données PAX ont déjà été chargées aujourd'hui.
    Vérifie d'abord le fichier de cache local, puis session_state.
    Retourne True si les données sont en cache et datent d'aujourd'hui.
    """
    today = dt.date.today()

    # D'abord vérifier le fichier de cache persistant
    cache_file_data = _read_pax_cache_file()
    if cache_file_data:
        loaded_date = cache_file_data.get('loaded_date')
        if loaded_date and loaded_date == today:
            # Le cache est valide, restaurer dans session_state si nécessaire
            if 'pax_loaded_date' not in st.session_state:
                st.session_state.pax_loaded_date = loaded_date
                st.session_state.pax_loaded_datetime = cache_file_data.get('loaded_datetime')
            return True

    # Sinon vérifier session_state (pour le cas où on vient de charger dans cette session)
    if 'pax_loaded_date' in st.session_state:
        loaded_date = st.session_state.pax_loaded_date
        if loaded_date == today:
            # Vérifier si les données sont présentes
            has_forecast = st.session_state.get('pax_forecast_status') == 'loaded'
            has_historical = st.session_state.get('pax_historical_status') == 'loaded'
            return has_forecast or has_historical

    return False


def get_pax_cache_info() -> dict:
    """
    Retourne les informations sur le cache PAX.
    Combine les infos du fichier et de session_state.
    """
    # Lire le cache file d'abord
    cache_file_data = _read_pax_cache_file()

    # Utiliser les données du fichier ou de session_state
    loaded_date = st.session_state.get('pax_loaded_date') or (cache_file_data.get('loaded_date') if cache_file_data else None)
    loaded_datetime = st.session_state.get('pax_loaded_datetime') or (cache_file_data.get('loaded_datetime') if cache_file_data else None)

    return {
        'is_cached': is_pax_data_cached_today(),
        'loaded_date': loaded_date,
        'loaded_datetime': loaded_datetime,
        'forecast_status': st.session_state.get('pax_forecast_status'),
        'historical_status': st.session_state.get('pax_historical_status'),
    }


def start_pax_loading(forecast_path: Path, historical_path: Path):
    """
    Démarre le chargement des données PAX (Forecast + Historic) en arrière-plan.
    Met à jour st.session_state pour tracker l'état.
    """
    # Initialiser l'état de chargement
    st.session_state.pax_loading_status = 'loading'
    st.session_state.pax_loading_progress = {'current_file': 'Démarrage...', 'percent': 0}
    st.session_state.pax_loading_error = None

    # Créer et démarrer le thread
    session_key = f'pax_loader_{dt.datetime.now().timestamp()}'
    loader_thread = PaxLoaderThread(forecast_path, historical_path, session_key)

    # Stocker la référence au thread
    st.session_state.pax_loader_thread = loader_thread
    st.session_state.pax_loader_start_time = dt.datetime.now()

    # Démarrer le thread
    loader_thread.start()

    return session_key


def check_pax_loading_status():
    """
    Vérifie l'état du chargement PAX et met à jour session_state.
    Retourne: 'loading', 'success', 'partial', 'error', ou 'idle'
    """
    if 'pax_loader_thread' not in st.session_state:
        return 'idle'

    thread = st.session_state.pax_loader_thread

    # Vérifier si le thread est toujours en cours
    if thread.is_alive():
        # Calculer le temps écoulé
        elapsed = (dt.datetime.now() - st.session_state.pax_loader_start_time).total_seconds()
        st.session_state.pax_loading_elapsed = elapsed
        # Mettre à jour la progression
        st.session_state.pax_loading_progress = thread.progress
        return 'loading'

    # Le thread est terminé, récupérer les résultats
    if thread.result is not None:
        result = thread.result
        status = result.get('status')

        # Stocker les données Forecast
        fc_data = None
        if result.get('forecast') and result['forecast'].get('status') == 'loaded':
            fc_data = result['forecast']['data']
            st.session_state.pax_forecast_data = fc_data
            st.session_state.pax_forecast_min_date = result['forecast']['min_date']
            st.session_state.pax_forecast_max_date = result['forecast']['max_date']
            st.session_state.pax_forecast_status = 'loaded'
        else:
            st.session_state.pax_forecast_status = result.get('forecast', {}).get('status', 'not_loaded')

        # Stocker les données Historic
        hist_data = None
        if result.get('historical') and result['historical'].get('status') == 'loaded':
            hist_data = result['historical']['data']
            st.session_state.pax_historical_data = hist_data
            st.session_state.pax_historical_min_date = result['historical']['min_date']
            st.session_state.pax_historical_max_date = result['historical']['max_date']
            st.session_state.pax_historical_status = 'loaded'
        else:
            st.session_state.pax_historical_status = result.get('historical', {}).get('status', 'not_loaded')

        # Sauvegarder les données sur disque pour réutilisation
        if fc_data is not None or hist_data is not None:
            _save_pax_data_to_disk(forecast_data=fc_data, historical_data=hist_data)

        # Stocker le statut global
        st.session_state.pax_loading_status = status
        st.session_state.pax_data_status = 'attempted'

        # Stocker les erreurs s'il y en a
        if result.get('errors'):
            st.session_state.pax_loading_error = ' | '.join(result['errors'])
        else:
            st.session_state.pax_loading_error = None

        # Stocker la date/heure de chargement et écrire dans le cache
        # pour tous les statuts (succès, partiel, erreur) afin d'éviter
        # les tentatives infinies en cas d'erreur
        # Utiliser timezone Europe/Paris pour heure locale France
        france_tz = ZoneInfo("Europe/Paris")
        now = dt.datetime.now(france_tz)
        st.session_state.pax_loaded_date = now.date()
        st.session_state.pax_loaded_datetime = now

        # Écrire dans le fichier de cache pour persister entre refreshs
        _write_pax_cache_file({
            'loaded_date': now.date(),
            'loaded_datetime': now,
            'status': status
        })

        # Nettoyer la référence au thread
        del st.session_state.pax_loader_thread

        # Marquer qu'on doit faire un rerun pour afficher les dates
        st.session_state.pax_needs_rerun = True

        return status

    # Erreur durant l'exécution
    if thread.error is not None:
        st.session_state.pax_loading_status = 'error'
        st.session_state.pax_loading_error = thread.error
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
        'progress': st.session_state.get('pax_loading_progress', {}),
        'forecast_status': st.session_state.get('pax_forecast_status'),
        'historical_status': st.session_state.get('pax_historical_status'),
        'forecast_min': st.session_state.get('pax_forecast_min_date'),
        'forecast_max': st.session_state.get('pax_forecast_max_date'),
        'historical_min': st.session_state.get('pax_historical_min_date'),
        'historical_max': st.session_state.get('pax_historical_max_date'),
    }

    return info
