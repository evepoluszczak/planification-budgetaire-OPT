# core/assistant_utils.py
from __future__ import annotations
import datetime as dt
import pandas as pd
import numpy as np

# ========= Libellés FR =========

MONTHS_FR = {
    1: "janvier", 2: "février", 3: "mars", 4: "avril", 5: "mai", 6: "juin",
    7: "juillet", 8: "août", 9: "septembre", 10: "octobre", 11: "novembre", 12: "décembre"
}

DAYS_FR = {
    0: "Lundi", 1: "Mardi", 2: "Mercredi", 3: "Jeudi", 4: "Vendredi", 5: "Samedi", 6: "Dimanche"
}

def month_name_fr(m: int) -> str:
    return MONTHS_FR.get(int(m), str(m))

def day_name_fr(dow: int) -> str:
    return DAYS_FR.get(int(dow), str(dow))

# ========= Safeguards / Utils =========

def to_float_safe(x, default=0.0):
    try:
        if pd.isna(x):
            return float(default)
        return float(x)
    except Exception:
        try:
            return float(str(x).replace(",", "."))
        except Exception:
            return float(default)

def ceil_half_hour(hours: float) -> float:
    """Arrondit à +0.5h au-dessus."""
    return np.ceil(hours * 2.0) / 2.0

def floor_half_hour(hours: float) -> float:
    """Arrondit à -0.5h en dessous."""
    return np.floor(hours * 2.0) / 2.0

def normalize_0_1(series: pd.Series) -> pd.Series:
    s = pd.to_numeric(series, errors="coerce").fillna(0)
    vmin, vmax = float(s.min()), float(s.max())
    if vmax - vmin < 1e-9:
        return pd.Series(np.zeros(len(s)), index=s.index)
    return (s - vmin) / (vmax - vmin)
