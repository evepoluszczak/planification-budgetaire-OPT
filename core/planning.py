"""
Logique métier pour la planification (grilles, jours-types)
"""
import pandas as pd
import streamlit as st
from config.constants import TIME_SLOTS
from utils.helpers import canon


def _get_grid(planning_dict: dict, name: str):
    """Récupère une grille de planification par nom (avec normalisation)"""
    if name in planning_dict:
        return name, planning_dict[name]
    cn = canon(name)
    for k in planning_dict.keys():
        if canon(k) == cn:
            return k, planning_dict[k]
    return None, None


def _ensure_grid(planning_dict: dict, name: str, perimetres: list, time_slots: list):
    """
    S'assure qu'une grille existe, la crée si nécessaire.
    Retourne (clé_stockée, DataFrame)
    """
    k, df = _get_grid(planning_dict, name)
    if df is not None:
        # Assurer que le DataFrame a les bons index et colonnes
        df = df.reindex(index=perimetres, columns=time_slots, fill_value=0)
        return k, df.fillna(0).astype(int).clip(0, 1)
    else:
        # Créer un nouveau DataFrame
        df = pd.DataFrame(0, index=perimetres, columns=time_slots).astype(int)
        planning_dict[name] = df
        return name, df


def _get_default_grid(planning_dict: dict):
    """Récupère la grille 'Default'"""
    return _get_grid(planning_dict, "Default")


def _apply_bulk_range(category_key: str, jt_key_stored: str, rows: list,
                      start_col: str, end_col: str, value: int):
    """Applique une modification en masse sur une plage de la grille"""
    df = st.session_state.planning_data[category_key][jt_key_stored]
    if df.empty or start_col not in df.columns or end_col not in df.columns:
        return

    value = 1 if int(value) == 1 else 0
    cols = list(df.columns)
    i1, i2 = cols.index(start_col), cols.index(end_col)
    if i1 > i2:
        i1, i2 = i2, i1
    target_cols = cols[i1:i2 + 1]
    valid_rows = [r for r in rows if r in df.index]
    if not valid_rows:
        return

    df.loc[valid_rows, target_cols] = value
    st.session_state.planning_data[category_key][jt_key_stored] = (
        df.fillna(0).astype(int).clip(0, 1)
    )


def _apply_ops_to_grid(base_df: pd.DataFrame, date_, jour: str, saison: str,
                       category: str):
    """
    Applique les règles d'ajustement (besoin jour) à une grille de base.
    Retourne une copie modifiée de la grille.
    """
    import datetime as dt
    from utils.date_utils import _str_to_date

    if not isinstance(base_df, pd.DataFrame) or base_df.empty:
        return base_df

    g = base_df.copy()
    cols = list(g.columns)

    for op in st.session_state.besoin_jour_ops:
        if op.get('category') != category:
            continue

        try:
            op_start = _str_to_date(op['start'])
            op_end = _str_to_date(op['end'])
            if op_start is None or op_end is None:
                continue
            if not (op_start <= date_ <= op_end):
                continue
        except Exception:
            continue

        if op['jours'] and (jour not in op['jours']):
            continue
        if op['saisons'] and (saison not in op['saisons']):
            continue

        if op['start_col'] in cols and op['end_col'] in cols:
            i1, i2 = cols.index(op['start_col']), cols.index(op['end_col'])
            if i1 > i2:
                i1, i2 = i2, i1
            target_cols = cols[i1:i2 + 1]
            rows = [r for r in op['rows'] if r in g.index]
            if rows and target_cols:
                try:
                    g.loc[rows, target_cols] = int(op['value'])
                except ValueError:
                    st.warning(f"Valeur invalide dans la règle: {op['value']}")
                    continue

    return g.fillna(0).astype(int).clip(0, 1)
