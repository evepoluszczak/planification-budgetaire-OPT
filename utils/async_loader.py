"""
Chargement asynchrone des données PAX en arrière-plan
- Thread dédié (non bloquant)
- Lecture CSV/Excel robuste (fallback séparateur/encoding)
- Mapping flexible des colonnes
- Normalisation Schengen / Arrivée-Départ
- Agrégation 30 minutes (resample '30T')
- Remontée d'erreurs avec traceback pour debug UI
"""

from __future__ import annotations

import threading
import datetime as dt
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

import pandas as pd
import numpy as np
import streamlit as st
import traceback


# =========================
# Configuration & constantes
# =========================

# Candidats de noms de colonnes tolérées (les fichiers sources peuvent varier)
COLUMN_CANDIDATES: Dict[str, list[str]] = {
    "time": ["Local Schedule Time", "DateTime", "Local Time", "Local_Time", "LocalScheduleTime"],
    "pax": ["Expected Pax", "Pax", "Expected_Pax"],
    "schengen": ["Schengen Flight", "Schengen_Flight", "Schengen"],
    "ad": ["Arrival - Departure Code", "ArrDep", "A-D Code", "AD_Code", "A_D_Code"],
}

# Valeurs acceptées pour Schengen = True
SCHENGEN_TRUE = {"y", "yes", "true", "1", "oui", "o", "schengen"}

# =========================
# Helpers
# =========================

def _pick_present_column(df: pd.DataFrame, candidates: list[str]) -> Optional[str]:
    """Renvoie le premier nom de colonne présent dans df, parmi candidates."""
    for c in candidates:
        if c in df.columns:
            return c
    return None


def _parse_datetime_tolerant(series: pd.Series) -> pd.Series:
    """
    Parsing tolérant des datetime :
    1) Tente '%d.%m.%Y %H:%M'
    2) Fallback parsing générique
    """
    dt1 = pd.to_datetime(series, format="%d.%m.%Y %H:%M", errors="coerce")
    if dt1.isna().all():
        return pd.to_datetime(series, errors="coerce")
    return dt1


def _read_table_robust(file_path: Path, file_description: str) -> pd.DataFrame:
    """
    Lecture robuste CSV/Excel :
    - CSV : tente sep=';' puis sep=','
    - Excel : openpyxl
    - Remonte une RuntimeError explicite en cas d'échec
    """
    try:
        if file_path.suffix.lower() == ".csv":
            try:
                return pd.read_csv(file_path, sep=";", encoding="utf-8")
            except Exception:
                # Fallback séparateur "," ; tentative encodage par défaut
                return pd.read_csv(file_path, sep=",")
        elif file_path.suffix.lower() in [".xlsx", ".xls"]:
            return pd.read_excel(file_path, engine="openpyxl")
        else:
            raise ValueError(f"Format non supporté: {file_path.suffix}")
    except Exception as e:
        raise RuntimeError(f"Échec lecture {file_description}: {type(e).__name__}: {e}") from e


def _vectorize_and_resample_30min(df: pd.DataFrame, c_pax: str, c_sch: str, c_ad: str) -> pd.DataFrame:
    """
    Normalise les colonnes Schengen/A-D, crée les 4 colonnes PAX et agrège par 30 minutes.
    Attend une colonne 'DateTime' déjà parsée.
    """
    # Pax numérique
    df["Expected_Pax"] = pd.to_numeric(df[c_pax], errors="coerce").fillna(0.0)

    # Normalisation Schengen & A/D
    sch_raw = df[c_sch].astype(str).strip().str.lower()
    ad_raw = df[c_ad].astype(str).strip().str.lower()

    df["Is_Schengen"] = sch_raw.isin(SCHENGEN_TRUE)
    df["Is_Arrival"] = ad_raw.str.startswith(("a", "arr"))
    df["Is_Departure"] = ad_raw.str.startswith(("d", "dep"))

    # Vectorisation
    pax = df["Expected_Pax"].to_numpy()
    sch = df["Is_Schengen"].to_numpy()
    arr = df["Is_Arrival"].to_numpy()
    dep = df["Is_Departure"].to_numpy()

    df["Pax_Schengen_A"] = np.where(sch & arr, pax, 0.0)
    df["Pax_Schengen_D"] = np.where(sch & dep, pax, 0.0)
    df["Pax_NonSchengen_A"] = np.where(~sch & arr, pax, 0.0)
    df["Pax_NonSchengen_D"] = np.where(~sch & dep, pax, 0.0)

    # Agrégation 30 minutes
    agg = (
        df.set_index("DateTime")
          .resample("30T")[["Pax_Schengen_A", "Pax_Schengen_D", "Pax_NonSchengen_A", "Pax_NonSchengen_D"]]
          .sum()
    )
    return agg


# =========================
# Thread worker
# =========================

class PaxLoaderThread(threading.Thread):
    """Thread pour charger les données PAX (Forecast + Historic) en arrière-plan"""

    def __init__(self, forecast_path: Path, historical_path: Path, session_state_key: str):
        super().__init__(daemon=True)
        self.forecast_path = forecast_path
        self.historical_path = historical_path
        self.session_state_key = session_state_key
        self.result: Optional[Dict[str, Any]] = None
        self.error: Optional[str] = None
        self.progress: Dict[str, Any] = {"current_file": None, "percent": 0}

    def run(self) -> None:
        """Exécute le chargement en arrière-plan"""
        try:
            results: Dict[str, Any] = {
                "forecast": None,
                "historical": None,
                "status": "success",
                "errors": [],
                "tracebacks": {},
            }

            # ---- Forecast ----
            self.progress = {"current_file": "Forecast", "percent": 0}
            try:
                forecast_data, fc_min, fc_max = self._load_pax_uncached(self.forecast_path, "Forecast PAX")
                if forecast_data is not None and not forecast_data.empty:
                    results["forecast"] = {
                        "data": forecast_data,
                        "min_date": fc_min,
                        "max_date": fc_max,
                        "status": "loaded",
                    }
                else:
                    results["forecast"] = {"status": "empty"}
                    results["errors"].append("Forecast: Fichier vide")
            except Exception as e:
                results["forecast"] = {"status": "error", "error": f"{type(e).__name__}: {e}"}
                results["errors"].append(f"Forecast: {type(e).__name__}: {e}")
                results["tracebacks"]["forecast"] = traceback.format_exc()

            self.progress = {"current_file": "Forecast", "percent": 50}

            # ---- Historic ----
            self.progress = {"current_file": "Historic", "percent": 50}
            try:
                historical_data, hist_min, hist_max = self._load_pax_uncached(self.historical_path, "Historic PAX")
                if historical_data is not None and not historical_data.empty:
                    results["historical"] = {
                        "data": historical_data,
                        "min_date": hist_min,
                        "max_date": hist_max,
                        "status": "loaded",
                    }
                else:
                    results["historical"] = {"status": "empty"}
                    results["errors"].append("Historic: Fichier vide")
            except Exception as e:
                results["historical"] = {"status": "error", "error": f"{type(e).__name__}: {e}"}
                results["errors"].append(f"Historic: {type(e).__name__}: {e}")
                results["tracebacks"]["historical"] = traceback.format_exc()

            self.progress = {"current_file": "Historic", "percent": 100}

            # ---- Statut global ----
            fc_loaded = results.get("forecast", {}).get("status") == "loaded"
            hi_loaded = results.get("historical", {}).get("status") == "loaded"
            if fc_loaded and hi_loaded:
                results["status"] = "success"
            elif fc_loaded ^ hi_loaded:
                results["status"] = "partial"
            else:
                results["status"] = "error"

            self.result = results

        except Exception as e:
            self.error = f"{type(e).__name__}: {e}"
            self.result = {
                "status": "error",
                "error": self.error,
                "errors": [self.error],
                "tracebacks": {"thread": traceback.format_exc()},
            }

    # ----------- Core loader (non-caché pour forcer relecture) -----------

    def _load_pax_uncached(self, file_path: Path, file_description: str) -> Tuple[pd.DataFrame, Optional[dt.date], Optional[dt.date]]:
        """Lecture robuste + mapping flexible + normalisation + agrégation 30'."""
        if not file_path.exists():
            raise FileNotFoundError(f"Fichier {file_description} non trouvé : {file_path}")

        # 1) Lecture
        df = _read_table_robust(file_path, file_description)

        # 2) Mapping dynamique des colonnes
        c_time = _pick_present_column(df, COLUMN_CANDIDATES["time"])
        c_pax  = _pick_present_column(df, COLUMN_CANDIDATES["pax"])
        c_sch  = _pick_present_column(df, COLUMN_CANDIDATES["schengen"])
        c_ad   = _pick_present_column(df, COLUMN_CANDIDATES["ad"])

        missing_keys = [k for k, v in {"time": c_time, "pax": c_pax, "schengen": c_sch, "ad": c_ad}.items() if v is None]
        if missing_keys:
            raise KeyError(f"Colonnes manquantes ({file_description}) : {', '.join(missing_keys)}")

        # 3) Datetime tolérant
        work = df.copy()
        work["DateTime"] = _parse_datetime_tolerant(work[c_time])
        work = work.dropna(subset=["DateTime"])
        if work.empty:
            return pd.DataFrame(), None, None

        # 4) Normalisation, vectorisation et agrégation
        agg = _vectorize_and_resample_30min(work, c_pax=c_pax, c_sch=c_sch, c_ad=c_ad)

        if agg.empty:
            return pd.DataFrame(), None, None

        # 5) Min/Max (dates)
        min_date = agg.index.min().date() if not agg.empty else None
        max_date = agg.index.max().date() if not agg.empty else None

        return agg, min_date, max_date


# =========================
# API Streamlit
# =========================

def start_pax_loading(forecast_path: Path, historical_path: Path) -> str:
    """
    Démarre le chargement des données PAX (Forecast + Historic) en arrière-plan.
    Initialise st.session_state et lance le thread.
    Retourne une clé de session (id) du loader.
    """
    # Initialiser l'état
    st.session_state.pax_loading_status = "loading"
    st.session_state.pax_loading_progress = {"current_file": "Démarrage...", "percent": 0}
    st.session_state.pax_loading_error = None
    st.session_state.pax_loading_tracebacks = {}
    st.session_state.pax_loading_elapsed = 0.0

    # Clé unique du loader
    session_key = f"pax_loader_{dt.datetime.now().timestamp()}"
    loader_thread = PaxLoaderThread(forecast_path, historical_path, session_key)

    # Stocker le thread et l'heure de départ
    st.session_state.pax_loader_thread = loader_thread
    st.session_state.pax_loader_start_time = dt.datetime.now()

    # Démarrer
    loader_thread.start()
    return session_key


def check_pax_loading_status() -> str:
    """
    Vérifie l'état du chargement PAX et met à jour st.session_state.
    Retourne: 'idle' | 'loading' | 'success' | 'partial' | 'error'
    """
    if "pax_loader_thread" not in st.session_state:
        return "idle"

    thread: PaxLoaderThread = st.session_state.pax_loader_thread

    # Toujours vivant → en cours
    if thread.is_alive():
        elapsed = (dt.datetime.now() - st.session_state.pax_loader_start_time).total_seconds()
        st.session_state.pax_loading_elapsed = elapsed
        st.session_state.pax_loading_progress = thread.progress
        return "loading"

    # Thread terminé : récupérer le résultat
    if thread.result is not None:
        result = thread.result
        status = result.get("status")

        # Forecast
        fc = result.get("forecast") or {}
        if fc.get("status") == "loaded":
            st.session_state.pax_forecast_data = fc.get("data")
            st.session_state.pax_forecast_min_date = fc.get("min_date")
            st.session_state.pax_forecast_max_date = fc.get("max_date")
            st.session_state.pax_forecast_status = "loaded"
        else:
            st.session_state.pax_forecast_status = fc.get("status", "not_loaded")

        # Historic
        hi = result.get("historical") or {}
        if hi.get("status") == "loaded":
            st.session_state.pax_historical_data = hi.get("data")
            st.session_state.pax_historical_min_date = hi.get("min_date")
            st.session_state.pax_historical_max_date = hi.get("max_date")
            st.session_state.pax_historical_status = "loaded"
        else:
            st.session_state.pax_historical_status = hi.get("status", "not_loaded")

        # Statut global
        st.session_state.pax_loading_status = status
        st.session_state.pax_data_status = "attempted"

        # Erreurs & tracebacks
        st.session_state.pax_loading_error = " | ".join(result.get("errors", [])) or None
        st.session_state.pax_loading_tracebacks = result.get("tracebacks", {}) or {}

        # Nettoyer la référence au thread (libère)
        del st.session_state.pax_loader_thread

        return status

    # Thread terminé mais sans result → erreur stockée ?
    if thread.error is not None:
        st.session_state.pax_loading_status = "error"
        st.session_state.pax_loading_error = thread.error
        # Nettoyage
        del st.session_state.pax_loader_thread
        return "error"

    # Cas limite : devrait rarement arriver
    return "loading"


def get_pax_loading_info() -> Dict[str, Any]:
    """Retourne les informations d'état du chargement pour affichage UI."""
    status = st.session_state.get("pax_loading_status", "idle")
    info: Dict[str, Any] = {
        "status": status,
        "elapsed": st.session_state.get("pax_loading_elapsed", 0.0),
        "error": st.session_state.get("pax_loading_error"),
        "progress": st.session_state.get("pax_loading_progress", {}),
        "forecast_status": st.session_state.get("pax_forecast_status"),
        "historical_status": st.session_state.get("pax_historical_status"),
        "forecast_min": st.session_state.get("pax_forecast_min_date"),
        "forecast_max": st.session_state.get("pax_forecast_max_date"),
        "historical_min": st.session_state.get("pax_historical_min_date"),
        "historical_max": st.session_state.get("pax_historical_max_date"),
        "tracebacks": st.session_state.get("pax_loading_tracebacks", {}),
    }
    return info


def reset_pax_loading() -> None:
    """Réinitialise proprement l'état de chargement PAX (utile pour 'Réessayer')."""
    st.cache_data.clear()
    for k in [
        "pax_loading_status", "pax_loading_progress", "pax_loading_error",
        "pax_loading_elapsed", "pax_loading_tracebacks", "pax_loader_thread",
        "pax_loader_start_time", "pax_data_status",
        "pax_forecast_data", "pax_forecast_min_date", "pax_forecast_max_date", "pax_forecast_status",
        "pax_historical_data", "pax_historical_min_date", "pax_historical_max_date", "pax_historical_status",
    ]:
        if k in st.session_state:
            st.session_state.pop(k, None)
