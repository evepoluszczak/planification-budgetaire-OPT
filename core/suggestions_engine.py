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
    category: str = 'AT',
    start_date: Optional[date] = None,
    end_date: Optional[date] = None,
    max_days: int = 30
) -> pd.DataFrame:
    """
    Charge et prépare les grilles de planification avec données PAX

    Args:
        config: Configuration des suggestions
        year: Année concernée
        category: Catégorie de personnel (AT, PP, PE, Admin, Support)
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
        - pax_schengen, pax_non_schengen, pax_total (seulement pour AT)
        - ratio_pax_per_agent (seulement pour AT)
    """
    from datetime import datetime, timedelta

    bs = st.session_state.get('budget_state', {})
    if not bs or 'calendar_df' not in bs or bs['calendar_df'].empty:
        raise ValueError("Budget state non initialisé. Générez d'abord un budget annuel.")

    # Dates par défaut : limiter à une fenêtre raisonnable
    today = datetime.now().date()
    start_of_year = date(year, 1, 1)
    end_of_year = date(year, 12, 31)

    if start_date is None:
        # Commencer à partir d'aujourd'hui si dans l'année, sinon début d'année
        if start_of_year <= today <= end_of_year:
            start_date = today
        else:
            # Si l'année du budget est dans le futur, commencer au début
            if year > today.year:
                start_date = start_of_year
            # Si l'année du budget est dans le passé, commencer quand même au début
            else:
                start_date = start_of_year

    if end_date is None:
        # Limiter à max_days jours après start_date
        end_date = min(start_date + timedelta(days=max_days), end_of_year)

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

    # Charger données PAX (seulement pour AT)
    pax_df = pd.DataFrame()
    if category == 'AT':
        pax_df = load_pax_data_for_dates(start_date, end_date)

    # Préparer les grilles pour la catégorie spécifiée
    perimetres = st.session_state.perimetres.get(category, [])
    time_slots = TIME_SLOTS
    planning_dict = st.session_state.planning_data.get(category, {})

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
        # Pour les catégories non-AT, utiliser "Default" comme jour-type
        jt_key = jt if category == 'AT' else 'Default'
        _, base_grid = _ensure_grid(planning_dict, jt_key, perimetres, time_slots)
        effective_grid = _apply_ops_to_grid(base_grid, date_val, jour, saison, category=category)

        # Pour chaque time slot
        for slot_idx, slot in enumerate(time_slots):
            # Pour chaque périmètre
            for perimetre in perimetres:
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

                # Récupérer la pénalité événement depuis calendar_df
                event_penalty = 0.0
                if 'Event_Penalty' in cal_row and not pd.isna(cal_row['Event_Penalty']):
                    event_penalty = float(cal_row['Event_Penalty'])

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
                    'ratio_pax_per_agent': ratio_pax_per_agent,
                    'event_penalty': event_penalty
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
    # ratio_pax_per_agent = PAX / Agent (combien de passagers par agent)
    # - Ratio FAIBLE (peu de PAX par agent) = potentiel sureffectif → score ÉLEVÉ pour retrait
    # - Ratio ÉLEVÉ (beaucoup de PAX par agent) = agents occupés → score FAIBLE pour retrait
    # Inversé pour l'ajout : ratio élevé → besoin d'agents → score élevé pour ajout
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

    # === FILTRE STRICT : Bloquer les événements critiques/majeurs ===
    # Les événements avec pénalité >= 0.7 sont EXCLUS complètement
    # (critical=1.0, major=0.8 sont bloqués ; minor=0.3 est gardé)
    EVENT_BLOCK_THRESHOLD = 0.7

    if 'event_penalty' in df.columns:
        nb_slots_before = len(df)
        df = df[df['event_penalty'] < EVENT_BLOCK_THRESHOLD].copy()
        nb_slots_after = len(df)

        if nb_slots_before > nb_slots_after:
            nb_blocked = nb_slots_before - nb_slots_after
            # Note: ce message sera visible dans les diagnostics si besoin
            # st.info(f"🚫 {nb_blocked} slot(s) bloqué(s) par des événements critiques/majeurs")

    if df.empty:
        # Tous les slots ont été filtrés par des événements critiques
        return df

    # Récupérer les pondérations
    w_pax = config.weights.get('pax_intensity', 0.40)
    w_ratio = config.weights.get('ratio_efficiency', 0.35)
    w_var = config.weights.get('variance_stability', 0.25)
    w_events = config.weights.get('events_penalty', 0.10)  # Poids pour la pénalité événements

    # Normaliser les pénalités événements (celles qui n'ont pas été bloquées)
    if 'event_penalty' in df.columns:
        events_penalty = df['event_penalty'].clip(0, 1)
    else:
        events_penalty = 0.0

    if objective == 'remove':
        # Pour retrait : privilégier faible PAX, faible ratio, faible variance
        # et pénaliser les dates avec événements (même mineurs)
        df['score'] = (
            w_pax * df['pax_intensity_norm'] +
            w_ratio * df['ratio_efficiency_norm'] +
            w_var * df['variance_score'] -
            w_events * events_penalty  # Réduire le score pour les événements
        )
    else:
        # Pour ajout : inverser les priorités (privilégier forte PAX, fort ratio)
        # et pénaliser les dates avec événements
        df['score'] = (
            w_pax * (1.0 - df['pax_intensity_norm']) +
            w_ratio * (1.0 - df['ratio_efficiency_norm']) +
            w_var * df['variance_score'] -
            w_events * events_penalty  # Réduire le score pour les événements
        )

    # Clipper le score entre 0 et 1
    df['score'] = df['score'].clip(0, 1)

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


def consolidate_suggestions(suggestions: List[Suggestion]) -> List[Suggestion]:
    """
    Regroupe les suggestions consécutives pour simplifier l'affichage et l'application

    Étape 1: Regroupe les créneaux consécutifs pour même (date, périmètre)
    Étape 2: Regroupe les périmètres pour même (date, plage_horaire)

    Args:
        suggestions: Liste de suggestions brutes

    Returns:
        Liste de suggestions consolidées
    """
    if not suggestions:
        return suggestions

    from datetime import datetime, timedelta

    # Trier par date, périmètre, puis slot_indices
    suggestions_sorted = sorted(
        suggestions,
        key=lambda s: (s.date, s.perimetre, min(s.slot_indices) if s.slot_indices else 0)
    )

    # Étape 1: Regrouper créneaux consécutifs par (date, périmètre)
    consolidated_step1 = []
    current_group = None

    for sugg in suggestions_sorted:
        if current_group is None:
            # Première suggestion
            current_group = {
                'date': sugg.date,
                'perimetre': sugg.perimetre,
                'categorie': sugg.categorie,
                'delta_hours': sugg.delta_hours,
                'delta_chf': sugg.delta_chf,
                'score': sugg.score,
                'motifs': sugg.motifs.copy(),
                'conflits': sugg.conflits.copy(),
                'slot_indices': sugg.slot_indices.copy() if sugg.slot_indices else [],
                'start_time': sugg.periode.split('-')[0],
                'end_time': sugg.periode.split('-')[1]
            }
        else:
            # Vérifier si consécutif
            same_date_perimetre = (
                sugg.date == current_group['date'] and
                sugg.perimetre == current_group['perimetre']
            )

            # Vérifier si les slots sont consécutifs
            consecutive = False
            if same_date_perimetre and sugg.slot_indices and current_group['slot_indices']:
                last_slot_idx = max(current_group['slot_indices'])
                first_new_slot_idx = min(sugg.slot_indices)
                consecutive = (first_new_slot_idx == last_slot_idx + 1)

            if same_date_perimetre and consecutive:
                # Fusionner avec le groupe actuel
                current_group['delta_hours'] += sugg.delta_hours
                current_group['delta_chf'] += sugg.delta_chf
                current_group['score'] = max(current_group['score'], sugg.score)  # Garder meilleur score
                current_group['slot_indices'].extend(sugg.slot_indices)
                current_group['end_time'] = sugg.periode.split('-')[1]

                # Fusionner motifs uniques
                for motif in sugg.motifs:
                    if motif not in current_group['motifs']:
                        current_group['motifs'].append(motif)
                for conflit in sugg.conflits:
                    if conflit not in current_group['conflits']:
                        current_group['conflits'].append(conflit)
            else:
                # Créer suggestion consolidée du groupe précédent
                consolidated_step1.append(Suggestion(
                    date=current_group['date'],
                    periode=f"{current_group['start_time']}-{current_group['end_time']}",
                    perimetre=current_group['perimetre'],
                    categorie=current_group['categorie'],
                    delta_hours=current_group['delta_hours'],
                    delta_chf=current_group['delta_chf'],
                    score=current_group['score'],
                    motifs=current_group['motifs'],
                    conflits=current_group['conflits'],
                    slot_indices=current_group['slot_indices']
                ))

                # Commencer nouveau groupe
                current_group = {
                    'date': sugg.date,
                    'perimetre': sugg.perimetre,
                    'categorie': sugg.categorie,
                    'delta_hours': sugg.delta_hours,
                    'delta_chf': sugg.delta_chf,
                    'score': sugg.score,
                    'motifs': sugg.motifs.copy(),
                    'conflits': sugg.conflits.copy(),
                    'slot_indices': sugg.slot_indices.copy() if sugg.slot_indices else [],
                    'start_time': sugg.periode.split('-')[0],
                    'end_time': sugg.periode.split('-')[1]
                }

    # Ajouter le dernier groupe
    if current_group:
        consolidated_step1.append(Suggestion(
            date=current_group['date'],
            periode=f"{current_group['start_time']}-{current_group['end_time']}",
            perimetre=current_group['perimetre'],
            categorie=current_group['categorie'],
            delta_hours=current_group['delta_hours'],
            delta_chf=current_group['delta_chf'],
            score=current_group['score'],
            motifs=current_group['motifs'],
            conflits=current_group['conflits'],
            slot_indices=current_group['slot_indices']
        ))

    # Étape 2: Regrouper par (date, plage_horaire) pour fusionner les périmètres
    # Grouper par date et période
    period_groups = {}
    for sugg in consolidated_step1:
        key = (sugg.date, sugg.periode)
        if key not in period_groups:
            period_groups[key] = []
        period_groups[key].append(sugg)

    consolidated_final = []
    for (date_val, periode), group in period_groups.items():
        if len(group) == 1:
            # Un seul périmètre, garder tel quel
            consolidated_final.append(group[0])
        else:
            # Plusieurs périmètres, fusionner
            perimetres = [s.perimetre for s in group]
            total_delta_hours = sum(s.delta_hours for s in group)
            total_delta_chf = sum(s.delta_chf for s in group)
            avg_score = sum(s.score for s in group) / len(group)

            all_motifs = []
            all_conflits = []
            all_slot_indices = []
            for s in group:
                all_motifs.extend(s.motifs)
                all_conflits.extend(s.conflits)
                if s.slot_indices:
                    all_slot_indices.extend(s.slot_indices)

            # Dédupliquer
            all_motifs = list(dict.fromkeys(all_motifs))
            all_conflits = list(dict.fromkeys(all_conflits))

            # Créer périmètre groupé
            perimetre_str = ", ".join(perimetres)

            consolidated_final.append(Suggestion(
                date=date_val,
                periode=periode,
                perimetre=perimetre_str,
                categorie=group[0].categorie,
                delta_hours=total_delta_hours,
                delta_chf=total_delta_chf,
                score=avg_score,
                motifs=all_motifs,
                conflits=all_conflits,
                slot_indices=list(set(all_slot_indices)) if all_slot_indices else None
            ))

    # Re-trier par date et période
    consolidated_final.sort(key=lambda s: (s.date, s.periode))

    return consolidated_final


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

    # Récupérer les catégories depuis la distribution de l'ajustement
    # (uniquement les catégories sélectionnées par l'utilisateur dans le simulateur)
    if not ajustement.distribution:
        # Pas de distribution définie, retourner vide
        return results

    # Boucler sur les catégories qui ont un ajustement dans la distribution
    for category in ajustement.distribution.keys():
        # Vérifier que la catégorie existe dans la configuration
        if category not in st.session_state.get('perimetres', {}):
            st.warning(f"⚠️ Catégorie '{category}' dans l'ajustement mais non définie dans la configuration. Ignorée.")
            results[category] = []
            continue

        # Récupérer delta pour cette catégorie
        delta_hours = ajustement.get_category_delta_hours(category)
        delta_chf = ajustement.get_category_delta_chf(category)

        if delta_hours == 0 and delta_chf == 0:
            # Pas d'ajustement nécessaire pour cette catégorie
            results[category] = []
            continue

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
        df_consolidated = load_and_prepare_grids(config_with_locks, year, category=category, max_days=max_days)

        # Stocker diagnostics dans session_state
        if 'suggestions_diagnostics' not in st.session_state:
            st.session_state.suggestions_diagnostics = []

        diagnostics = []

        if df_consolidated.empty:
            diagnostics.append(("error", f"Aucune donnée de planification trouvée pour {category} sur la période analysée."))
            st.session_state.suggestions_diagnostics = diagnostics
            results[category] = []
            continue

        # Diagnostic 1
        nb_days = len(df_consolidated['date'].unique())
        nb_slots = len(df_consolidated)
        diagnostics.append(("info", f"[{category}] Données chargées : {nb_slots} slots analysés sur {nb_days} jours"))

        # 2. Calculer features
        df_with_features = compute_slot_features(df_consolidated, config_with_locks)

        # 3. Scorer les slots
        objective = 'remove' if delta_hours < 0 else 'add'
        df_scored = score_slots(df_with_features, config_with_locks, objective=objective)

        # Diagnostic 2
        eligible_count = df_scored['eligible'].sum() if 'eligible' in df_scored.columns else 0
        diagnostics.append(("info", f"[{category}] Slots éligibles : {eligible_count} / {len(df_scored)} (objectif: {objective}, delta: {delta_hours:+.1f}h / {delta_chf:+.0f} CHF)"))

        if eligible_count == 0:
            diagnostics.append(("warning", f"[{category}] Aucun slot éligible trouvé. Vérifiez les contraintes (min_agents={config_with_locks.min_agents_per_slot})."))
            st.session_state.suggestions_diagnostics = diagnostics
            results[category] = []
            continue

        # 4. Allouer via greedy
        suggestions = allocate_delta_greedy(
            df_scored,
            delta_hours,
            delta_chf,
            config_with_locks,
            category=category,
            hourly_rate=hourly_rate
        )

        # Diagnostic avant consolidation
        nb_suggestions_brutes = len(suggestions)
        if suggestions:
            total_h_brut = sum(s.delta_hours for s in suggestions)
            total_c_brut = sum(s.delta_chf for s in suggestions)
            diagnostics.append(("info", f"[{category}] {nb_suggestions_brutes} suggestion(s) brute(s) générée(s) : {total_h_brut:+.1f}h / {total_c_brut:+.0f} CHF"))
        else:
            diagnostics.append(("warning", f"[{category}] L'algorithme greedy n'a généré aucune suggestion. L'objectif ({delta_hours:+.1f}h) est peut-être trop ambitieux pour la période analysée."))
            st.session_state.suggestions_diagnostics = diagnostics
            results[category] = suggestions
            continue

        # 5. Consolider les suggestions (regrouper créneaux consécutifs et périmètres)
        suggestions_consolidated = consolidate_suggestions(suggestions)

        # Diagnostic final après consolidation
        total_h = sum(s.delta_hours for s in suggestions_consolidated)
        total_c = sum(s.delta_chf for s in suggestions_consolidated)
        diagnostics.append(("success", f"[{category}] {len(suggestions_consolidated)} suggestion(s) consolidée(s) : {total_h:+.1f}h / {total_c:+.0f} CHF (regroupées depuis {nb_suggestions_brutes} suggestions brutes)"))

        st.session_state.suggestions_diagnostics = diagnostics
        results[category] = suggestions_consolidated

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
        value = 0 if sugg.delta_hours < 0 else 1

        # Gérer périmètres groupés (séparés par ", ")
        # Ex: "Arrivée Schengen, Départ Schengen" → ["Arrivée Schengen", "Départ Schengen"]
        perimetres_list = [p.strip() for p in sugg.perimetre.split(',')]

        # Créer une règle groupée avec tous les périmètres
        rule = {
            'category': category,
            'start': sugg.date,
            'end': sugg.date,
            'jours': [],  # Pas de filtre jour
            'saisons': [],  # Pas de filtre saison
            'rows': perimetres_list,  # Liste de périmètres
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
