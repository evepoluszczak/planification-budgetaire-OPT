"""
Chargement des données PAX et facturation AT
"""
from pathlib import Path
import datetime as dt
import re
import pandas as pd
import numpy as np
import streamlit as st


@st.cache_data
def load_pax_data(file_path: Path, file_description: str):
    """
    Charge et transforme les données passagers depuis un fichier local.
    Retourne (DataFrame agrégé, date_min, date_max).
    """
    if not file_path.exists():
        st.warning(f"Fichier {file_description} non trouvé : {file_path}")
        return pd.DataFrame(), None, None

    try:
        # Lecture du fichier (CSV ou Excel)
        if file_path.suffix.lower() == '.csv':
            df = pd.read_csv(file_path, delimiter=";")
        elif file_path.suffix.lower() in ['.xlsx', '.xls']:
            try:
                df = pd.read_excel(file_path, engine='openpyxl')
            except ImportError:
                st.error("Lecture Excel nécessite 'openpyxl'. Installez-le.")
                return pd.DataFrame(), None, None
            except Exception as e_read_excel:
                st.error(f"Erreur lecture Excel ({file_path}): {e_read_excel}")
                return pd.DataFrame(), None, None
        else:
            st.error(f"Format non supporté: {file_path.suffix}")
            return pd.DataFrame(), None, None

        # Conversion DateTime
        time_col_name = 'Local Schedule Time'
        try:
            df['DateTime'] = pd.to_datetime(
                df[time_col_name],
                format='%d.%m.%Y %H:%M',
                errors='coerce'
            )
            if df['DateTime'].isnull().sum() > len(df) / 2:
                st.warning(f"Format incorrect pour '{time_col_name}'. Tentative générique.")
                df['DateTime'] = pd.to_datetime(df[time_col_name], errors='coerce')
        except KeyError as e:
            st.error(f"Colonne '{time_col_name}' manquante : {e}")
            return pd.DataFrame(), None, None
        except ValueError:
            st.warning(f"Format invalide pour '{time_col_name}'. Tentative générique.")
            try:
                df['DateTime'] = pd.to_datetime(df[time_col_name], errors='coerce')
            except Exception as e_dt_generic:
                st.error(f"Échec conversion de '{time_col_name}' : {e_dt_generic}")
                return pd.DataFrame(), None, None
        except Exception as e_dt:
            st.error(f"Erreur inattendue conversion '{time_col_name}' : {e_dt}")
            return pd.DataFrame(), None, None

        # Nettoyage
        pax_col = 'Expected Pax'
        schengen_col = 'Schengen Flight'
        arrdep_col = 'Arrival - Departure Code'

        try:
            df[pax_col] = pd.to_numeric(df[pax_col], errors='coerce').fillna(0)
            if not all(col in df.columns for col in [schengen_col, arrdep_col]):
                missing = [col for col in [schengen_col, arrdep_col] if col not in df.columns]
                st.error(f"Colonnes manquantes : {', '.join(missing)}")
                return pd.DataFrame(), None, None
            df = df.dropna(subset=['DateTime'])
        except KeyError as e:
            st.error(f"Colonne manquante : {e}")
            return pd.DataFrame(), None, None

        # Dates Min/Max
        if df.empty:
            st.warning(f"Fichier {file_description} vide après nettoyage.")
            return pd.DataFrame(), None, None
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

    except FileNotFoundError:
        st.error(f"Fichier {file_description} non trouvé : {file_path}")
        return pd.DataFrame(), None, None
    except Exception as e:
        st.error(f"Erreur chargement {file_description} : {e}")
        import traceback
        st.error(traceback.format_exc())
        return pd.DataFrame(), None, None


@st.cache_data
def load_facturation_at_month(year: int, month: int, factu_dir: Path) -> pd.DataFrame:
    """
    Charge le fichier 'Facturation Lot A mm.yyyy.xlsx' pour le mois/année donnés.
    Détecte automatiquement la ligne d'en-têtes.
    """
    file_path = factu_dir / f"Facturation Lot A {month:02d}.{year}.xlsx"
    if not file_path.exists():
        st.info(f"Fichier facturation introuvable: {file_path.name}")
        return pd.DataFrame()

    try:
        df = None
        found_header = False

        # Tester les 5 premières lignes pour trouver les bonnes colonnes
        for i in range(5):
            temp = pd.read_excel(file_path, engine="openpyxl", header=i, nrows=5)
            cols = [str(c).strip() for c in temp.columns]
            if "Date ouvrable" in cols and "Heures" in cols:
                df = pd.read_excel(file_path, engine="openpyxl", header=i)
                df.columns = cols
                found_header = True
                break

        if not found_header:
            st.warning(
                f"Colonnes attendues ('Date ouvrable', 'Heures') non trouvées "
                f"dans {file_path.name}."
            )
            return pd.DataFrame()

        return df

    except Exception as e:
        st.warning(f"Erreur chargement {file_path.name} : {e}")
        return pd.DataFrame()


def get_billed_hours_for_date(date_obj: dt.date, factu_dir: Path) -> float:
    """
    Récupère les heures facturées pour une date donnée.
    Cherche la ligne 'Total dd.mm.yyyy' dans le fichier mensuel correspondant.
    Retourne 0.0 si non trouvé.
    """
    df = load_facturation_at_month(date_obj.year, date_obj.month, factu_dir)
    if df.empty:
        return 0.0

    if "Date ouvrable" not in df.columns or "Heures" not in df.columns:
        st.warning("Colonnes attendues manquantes.")
        return 0.0

    date_str = date_obj.strftime("%d.%m.%Y")
    target_exact = f"Total {date_str}"

    s = df["Date ouvrable"].astype(str).str.strip()

    # Correspondance exacte
    match = df[s == target_exact]

    # Tolérer les espaces variables
    if match.empty:
        pattern = rf"^Total\s*{re.escape(date_str)}$"
        match = df[s.str.match(pattern, na=False)]

    # Si Excel a stocké une vraie date
    if match.empty:
        def normalize_total(v):
            try:
                d = pd.to_datetime(v, dayfirst=True, errors="raise")
                return f"Total {d.strftime('%d.%m.%Y')}"
            except Exception:
                return str(v).strip()
        s2 = df["Date ouvrable"].apply(normalize_total)
        match = df[s2 == target_exact]

    if match.empty:
        return 0.0

    from utils.helpers import _to_float_hours
    heures = match["Heures"].apply(_to_float_hours).sum()
    return float(heures)


def _daily_pax_total(pax_df_30min: pd.DataFrame, date_: dt.date, flux: str = "Tous") -> float:
    """Calcule le total de passagers pour une date et un flux donnés"""
    if pax_df_30min is None or pax_df_30min.empty:
        return 0.0
    day = pax_df_30min[pax_df_30min.index.date == date_]
    if day.empty:
        return 0.0

    if flux == "Arrivée":
        total = (day.get("Pax_Schengen_A", 0).fillna(0) +
                day.get("Pax_NonSchengen_A", 0).fillna(0)).sum()
    elif flux == "Départ":
        total = (day.get("Pax_Schengen_D", 0).fillna(0) +
                day.get("Pax_NonSchengen_D", 0).fillna(0)).sum()
    else:
        total = (
            day.get("Pax_Schengen_A", 0).fillna(0) +
            day.get("Pax_Schengen_D", 0).fillna(0) +
            day.get("Pax_NonSchengen_A", 0).fillna(0) +
            day.get("Pax_NonSchengen_D", 0).fillna(0)
        ).sum()
    return float(total)


def estimate_at_hours_from_pax_variation(
    historical_date: dt.date,
    forecast_date: dt.date,
    factu_dir: Path
) -> dict:
    """
    Calcule l'estimation des heures AT basée sur la variation PAX.
    Retourne un dictionnaire avec les métriques.
    """
    from utils.helpers import _round_half

    heures_hist = get_billed_hours_for_date(historical_date, factu_dir)

    hist_df = st.session_state.get("pax_historical_data", pd.DataFrame())
    fc_df = st.session_state.get("pax_forecast_data", pd.DataFrame())

    pax_hist = _daily_pax_total(hist_df, historical_date)
    pax_fc = _daily_pax_total(fc_df, forecast_date)

    facteur = (pax_fc / pax_hist) if pax_hist > 0 else None
    heures_estimees = _round_half(heures_hist * facteur) if facteur is not None else 0.0

    return {
        "heures_hist": heures_hist,
        "pax_hist": pax_hist,
        "pax_fc": pax_fc,
        "facteur": facteur,
        "heures_estimees": heures_estimees
    }
