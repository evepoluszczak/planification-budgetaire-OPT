"""
Système de sauvegarde automatique de l'état de l'application
"""
import json
import datetime
import hashlib
from pathlib import Path
import pandas as pd
import streamlit as st
from utils.date_utils import _date_to_str, _str_to_date
from core.rules import load_rules_from_json
from core.budget import generate_budget_state
from config.constants import RULES_BESOIN_JOUR_PATH, TIME_SLOTS


AUTOSAVE_DIR = Path("autosaves")
AUTOSAVE_FILE = AUTOSAVE_DIR / "autosave_session.json"  # Fichier principal (le plus récent)
MAX_AUTOSAVES = 5  # Nombre maximum de sauvegardes historiques à conserver (garantit plusieurs jours)


def _compute_session_hash():
    """
    Calcule un hash des données importantes de la session pour détecter les changements
    """
    try:
        hash_data = {}

        # Hash du personnel
        if 'personnel' in st.session_state and st.session_state.personnel is not None:
            hash_data['personnel'] = st.session_state.personnel.to_json()

        # Hash des saisons
        if 'saisons' in st.session_state and st.session_state.saisons is not None:
            hash_data['saisons'] = st.session_state.saisons.to_json()

        # Hash des périmètres
        if 'perimetres' in st.session_state:
            hash_data['perimetres'] = json.dumps(st.session_state.perimetres, sort_keys=True)

        # Hash des planning_data (grilles)
        if 'planning_data' in st.session_state:
            planning_hash = {}
            for category, day_types in st.session_state.planning_data.items():
                planning_hash[category] = {}
                for day_type, grid_df in day_types.items():
                    if isinstance(grid_df, pd.DataFrame):
                        planning_hash[category][day_type] = grid_df.to_json()
            hash_data['planning_data'] = json.dumps(planning_hash, sort_keys=True)

        # Hash des règles besoin jour
        if 'besoin_jour_ops' in st.session_state:
            # Convertir les dates en string pour le hash
            ops_for_hash = []
            for op in st.session_state.besoin_jour_ops:
                op_copy = op.copy()
                if 'start' in op_copy and op_copy['start']:
                    op_copy['start'] = str(op_copy['start'])
                if 'end' in op_copy and op_copy['end']:
                    op_copy['end'] = str(op_copy['end'])
                ops_for_hash.append(op_copy)
            hash_data['besoin_jour_ops'] = json.dumps(ops_for_hash, sort_keys=True)

        # Hash des formations
        if 'budget_formation_at' in st.session_state and st.session_state.budget_formation_at is not None:
            hash_data['budget_formation_at'] = st.session_state.budget_formation_at.to_json()

        if 'budget_formateurs_at' in st.session_state and st.session_state.budget_formateurs_at is not None:
            hash_data['budget_formateurs_at'] = st.session_state.budget_formateurs_at.to_json()

        # Créer le hash SHA256
        hash_string = json.dumps(hash_data, sort_keys=True)
        return hashlib.sha256(hash_string.encode()).hexdigest()

    except Exception as e:
        # En cas d'erreur, retourner None pour forcer une sauvegarde
        return None


def has_session_changed():
    """
    Vérifie si la session a changé depuis la dernière sauvegarde

    Returns:
        bool: True si la session a changé, False sinon
    """
    if not st.session_state.get('data_loaded', False):
        return False

    current_hash = _compute_session_hash()
    last_hash = st.session_state.get('_last_autosave_hash')

    # Si c'est la première fois ou si le hash a changé
    if last_hash is None or current_hash != last_hash:
        return True

    return False


def update_session_hash():
    """
    Met à jour le hash de la session après une sauvegarde
    """
    st.session_state._last_autosave_hash = _compute_session_hash()


def _serialize_dataframe(df):
    """Convertit un DataFrame en format sérialisable"""
    if df is None or not isinstance(df, pd.DataFrame):
        return None
    return df.to_dict('records')


def _deserialize_dataframe(data):
    """Reconvertit des données en DataFrame"""
    if data is None:
        return None
    return pd.DataFrame(data)


def _serialize_date(date_obj):
    """Convertit une date en string"""
    if date_obj is None:
        return None
    if isinstance(date_obj, (datetime.date, datetime.datetime)):
        return date_obj.strftime('%Y-%m-%d')
    return str(date_obj)


def _deserialize_date(date_str):
    """Convertit une string en date"""
    if date_str is None or date_str == '':
        return None
    try:
        return datetime.datetime.strptime(date_str, '%Y-%m-%d').date()
    except:
        return None


def save_session_state_auto():
    """Sauvegarde automatique de l'état de session en JSON"""
    try:
        # Créer le dossier de sauvegardes s'il n'existe pas
        AUTOSAVE_DIR.mkdir(exist_ok=True)

        # Si le fichier principal existe, le copier dans l'historique avant d'écraser
        if AUTOSAVE_FILE.exists():
            try:
                # Lire la date de l'ancienne sauvegarde
                with open(AUTOSAVE_FILE, 'r', encoding='utf-8') as f:
                    old_data = json.load(f)
                old_timestamp = old_data.get('saved_at', datetime.datetime.now().isoformat())
                # Créer un nom de fichier avec timestamp
                timestamp_str = old_timestamp.replace(':', '-').replace('.', '-')[:19]
                backup_file = AUTOSAVE_DIR / f"autosave_{timestamp_str}.json"
                # Copier l'ancienne sauvegarde
                import shutil
                shutil.copy2(AUTOSAVE_FILE, backup_file)
            except Exception:
                pass  # Ne pas bloquer si la copie échoue

        # Construire l'état à sauvegarder
        state_to_save = {
            'saved_at': datetime.datetime.now().isoformat(),
            'data_loaded': st.session_state.get('data_loaded', False),
        }

        # Personnel
        if 'personnel' in st.session_state:
            state_to_save['personnel'] = _serialize_dataframe(st.session_state.personnel)

        # Saisons
        if 'saisons' in st.session_state:
            saisons_df = st.session_state.saisons.copy()
            if 'Date Début' in saisons_df.columns:
                saisons_df['Date Début'] = saisons_df['Date Début'].apply(_serialize_date)
            if 'Date Fin' in saisons_df.columns:
                saisons_df['Date Fin'] = saisons_df['Date Fin'].apply(_serialize_date)
            state_to_save['saisons'] = _serialize_dataframe(saisons_df)
            state_to_save['reference_year_saisons'] = st.session_state.get('reference_year_saisons')

        # Saisons ajustées
        if 'adjusted_saisons' in st.session_state:
            adj_df = st.session_state.adjusted_saisons.copy()
            if 'Date Début' in adj_df.columns:
                adj_df['Date Début'] = adj_df['Date Début'].apply(_serialize_date)
            if 'Date Fin' in adj_df.columns:
                adj_df['Date Fin'] = adj_df['Date Fin'].apply(_serialize_date)
            state_to_save['adjusted_saisons'] = _serialize_dataframe(adj_df)
            state_to_save['adjusted_saisons_year'] = st.session_state.get('adjusted_saisons_year')

        # Périmètres
        if 'perimetres' in st.session_state:
            state_to_save['perimetres'] = st.session_state.perimetres

        # Cost mapping
        if 'cost_mapping' in st.session_state:
            state_to_save['cost_mapping'] = st.session_state.cost_mapping

        # Planning data (grilles)
        if 'planning_data' in st.session_state:
            planning_serialized = {}
            for category, day_types_dict in st.session_state.planning_data.items():
                planning_serialized[category] = {}
                for day_type, grid_df in day_types_dict.items():
                    # Convertir le DataFrame en dict avec index
                    grid_dict = {
                        'index': grid_df.index.tolist(),
                        'columns': grid_df.columns.tolist(),
                        'data': grid_df.values.tolist()
                    }
                    planning_serialized[category][day_type] = grid_dict
            state_to_save['planning_data'] = planning_serialized

        # Règles Besoin Jour
        if 'besoin_jour_ops' in st.session_state:
            rules_serialized = []
            for op in st.session_state.besoin_jour_ops:
                op_copy = op.copy()
                op_copy['start'] = _serialize_date(op.get('start'))
                op_copy['end'] = _serialize_date(op.get('end'))
                rules_serialized.append(op_copy)
            state_to_save['besoin_jour_ops'] = rules_serialized

        # Tables Formation/Formateurs
        if 'budget_formation_at' in st.session_state:
            state_to_save['budget_formation_at'] = _serialize_dataframe(
                st.session_state.budget_formation_at
            )

        if 'budget_formateurs_at' in st.session_state:
            state_to_save['budget_formateurs_at'] = _serialize_dataframe(
                st.session_state.budget_formateurs_at
            )

        # Sauvegarder dans le fichier
        with open(AUTOSAVE_FILE, 'w', encoding='utf-8') as f:
            json.dump(state_to_save, f, ensure_ascii=False, indent=2)

        # Nettoyer les anciennes sauvegardes (garder seulement les MAX_AUTOSAVES plus récentes)
        _cleanup_old_autosaves()

        # Mettre à jour le hash après sauvegarde réussie
        update_session_hash()

        return True, "Sauvegarde automatique réussie"

    except Exception as e:
        return False, f"Erreur lors de la sauvegarde automatique: {e}"


def load_session_state_auto(file_path=None):
    """Charge l'état de session depuis la sauvegarde automatique JSON"""
    try:
        if file_path is None:
            file_path = AUTOSAVE_FILE

        if not file_path.exists():
            return False, "Aucune sauvegarde automatique trouvée"

        with open(file_path, 'r', encoding='utf-8') as f:
            state_data = json.load(f)

        # Personnel
        if 'personnel' in state_data:
            st.session_state.personnel = _deserialize_dataframe(state_data['personnel'])

        # Saisons
        if 'saisons' in state_data:
            saisons_df = _deserialize_dataframe(state_data['saisons'])
            if 'Date Début' in saisons_df.columns:
                saisons_df['Date Début'] = saisons_df['Date Début'].apply(_deserialize_date)
            if 'Date Fin' in saisons_df.columns:
                saisons_df['Date Fin'] = saisons_df['Date Fin'].apply(_deserialize_date)
            st.session_state.saisons = saisons_df
            st.session_state.reference_year_saisons = state_data.get('reference_year_saisons')

        # Saisons ajustées
        if 'adjusted_saisons' in state_data:
            adj_df = _deserialize_dataframe(state_data['adjusted_saisons'])
            if 'Date Début' in adj_df.columns:
                adj_df['Date Début'] = adj_df['Date Début'].apply(_deserialize_date)
            if 'Date Fin' in adj_df.columns:
                adj_df['Date Fin'] = adj_df['Date Fin'].apply(_deserialize_date)
            st.session_state.adjusted_saisons = adj_df
            st.session_state.adjusted_saisons_year = state_data.get('adjusted_saisons_year')

        # Périmètres
        if 'perimetres' in state_data:
            st.session_state.perimetres = state_data['perimetres']

        # Cost mapping
        if 'cost_mapping' in state_data:
            st.session_state.cost_mapping = state_data['cost_mapping']

        # Planning data
        if 'planning_data' in state_data:
            planning_deserialized = {}
            for category, day_types_dict in state_data['planning_data'].items():
                planning_deserialized[category] = {}
                for day_type, grid_dict in day_types_dict.items():
                    # Reconstruire le DataFrame
                    df = pd.DataFrame(
                        data=grid_dict['data'],
                        index=grid_dict['index'],
                        columns=grid_dict['columns']
                    )
                    # Assurer que les colonnes sont bien TIME_SLOTS
                    df = df.reindex(columns=TIME_SLOTS, fill_value=0)
                    planning_deserialized[category][day_type] = df.fillna(0).astype(int).clip(0, 1)
            st.session_state.planning_data = planning_deserialized

        # Règles Besoin Jour
        if 'besoin_jour_ops' in state_data:
            rules_deserialized = []
            for op in state_data['besoin_jour_ops']:
                op_copy = op.copy()
                op_copy['start'] = _deserialize_date(op.get('start'))
                op_copy['end'] = _deserialize_date(op.get('end'))
                rules_deserialized.append(op_copy)
            st.session_state.besoin_jour_ops = rules_deserialized
        else:
            # Fallback
            st.session_state.besoin_jour_ops = load_rules_from_json(RULES_BESOIN_JOUR_PATH)

        # Tables Formation/Formateurs
        if 'budget_formation_at' in state_data:
            formation_df = _deserialize_dataframe(state_data['budget_formation_at'])
            # Normaliser les types
            if 'Effectif (pers.)' in formation_df.columns:
                formation_df['Effectif (pers.)'] = pd.to_numeric(
                    formation_df['Effectif (pers.)'], errors='coerce'
                ).fillna(0).astype(int)
            if 'Heures' in formation_df.columns:
                formation_df['Heures'] = pd.to_numeric(
                    formation_df['Heures'], errors='coerce'
                ).fillna(0.0)
            if 'Nbre de shifts' in formation_df.columns:
                formation_df['Nbre de shifts'] = pd.to_numeric(
                    formation_df['Nbre de shifts'], errors='coerce'
                ).fillna(0).astype(int)
            st.session_state.budget_formation_at = formation_df

        if 'budget_formateurs_at' in state_data:
            formateurs_df = _deserialize_dataframe(state_data['budget_formateurs_at'])
            # Normaliser les types
            if 'Effectif (pers.)' in formateurs_df.columns:
                formateurs_df['Effectif (pers.)'] = pd.to_numeric(
                    formateurs_df['Effectif (pers.)'], errors='coerce'
                ).fillna(0).astype(int)
            if 'Heures' in formateurs_df.columns:
                formateurs_df['Heures'] = pd.to_numeric(
                    formateurs_df['Heures'], errors='coerce'
                ).fillna(0.0)
            if 'Nbre de shifts' in formateurs_df.columns:
                formateurs_df['Nbre de shifts'] = pd.to_numeric(
                    formateurs_df['Nbre de shifts'], errors='coerce'
                ).fillna(0).astype(int)
            st.session_state.budget_formateurs_at = formateurs_df

        # Générer le budget automatiquement
        try:
            year_to_generate = int(
                st.session_state.get('adjusted_saisons_year',
                                    st.session_state.saisons['Date Début'].iloc[0].year)
            )
            generate_budget_state(year_to_generate)
        except Exception as _e:
            pass  # Ne pas bloquer si la génération échoue

        st.session_state.data_loaded = True

        # Récupérer la date de sauvegarde
        saved_at = state_data.get('saved_at', 'inconnue')
        return True, f"Session restaurée (sauvegardée le {saved_at})"

    except Exception as e:
        # Nettoyer en cas d'erreur
        st.session_state.data_loaded = False
        for key in ['personnel', 'saisons', 'perimetres', 'planning_data',
                   'cost_mapping', 'adjusted_saisons', 'besoin_jour_ops', 'budget_state',
                   'budget_formation_at', 'budget_formateurs_at']:
            st.session_state.pop(key, None)
        return False, f"Erreur lors du chargement de la sauvegarde automatique: {e}"


def autosave_exists():
    """Vérifie si une sauvegarde automatique existe"""
    return AUTOSAVE_FILE.exists()


def get_autosave_info(file_path=None):
    """Retourne des informations sur la sauvegarde automatique"""
    if file_path is None:
        file_path = AUTOSAVE_FILE

    if not file_path.exists():
        return None

    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            state_data = json.load(f)

        saved_at = state_data.get('saved_at', 'inconnu')
        # Parser la date ISO
        saved_datetime = None
        saved_at_str = saved_at
        days_old = 0
        try:
            saved_datetime = datetime.datetime.fromisoformat(saved_at)
            saved_at_str = saved_datetime.strftime('%d/%m/%Y à %H:%M:%S')
            # Calculer l'âge en jours
            days_old = (datetime.datetime.now() - saved_datetime).days
        except:
            pass

        return {
            'saved_at': saved_at_str,
            'saved_datetime': saved_datetime,
            'days_old': days_old,
            'file_size': file_path.stat().st_size,
            'has_personnel': 'personnel' in state_data,
            'has_planning': 'planning_data' in state_data,
            'has_formation': 'budget_formation_at' in state_data,
            'file_path': file_path,
        }
    except Exception as e:
        return {'error': str(e)}


def list_all_autosaves():
    """Liste toutes les sauvegardes automatiques disponibles"""
    if not AUTOSAVE_DIR.exists():
        return []

    autosaves = []
    # Fichier principal
    if AUTOSAVE_FILE.exists():
        info = get_autosave_info(AUTOSAVE_FILE)
        if info and 'error' not in info:
            info['is_current'] = True
            autosaves.append(info)

    # Fichiers d'historique
    for file_path in sorted(AUTOSAVE_DIR.glob("autosave_*.json"), reverse=True):
        if file_path != AUTOSAVE_FILE:
            info = get_autosave_info(file_path)
            if info and 'error' not in info:
                info['is_current'] = False
                autosaves.append(info)

    # Trier par date (plus récent en premier)
    autosaves.sort(key=lambda x: x.get('saved_datetime', datetime.datetime.min), reverse=True)

    return autosaves


def _cleanup_old_autosaves():
    """Supprime les anciennes sauvegardes en gardant seulement les MAX_AUTOSAVES plus récentes"""
    try:
        if not AUTOSAVE_DIR.exists():
            return

        # Lister tous les fichiers de sauvegarde (sauf le principal)
        backup_files = []
        for file_path in AUTOSAVE_DIR.glob("autosave_*.json"):
            if file_path != AUTOSAVE_FILE:
                try:
                    mtime = file_path.stat().st_mtime
                    backup_files.append((mtime, file_path))
                except:
                    pass

        # Trier par date (plus ancien en premier)
        backup_files.sort()

        # Supprimer les plus anciens si on dépasse MAX_AUTOSAVES
        while len(backup_files) > MAX_AUTOSAVES:
            _, old_file = backup_files.pop(0)
            try:
                old_file.unlink()
            except:
                pass
    except Exception:
        pass  # Ne pas bloquer en cas d'erreur
