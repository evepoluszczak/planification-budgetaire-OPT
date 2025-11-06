"""
Moteur de génération de suggestions d'ajustement intelligent
Génère des suggestions d'ajustement d'heures basées sur les données PAX et les objectifs
"""
import streamlit as st
import pandas as pd
import numpy as np
from datetime import date, datetime
from typing import List, Dict, Tuple, Optional, Any
from dataclasses import asdict

from models.suggestion import (
    Suggestion, SuggestionConfig, AjustementPropose,
    create_suggestion_from_row
)
from config.constants import TIME_SLOTS
from core.planning import _ensure_grid, _apply_ops_to_grid
from utils.date_utils import _day_name_fr


def load_pax_data_for_dates(start_date: date, end_date: date) -> pd.DataFrame:
    """
    Charge les données PAX forecast depuis session_state pour une plage de dates

    Args:
        start_date: Date de début
        end_date: Date de fin

    Returns:
        DataFrame avec index datetime et colonnes PAX par zone/flux
    """
    if 'pax_forecast_data' not in st.session_state:
        return pd.DataFrame()

    pax_df = st.session_state.pax_forecast_data

    if pax_df.empty:
        return pd.DataFrame()

    # Filtrer par plage de dates
    # Le DataFrame PAX a un index datetime
    mask = (pax_df.index.date >= start_date) & (pax_df.index.date <= end_date)
    filtered_df = pax_df[mask].copy()

    return filtered_df


def load_and_prepare_grids(
    config: SuggestionConfig,
    year: int,
    start_date: Optional[date] = None,
    end_date: Optional[date] = None,
    max_days: int = 30
) -> pd.DataFrame:
    """
    Charge et prépare les grilles de planification avec données PAX

    Args:
        config: Configuration des suggestions
        year: Année concernée
        start_date: Date de début (optionnel, défaut: aujourd'hui)
        end_date: Date de fin (optionnel, défaut: start_date + max_days)
        max_days: Nombre maximum de jours à analyser (défaut: 30)

    Returns:
        DataFrame consolidé avec colonnes:
        - Date, Jour, Saison, Jour_Type_Global
        - time_slot (période horaire)
        - perimetre
        - effectif_base (nombre d'agents planifiés avant règles)
        - effectif_actuel (nombre d'agents après règles Besoin Jour)
        - pax_schengen, pax_non_schengen, pax_total
        - ratio_pax_per_agent
    """
    from datetime import datetime, timedelta

    bs = st.session_state.get('budget_state', {})
    if not bs or 'calendar_df' not in bs or bs['calendar_df'].empty:
        raise ValueError("Budget state non initialisé. Générez d'abord un budget annuel.")

    # Dates par défaut : limiter à une fenêtre raisonnable
    today = datetime.now().date()
    if start_date is None:
        # Commencer à partir d'aujourd'hui ou début d'année si aujourd'hui n'est pas dans l'année
        start_of_year = date(year, 1, 1)
        end_of_year = date(year, 12, 31)

        if start_of_year <= today <= end_of_year:
            start_date = today
        else:
            start_date = start_of_year

    if end_date is None:
        # Limiter à max_days jours après start_date
        end_date = min(start_date + timedelta(days=max_days), date(year, 12, 31))

    # Sécurité: limiter la plage totale
    days_span = (end_date - start_date).days
    if days_span > max_days:
        end_date = start_date + timedelta(days=max_days)
        st.warning(f"⚠️ Plage limitée à {max_days} jours pour des raisons de performance.")

    # Charger calendar
    calendar_df = bs['calendar_df'].copy()
    calendar_df['Date'] = pd.to_datetime(calendar_df['Date']).dt.date

    # Filtrer par dates
    calendar_df = calendar_df[
        (calendar_df['Date'] >= start_date) &
        (calendar_df['Date'] <= end_date)
    ].copy()

    # Charger données PAX
    pax_df = load_pax_data_for_dates(start_date, end_date)

    # Préparer les grilles AT
    perimetres_at = st.session_state.perimetres.get("AT", [])
    time_slots = TIME_SLOTS
    planning_dict_at = st.session_state.planning_data.get("AT", {})

    # Créer un dictionnaire de lookup PAX pour accès rapide
    pax_lookup = {}
    if not pax_df.empty:
        for idx in pax_df.index:
            date_key = idx.date()
            time_key = idx.time()
            key = (date_key, time_key)
            pax_lookup[key] = {
                'pax_schengen': float(pax_df.loc[idx, 'Pax_Schengen_A'] + pax_df.loc[idx, 'Pax_Schengen_D']),
                'pax_non_schengen': float(pax_df.loc[idx, 'Pax_NonSchengen_A'] + pax_df.loc[idx, 'Pax_NonSchengen_D'])
            }

    # Construire le DataFrame consolidé
    rows = []
    total_days = len(calendar_df)

    # Progress bar
    progress_bar = st.progress(0, text=f"Analyse de {total_days} jours...")

    for day_idx, (_, cal_row) in enumerate(calendar_df.iterrows()):
        date_val = cal_row['Date']
        jour = cal_row['Jour']
        saison = cal_row['Saison']
        jt = cal_row['Jour_Type_Global']

        # Mise à jour progress bar
        if day_idx % 5 == 0:  # Mettre à jour tous les 5 jours
            progress = (day_idx + 1) / total_days
            progress_bar.progress(progress, text=f"Analyse jour {day_idx + 1}/{total_days}...")

        # Vérifier si date verrouillée
        if config.is_locked(date_val=date_val):
            continue

        # Charger grilles base et effective
        _, base_grid = _ensure_grid(planning_dict_at, jt, perimetres_at, time_slots)
        effective_grid = _apply_ops_to_grid(base_grid, date_val, jour, saison, category="AT")

        # Pour chaque time slot
        for slot_idx, slot in enumerate(time_slots):
            # Pour chaque périmètre
            for perimetre in perimetres_at:
                # Vérifier si périmètre verrouillé
                if config.is_locked(perimetre=perimetre):
                    continue

                effectif_base = base_grid.loc[perimetre, slot]
                effectif_actuel = effective_grid.loc[perimetre, slot]

                # Lookup PAX rapide via dictionnaire
                pax_schengen = 0.0
                pax_non_schengen = 0.0
                pax_total = 0.0

                if pax_lookup:
                    from datetime import datetime
                    slot_time = datetime.strptime(slot, "%H:%M").time()
                    key = (date_val, slot_time)

                    if key in pax_lookup:
                        pax_data = pax_lookup[key]
                        pax_schengen = pax_data['pax_schengen']
                        pax_non_schengen = pax_data['pax_non_schengen']
                        pax_total = pax_schengen + pax_non_schengen

                # Calculer ratio PAX/agent
                ratio_pax_per_agent = 0.0
                if effectif_actuel > 0:
                    ratio_pax_per_agent = pax_total / effectif_actuel

                rows.append({
                    'date': date_val,
                    'jour': jour,
                    'saison': saison,
                    'jour_type': jt,
                    'slot_idx': slot_idx,
                    'time_slot': slot,
                    'perimetre': perimetre,
                    'effectif_base': effectif_base,
                    'effectif_actuel': effectif_actuel,
                    'pax_schengen': pax_schengen,
                    'pax_non_schengen': pax_non_schengen,
                    'pax_total': pax_total,
                    'ratio_pax_per_agent': ratio_pax_per_agent
                })

    # Finaliser progress bar
    progress_bar.progress(1.0, text="Analyse terminée !")
    progress_bar.empty()  # Nettoyer

    df_consolidated = pd.DataFrame(rows)
    return df_consolidated


def compute_slot_features(df: pd.DataFrame, config: SuggestionConfig) -> pd.DataFrame:
    """
    Calcule les features pour chaque slot (intensité PAX, ratio, variance)

    Args:
        df: DataFrame consolidé des grilles
        config: Configuration

    Returns:
        DataFrame enrichi avec colonnes de features
    """
    df = df.copy()

    # 1. Intensité PAX normalisée (0-1)
    # Plus le PAX est faible, plus le score est élevé (favorable au retrait)
    max_pax = df['pax_total'].max()
    if max_pax > 0:
        df['pax_intensity_norm'] = 1.0 - (df['pax_total'] / max_pax)
    else:
        df['pax_intensity_norm'] = 0.5  # Valeur neutre si pas de PAX

    # 2. Efficacité ratio PAX/agent
    # Plus le ratio est faible (surplus d'agents), plus le score est élevé
    max_ratio = df['ratio_pax_per_agent'].max()
    if max_ratio > 0:
        df['ratio_efficiency_norm'] = 1.0 - (df['ratio_pax_per_agent'] / max_ratio)
    else:
        df['ratio_efficiency_norm'] = 0.5

    # 3. Stabilité (variance sur la semaine pour même slot/périmètre)
    # Calcul de la variance par (jour_semaine, time_slot, perimetre)
    df['variance_score'] = 0.5  # Par défaut neutre

    # Grouper par (jour, time_slot, perimetre) et calculer variance PAX
    grouped = df.groupby(['jour', 'time_slot', 'perimetre'])
    for name, group in grouped:
        if len(group) > 1:
            variance = group['pax_total'].var()
            # Variance faible = stable = bon candidat pour retrait
            # Normaliser : variance élevée = score faible
            max_variance = df.groupby(['jour', 'time_slot', 'perimetre'])['pax_total'].var().max()
            if max_variance > 0 and not np.isnan(variance):
                stability_score = 1.0 - (variance / max_variance)
                df.loc[group.index, 'variance_score'] = stability_score

    return df


def score_slots(
    df: pd.DataFrame,
    config: SuggestionConfig,
    objective: str = 'remove'
) -> pd.DataFrame:
    """
    Calcule un score de priorité pour chaque slot

    Args:
        df: DataFrame avec features
        config: Configuration avec pondérations
        objective: 'remove' (retirer des heures) ou 'add' (ajouter des heures)

    Returns:
        DataFrame avec colonne 'score' (0-1, plus élevé = meilleure priorité)
    """
    df = df.copy()

    # Récupérer les pondérations
    w_pax = config.weights.get('pax_intensity', 0.40)
    w_ratio = config.weights.get('ratio_efficiency', 0.35)
    w_var = config.weights.get('variance_stability', 0.25)

    if objective == 'remove':
        # Pour retrait : privilégier faible PAX, faible ratio, faible variance
        df['score'] = (
            w_pax * df['pax_intensity_norm'] +
            w_ratio * df['ratio_efficiency_norm'] +
            w_var * df['variance_score']
        )
    else:
        # Pour ajout : inverser les priorités (privilégier forte PAX, fort ratio)
        df['score'] = (
            w_pax * (1.0 - df['pax_intensity_norm']) +
            w_ratio * (1.0 - df['ratio_efficiency_norm']) +
            w_var * df['variance_score']
        )

    # Appliquer pénalités pour événements spéciaux (si implémenté)
    # TODO: gérer les événements dans V1.1

    # Filtrer les slots invalides (effectif <= min après retrait)
    if objective == 'remove':
        df['eligible'] = df['effectif_actuel'] > config.min_agents_per_slot
    else:
        if config.max_agents_per_slot is not None:
            df['eligible'] = df['effectif_actuel'] < config.max_agents_per_slot
        else:
            df['eligible'] = True

    return df


def allocate_delta_greedy(
    df: pd.DataFrame,
    target_delta_hours: float,
    target_delta_chf: float,
    config: SuggestionConfig,
    category: str = 'AT',
    hourly_rate: float = 45.50
) -> List[Suggestion]:
    """
    Alloue le delta d'heures/CHF de manière greedy en priorisant les meilleurs scores

    Args:
        df: DataFrame scoré avec colonnes score, eligible
        target_delta_hours: Objectif en heures (négatif pour retrait)
        target_delta_chf: Objectif en CHF (négatif pour retrait)
        config: Configuration
        category: Catégorie de personnel
        hourly_rate: Tarif horaire

    Returns:
        Liste de Suggestion
    """
    objective = 'remove' if target_delta_hours < 0 else 'add'
    target_hours_abs = abs(target_delta_hours)
    target_chf_abs = abs(target_delta_chf)

    # Filtrer slots éligibles et trier par score décroissant
    df_eligible = df[df['eligible']].copy()
    df_sorted = df_eligible.sort_values('score', ascending=False)

    suggestions = []
    accumulated_hours = 0.0
    accumulated_chf = 0.0

    # Greedy allocation
    for _, row in df_sorted.iterrows():
        # Vérifier si objectif atteint
        if config.respect_strict_delta:
            # Priorité heures
            if accumulated_hours >= target_hours_abs:
                break
        else:
            # Priorité CHF
            if accumulated_chf >= target_chf_abs:
                break

        # Déterminer combien d'agents on peut retirer/ajouter
        if objective == 'remove':
            # On peut retirer jusqu'à (effectif_actuel - min_agents)
            max_removable = row['effectif_actuel'] - config.min_agents_per_slot
            agents_to_remove = min(max_removable, 1)  # V1: retirer 1 agent à la fois

            if agents_to_remove <= 0:
                continue

            delta_hours_slot = -agents_to_remove * 0.5  # 0.5h par slot de 30min
            delta_chf_slot = delta_hours_slot * hourly_rate

        else:
            # Ajout
            if config.max_agents_per_slot is not None:
                max_addable = config.max_agents_per_slot - row['effectif_actuel']
            else:
                max_addable = 1  # V1: ajouter 1 agent à la fois

            agents_to_add = min(max_addable, 1)

            if agents_to_add <= 0:
                continue

            delta_hours_slot = agents_to_add * 0.5
            delta_chf_slot = delta_hours_slot * hourly_rate

        # Créer suggestion
        periode_str = f"{row['time_slot']}-{_get_next_slot(row['time_slot'])}"

        motifs = []
        if row['pax_total'] > 0:
            motifs.append(f"PAX prévu: {row['pax_total']:.0f}")
        if row['ratio_pax_per_agent'] > 0:
            motifs.append(f"Ratio PAX/agent: {row['ratio_pax_per_agent']:.1f}")
        motifs.append(f"Score de priorité: {row['score']:.2f}")

        conflits = []
        if row['effectif_actuel'] <= config.min_agents_per_slot + 1 and objective == 'remove':
            conflits.append("⚠ Proche du minimum d'agents")

        suggestion = Suggestion(
            date=row['date'],
            periode=periode_str,
            perimetre=row['perimetre'],
            categorie=category,
            delta_hours=delta_hours_slot,
            delta_chf=delta_chf_slot,
            score=row['score'],
            motifs=motifs,
            conflits=conflits,
            slot_indices=[row['slot_idx']]
        )

        suggestions.append(suggestion)
        accumulated_hours += abs(delta_hours_slot)
        accumulated_chf += abs(delta_chf_slot)

    return suggestions


def _get_next_slot(slot: str) -> str:
    """Helper pour obtenir le slot suivant (ex: 06:00 -> 06:30)"""
    time_slots = TIME_SLOTS
    try:
        idx = time_slots.index(slot)
        if idx < len(time_slots) - 1:
            return time_slots[idx + 1]
        else:
            # Dernier slot de la journée
            return "23:59"
    except ValueError:
        return slot


def generate_suggestions(
    ajustement: AjustementPropose,
    config: SuggestionConfig,
    year: int,
    max_days: int = 30
) -> Dict[str, List[Suggestion]]:
    """
    Fonction principale : génère les suggestions d'ajustement

    Args:
        ajustement: Paquet d'ajustement depuis le Simulateur
        config: Configuration des suggestions
        year: Année concernée
        max_days: Nombre maximum de jours à analyser (défaut: 30)

    Returns:
        Dictionnaire {category: [Suggestion, ...]}
    """
    results = {}

    # V1: Seulement AT
    category = 'AT'

    # Récupérer delta pour AT
    delta_hours = ajustement.get_category_delta_hours(category)
    delta_chf = ajustement.get_category_delta_chf(category)

    if delta_hours == 0 and delta_chf == 0:
        return {category: []}

    # Récupérer tarif horaire
    personnel_df = st.session_state.get('personnel', pd.DataFrame())
    hourly_rate = 45.50  # Valeur par défaut

    cost_mapping = st.session_state.get('cost_mapping', {})
    personnel_type = cost_mapping.get(category)

    if personnel_type and not personnel_df.empty:
        rate_row = personnel_df[personnel_df['Type'] == personnel_type]
        if not rate_row.empty:
            try:
                hourly_rate = float(rate_row['Coût Horaire'].iloc[0])
            except Exception:
                pass

    # Appliquer les verrous depuis ajustement
    config_with_locks = SuggestionConfig(
        min_block_hours=config.min_block_hours,
        min_agents_per_slot=config.min_agents_per_slot,
        max_agents_per_slot=config.max_agents_per_slot,
        penalty_events=config.penalty_events,
        weights=config.weights.copy(),
        locked_categories=ajustement.locks.get('categories', []),
        locked_perimetres=ajustement.locks.get('perimetres', []),
        locked_dates=ajustement.locks.get('dates', []),
        respect_strict_delta=config.respect_strict_delta
    )

    # 1. Charger et préparer grilles avec PAX (avec limite de jours)
    df_consolidated = load_and_prepare_grids(config_with_locks, year, max_days=max_days)

    if df_consolidated.empty:
        return {category: []}

    # 2. Calculer features
    df_with_features = compute_slot_features(df_consolidated, config_with_locks)

    # 3. Scorer les slots
    objective = 'remove' if delta_hours < 0 else 'add'
    df_scored = score_slots(df_with_features, config_with_locks, objective=objective)

    # 4. Allouer via greedy
    suggestions = allocate_delta_greedy(
        df_scored,
        delta_hours,
        delta_chf,
        config_with_locks,
        category=category,
        hourly_rate=hourly_rate
    )

    results[category] = suggestions

    return results


def apply_suggestions(
    suggestions: List[Suggestion],
    category: str = 'AT'
) -> Dict[str, Any]:
    """
    Applique les suggestions en créant des règles Besoin Jour

    Args:
        suggestions: Liste de suggestions à appliquer
        category: Catégorie concernée

    Returns:
        Dictionnaire avec résultat de l'application (totaux, règles créées)
    """
    if not suggestions:
        return {'success': False, 'message': 'Aucune suggestion à appliquer'}

    # Grouper par date et périmètre pour créer des règles cohérentes
    rules_created = []

    for sugg in suggestions:
        # Extraire période
        try:
            start_time, end_time = sugg.periode.split('-')
        except Exception:
            continue

        # Déterminer valeur (0 pour retrait, 1 pour ajout)
        # Note: En V1, on ne fait que des retraits
        value = 0 if sugg.delta_hours < 0 else 1

        # Créer règle
        rule = {
            'category': category,
            'start': sugg.date,
            'end': sugg.date,
            'jours': [],  # Pas de filtre jour
            'saisons': [],  # Pas de filtre saison
            'rows': [sugg.perimetre],
            'start_col': start_time,
            'end_col': end_time,
            'value': value
        }

        rules_created.append(rule)

    # Ajouter les règles à session_state
    if 'besoin_jour_ops' not in st.session_state:
        st.session_state.besoin_jour_ops = []

    st.session_state.besoin_jour_ops.extend(rules_created)

    # Calculer totaux
    total_hours = sum(s.delta_hours for s in suggestions)
    total_chf = sum(s.delta_chf for s in suggestions)

    return {
        'success': True,
        'rules_created': len(rules_created),
        'totaux': {
            'hours': total_hours,
            'chf': total_chf
        }
    }
