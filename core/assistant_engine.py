# core/assistant_engine.py
from __future__ import annotations
import datetime as dt
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple
import pandas as pd
import numpy as np
import streamlit as st

from core.assistant_utils import normalize_0_1, ceil_half_hour, floor_half_hour

# On utilise les helpers existants pour reconstruire les grilles effectives jour/slot
from core.planning import _ensure_grid, _apply_ops_to_grid
from config.constants import TIME_SLOTS


# ==============================
# Structures
# ==============================

@dataclass
class AssistantParams:
    # pondérations du score (0..1)
    w_intensity: float = 0.35   # intensité PAX
    w_ratio: float = 0.25       # efficacité PAX/heure
    w_stability: float = 0.15   # stabilité (faible variance favorisée pour retraits)
    w_history: float = 0.15     # historique (excédent/déficit)
    w_events: float = 0.10      # pénalité évènement

    # contraintes opérationnelles
    min_block_hours: float = 1.0   # taille mini d'une suggestion regroupée
    unit: float = 0.5              # granularité d'allocation (0.5h)
    honor_min_agents: bool = True  # ne pas franchir le plancher "agents actuels"

    # seuil de blocage événements
    event_block_threshold: float = 0.7  # événements avec pénalité >= seuil sont bloqués

@dataclass
class Locks:
    categories: List[str]
    perimetres: List[str]
    dates: List[dt.date]

@dataclass
class Suggestion:
    date: dt.date
    slot_start: str          # "HH:MM"
    slot_end: str            # "HH:MM"
    perimetre: str
    categorie: str
    delta_hours: float       # + ou - (multiple de 0.5)
    delta_chf: float
    score: float
    motifs: List[str]


# ==============================
# Données & construction slots
# ==============================

def _effective_grid_for_day(category: str, date_: dt.date, jour: str, saison: str) -> pd.DataFrame:
    """
    Reconstruit la grille effective (après Besoin Jour) pour une catégorie à la date donnée.
    Retour: DataFrame index=perimetres, columns=TIME_SLOTS (nb agents).
    """
    perims = st.session_state.perimetres.get(category, [])
    planning_dict = st.session_state.planning_data.get(category, {})
    _, base_df = _ensure_grid(planning_dict, st.session_state['calendar_df'].loc[
        st.session_state['calendar_df']['Date'].dt.date == date_, 'Jour_Type_Global'
    ].iloc[0], perims, TIME_SLOTS)

    eff_df = _apply_ops_to_grid(base_df, date_, jour, saison, category=category)
    return eff_df


def _collect_slots_df(year: int, categories: List[str]) -> pd.DataFrame:
    """
    Construit un DF de slots: (date, slot, perimetre, categorie, agents, pax, ratio, variance, historique)
    - pax: total PAX (A/D; Schengen/Non) agrégé sur le slot
    - agents: nb agents (grille effective) pour la catégorie et le périmètre
    - ratio: pax / (agents * 0.5h) ; si agents=0 => ratio très élevé pour ajout
    """
    bs = st.session_state.get('budget_state', {})
    cal = bs.get('calendar_df', pd.DataFrame()).copy()
    if cal.empty:
        return pd.DataFrame()

    cal['Date'] = pd.to_datetime(cal['Date'])
    cal = cal[cal['Date'].dt.year == year].copy()
    if cal.empty:
        return pd.DataFrame()

    # PAX agrégé 30'
    pax_hist = st.session_state.get("pax_historical_data", pd.DataFrame())
    pax_fc = st.session_state.get("pax_forecast_data", pd.DataFrame())
    pax_df_30 = pax_fc if (isinstance(pax_fc, pd.DataFrame) and not pax_fc.empty) else pax_hist
    # Colonne pax total
    def _pax_total(df):
        if df is None or df.empty:
            return pd.DataFrame()
        total = df.copy()
        for c in ['Pax_Schengen_A','Pax_Schengen_D','Pax_NonSchengen_A','Pax_NonSchengen_D']:
            if c not in total.columns:
                total[c] = 0
        total['PAX_TOTAL'] = total[['Pax_Schengen_A','Pax_Schengen_D','Pax_NonSchengen_A','Pax_NonSchengen_D']].sum(axis=1)
        return total
    pax_df_30 = _pax_total(pax_df_30)
    if pax_df_30 is None or pax_df_30.empty or 'PAX_TOTAL' not in pax_df_30.columns:
        # fallback: zéro
        pax_df_30 = pd.DataFrame(columns=['PAX_TOTAL'])
        pax_available = False
    else:
        pax_available = True

    rows = []
    # Itère chaque jour du calendrier (déjà filtré à l’année)
    for _, r in cal.iterrows():
        date_ = r['Date'].date()
        jour = r['Jour']
        saison = r['Saison']
        # PAX slotisés pour ce jour (somme par 30')
        if pax_available:
            pax_day = pax_df_30[pax_df_30.index.date == date_].copy()
            if pax_day.empty:
                # journée sans PAX => slots à 0
                pax_slot = {ts: 0.0 for ts in TIME_SLOTS}
            else:
                # index DateTime => map HH:MM -> somme sur tranche
                pax_slot = {}
                for ts in TIME_SLOTS:
                    # tranche [ts ; ts+30min)
                    h, m = map(int, ts.split(':'))
                    start = pd.Timestamp(dt.datetime.combine(date_, dt.time(h, m)))
                    end = start + pd.Timedelta(minutes=30)
                    mask = (pax_day.index >= start) & (pax_day.index < end)
                    pax_slot[ts] = float(pax_day.loc[mask, 'PAX_TOTAL'].sum())
        else:
            pax_slot = {ts: 0.0 for ts in TIME_SLOTS}

        for cat in categories:
            # grille effective nb agents (rows perimetres, cols timeslots)
            eff_df = _effective_grid_for_day(cat, date_, jour, saison)
            if eff_df is None or eff_df.empty:
                continue
            for perim, row_vals in eff_df.iterrows():
                for ts in TIME_SLOTS:
                    agents = float(row_vals.get(ts, 0.0) or 0.0)
                    pax = float(pax_slot.get(ts, 0.0) or 0.0)
                    slot_hours = max(agents, 0.0) * 0.5
                    # ratio : privilégier l'ajout quand ratio élevé, retrait quand ratio faible
                    ratio = (pax / slot_hours) if slot_hours > 0 else (9999.0 if pax > 0 else 0.0)
                    rows.append({
                        'Date': date_,
                        'Jour': jour,
                        'Saison': saison,
                        'Categorie': cat,
                        'Perimetre': perim,
                        'Slot': ts,
                        'Agents': agents,
                        'PAX': pax,
                        'Ratio': ratio,
                        # On mettra Stability/History plus tard (0 par défaut)
                        'Stability': 0.0,
                        'HistoryExc': 0.0,
                        'EventPenalty': 0.0,  # Sera enrichi plus bas
                    })

    slots = pd.DataFrame(rows)
    if slots.empty:
        return slots

    # Enrichir avec les pénalités événements depuis le calendrier
    try:
        from models.event import EventManager
        def get_event_penalty(date_):
            return EventManager.get_penalty_for_date(date_)

        slots['EventPenalty'] = slots['Date'].apply(get_event_penalty)
    except Exception:
        # Si erreur, garder les pénalités à 0
        slots['EventPenalty'] = 0.0

    # Stabilité (variance locale) par (categorie/perimetre/jour)
    # Ici approche simple: variance des PAX entre slots du jour
    stab = slots.groupby(['Date','Categorie','Perimetre'])['PAX'].var().reset_index().rename(columns={'PAX':'VarPAX'})
    slots = slots.merge(stab, on=['Date','Categorie','Perimetre'], how='left')
    slots['VarPAX'] = slots['VarPAX'].fillna(0.0)
    # Normalisation "stabilité": faible variance => plus stable
    slots['Stability'] = 1.0 - normalize_0_1(slots['VarPAX'])

    # Historique (excédent par mois) – placeholder simple à 0.0 (possible d’intégrer Analyse Budgétaire)
    slots['HistoryExc'] = 0.0

    return slots


# ==============================
# Scoring
# ==============================

def _score_slots(slots: pd.DataFrame, direction: str, params: AssistantParams) -> pd.Series:
    """
    direction: "add" ou "remove"
    Retourne un score 0..1 par ligne.
    """
    # Intensité PAX (pour add: plus c'est intense, mieux c'est ; pour remove: inverse)
    inten = normalize_0_1(slots['PAX'])
    if direction == "remove":
        inten = 1.0 - inten

    # Ratio efficacité (add: haut ratio -> mieux; remove: bas ratio -> mieux)
    ratio = normalize_0_1(slots['Ratio'])
    if direction == "remove":
        ratio = 1.0 - ratio

    # Stabilité : déjà calculé dans [0..1]. Pour add, on peut favoriser la stabilité moyenne (neutre)
    stability = slots['Stability'].clip(0,1)
    if direction == "add":
        # on réduit l'impact de la stabilité (facultatif)
        stability = 0.5 + 0.5 * stability

    # Historique excédent/déficit (placeholder ici = 0 neutre)
    hist = slots['HistoryExc'].clip(0,1)

    # Pénalité événements (depuis EventManager)
    events_penalty = slots['EventPenalty'].clip(0, 1)

    s = (
        params.w_intensity * inten +
        params.w_ratio     * ratio +
        params.w_stability * stability +
        params.w_history   * hist -
        params.w_events    * events_penalty
    )
    # clamp
    s = np.clip(s, 0.0, 1.0)
    return pd.Series(s, index=slots.index)


# ==============================
# Génération de suggestions
# ==============================

def generate_suggestions(
    year: int,
    delta_by_category_hours: Dict[str, float],
    locks: Locks,
    params: Optional[AssistantParams] = None,
) -> List[Suggestion]:
    """
    Retourne une liste de Suggestion (non-appliquées).
    delta_by_category_hours: ex {"AT": -120.0, "ATR": 40.0}
    """
    if params is None:
        params = AssistantParams()

    categories = [c for c, h in delta_by_category_hours.items() if abs(h) >= 0.25]
    if not categories:
        return []

    slots = _collect_slots_df(year, categories)
    if slots.empty:
        return []

    # Applique locks
    if locks.categories:
        slots = slots[~slots['Categorie'].isin(locks.categories)]
    if locks.perimetres:
        slots = slots[~slots['Perimetre'].isin(locks.perimetres)]
    if locks.dates:
        lock_dates = set(locks.dates)
        slots = slots[~slots['Date'].isin(lock_dates)]

    # Filtrer les événements critiques et majeurs
    # Les événements avec pénalité >= threshold sont exclus complètement
    # Par défaut 0.7 (bloque 'critical'=1.0 et 'major'=0.8, garde 'minor'=0.3)
    slots = slots[slots['EventPenalty'] < params.event_block_threshold].copy()

    if slots.empty:
        # Tous les slots ont été filtrés par des événements critiques
        return []

    # Build index -> quick lookup
    suggestions: List[Suggestion] = []

    for cat in categories:
        need = float(delta_by_category_hours.get(cat, 0.0) or 0.0)
        if abs(need) < 0.25:
            continue

        cat_slots = slots[slots['Categorie'] == cat].copy()
        if cat_slots.empty:
            continue

        direction = "add" if need > 0 else "remove"
        cat_slots['Score'] = _score_slots(cat_slots, direction, params)

        # Tri desc
        cat_slots = cat_slots.sort_values('Score', ascending=False).reset_index(drop=True)

        remaining = abs(need)
        unit = float(params.unit)

        # Tarif horaire pour valoriser ΔCHF
        hourly_rate = _hourly_rate_for_category(cat)

        # Greedy
        for _, s in cat_slots.iterrows():
            if remaining < 0.25:
                break

            agents = float(s['Agents'])
            # Respect du plancher agents (par défaut : on ne descend pas sous agents actuels)
            if params.honor_min_agents and direction == "remove" and agents <= 0:
                continue

            # allocation sur ce slot
            alloc = min(unit, remaining)

            # delta +/-
            delta_h = alloc if direction == "add" else -alloc
            delta_chf = delta_h * hourly_rate

            suggestions.append(Suggestion(
                date=s['Date'],
                slot_start=str(s['Slot']),
                slot_end=_slot_end_from_start(str(s['Slot'])),
                perimetre=str(s['Perimetre']),
                categorie=cat,
                delta_hours=delta_h,
                delta_chf=delta_chf,
                score=float(s['Score']),
                motifs=_motifs_from_row(s, direction)
            ))

            remaining -= alloc

    # Regroupement par (date, perimetre, categorie, continuité de slots, même signe)
    suggestions = _merge_adjacent_suggestions(suggestions, min_block=params.min_block_hours)

    # Stockage en session pour UI
    st.session_state.assistant_suggestions = suggestions
    return suggestions


def _motifs_from_row(row: pd.Series, direction: str) -> List[str]:
    motifs = []
    if direction == "remove":
        if row['PAX'] < row['PAX'].mean() if hasattr(row['PAX'], 'mean') else True:
            motifs.append("Faible intensité PAX")
        if row['Ratio'] < 1.0:
            motifs.append("Ratio PAX/heure bas")
        motifs.append("Slot stable")
    else:
        motifs.append("Slot à forte intensité PAX")
        motifs.append("Ratio PAX/heure élevé")
    return motifs


def _slot_end_from_start(ts: str) -> str:
    h, m = map(int, ts.split(':'))
    end = (h * 60 + m + 30) % (24 * 60)
    he, me = divmod(end, 60)
    return f"{he:02d}:{me:02d}"


def _merge_adjacent_suggestions(items: List[Suggestion], min_block: float) -> List[Suggestion]:
    if not items:
        return []

    # Regroupe par clé & continuité (simple : on cumule par slot contigu de 30' même signe)
    items = sorted(items, key=lambda x: (x.date, x.perimetre, x.categorie, x.slot_start))
    merged: List[Suggestion] = []

    def _slot_to_minutes(s: str) -> int:
        h, m = map(int, s.split(':'))
        return h * 60 + m

    cur: Optional[Suggestion] = None
    last_end_min = None

    for s in items:
        if cur is None:
            cur = s
            last_end_min = _slot_to_minutes(s.slot_end)
            continue

        same_group = (
            s.date == cur.date and
            s.perimetre == cur.perimetre and
            s.categorie == cur.categorie and
            np.sign(s.delta_hours) == np.sign(cur.delta_hours) and
            _slot_to_minutes(s.slot_start) == last_end_min  # contigu
        )
        if same_group:
            # étend le bloc
            cur.slot_end = s.slot_end
            cur.delta_hours += s.delta_hours
            cur.delta_chf += s.delta_chf
            cur.score = max(cur.score, s.score)  # max score du groupe
            last_end_min = _slot_to_minutes(s.slot_end)
        else:
            merged.append(cur)
            cur = s
            last_end_min = _slot_to_minutes(s.slot_end)

    if cur is not None:
        merged.append(cur)

    # filtre blocs trop petits si demandé
    if min_block and min_block > 0:
        keep = []
        for s in merged:
            if abs(s.delta_hours) + 1e-9 >= float(min_block):
                keep.append(s)
        return keep
    return merged


def _hourly_rate_for_category(category: str) -> float:
    """Récupère le coût horaire pour la catégorie via st.session_state.cost_mapping/personnel."""
    cost_mapping = st.session_state.get('cost_mapping', {})
    perso = st.session_state.get('personnel', pd.DataFrame())
    ptype = cost_mapping.get(category, category)
    if isinstance(perso, pd.DataFrame) and not perso.empty:
        row = perso[perso['Type'] == ptype]
        if not row.empty:
            try:
                return float(row['Coût Horaire'].iloc[0])
            except Exception:
                pass
    # défaut
    return 45.0


# ==============================
# Application / Undo
# ==============================

def apply_suggestions(suggestions: List[Suggestion]) -> None:
    """
    Crée un journal minimal pour UNDO et dépose les deltas dans un espace isolé
    (sans toucher aux structures natives de tes grilles).
    Ici, on stocke en session un patch "assistant_applied_ops" que ton calcul
    de Budget Modifié pourra lire en bonus si tu le souhaites (non destructif).
    """
    if not suggestions:
        return
    # journal pour undo
    st.session_state.assistant_last_apply = {
        "when": dt.datetime.now().isoformat(timespec="seconds"),
        "items": [s.__dict__ for s in suggestions],
    }
    # patch agrégé par (date, perimetre, categorie, slot_start..slot_end)
    patch = []
    for s in suggestions:
        patch.append(s.__dict__)
    # on cumule sur la clé identique
    st.session_state.setdefault("assistant_applied_ops", [])
    st.session_state.assistant_applied_ops.extend(patch)


def undo_last_apply() -> None:
    """Annule la dernière application (uniquement les ops de l'assistant)."""
    if "assistant_last_apply" not in st.session_state:
        return
    last = st.session_state.assistant_last_apply
    items = last.get("items", [])
    if not items:
        return
    # retire ces items du patch
    cur = st.session_state.get("assistant_applied_ops", [])
    keys = {(i['date'], i['slot_start'], i['slot_end'], i['perimetre'], i['categorie'], i['delta_hours'], i['delta_chf']) for i in items}
    remained = []
    for p in cur:
        k = (p['date'], p['slot_start'], p['slot_end'], p['perimetre'], p['categorie'], p['delta_hours'], p['delta_chf'])
        if k not in keys:
            remained.append(p)
    st.session_state.assistant_applied_ops = remained
    del st.session_state.assistant_last_apply
