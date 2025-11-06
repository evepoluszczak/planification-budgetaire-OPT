# ui/pages/assistant_besoin_jour.py
from __future__ import annotations

import pandas as pd
import numpy as np
import altair as alt
import streamlit as st
import datetime as dt

# --- 4.1 Helpers : PAX/jour ---
def _daily_pax_from_forecast(flux: str = "Tous") -> pd.DataFrame:
    """
    Construit un DF [Date (date), Pax_Total] depuis les données PAX en session.
    flux: 'Tous' | 'Arrivée' | 'Départ'
    Attend que st.session_state contienne les data PAX fusionnées ou séparées.
    """
    pax = st.session_state.get("pax_data", {})
    if not pax:
        # Ton chargeur place peut-être ailleurs; adapte ce getter si besoin
        pax = st.session_state.get("pax_merged") or st.session_state.get("pax_forecast")

    if pax is None:
        return pd.DataFrame()

    # On s'attend à un DataFrame 30' avec colonnes par flux; sinon, on agrège intelligemment
    if isinstance(pax, pd.DataFrame):
        df = pax.copy()
    elif isinstance(pax, dict) and "forecast" in pax and isinstance(pax["forecast"], pd.DataFrame):
        df = pax["forecast"].copy()
    else:
        return pd.DataFrame()

    # Harmonisation index/colonnes
    if "DateTime" in df.columns:
        df["DateTime"] = pd.to_datetime(df["DateTime"])
        df = df.set_index("DateTime")
    if not isinstance(df.index, pd.DatetimeIndex):
        # tente conversion large
        try:
            df.index = pd.to_datetime(df.index)
        except Exception:
            return pd.DataFrame()

    # Colonnes fréquentes (adapte selon ton schéma)
    # On tente plusieurs conventions puis on retombe sur une somme brute si nécessaire
    def _sum_cols(candidates):
        cols = [c for c in candidates if c in df.columns]
        if cols:
            return df[cols].sum(axis=1)
        return None

    if flux == "Arrivée":
        s = _sum_cols(["Pax_Schengen_A", "Pax_NonSchengen_A", "PAX_A", "Pax_A"])
    elif flux == "Départ":
        s = _sum_cols(["Pax_Schengen_D", "Pax_NonSchengen_D", "PAX_D", "Pax_D"])
    else:
        sA = _sum_cols(["Pax_Schengen_A", "Pax_NonSchengen_A", "PAX_A", "Pax_A"])
        sD = _sum_cols(["Pax_Schengen_D", "Pax_NonSchengen_D", "PAX_D", "Pax_D"])
        if sA is not None and sD is not None:
            s = sA.add(sD, fill_value=0)
        elif sA is not None:
            s = sA
        elif sD is not None:
            s = sD
        else:
            # dernier recours: somme de toutes colonnes int/float présentes
            num = df.select_dtypes(include=[np.number])
            s = num.sum(axis=1) if not num.empty else None

    if s is None:
        return pd.DataFrame()

    daily = s.groupby(s.index.date).sum()  # somme 30' -> jour
    out = pd.DataFrame({"Date": pd.to_datetime(daily.index), "Pax_Total": daily.values})
    return out


# --- 4.2 Helpers : Heures AT/jour (Annuel ou Modifié) ---
def _daily_hours_from_calendar(*, prefer_modifie: bool = True) -> pd.DataFrame:
    """
    Retourne [Date, Heures_AT] à partir de calendar_df (budget annuel) et
    calendar_df modifié (budget modifié). On prend Modifié si disponible.
    """
    bs = st.session_state.get("budget_state", {}) or {}
    ann = bs.get("calendar_df", pd.DataFrame())
    mod_state = st.session_state.get("budget_modifie_state")  # si tu stockes le modifié
    mod = None
    if mod_state and isinstance(mod_state, dict):
        mod = mod_state.get("calendar_df", None)

    base = None
    if prefer_modifie and isinstance(mod, pd.DataFrame) and not mod.empty:
        base = mod.copy()
    else:
        base = ann.copy()

    if not isinstance(base, pd.DataFrame) or base.empty:
        return pd.DataFrame()

    # Colonne candidate pour heures AT/jour
    # Si tu as 'Heures_AT' explicite dans ta calendar_df modifiée, prends-la.
    # Sinon retombe sur Heures_Total_Jour qui inclut AT + autres (à adapter si besoin).
    candidate_cols = ["Heures_AT", "Heures_AT_jour", "Heures_Total_Jour"]
    hcol = next((c for c in candidate_cols if c in base.columns), None)
    if hcol is None:
        return pd.DataFrame()

    base = base.copy()
    base["Date"] = pd.to_datetime(base["Date"]).dt.date
    hours = base.groupby("Date")[hcol].sum().reset_index()
    hours.rename(columns={hcol: "Heures_AT"}, inplace=True)
    hours["Date"] = pd.to_datetime(hours["Date"])
    return hours


# --- 4.3 Ciblage ratio AT / 1000 PAX ---
def _build_ratio_table(flux: str, prefer_modifie: bool, pax_min: float,
                       qmin: float | None = 0.3, smooth: bool = False) -> pd.DataFrame:
    """
    Construit un DF journées avec:
      [Date, Jour_FR, Saison, Mois_FR, Pax_Total, Heures_AT, Ratio_AT_pour_1000PAX]
    Filtres: seuil PAX, quantile bas (qmin).
    """
    df_pax = _daily_pax_from_forecast(flux=flux)
    df_h = _daily_hours_from_calendar(prefer_modifie=prefer_modifie)

    if df_pax.empty or df_h.empty:
        return pd.DataFrame()

    df = df_h.merge(df_pax, on="Date", how="inner")
    if df.empty:
        return pd.DataFrame()

    # Ajouts lisibles
    df["Date"] = pd.to_datetime(df["Date"])
    df["Jour_FR"] = df["Date"].dt.day_name(locale="fr_FR").str.capitalize()
    df["Mois_FR"] = df["Date"].dt.month_name(locale="fr_FR").str.capitalize()

    # Récup saison si dispo dans calendar_df
    bs = st.session_state.get("budget_state", {}) or {}
    cal = bs.get("calendar_df", pd.DataFrame()).copy()
    saison_col = next((c for c in ["Saison", "Saison_FR", "Season"] if c in cal.columns), None)
    if saison_col:
        cal["Date"] = pd.to_datetime(cal["Date"]).dt.date
        season_map = cal.drop_duplicates("Date")[["Date", saison_col]].copy()
        season_map["Date"] = pd.to_datetime(season_map["Date"])
        season_map.rename(columns={saison_col: "Saison"}, inplace=True)
        df = df.merge(season_map, on="Date", how="left")
    else:
        df["Saison"] = None

    # Ratio
    df = df[(df["Pax_Total"] > 0) & (df["Heures_AT"] >= 0)].copy()
    df["Ratio_AT_pour_1000PAX"] = df["Heures_AT"] / (df["Pax_Total"] / 1000.0)

    # Seuil PAX minimum
    if pax_min > 0:
        df = df[df["Pax_Total"] >= pax_min].copy()

    # Filtrage quantile bas (évite les très petits jours)
    if qmin is not None and 0 < qmin < 1:
        thr = df["Pax_Total"].quantile(qmin)
        df = df[df["Pax_Total"] >= thr].copy()

    # Option lissage (rolling médian sur 7 jours, sans décalage)
    if smooth and len(df) >= 7:
        df = df.sort_values("Date").reset_index(drop=True)
        df["Ratio_smooth"] = (
            df["Ratio_AT_pour_1000PAX"].rolling(window=7, center=True, min_periods=3).median()
        )
        df["Ratio_AT_pour_1000PAX"] = df["Ratio_smooth"].fillna(df["Ratio_AT_pour_1000PAX"])
        df.drop(columns=["Ratio_smooth"], inplace=True)

    # Tri par ratio décroissant par défaut (utile pour réduire)
    return df[["Date", "Jour_FR", "Saison", "Mois_FR", "Pax_Total", "Heures_AT", "Ratio_AT_pour_1000PAX"]]


def _distribute_delta_hours(delta_hours: float,
                            ranked_days: pd.DataFrame,
                            cap_per_day: float,
                            locked_dates: set[dt.date] | None = None) -> pd.DataFrame:
    """
    Distribue un delta d'heures (positif = ajout, négatif = réduction)
    sur les journées triées (ranked_days) en respectant un cap/jour et des dates verrouillées.
    Retourne DF [Date, Suggestion_Heures].
    """
    if locked_dates is None:
        locked_dates = set()

    out = []
    remaining = float(delta_hours)

    # sens: si on ajoute -> on part du bas ratio; si on réduit -> on part du haut ratio
    # ranked_days doit donc déjà être trié dans le bon sens par l'appelant.
    for _, r in ranked_days.iterrows():
        d = r["Date"].date() if isinstance(r["Date"], pd.Timestamp) else r["Date"]
        if d in locked_dates:
            continue

        if remaining == 0:
            break

        step = min(abs(remaining), abs(cap_per_day))
        step = round(step, 1)  # arrondi 0.1h par ex

        if step == 0:
            break

        sug = step if remaining > 0 else -step
        out.append({"Date": pd.to_datetime(d), "Suggestion_Heures": sug})
        remaining -= sug

    return pd.DataFrame(out)


# --- 4.4 UI Pane : Ciblage AT/PAX ---
def render_at_pax_targeting_panel():
    st.markdown("### 🎯 Ciblage via ratio AT / 1000 PAX")

    c1, c2, c3 = st.columns(3)
    with c1:
        flux = st.selectbox("Flux PAX", ["Tous", "Arrivée", "Départ"], index=0)
    with c2:
        prefer_modifie = st.toggle("Utiliser Budget **Modifié** (sinon Annuel)", value=True)
    with c3:
        pax_min = st.number_input("Seuil PAX minimum/jour", min_value=0.0, value=2000.0, step=500.0)

    c4, c5, c6 = st.columns(3)
    with c4:
        qmin = st.slider("Filtre quantile bas PAX", 0.0, 0.9, 0.3, 0.05, help="Ignore les jours trop petits en trafic.")
    with c5:
        smooth = st.toggle("Lisser le ratio (médiane 7j)", value=False)
    with c6:
        cap_per_day = st.number_input("Cap/jour (heures)", min_value=0.1, value=1.0, step=0.1)

    df = _build_ratio_table(flux, prefer_modifie, pax_min, qmin=qmin, smooth=smooth)
    if df.empty:
        st.info("Pas de données suffisantes pour calculer le ratio AT/PAX.")
        return

    st.dataframe(
        df.sort_values("Ratio_AT_pour_1000PAX", ascending=False),
        hide_index=True, use_container_width=True,
        column_config={
            "Pax_Total": st.column_config.NumberColumn(format="%.0f"),
            "Heures_AT": st.column_config.NumberColumn(format="%.1f h"),
            "Ratio_AT_pour_1000PAX": st.column_config.NumberColumn("AT / 1000 PAX", format="%.2f"),
        }
    )

    # Scatter Mois vs Ratio (taille = PAX)
    chart = alt.Chart(df).mark_circle().encode(
        x=alt.X("month(Date):T", title="Mois"),
        y=alt.Y("Ratio_AT_pour_1000PAX:Q", title="AT / 1000 PAX"),
        size=alt.Size("Pax_Total:Q", title="PAX/jour", legend=None),
        color=alt.Color("Saison:N", title="Saison"),
        tooltip=[
            alt.Tooltip("Date:T", format="%d %B %Y"),
            alt.Tooltip("Jour_FR:N", title="Jour"),
            alt.Tooltip("Mois_FR:N", title="Mois"),
            alt.Tooltip("Pax_Total:Q", title="PAX/jour", format=","),
            alt.Tooltip("Heures_AT:Q", title="Heures AT", format=","),
            alt.Tooltip("Ratio_AT_pour_1000PAX:Q", title="AT/1000", format=".2f"),
        ]
    ).properties(height=320)
    st.altair_chart(chart, use_container_width=True)

    st.markdown("#### Générer des **suggestions d’heures** automatiquement")
    delta_side = st.radio("Objectif", ["Réduire des heures (delta < 0)", "Ajouter des heures (delta > 0)"], horizontal=True)
    sign = -1.0 if delta_side.startswith("Réduire") else +1.0
    delta_hours = st.number_input("Delta d'heures total (ex. 10 = +10h,  -10 = −10h)",
                                  value=0.0, step=1.0) * (1.0 if sign > 0 else -1.0)

    locked = st.multiselect(
        "Verrouiller des dates (sans modification)",
        options=[d.date() for d in df["Date"].sort_values().unique()],
        default=[]
    )

    # Ordonner selon le sens de l’objectif
    rank = df.sort_values("Ratio_AT_pour_1000PAX", ascending=(sign > 0)).reset_index(drop=True)
    if st.button("Proposer des jours cibles (AT/PAX)"):
        suggestions = _distribute_delta_hours(delta_hours, rank, cap_per_day, set(locked))
        if suggestions.empty:
            st.warning("Aucune suggestion n’a pu être générée (paramètres trop stricts ?).")
        else:
            st.success(f"{len(suggestions)} jours proposés (cap/jour {cap_per_day}h).")
            st.dataframe(
                suggestions,
                hide_index=True, use_container_width=True,
                column_config={"Suggestion_Heures": st.column_config.NumberColumn(format="%.1f h")}
            )
            # Sauvegarde pour qu’un autre panneau puisse consommer
            st.session_state["assistant_at_pax_suggestions"] = suggestions.copy()





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

    # Saison présente dans ton modèle (sinon Standard)
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
                                    max_per_day: float) -> pd.DataFrame:
    """
    Construit des suggestions pour UNE catégorie.
    - df_candidates doit contenir 'Date','Jour','Saison','Mois_FR' et une colonne 'Heures_base'
    - target_hours : peut être >0 (ajouter) ou <0 (réduire)
    """
    required = {'Date', 'Jour', 'Saison', 'Mois_FR', 'Heures_base'}
    missing = required - set(df_candidates.columns)
    if missing:
        raise KeyError(f"Colonnes manquantes pour _build_suggestions_for_category({cat}): {sorted(missing)}")

    df = df_candidates.copy()
    if df.empty or abs(target_hours) == 0:
        return pd.DataFrame(columns=[
            'Catégorie', 'Date', 'Jour', 'Saison', 'Mois_FR',
            'Heures_base', 'Ajustement_propose', 'Heures_nouvelles'
        ])

    # Mode par catégorie
    mode = 'add' if target_hours > 0 else 'reduce'
    remaining = abs(float(target_hours))
    sign = 1.0 if mode == 'add' else -1.0

    # Tri : pour réduire → jours les plus chargés d’abord ; pour ajouter → les moins chargés
    df = df.sort_values('Heures_base', ascending=(mode == 'add')).reset_index(drop=True)

    rows = []
    for _, r in df.iterrows():
        if remaining <= 0:
            break

        proposed = min(remaining, max_per_day)
        proposed = float(np.ceil(proposed / step) * step)  # multiple du step—arrondi haut

        base = float(r['Heures_base'])
        if mode == 'reduce':
            new_val = max(0.0, base - proposed)
            effective = base - new_val  # ajustement réel si on touche 0
            signed = -effective
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
    cats = sorted(set(cats))
    if "AT" in cats:
        cats.remove("AT")
        cats = ["AT"] + cats
    return cats


def _get_targets_from_simulator(selected_cats: list[str]) -> dict[str, float] | None:
    """
    Lit st.session_state['simulateur_objectif_results'] et en déduit
    les cibles d'ajustement d'heures par catégorie.
    Retourne None si indisponible.
    """
    sim_df = st.session_state.get("simulateur_objectif_results", pd.DataFrame())
    if sim_df is None or sim_df.empty:
        return None
    if "Catégorie" not in sim_df.columns:
        return None

    # Cherche une colonne contenant l'ajustement d'heures
    hour_col = None
    for c in sim_df.columns:
        c_low = str(c).lower()
        if ("ajustement" in c_low or "adjust" in c_low) and ("heure" in c_low or c_low.endswith("(h)") or "h)" in c_low or " hours" in c_low):
            hour_col = c
            break
    if hour_col is None:
        # fallback : si une colonne ressemble à "Ajustement Heures (h)" ou "Ajustement Heures"
        for c in sim_df.columns:
            if "heure" in str(c).lower():
                hour_col = c
                break
    if hour_col is None:
        return None

    # Agrège par catégorie (certaines versions du simulateur listent plusieurs lignes/cat)
    pick = sim_df[sim_df['Catégorie'].isin(selected_cats)].copy()
    if pick.empty:
        return None

    # Somme par catégorie (positif = ajouter, négatif = réduire)
    grp = pick.groupby('Catégorie', dropna=True)[hour_col].sum().to_dict()

    # Cast en float & nettoyer les NaN
    targets = {}
    for k in selected_cats:
        v = float(grp.get(k, 0.0)) if grp.get(k, 0.0) is not None else 0.0
        # Pas de normalisation de signe ici : on respecte le signe par catégorie
        targets[k] = round(v, 2)

    return targets if any(abs(v) > 0 for v in targets.values()) else None


# ============================================================
# Page
# ============================================================

def render_besoin_jour_assistant_page():
    st.title("Assistant Besoin Jour (auto depuis Simulateur)")
    st.markdown(
        "Génère des **suggestions d’ajustements d’heures par catégorie**.\n\n"
        "- Si des résultats existent dans **Simulateur d’Objectif**, ils sont **importés automatiquement**.\n"
        "- Sinon, vous pouvez **saisir manuellement** les cibles d’ajustement (heures) par catégorie.\n"
        "- Les **verrous** (mois / saisons / jours) s’appliquent à **toutes** les catégories."
    )
    st.markdown("---")
    render_at_pax_targeting_panel()

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

    # ===================== Paramètres globaux =====================
    with st.container(border=True):
        st.subheader("Paramètres d'application")
        c1, c2 = st.columns([1, 1])
        with c1:
            step = st.select_slider("Pas (heures)", options=[0.25, 0.5, 1.0, 2.0], value=0.5)
        with c2:
            max_per_day = st.number_input(
                "Ajustement max par jour (h, par catégorie)",
                min_value=float(step), max_value=24.0,
                value=2.0, step=float(step), format="%.2f"
            )

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
        st.subheader("Catégories à ajuster")
        selected_cats = st.multiselect(
            "Choisissez les catégories concernées",
            options=cats_all,
            default=[c for c in cats_all if c in ("AT", "ATR", "ATF")] or cats_all[:3],
            key="abj_selected_cats"
        )
        if not selected_cats:
            st.info("Sélectionnez au moins une catégorie.")
            st.stop()

    # ===================== Cibles : Auto (Simulateur) → fallback Manuel =====================
    targets_by_cat: dict[str, float] = {c: 0.0 for c in selected_cats}
    auto_targets = _get_targets_from_simulator(selected_cats)

    if auto_targets is not None:
        with st.container(border=True):
            st.subheader("Cibles importées du Simulateur d’Objectif")
            scale = st.slider(
                "Facteur d'échelle des cibles du Simulateur",
                min_value=0.0, max_value=2.0, value=1.0, step=0.05
            )
            for cat in selected_cats:
                targets_by_cat[cat] = round(float(auto_targets.get(cat, 0.0)) * scale, 2)

            # Aperçu rapide
            df_preview = pd.DataFrame(
                [{'Catégorie': c, 'Cible (heures)': targets_by_cat[c]} for c in selected_cats]
            )
            st.dataframe(df_preview, hide_index=True, use_container_width=True)
            st.caption("Astuce : si vous voulez ignorer le Simulateur, mettez le facteur à 0 et utilisez le bloc de saisie manuelle ci-dessous.")

        # Option de surcouche manuelle (facultative)
        with st.expander("➕ Surcharge manuelle (facultatif)"):
            cols = st.columns(min(5, max(1, len(selected_cats))))
            for i, cat in enumerate(selected_cats):
                with cols[i % len(cols)]:
                    add_delta = st.number_input(
                        f"Δ {cat} (h) (+/-)",
                        value=0.0, step=1.0, format="%.1f", key=f"abj_manual_overlay_{cat}"
                    )
                    targets_by_cat[cat] = round(targets_by_cat[cat] + add_delta, 2)
    else:
        with st.container(border=True):
            st.subheader("Cibles (Saisie manuelle)")
            cols = st.columns(min(5, max(1, len(selected_cats))))
            for i, cat in enumerate(selected_cats):
                with cols[i % len(cols)]:
                    targets_by_cat[cat] = st.number_input(
                        f"{cat} (h)  (+ = ajouter,  − = réduire)",
                        value=0.0, step=1.0, format="%.1f", key=f"abj_manual_target_{cat}"
                    )

    # Résumé total
    total_target = sum(targets_by_cat.values())
    st.metric("Cible totale (toutes catégories)", f"{total_target:+.1f} h")

    # ===================== Génération des suggestions =====================
    with st.container(border=True):
        st.subheader("Suggestions d’ajustements")

        all_suggestions = []
        for cat in selected_cats:
            target_cat = float(targets_by_cat.get(cat, 0.0))
            if abs(target_cat) < 0.001:
                continue  # pas de cible pour cette catégorie

            # Prépare un DF candidats avec Heures_base = Heures_{cat}
            dfc = candidates_common.copy()
            dfc['Heures_base'] = _hours_series_for_category(bs['calendar_df'], cat)

            out = _build_suggestions_for_category(
                df_candidates=dfc[['Date', 'Jour', 'Saison', 'Mois_FR', 'Heures_base']],
                cat=cat,
                target_hours=target_cat,           # signe respecté par catégorie
                step=float(step),
                max_per_day=float(max_per_day),
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

        with st.expander("Exports par catégorie"):
            cats_in_results = suggestions['Catégorie'].dropna().unique().tolist()
            for cat in cats_in_results:
                dfc = suggestions[suggestions['Catégorie'] == cat].copy()
                st.download_button(
                    f"Exporter {cat} (CSV)",
                    data=dfc.to_csv(index=False).encode('utf-8'),
                    file_name=f"suggestions_{cat}_{year}.csv",
                    mime="text/csv",
                    use_container_width=True,
                    key=f"dl_{cat}_csv"
                )

    st.caption(
        "💡 Applique ces propositions manuellement dans **Besoin Jour**. "
        "Si tu veux un export d’**ops JSON** prêtes à injecter, dis-moi le format attendu et je le produis."
    )
