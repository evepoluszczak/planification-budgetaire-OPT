# ui/pages/assistant_besoin_jour.py
from __future__ import annotations

import datetime as dt
import numpy as np
import pandas as pd
import streamlit as st

# ============================================================
# Helpers (FR labels)
# ============================================================

FR_MONTHS = {
    1: "janvier", 2: "février", 3: "mars", 4: "avril", 5: "mai", 6: "juin",
    7: "juillet", 8: "août", 9: "septembre", 10: "octobre", 11: "novembre", 12: "décembre"
}
FR_WEEKDAYS = {
    0: "Lundi", 1: "Mardi", 2: "Mercredi", 3: "Jeudi", 4: "Vendredi", 5: "Samedi", 6: "Dimanche"
}


def _safe_hours_series(df: pd.DataFrame, col_candidates: list[str]) -> pd.Series:
    """Renvoie la première colonne d'heures existante, sinon une série 0."""
    for c in col_candidates:
        if c in df.columns:
            return pd.to_numeric(df[c], errors="coerce").fillna(0.0)
    return pd.Series(0.0, index=df.index)


def _prepare_calendar(calendar_df: pd.DataFrame) -> pd.DataFrame:
    """Normalise les colonnes nécessaires et ajoute Mois/Jour FR + Heures_AT_base."""
    df = calendar_df.copy()
    if 'Date' not in df.columns:
        raise ValueError("La colonne 'Date' est absente du calendar_df.")

    df['Date'] = pd.to_datetime(df['Date'], errors='coerce')
    df = df.dropna(subset=['Date']).reset_index(drop=True)

    # Colonnes de base usuelles
    if 'Jour' not in df.columns:
        # on laissera la version FR ci-dessous
        df['Jour'] = df['Date'].dt.day_name()

    if 'Saison' not in df.columns:
        df['Saison'] = "Standard"

    # Heures AT du jour : candidates
    df['Heures_AT_base'] = _safe_hours_series(df, ['Heures_AT', 'Heures AT', 'H_AT', 'AT'])

    # Enrichissements temporels
    df['Mois'] = df['Date'].dt.month
    df['Mois_FR'] = df['Mois'].map(FR_MONTHS)
    df['Weekday'] = df['Date'].dt.weekday  # 0=Lundi
    df['Jour_FR'] = df['Weekday'].map(FR_WEEKDAYS)

    # Remplace 'Jour' par label FR pour cohérence UI
    df['Jour'] = df['Jour_FR']

    # Tri par date
    df = df.sort_values('Date').reset_index(drop=True)
    return df


def _filter_with_locks(df: pd.DataFrame,
                       months_keep: list[int] | None,
                       seasons_keep: list[str] | None,
                       weekdays_keep: list[str] | None) -> pd.DataFrame:
    """Garde uniquement les jours autorisés par les filtres (les verrous excluent)."""
    out = df.copy()

    if months_keep:
        out = out[out['Mois'].isin(months_keep)]

    if seasons_keep:
        out = out[out['Saison'].astype(str).isin(seasons_keep)]

    if weekdays_keep:
        out = out[out['Jour'].isin(weekdays_keep)]

    return out.reset_index(drop=True)


def _build_suggestions(df_candidates: pd.DataFrame,
                       target_hours: float,
                       step: float,
                       max_per_day: float,
                       mode: str) -> pd.DataFrame:
    """
    Construit des suggestions incrémentales par pas 'step' jusqu'à couvrir target_hours.
    mode = 'reduce' (on enlève) ou 'add' (on ajoute).
    - reduce : on commence par les jours les plus chargés (Heures_AT_base décroissant)
    - add    : on commence par les jours les moins chargés (Heures_AT_base croissant)

    df_candidates DOIT contenir : ['Date','Jour','Saison','Mois_FR','Heures_AT_base']
    """
    required_cols = {'Date', 'Jour', 'Saison', 'Mois_FR', 'Heures_AT_base'}
    missing = required_cols - set(df_candidates.columns)
    if missing:
        raise KeyError(f"Colonnes manquantes pour _build_suggestions: {sorted(missing)}")

    if df_candidates.empty or target_hours == 0:
        return pd.DataFrame(columns=[
            'Date', 'Jour', 'Saison', 'Mois_FR',
            'Heures_AT_base', 'Ajustement_propose', 'Heures_AT_nouvelles'
        ])

    df = df_candidates.copy()
    df = df.sort_values('Heures_AT_base', ascending=(mode == 'add')).reset_index(drop=True)

    remaining = abs(float(target_hours))
    sign = -1.0 if mode == 'reduce' else 1.0

    adjustments = []
    for _, r in df.iterrows():
        if remaining <= 0:
            break

        # Quantité à proposer sur ce jour
        proposed = min(remaining, max_per_day)
        proposed = float(np.ceil(proposed / step) * step)  # multiple du step (arrondi au-dessus)

        # En mode réduction, on évite de descendre sous 0
        if mode == 'reduce':
            new_val = max(0.0, float(r['Heures_AT_base']) + sign * proposed)
            proposed = float(r['Heures_AT_base']) - new_val  # ajusté si on touche 0
        else:
            new_val = float(r['Heures_AT_base']) + sign * proposed

        if proposed <= 0:
            continue

        adjustments.append({
            'Date': pd.to_datetime(r['Date']).date(),
            'Jour': r['Jour'],
            'Saison': r['Saison'],
            'Mois_FR': r['Mois_FR'],
            'Heures_AT_base': round(float(r['Heures_AT_base']), 2),
            'Ajustement_propose': round(sign * proposed, 2),
            'Heures_AT_nouvelles': round(float(new_val), 2),
        })
        remaining -= proposed

    return pd.DataFrame(adjustments)


# ============================================================
# Page
# ============================================================

def render_besoin_jour_assistant_page():
    st.title("Assistant Besoin Jour")
    st.markdown(
        "Cet assistant propose **des suggestions d'ajustements d'heures AT** "
        "à ajouter ou à retirer, en respectant vos filtres/verrous (mois, saisons, jours). "
        "Il n’applique **aucune modification** automatiquement."
    )

    # Pré-requis
    bs = st.session_state.get('budget_state', {})
    if not bs or 'calendar_df' not in bs or bs['calendar_df'] is None or bs['calendar_df'].empty:
        st.warning("⚠️ Aucun Calendar disponible. Générez d’abord un budget (page **Budget Annuel**).")
        st.stop()

    try:
        base_df = _prepare_calendar(bs['calendar_df'])
    except Exception as e:
        st.error(f"Impossible de préparer le calendrier : {e}")
        st.stop()

    year = int(pd.to_datetime(base_df['Date']).dt.year.mode().iloc[0]) if not base_df.empty else dt.date.today().year
    st.caption(f"Année détectée : {year}")

    # -------- Bloc Objectif --------
    with st.container(border=True):
        st.subheader("Objectif global & pas d'ajustement")
        c1, c2, c3 = st.columns([1, 1, 1])
        with c1:
            mode_label = st.radio(
                "Type d’ajustement",
                options=["Réduire des heures", "Ajouter des heures"],
                index=0,
                horizontal=True,
                key="assistant_mode",
            )
        with c2:
            target = st.number_input(
                "Objectif (heures)",
                min_value=-100000.0, max_value=100000.0, value=-100.0, step=1.0, format="%.1f",
                help="Valeur négative pour réduire, positive pour ajouter."
            )
        with c3:
            step = st.select_slider(
                "Pas (heures)",
                options=[0.25, 0.5, 1.0, 2.0],
                value=0.5,
                help="Taille de l'ajustement proposé par jour."
            )

        # Harmonisation signe ⇄ mode
        if target < 0:
            effective_mode = 'reduce'
            target_hours = abs(target)
        elif target > 0:
            effective_mode = 'add'
            target_hours = target
        else:
            effective_mode = 'reduce' if mode_label.startswith("Réduire") else 'add'
            target_hours = 0.0

        if mode_label.startswith("Réduire") and effective_mode != 'reduce':
            effective_mode = 'reduce'
            target_hours = abs(target)
        if mode_label.startswith("Ajouter") and effective_mode != 'add':
            effective_mode = 'add'
            target_hours = abs(target)

    # -------- Bloc Verrous --------
    with st.container(border=True):
        st.subheader("Verrous & filtres")
        st.markdown("Sélectionnez **ce que l’on est autorisé à toucher** (les autres sont verrouillés).")

        # Mois autorisés
        months_all = list(range(1, 12 + 1))
        default_months = months_all  # par défaut tout est autorisé
        months_keep = st.multiselect(
            "Mois autorisés",
            options=months_all,
            default=default_months,
            format_func=lambda m: f"{m:02d} - {FR_MONTHS[m]}",
            key="assistant_months_keep"
        )

        # Saisons autorisées (détectées)
        seasons_all = sorted(base_df['Saison'].dropna().astype(str).unique().tolist())
        seasons_keep = st.multiselect(
            "Saisons autorisées",
            options=seasons_all,
            default=seasons_all,
            key="assistant_seasons_keep"
        )

        # Jours de semaine autorisés
        weekdays_all = list(FR_WEEKDAYS.values())
        weekdays_keep = st.multiselect(
            "Jours autorisés",
            options=weekdays_all,
            default=weekdays_all,
            key="assistant_weekdays_keep"
        )

        c1, c2 = st.columns(2)
        with c1:
            max_per_day = st.number_input(
                "Ajustement maximum par jour (h)",
                min_value=step, max_value=24.0, value=2.0, step=step, format="%.2f"
            )
        with c2:
            limit_rows = st.number_input(
                "Nombre maximum de jours à suggérer",
                min_value=1, max_value=365, value=60, step=1
            )

    # -------- Candidats après verrous --------
    candidates = _filter_with_locks(base_df, months_keep, seasons_keep, weekdays_keep)

    with st.expander("État des candidats (debug)", expanded=False):
        st.caption(f"Jours candidats après verrous : **{len(candidates)}**")
        if not candidates.empty:
            by_month = candidates.groupby('Mois_FR')['Date'].count().rename('Jours').reset_index()
            st.dataframe(by_month, hide_index=True, use_container_width=True)

    # -------- Suggestions --------
    with st.container(border=True):
        st.subheader("Suggestions d’ajustements")
        if target_hours == 0:
            st.info("Définissez un objectif d’ajustement non nul pour générer des suggestions.")
            return

        if candidates.empty:
            st.warning("Aucun jour n’est éligible avec les verrous actuels. Assouplissez les filtres.")
            return

        # IMPORTANT : on passe une table dont les colonnes correspondent à ce que _build_suggestions attend
        df_for_algo = candidates[['Date', 'Jour', 'Saison', 'Mois_FR', 'Heures_AT_base']].copy()

        suggestions = _build_suggestions(
            df_candidates=df_for_algo,
            target_hours=target_hours,
            step=float(step),
            max_per_day=float(max_per_day),
            mode=effective_mode
        )

        if suggestions.empty:
            st.warning("Aucune suggestion n’a pu être générée (verrous trop stricts ou pas de delta atteignable).")
            return

        # Limiter l’affichage si demandé
        if len(suggestions) > int(limit_rows):
            suggestions = suggestions.iloc[:int(limit_rows)].copy()

        total_adj = float(suggestions['Ajustement_propose'].sum())
        st.metric(
            "Ajustement total proposé (h)",
            f"{total_adj:+.1f} h",
            help="Somme des ajustements proposés. Un signe négatif = réduction."
        )

        st.dataframe(
            suggestions,
            hide_index=True,
            use_container_width=True,
            column_config={
                'Date': st.column_config.DateColumn('Date', format="YYYY-MM-DD"),
                'Jour': st.column_config.TextColumn('Jour'),
                'Saison': st.column_config.TextColumn('Saison'),
                'Mois_FR': st.column_config.TextColumn('Mois'),
                'Heures_AT_base': st.column_config.NumberColumn('Heures AT (base)', format="%.2f h"),
                'Ajustement_propose': st.column_config.NumberColumn('Ajustement', format="%+.2f h"),
                'Heures_AT_nouvelles': st.column_config.NumberColumn('Heures AT (proposé)', format="%.2f h"),
            }
        )

        # Export CSV
        csv_bytes = suggestions.to_csv(index=False).encode('utf-8')
        st.download_button(
            "Exporter les suggestions (CSV)",
            data=csv_bytes,
            file_name=f"suggestions_assistant_besoin_jour_{year}.csv",
            mime="text/csv",
            use_container_width=True,
            type="secondary"
        )

        st.caption(
            "💡 Astuce : applique ces propositions manuellement dans **Besoin Jour**. "
            "Si tu veux une version qui génère directement des **ops JSON** exploitables par le moteur, dis-moi le format attendu."
        )
