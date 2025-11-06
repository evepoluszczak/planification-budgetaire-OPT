# ui/pages/assistant_besoin_jour.py
from __future__ import annotations

import datetime as dt
import numpy as np
import pandas as pd
import streamlit as st

# ============================================================
# Libellés FR
# ============================================================

FR_MONTHS = {
    1: "janvier", 2: "février", 3: "mars", 4: "avril", 5: "mai", 6: "juin",
    7: "juillet", 8: "août", 9: "septembre", 10: "octobre", 11: "novembre", 12: "décembre"
}
FR_WEEKDAYS = {
    0: "Lundi", 1: "Mardi", 2: "Mercredi", 3: "Jeudi", 4: "Vendredi", 5: "Samedi", 6: "Dimanche"
}


# ============================================================
# Helpers génériques
# ============================================================

def _hours_series_for_category(df: pd.DataFrame, cat: str) -> pd.Series:
    """
    Retourne une série d'heures pour la catégorie demandée.
    Essaie successivement plusieurs conventions de colonnes.
    """
    candidates = [
        f"Heures_{cat}",
        f"Heures {cat}",
        f"H_{cat}",
        cat,  # au cas où
    ]
    for c in candidates:
        if c in df.columns:
            return pd.to_numeric(df[c], errors="coerce").fillna(0.0)
    # fallback : tout à 0
    return pd.Series(0.0, index=df.index)


def _prepare_calendar(calendar_df: pd.DataFrame) -> pd.DataFrame:
    """Normalise les colonnes Date/Mois/Jour FR/Saison et ordonne par date."""
    if calendar_df is None or calendar_df.empty:
        return pd.DataFrame()

    df = calendar_df.copy()
    if 'Date' not in df.columns:
        st.error("Le calendar ne contient pas la colonne 'Date'.")
        return pd.DataFrame()

    df['Date'] = pd.to_datetime(df['Date'], errors='coerce')
    df = df.dropna(subset=['Date']).reset_index(drop=True)

    # Saison présente dans ton modèle
    if 'Saison' not in df.columns:
        df['Saison'] = "Standard"

    df['Mois'] = df['Date'].dt.month
    df['Mois_FR'] = df['Mois'].map(FR_MONTHS)
    df['Weekday'] = df['Date'].dt.weekday
    df['Jour'] = df['Weekday'].map(FR_WEEKDAYS)

    return df.sort_values('Date').reset_index(drop=True)


def _filter_with_locks(df: pd.DataFrame,
                       months_keep: list[int] | None,
                       seasons_keep: list[str] | None,
                       weekdays_keep: list[str] | None) -> pd.DataFrame:
    """Applique les verrous : on ne garde que ce qui est AUTORISÉ."""
    out = df.copy()
    if months_keep:
        out = out[out['Mois'].isin(months_keep)]
    if seasons_keep:
        out = out[out['Saison'].astype(str).isin(seasons_keep)]
    if weekdays_keep:
        out = out[out['Jour'].isin(weekdays_keep)]
    return out.reset_index(drop=True)


def _build_suggestions_for_category(df_candidates: pd.DataFrame,
                                    cat: str,
                                    target_hours: float,
                                    step: float,
                                    max_per_day: float,
                                    mode: str) -> pd.DataFrame:
    """
    Construit des suggestions pour UNE catégorie.
    - df_candidates doit contenir 'Date','Jour','Saison','Mois_FR' et une colonne 'Heures_base'
    - mode: 'reduce' ou 'add'
    """
    required = {'Date', 'Jour', 'Saison', 'Mois_FR', 'Heures_base'}
    missing = required - set(df_candidates.columns)
    if missing:
        raise KeyError(f"Colonnes manquantes pour _build_suggestions_for_category({cat}): {sorted(missing)}")

    df = df_candidates.copy()
    if df.empty or target_hours == 0:
        return pd.DataFrame(columns=[
            'Catégorie', 'Date', 'Jour', 'Saison', 'Mois_FR',
            'Heures_base', 'Ajustement_propose', 'Heures_nouvelles'
        ])

    # Tri : pour réduire → jours les plus chargés d’abord ; pour ajouter → les moins chargés
    df = df.sort_values('Heures_base', ascending=(mode == 'add')).reset_index(drop=True)

    remaining = abs(float(target_hours))
    sign = -1.0 if mode == 'reduce' else 1.0

    rows = []
    for _, r in df.iterrows():
        if remaining <= 0:
            break

        proposed = min(remaining, max_per_day)
        proposed = float(np.ceil(proposed / step) * step)  # multiple du step—arrondi haut

        base = float(r['Heures_base'])
        if mode == 'reduce':
            new_val = max(0.0, base - proposed)
            proposed = base - new_val  # si on touche 0
            signed = -proposed
        else:
            new_val = base + proposed
            signed = proposed

        if proposed <= 0:
            continue

        rows.append({
            'Catégorie': cat,
            'Date': pd.to_datetime(r['Date']).date(),
            'Jour': r['Jour'],
            'Saison': r['Saison'],
            'Mois_FR': r['Mois_FR'],
            'Heures_base': round(base, 2),
            'Ajustement_propose': round(signed, 2),
            'Heures_nouvelles': round(new_val, 2),
        })
        remaining -= proposed

    return pd.DataFrame(rows)


def _categories_available(calendar_df: pd.DataFrame) -> list[str]:
    """
    Détecte les catégories présentes dans le calendar via les colonnes 'Heures_*'.
    Exemple: 'Heures_AT','Heures_ATR','Heures_CSC',...
    """
    cats = []
    for c in calendar_df.columns:
        if isinstance(c, str) and c.startswith("Heures_"):
            cats.append(c.replace("Heures_", ""))  # garde le suffixe (la catégorie)
    # tri : AT d'abord si présent
    cats = sorted(set(cats))
    if "AT" in cats:
        cats.remove("AT")
        cats = ["AT"] + cats
    return cats


# ============================================================
# Page
# ============================================================

def render_besoin_jour_assistant_page():
    st.title("Assistant Besoin Jour (multi-catégories)")
    st.markdown(
        "Génère des **suggestions d’ajustements d’heures** par **catégorie** "
        "en respectant vos verrous *(mois, saisons, jours)* et des cibles "
        "qui peuvent venir soit du **Simulateur d’Objectif**, soit d’une **saisie manuelle**."
    )

    # Pré-requis
    bs = st.session_state.get('budget_state', {})
    if not bs or 'calendar_df' not in bs or bs['calendar_df'] is None or bs['calendar_df'].empty:
        st.warning("⚠️ Aucun Calendar disponible. Générez d’abord un budget (page **Budget Annuel**).")
        st.stop()

    base_df = _prepare_calendar(bs['calendar_df'])
    if base_df.empty:
        st.warning("Calendar vide après normalisation.")
        st.stop()

    year = int(pd.to_datetime(base_df['Date']).dt.year.mode().iloc[0]) if not base_df.empty else dt.date.today().year
    st.caption(f"Année détectée : {year}")

    # Détecter les catégories disponibles (colonnes Heures_*)
    cats_all = _categories_available(bs['calendar_df'])
    if not cats_all:
        st.error("Aucune colonne 'Heures_*' détectée dans le calendar. Impossible de proposer des ajustements.")
        st.stop()

    # ===================== Objectif global & mode =====================
    with st.container(border=True):
        st.subheader("Objectif & Paramètres généraux")
        c1, c2, c3 = st.columns([1, 1, 1])
        with c1:
            mode_label = st.radio(
                "Type d’ajustement",
                options=["Réduire des heures", "Ajouter des heures"],
                index=0, horizontal=True, key="abj_mode"
            )
        with c2:
            # Pas commun pour toutes les catégories (simple et lisible)
            step = st.select_slider("Pas (heures)", options=[0.25, 0.5, 1.0, 2.0], value=0.5)
        with c3:
            max_per_day = st.number_input(
                "Ajustement max par jour (h, par catégorie)",
                min_value=float(step), max_value=24.0, value=2.0, step=float(step), format="%.2f"
            )

        effective_mode = 'reduce' if mode_label.startswith("Réduire") else 'add'

    # ===================== Verrous & filtres =====================
    with st.container(border=True):
        st.subheader("Verrous & filtres (communs à toutes les catégories)")
        months_keep = st.multiselect(
            "Mois autorisés",
            options=list(range(1, 13)),
            default=list(range(1, 13)),
            format_func=lambda m: f"{m:02d} - {FR_MONTHS[m]}",
            key="abj_months_keep"
        )
        seasons_all = sorted(base_df['Saison'].dropna().astype(str).unique().tolist())
        seasons_keep = st.multiselect(
            "Saisons autorisées", options=seasons_all, default=seasons_all, key="abj_seasons_keep"
        )
        weekdays_all = list(FR_WEEKDAYS.values())
        weekdays_keep = st.multiselect(
            "Jours autorisés", options=weekdays_all, default=weekdays_all, key="abj_weekdays_keep"
        )

    # Candidats après verrous
    candidates_common = _filter_with_locks(base_df, months_keep, seasons_keep, weekdays_keep)
    if candidates_common.empty:
        st.warning("Aucun jour éligible avec les verrous appliqués. Assouplissez les filtres.")
        st.stop()

    # ===================== Sélection des catégories =====================
    with st.container(border=True):
        st.subheader("Catégories concernées")
        selected_cats = st.multiselect(
            "Choisissez les catégories sur lesquelles appliquer la cible",
            options=cats_all,
            default=[c for c in cats_all if c in ("AT", "ATR", "ATF")] or cats_all[:3],
            key="abj_selected_cats"
        )
        if not selected_cats:
            st.info("Sélectionnez au moins une catégorie.")
            st.stop()

    # ===================== Source des cibles par catégorie =====================
    with st.container(border=True):
        st.subheader("Cibles d’ajustement par catégorie (heures)")
        source_mode = st.radio(
            "Source des cibles :",
            options=["Depuis le Simulateur (si disponible)", "Saisie manuelle"],
            index=0, horizontal=True, key="abj_target_source"
        )

        targets_by_cat: dict[str, float] = {c: 0.0 for c in selected_cats}

        if source_mode.startswith("Depuis"):
            # On attend un DF sauvegardé par le simulateur :
            # st.session_state["simulateur_objectif_results"] (DataFrame)
            # Colonnes attendues au minimum :
            #   'Catégorie' , 'Ajustement Heures (h)'  (positive = ajouter, négative = réduire)
            sim_df = st.session_state.get("simulateur_objectif_results", pd.DataFrame())
            if sim_df is None or sim_df.empty or "Catégorie" not in sim_df.columns:
                st.warning("Aucun résultat du Simulateur trouvé. Passe en saisie manuelle.")
                source_mode = "Saisie manuelle"
            else:
                # Nettoyage colonnes
                col_h = None
                for c in sim_df.columns:
                    if "Ajustement" in c and "Heure" in c:
                        col_h = c
                        break
                if col_h is None:
                    st.warning("Le tableau du Simulateur ne contient pas de colonne d'ajustement en heures. Passe en saisie manuelle.")
                    source_mode = "Saisie manuelle"
                else:
                    # Filtre sur les catégories retenues
                    pick = sim_df[sim_df['Catégorie'].isin(selected_cats)].copy()
                    if pick.empty:
                        st.warning("Le Simulateur ne contient pas ces catégories. Passe en saisie manuelle.")
                        source_mode = "Saisie manuelle"
                    else:
                        # Option : inverser le signe auto si mode contraire
                        st.caption("Cibles importées du Simulateur (ajustables ci-dessous).")
                        scale = st.slider("Facteur d'échelle des cibles du Simulateur", min_value=0.0, max_value=2.0, value=1.0, step=0.05)
                        for cat in selected_cats:
                            val = float(pick[pick['Catégorie'] == cat][col_h].sum()) if cat in pick['Catégorie'].values else 0.0
                            # Harmonise avec le mode sélectionné (Réduire/Ajouter)
                            if effective_mode == 'reduce':
                                # on veut un nombre négatif → si positif, on inverse le signe
                                val = -abs(val)
                            else:
                                # on veut un nombre positif
                                val = abs(val)
                            targets_by_cat[cat] = round(val * scale, 2)

        if source_mode == "Saisie manuelle":
            # Grille d'inputs
            cols = st.columns(min(5, max(1, len(selected_cats))))
            for i, cat in enumerate(selected_cats):
                with cols[i % len(cols)]:
                    targets_by_cat[cat] = st.number_input(
                        f"{cat} (h) {'à retirer' if effective_mode=='reduce' else 'à ajouter'}",
                        value=0.0, step=1.0, format="%.1f", key=f"abj_manual_target_{cat}"
                    )
                    # Harmonise le signe avec le mode
                    if effective_mode == 'reduce':
                        targets_by_cat[cat] = -abs(targets_by_cat[cat])
                    else:
                        targets_by_cat[cat] = abs(targets_by_cat[cat])

        # Résumé
        total_target = sum(targets_by_cat.values())
        st.metric("Cible totale (toutes catégories)", f"{total_target:+.1f} h")

    # ===================== Génération des suggestions =====================
    with st.container(border=True):
        st.subheader("Suggestions d’ajustements (par catégorie)")

        all_suggestions = []
        for cat in selected_cats:
            target_cat = float(targets_by_cat.get(cat, 0.0))
            if abs(target_cat) < 0.001:
                continue  # pas de cible pour cette catégorie

            # Prépare un DF candidats avec Heures_base = Heures_{cat}
            dfc = candidates_common.copy()
            dfc['Heures_base'] = _hours_series_for_category(bs['calendar_df'], cat)
            # On enlève les jours où la base est NaN (déjà 0.0) → ok

            mode_cat = 'reduce' if target_cat < 0 else 'add'
            out = _build_suggestions_for_category(
                df_candidates=dfc[['Date', 'Jour', 'Saison', 'Mois_FR', 'Heures_base']],
                cat=cat,
                target_hours=abs(target_cat),
                step=float(step),
                max_per_day=float(max_per_day),
                mode=mode_cat
            )
            if not out.empty:
                all_suggestions.append(out)

        if not all_suggestions:
            st.warning("Aucune suggestion générée. Vérifiez vos cibles et/ou assouplissez les verrous.")
            return

        suggestions = pd.concat(all_suggestions, ignore_index=True)

        # Limiteur optionnel d'affichage
        limit_rows = st.number_input(
            "Limiter l’affichage à N premières lignes (0 = illimité)",
            min_value=0, max_value=2000, value=0, step=50
        )
        to_show = suggestions if limit_rows == 0 else suggestions.head(limit_rows)

        # KPI
        total_adj = float(suggestions['Ajustement_propose'].sum())
        st.metric("Ajustement total proposé (toutes catégories)", f"{total_adj:+.1f} h")

        st.dataframe(
            to_show,
            hide_index=True,
            use_container_width=True,
            column_config={
                'Catégorie': st.column_config.TextColumn('Catégorie'),
                'Date': st.column_config.DateColumn('Date', format="YYYY-MM-DD"),
                'Jour': st.column_config.TextColumn('Jour'),
                'Saison': st.column_config.TextColumn('Saison'),
                'Mois_FR': st.column_config.TextColumn('Mois'),
                'Heures_base': st.column_config.NumberColumn('Heures (base)', format="%.2f h"),
                'Ajustement_propose': st.column_config.NumberColumn('Ajustement', format="%+.2f h"),
                'Heures_nouvelles': st.column_config.NumberColumn('Heures (proposé)', format="%.2f h"),
            }
        )

        # Exports
        csv_bytes = suggestions.to_csv(index=False).encode('utf-8')
        st.download_button(
            "Exporter toutes les suggestions (CSV)",
            data=csv_bytes,
            file_name=f"suggestions_multi_categories_{year}.csv",
            mime="text/csv",
            use_container_width=True,
            type="secondary",
            key="dl_sugg_all"
        )

        # Export par catégorie (facultatif, pratique)
        with st.expander("Exports par catégorie"):
            cats_in_results = suggestions['Catégorie'].dropna().unique().tolist()
            for cat in cats_in_results:
                dfc = suggestions[suggestions['Catégorie'] == cat].copy()
                btn_key = f"dl_{cat}_csv"
                st.download_button(
                    f"Exporter {cat} (CSV)",
                    data=dfc.to_csv(index=False).encode('utf-8'),
                    file_name=f"suggestions_{cat}_{year}.csv",
                    mime="text/csv",
                    use_container_width=True,
                    key=btn_key
                )

    # Astuce finale
    st.caption(
        "💡 Applique ces propositions manuellement dans **Besoin Jour**. "
        "Si tu veux que je génère directement les *ops JSON* prêtes à injecter dans `_apply_ops_to_grid`, "
        "dis-moi le format exact (clé, structure) et je te fournis l’export prêt à coller."
    )
