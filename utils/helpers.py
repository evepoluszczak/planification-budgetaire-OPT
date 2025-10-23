"""
Fonctions utilitaires générales
"""
import re
import unicodedata
import numpy as np
import pandas as pd
import streamlit as st
from config.constants import JOURS_FR


def _strip_accents(s: str) -> str:
    """Retire les accents d'une chaîne"""
    return ''.join(
        c for c in unicodedata.normalize('NFKD', s)
        if not unicodedata.combining(c)
    )


def canon(s: str) -> str:
    """Normalise une chaîne (sans accents, lowercase, espaces simples)"""
    s = "" if s is None else str(s)
    s = re.sub(r"\s+", " ", s.strip())
    s = _strip_accents(s).lower()
    return s


def split_jour_type(name: str):
    """
    Divise un nom de jour-type en (jour, saison)
    Ex: "Lundi Été" -> ("Lundi", "Été")
    """
    if not name:
        return (None, None)
    name = str(name).strip()
    for j in JOURS_FR:
        if name.startswith(j + " "):
            return j, name[len(j):].strip()
        if name == j:
            return j, ""
    return (None, None)


def clean_dataframe(df):
    """Nettoie un DataFrame en remplaçant les valeurs infinies et NaN problématiques"""
    df = df.copy()
    # Remplacer les inf par de grandes valeurs finies
    df = df.replace([np.inf, -np.inf], [999999.0, -999999.0])
    # Remplacer les NaN par 0 dans les colonnes numériques
    numeric_cols = df.select_dtypes(include=[np.number]).columns
    df[numeric_cols] = df[numeric_cols].fillna(0)
    return df


def safe_metric_display(value, format_str="%,.0f"):
    """Affiche une métrique de manière sécurisée en gérant les valeurs infinies"""
    if pd.isna(value) or not np.isfinite(value):
        return "N/A"
    try:
        return format_str % value
    except Exception:
        return str(value)


def _round_half(x: float) -> float:
    """Arrondi au pas de 0.5h (30 minutes)"""
    return float(round(x * 2) / 2.0)


def _to_float_hours(x) -> float:
    """Convertit une valeur de type 'Heures' en float, gère les virgules"""
    try:
        return float(str(x).replace(",", "."))
    except Exception:
        return 0.0


def sync_all_planning_grids_from_widgets():
    """Synchronise toutes les grilles de planning depuis les widgets Streamlit"""
    if "planning_data" not in st.session_state:
        return
    for category_key, day_types in st.session_state.planning_data.items():
        for jt_key, df in day_types.items():
            if isinstance(df, pd.DataFrame) and not df.empty:
                st.session_state.planning_data[category_key][jt_key] = (
                    df.fillna(0).astype(int).clip(0, 1)
                )
