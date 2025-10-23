"""
Fonctions utilitaires pour la gestion des dates
"""
import datetime as dt
from datetime import timedelta
import pandas as pd
import streamlit as st


def _date_to_str(d):
    """Convertit une date en chaîne ISO"""
    if isinstance(d, dt.date):
        return d.isoformat()
    return str(d)


def _str_to_date(x):
    """Convertit une chaîne en objet date"""
    if isinstance(x, dt.date):
        return x
    try:
        return dt.date.fromisoformat(str(x))
    except Exception:
        try:
            return pd.to_datetime(x).date()
        except Exception:
            return None


def find_closest_weekday(target_date: dt.date, target_weekday: int) -> dt.date:
    """
    Trouve la date la plus proche ayant le jour de semaine spécifié
    target_weekday: 0=Lundi, 1=Mardi, ..., 6=Dimanche
    """
    current_weekday = target_date.weekday()
    days_backward = (current_weekday - target_weekday + 7) % 7
    days_forward = (target_weekday - current_weekday + 7) % 7

    if days_backward <= days_forward:
        return target_date - timedelta(days=days_backward)
    else:
        return target_date + timedelta(days=days_forward)


def _day_name_fr(series_dt):
    """Retourne le nom du jour en français pour une Series de datetime"""
    mapping = {
        0: "Lundi", 1: "Mardi", 2: "Mercredi",
        3: "Jeudi", 4: "Vendredi", 5: "Samedi", 6: "Dimanche"
    }
    try:
        # Use French locale directly if available
        return series_dt.dt.day_name(locale='fr_FR.UTF-8').str.capitalize()
    except Exception:
        # Fallback to English names and mapping if locale fails
        try:
            return series_dt.dt.day_name().map({
                'Monday': 'Lundi', 'Tuesday': 'Mardi', 'Wednesday': 'Mercredi',
                'Thursday': 'Jeudi', 'Friday': 'Vendredi', 'Saturday': 'Samedi',
                'Sunday': 'Dimanche'
            })
        except Exception:
            # Final fallback using weekday number
            return series_dt.dt.weekday.map(mapping)
