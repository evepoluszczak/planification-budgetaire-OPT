# ui/pages/simulateur_objectif.py
"""
Page Simulateur Objectif - Simulation d'objectifs de coût (améliorée)
- Presets d'objectif (+/- 2/5/10 %)
- Auto-répartition (équitable, pro-rata planifié, pro-rata coût horaire)
- Verrouillage de catégories, cap par catégorie, arrondi configurable
- Visualisations (barres triées + pseudo-waterfall)
- Scénarios (enregistrer, comparer, exporter)
"""
from __future__ import annotations

import io
import numpy as np
import pandas as pd
import streamlit as st
import altair as alt


# =========================
# Helpers données & calculs
# =========================

def _get_all_categories() -> list[str]:
    """Récupère la liste des catégories depuis st.session_state.perimetres (clés)."""
    perims = st.session_state.get("perimetres", {}) or {}
    return sorted(list(perims.keys()))


def _get_cost_mapping() -> dict:
    """Mapping catégorie -> Type personnel (pour retrouver le coût horaire)."""
    return st.session_state.get("cost_mapping", {}) or {}


def _get_personnel_df() -> pd.DataFrame:
    """Table des coûts horaires (colonnes attendues: 'Type', 'Coût Horaire')."""
    df = st.session_state.get("personnel", pd.DataFrame())
    return df if isinstance(df, pd.DataFrame) else pd.DataFrame()


def _hourly_rate_for_type(perso_df: pd.DataFrame, perso_type: str) -> float:
    """Retourne le coût horaire d'un type (0.0 si non trouvé/invalid)."""
    try:
        row = perso_df[perso_df["Type"] == perso_type]
        if not row.empty:
            val = float(row["Coût Horaire"].iloc[0])
            return val if val > 0 else 0.0
    except Exception:
        pass
    return 0.0


def _hourly_rates_by_category() -> tuple[dict[str, float], list[str]]:
    """
    Construit un dict {cat: cout_horaire} via cost_mapping + personnel.
    Retourne également la liste des catégories à problème (tarif manquant/invalide).
    """
    mapping = _get_cost_mapping()
    perso = _get_personnel_df()
    cats = _get_all_categories()

    rates, missing = {}, []
    for cat in cats:
        t = mapping.get(cat)
        if not t:
            rates[cat] = 0.0
            missing.append(f"'{cat}' (pas de mapping)")
            continue
        r = _hourly_rate_for_type(perso, t)
        if r <= 0:
            rates[cat] = 0.0
            missing.append(f"'{cat}' (tarif invalide ou 0)")
        else:
            rates[cat] = r
    return rates, missing


def _safe_to_float(x, default=0.0) -> float:
    try:
        return float(x)
    except Exception:
        return float(default)


def _compute_training_costs() -> tuple[float, float]:
    """
    Calcule les coûts 'formation AT' et 'formateurs ATF' pour être cohérent
    avec Budget Annuel / Analyse.
    Retourne (cout_formation_AT, cout_formateurs_ATF)
    """
    # AT
    at_rate = 45.50
    pers = _get_personnel_df()
    if not pers.empty:
        at_rate = _hourly_rate_for_type(pers, "AT") or at_rate

    total_heures_formation = 0.0
    if "budget_formation_at" in st.session_state:
        df_formation = st.session_state.budget_formation_at.copy()
        df_formation["Effectif (pers.)"] = pd.to_numeric(
            df_formation.get("Effectif (pers.)", 0), errors="coerce"
        ).fillna(0).astype(int).clip(lower=0)
        df_formation["Heures"] = df_formation.get("Heures", 0).apply(
            lambda x: float(str(x).replace(",", ".")) if pd.notna(x) else 0.0
        ).clip(lower=0)
        df_formation["Nbre de shifts"] = pd.to_numeric(
            df_formation.get("Nbre de shifts", 0), errors="coerce"
        ).fillna(0).astype(int).clip(lower=0)
        df_formation["Total (heures)"] = (
            df_formation["Effectif (pers.)"]
            * df_formation["Heures"]
            * df_formation["Nbre de shifts"]
        )
        total_heures_formation = _safe_to_float(df_formation["Total (heures)"].sum(), 0.0)
    cout_formation = total_heures_formation * at_rate

    # ATF
    atf_rate = 52.00
    if not pers.empty:
        atf_rate = _hourly_rate_for_type(pers, "ATF") or atf_rate

    total_heures_formateurs = 0.0
    if "budget_formateurs_at" in st.session_state:
        df_form = st.session_state.budget_formateurs_at.copy()
        df_form["Effectif (pers.)"] = pd.to_numeric(
            df_form.get("Effectif (pers.)", 0), errors="coerce"
        ).fillna(0).astype(int).clip(lower=0)
        df_form["Heures"] = df_form.get("Heures", 0).apply(
            lambda x: float(str(x).replace(",", ".")) if pd.notna(x) else 0.0
        ).clip(lower=0)
        df_form["Nbre de shifts"] = pd.to_numeric(
            df_form.get("Nbre de shifts", 0), errors="coerce"
        ).fillna(0).astype(int).clip(lower=0)
        df_form["Total (heures)"] = (
            df_form["Effectif (pers.)"]
            * df_form["Heures"]
            * df_form["Nbre de shifts"]
        )
        total_heures_formateurs = _safe_to_float(df_form["Total (heures)"].sum(), 0.0)
    cout_formateurs = total_heures_formateurs * atf_rate

    return cout_formation, cout_formateurs


def _base_cost_total_with_training() -> float:
    """
    Budget annuel planifié + formation + formateurs (cohérent avec les autres pages).
    """
    bs = st.session_state.get("budget_state", {}) or {}
    planif = _safe_to_float(bs.get("totals", {}).get("cout_annuel", 0.0), 0.0)
    c_form, c_formateurs = _compute_training_costs()
    return planif + c_form + c_formateurs


def _weights_equitable() -> dict[str, float]:
    """Répartition équitable entre catégories."""
    cats = _get_all_categories()
    if not cats:
        return {}
    w = 1.0 / len(cats)
    return {c: w for c in cats}


def _weights_from_calendar_costs() -> dict[str, float]:
    """
    Pro-rata des coûts planifiés par catégorie via calendar_df (Budget Annuel).
    Utilise les colonnes 'Coût_<cat>' si présentes, sinon heuristique = sum heures * tarif.
    """
    cats = _get_all_categories()
    bs = st.session_state.get("budget_state", {}) or {}
    cal = bs.get("calendar_df", pd.DataFrame())
    if not isinstance(cal, pd.DataFrame) or cal.empty:
        return _weights_equitable()

    rates, _ = _hourly_rates_by_category()
    # Tente d'utiliser des colonnes 'Coût_<cat>' si elles existent
    has_cost_cols = any([f"Coût_{c}" in cal.columns for c in cats])

    weights = {}
    for c in cats:
        if has_cost_cols and f"Coût_{c}" in cal.columns:
            v = _safe_to_float(cal[f"Coût_{c}"].sum(), 0.0)
        else:
            # fallback heuristique: heures * tarif
            h_col = f"Heures_{c}"
            h = _safe_to_float(cal[h_col].sum(), 0.0) if h_col in cal.columns else 0.0
            v = h * _safe_to_float(rates.get(c, 0.0), 0.0)
        weights[c] = max(0.0, v)

    # Normalisation
    total = sum(weights.values())
    if total <= 0:
        return _weights_equitable()
    return {k: v / total for k, v in weights.items()}


def _weights_from_hourly_rates() -> dict[str, float]:
    """
    Pro-rata des coûts horaires (cat plus chère = plus de poids).
    """
    rates, _ = _hourly_rates_by_category()
    # si tous 0 → équitable
    total = sum([max(0.0, r) for r in rates.values()])
    if total <= 0:
        return _weights_equitable()
    return {c: max(0.0, r) / total for c, r in rates.items()}


def _normalize_distribution(pcts: dict[str, float], locked: set[str]) -> dict[str, float]:
    """
    Normalise pour total 100%, sans toucher aux catégories verrouillées
    (leurs % sont conservés tels quels).
    """
    cats = _get_all_categories()
    fixed = sum([pcts.get(c, 0.0) for c in cats if c in locked])
    free = [c for c in cats if c not in locked]

    remaining = max(0.0, 100.0 - fixed)
    current_free_total = sum([pcts.get(c, 0.0) for c in free])

    if current_free_total <= 0:
        # tout le restant équitablement entre free
        if free:
            eq = remaining / len(free)
            for c in free:
                pcts[c] = round(eq, 1)
        return pcts

    ratio = remaining / current_free_total
    for c in free:
        pcts[c] = round(pcts.get(c, 0.0) * ratio, 1)
    return pcts


def _apply_cap_on_target_shares(pcts: dict[str, float], cap_pct: float) -> dict[str, float]:
    """
    Applique un cap (max %) par catégorie sur la PART de l'objectif (et renormalise).
    """
    if cap_pct >= 100.0:
        return pcts

    # Cap
    capped = {c: min(v, cap_pct) for c, v in pcts.items()}
    total = sum(capped.values())
    if total <= 0:
        return pcts  # rien à répartir

    # Renormalise à 100%
    return {c: round(v / total * 100.0, 1) for c, v in capped.items()}


def _round_value(val: float, mode: str) -> float:
    if mode == "Plafond (ceil)":
        return float(np.ceil(val))
    if mode == "Plancher (floor)":
        return float(np.floor(val))
    return float(np.round(val))


def _results_table(target_adjustment: float,
                   distrib_pct: dict[str, float],
                   hourly_rates: dict[str, float],
                   rounding: str) -> pd.DataFrame:
    """
    Construit la table résultat (par catégorie).
    """
    rows = []
    total_pct = sum(distrib_pct.values()) or 1.0
    for cat, pct in distrib_pct.items():
        share = (pct / total_pct)
        cost_adj_raw = target_adjustment * share
        cost_adj = _round_value(cost_adj_raw, rounding)

        rate = _safe_to_float(hourly_rates.get(cat, 0.0), 0.0)
        if rate > 0:
            hours_raw = cost_adj_raw / rate
            hours = _round_value(hours_raw, rounding)
        else:
            hours = np.nan  # non calculable (tarif manquant)

        rows.append({
            "Catégorie": cat,
            "Part Répartition (%)": round(pct, 1),
            "Ajustement Coût (CHF)": float(cost_adj),
            "Tarif Horaire (CHF)": float(rate),
            "Ajustement Heures (h)": float(hours) if pd.notna(hours) else None
        })
    df = pd.DataFrame(rows)
    # n'affiche pas les 0% pour plus de lisibilité
    df = df[df["Part Répartition (%)"] > 0].copy()
    # tri par impact coût desc
    df = df.sort_values("Ajustement Coût (CHF)", ascending=False)
    return df


def _export_scenario_excel(scen_name: str, scen_payload: dict) -> bytes:
    """Crée un fichier Excel en mémoire pour un scénario."""
    out = io.BytesIO()
    with pd.ExcelWriter(out, engine="xlsxwriter") as xw:
        # Résultats
        if "results" in scen_payload and isinstance(scen_payload["results"], pd.DataFrame):
            scen_payload["results"].to_excel(xw, sheet_name="Résultats", index=False)
        # Hypothèses
        hyp = {
            "Objectif (CHF)": [scen_payload.get("target_adjustment", 0.0)],
            "Arrondi": [scen_payload.get("rounding", "")],
            "Cap (%)": [scen_payload.get("cap_pct", 100.0)],
        }
        df_hyp = pd.DataFrame(hyp)
        df_hyp.to_excel(xw, sheet_name="Hypothèses", index=False)

        # Répartition
        distrib = scen_payload.get("distribution", {})
        if isinstance(distrib, dict) and distrib:
            df_distrib = pd.DataFrame(
                [{"Catégorie": k, "Part (%)": v} for k, v in distrib.items()]
            )
            df_distrib.to_excel(xw, sheet_name="Répartition", index=False)
    out.seek(0)
    return out.read()


# =========================
# Page principale
# =========================

def render_simulateur_objectif_page():
    """Affiche la page Simulateur Objectif (version améliorée)."""

    st.title("Simulateur d'Objectif de Coût")
    st.markdown(
        "Simulez l'impact en heures d'un **ajustement de coût global** (augmentation/réduction) "
        "en le répartissant sur les catégories. *Ce simulateur n’applique pas de règles Besoin Jour.*"
    )

    # Pré-requis : Budget généré
    bs = st.session_state.get("budget_state", {}) or {}
    if not bs or "year" not in bs or "calendar_df" not in bs or bs["calendar_df"] is None or bs["calendar_df"].empty:
        st.warning("⚠️ Aucun budget annuel valide en mémoire. "
                   "Veuillez d'abord en générer un via la page **Budget Annuel**.")
        st.stop()

    # Base de référence (cohérente avec Analyse / Budget Annuel)
    base_cost_total = _base_cost_total_with_training()

    st.markdown("---")
    with st.container(border=True):
        st.subheader("Simulation d'Objectif de Coût Annuel")
        st.metric("Budget Annuel de Base (avec formation)", f"{base_cost_total:,.0f} CHF")

        # ==== Presets d'objectif ====
        colp1, colp2, colp3, colp4, colp5 = st.columns(5)
        with colp1:
            if st.button("−2%"):
                st.session_state.sim_target_adjustment = round(-0.02 * base_cost_total, 0)
        with colp2:
            if st.button("−5%"):
                st.session_state.sim_target_adjustment = round(-0.05 * base_cost_total, 0)
        with colp3:
            if st.button("−10%"):
                st.session_state.sim_target_adjustment = round(-0.10 * base_cost_total, 0)
        with colp4:
            if st.button("+2%"):
                st.session_state.sim_target_adjustment = round(+0.02 * base_cost_total, 0)
        with colp5:
            if st.button("Réinitialiser"):
                st.session_state.sim_target_adjustment = 0.0
                st.session_state.sim_target_percent = 0.0
        
        # ==== Mode d'objectif : CHF ou % ====
        mode_obj = st.radio(
            "Mode d'objectif",
            ["Montant (CHF)", "Pourcentage (%)"],
            horizontal=True,
            key="sim_mode_objectif",
        )
        
        if mode_obj == "Montant (CHF)":
            target_adjustment = st.number_input(
                "Objectif d'ajustement (CHF — négatif pour réduire)",
                value=_safe_to_float(st.session_state.get("sim_target_adjustment", 0.0), 0.0),
                step=1000.0,
                format="%.0f",
                key="sim_target_adjustment",
                help="Saisir un montant total à répartir entre les catégories (ex: -150000 pour réduire de 150k).",
            )
        else:
            # % manuel de l’utilisateur, appliqué à la base (avec formation)
            target_percent = st.number_input(
                "Objectif d'ajustement (%) — négatif pour réduire",
                value=_safe_to_float(st.session_state.get("sim_target_percent", 0.0), 0.0),
                step=0.5,
                format="%.1f",
                key="sim_target_percent",
                help="Ex: -5.0 pour réduire de 5% le budget annuel (avec formation).",
            )
            target_adjustment = round(base_cost_total * (target_percent / 100.0), 0)


        # ==== Stratégies d'auto-répartition ====
        st.markdown("**Remplissage automatique de la répartition (%)**")
        colm1, colm2, colm3, colm4 = st.columns(4)
        do_equitable = colm1.button("Équitable")
        do_planif = colm2.button("Pro-rata **coûts planifiés**")
        do_rates = colm3.button("Pro-rata **coûts horaires**")
        do_clear = colm4.button("Tout mettre à 0%")

        cats = _get_all_categories()
        # init state for distrib
        for c in cats:
            st.session_state.setdefault(f"distrib_pct_{c}", 0.0)

        if do_equitable:
            w = _weights_equitable()
            for c, p in w.items():
                st.session_state[f"distrib_pct_{c}"] = round(p * 100.0, 1)

        if do_planif:
            w = _weights_from_calendar_costs()
            for c, p in w.items():
                st.session_state[f"distrib_pct_{c}"] = round(p * 100.0, 1)

        if do_rates:
            w = _weights_from_hourly_rates()
            for c, p in w.items():
                st.session_state[f"distrib_pct_{c}"] = round(p * 100.0, 1)

        if do_clear:
            for c in cats:
                st.session_state[f"distrib_pct_{c}"] = 0.0

        st.markdown("**Répartition manuelle (%)**")

        # ==== Options d’application ====
        col_opt1, col_opt2, col_opt3 = st.columns(3)
        with col_opt1:
            rounding = st.selectbox("Arrondi", ["Au plus proche", "Plafond (ceil)", "Plancher (floor)"], index=0)
        with col_opt2:
            cap_pct = st.number_input("Cap par catégorie (%)", min_value=0.0, max_value=100.0, value=100.0, step=1.0,
                                      help="Limite la part maximale de l'objectif assignable à une catégorie.")
        with col_opt3:
            locked_cats = st.multiselect("Verrouiller des catégories (inchangées)",
                                         options=cats, default=[], help="Les % verrouillés ne seront pas renormalisés.")

        # ==== Saisie des pourcentages ====
        distrib_pct = {}
        total_pct = 0.0
        cols_per_row = 5
        n_rows = (len(cats) + cols_per_row - 1) // cols_per_row
        it = iter(cats)
        for _ in range(n_rows):
            row = st.columns(cols_per_row)
            for col in row:
                try:
                    c = next(it)
                except StopIteration:
                    break
                key = f"distrib_pct_{c}"
                val = st.number_input(f"% {c}",
                                      min_value=0.0, max_value=100.0, step=1.0,
                                      key=key, format="%.1f")
                distrib_pct[c] = _safe_to_float(val, 0.0)
                total_pct += distrib_pct[c]

        # Bandeau d’état
        rates, missing_rates = _hourly_rates_by_category()
        st.info(
            f"État: Répartition={total_pct:.1f}% | Arrondi={rounding} | Cap={cap_pct:.0f}% | "
            f"Catégories sans tarif: {len(missing_rates)}"
        )
        if missing_rates:
            st.warning("Vérifiez les tarifs dans **Configuration → Personnel** : " + ", ".join(missing_rates))

        # Normalisations (verrous + cap + 100%)
        # 1) Applique cap
        distrib_pct = _apply_cap_on_target_shares(distrib_pct, cap_pct)
        # 2) Renormalise à 100% en respectant les verrous
        distrib_pct = _normalize_distribution(distrib_pct, set(locked_cats))
        total_pct = sum(distrib_pct.values())

        if abs(total_pct - 100.0) > 0.1:
            st.warning(f"Le total des pourcentages est **{total_pct:.1f}%**. "
                       f"Il devrait être de 100%. La normalisation automatique est appliquée.")

        st.divider()

        # ==== Calcul & affichages ====
        if target_adjustment == 0:
            st.info("Saisissez un objectif d'ajustement non nul pour lancer la simulation.")
            return

        results_df = _results_table(target_adjustment, distrib_pct, rates, rounding)

        st.subheader("Résultat de la Simulation")
        st.dataframe(
            results_df,
            hide_index=True,
            use_container_width=True,
            column_config={
                "Part Répartition (%)": st.column_config.NumberColumn(format="%.1f%%"),
                "Ajustement Coût (CHF)": st.column_config.NumberColumn(format="%.0f"),
                "Tarif Horaire (CHF)": st.column_config.NumberColumn(format="%.2f"),
                "Ajustement Heures (h)": st.column_config.NumberColumn(format="%.0f"),
            },
        )

        # Deltas globaux
        new_total = base_cost_total + target_adjustment
        colg1, colg2, colg3 = st.columns(3)
        with colg1:
            st.metric("Objectif (Δ coût)", f"{target_adjustment:,.0f} CHF")
        with colg2:
            st.metric("Budget après ajustement", f"{new_total:,.0f} CHF")
        with colg3:
            # total heures simulées (ignore NaN)
            tot_hours = results_df["Ajustement Heures (h)"].fillna(0).sum()
            st.metric("Variation estimée d'heures", f"{tot_hours:,.0f} h")

        # ==== Visualisations ====
        st.markdown("### Visualisations")
        if not results_df.empty:
            top = results_df.sort_values("Ajustement Coût (CHF)", ascending=False)

            # Barres (CHF)
            bar_chf = alt.Chart(top).mark_bar().encode(
                x=alt.X("Ajustement Coût (CHF):Q", title="Impact (CHF)"),
                y=alt.Y("Catégorie:N", sort='-x', title="Catégorie"),
                tooltip=[
                    alt.Tooltip("Catégorie:N"),
                    alt.Tooltip("Part Répartition (%):Q", format=".1f"),
                    alt.Tooltip("Ajustement Coût (CHF):Q", format=","),
                    alt.Tooltip("Ajustement Heures (h):Q", format=","),
                    alt.Tooltip("Tarif Horaire (CHF):Q", format=".2f"),
                ],
                color=alt.value("#0076AA") if target_adjustment >= 0 else alt.value("#DC143C")
            ).properties(height=320)

            st.altair_chart(bar_chf, use_container_width=True)

            # Pseudo-waterfall (cumul sur l'ordre trié)
            wf_df = top.copy()
            wf_df["Cumul (CHF)"] = wf_df["Ajustement Coût (CHF)"].cumsum()

            wf_line = alt.Chart(wf_df).mark_line(point=True).encode(
                x=alt.X("Catégorie:N", title="Catégorie"),
                y=alt.Y("Cumul (CHF):Q", title="Cumul (CHF)"),
                tooltip=[alt.Tooltip("Catégorie:N"), alt.Tooltip("Cumul (CHF):Q", format=",")]
            ).properties(height=260)

            st.altair_chart(wf_line, use_container_width=True)

        st.divider()

        # ==== Scénarios ====
        st.subheader("Scénarios")
        sc_name = st.text_input("Nom du scénario", value="Scénario 1")

        if st.button("💾 Enregistrer le scénario"):
            scen_payload = {
                "target_adjustment": float(target_adjustment),
                "distribution": {c: float(distrib_pct.get(c, 0.0)) for c in _get_all_categories()},
                "rounding": rounding,
                "cap_pct": float(cap_pct),
                "results": results_df.copy(),
            }
            st.session_state.setdefault("sim_scenarios", {})[sc_name] = scen_payload
            st.success(f"Scénario **{sc_name}** enregistré.")

        # Export du scénario courant
        if not results_df.empty:
            xbytes = _export_scenario_excel(sc_name, {
                "target_adjustment": float(target_adjustment),
                "distribution": {c: float(distrib_pct.get(c, 0.0)) for c in _get_all_categories()},
                "rounding": rounding,
                "cap_pct": float(cap_pct),
                "results": results_df.copy(),
            })
            st.download_button(
                "⬇️ Exporter ce scénario (Excel)",
                data=xbytes,
                file_name=f"simulateur_objectif_{sc_name}.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            )

        # Comparaison de scénarios
        scen_keys = list(st.session_state.get("sim_scenarios", {}).keys())
        if len(scen_keys) >= 2:
            colc1, colc2 = st.columns(2)
            with colc1:
                sA = st.selectbox("Scénario A", scen_keys, key="cmpA")
            with colc2:
                sB = st.selectbox("Scénario B", scen_keys, key="cmpB")

            if sA and sB and sA != sB:
                A = st.session_state.sim_scenarios[sA]["results"]
                B = st.session_state.sim_scenarios[sB]["results"]
                cmp = A.merge(B, on="Catégorie", how="outer", suffixes=(" A", " B")).fillna(0)
                cmp["Δ Coût (B−A)"] = cmp["Ajustement Coût (CHF) B"] - cmp["Ajustement Coût (CHF) A"]
                cmp["Δ Heures (B−A)"] = cmp["Ajustement Heures (h) B"] - cmp["Ajustement Heures (h) A"]

                st.markdown("#### Comparaison A vs B")
                st.dataframe(cmp, use_container_width=True)

                # Petite visu des deltas
                if not cmp.empty:
                    cmp_bar = alt.Chart(cmp).transform_fold(
                        ["Δ Coût (B−A)", "Δ Heures (B−A)"],
                        as_=["Type", "Delta"]
                    ).mark_bar().encode(
                        x=alt.X("Delta:Q", title="Delta (B−A)"),
                        y=alt.Y("Catégorie:N", sort='-x'),
                        color=alt.Color("Type:N", legend=alt.Legend(title="Mesure")),
                        tooltip=["Catégorie", "Type", alt.Tooltip("Delta:Q", format=",")]
                    ).properties(height=320)
                    st.altair_chart(cmp_bar, use_container_width=True)

    # Aide
    with st.expander("ℹ️ Aide & Hypothèses"):
        st.markdown("""
- **Ce simulateur n’applique pas les règles opérationnelles** (*Besoin Jour*). Il sert à estimer
  l'impact **macro** d’un objectif de coût, converti en heures via les tarifs.
- Utilisez les **presets** pour gagner du temps (±2/5/10 %), puis affinez avec la **répartition**.
- Les **verrous** conservent le pourcentage saisi pour certaines catégories (protégées).
- Le **cap** limite la part maximale de l’objectif assignable par catégorie.
- L’**arrondi** s’applique aux montants et aux heures.
- Enregistrez des **scénarios** pour comparer les impacts et **exportez** vers Excel.
""")


if __name__ == "__main__":
    render_simulateur_objectif_page()
