# ui/pages/simulateur_objectif.py
"""
Page Simulateur Objectif - Simulation d'objectifs de coût (améliorée)
- Montant (CHF) OU Pourcentage (%)
- Presets d'objectif (+/- 2/5/10 %)
- Auto-répartition (équitable, pro-rata planifié, pro-rata coût horaire)
- Verrouillage de catégories, cap par catégorie, arrondi configurable
- Visualisations (barres triées + pseudo-waterfall)
- Scénarios (enregistrer, comparer, exporter)
- Export XLSX avec fallback (openpyxl), sinon CSV
- Sauvegarde automatique des résultats dans st.session_state
"""
from __future__ import annotations

import io
import numpy as np
import pandas as pd
import streamlit as st
import altair as alt
from datetime import datetime

from models.suggestion import AjustementPropose


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
    has_cost_cols = any([f"Coût_{c}" in cal.columns for c in cats])

    weights = {}
    for c in cats:
        col_cost = f"Coût_{c}"
        if has_cost_cols and col_cost in cal.columns:
            v = _safe_to_float(cal[col_cost].sum(), 0.0)
        else:
            h_col = f"Heures_{c}"
            h = _safe_to_float(cal[h_col].sum(), 0.0) if h_col in cal.columns else 0.0
            v = h * _safe_to_float(rates.get(c, 0.0), 0.0)
        weights[c] = max(0.0, v)

    total = sum(weights.values())
    if total <= 0:
        return _weights_equitable()
    return {k: v / total for k, v in weights.items()}


def _weights_from_hourly_rates() -> dict[str, float]:
    """Pro-rata des coûts horaires (cat plus chère = plus de poids)."""
    rates, _ = _hourly_rates_by_category()
    total = sum([max(0.0, r) for r in rates.values()])
    if total <= 0:
        return _weights_equitable()
    return {c: max(0.0, r) / total for c, r in rates.items()}


def _apply_cap_and_normalize(pcts: dict[str, float], cap_pct: float, locked: set[str]) -> dict[str, float]:
    """
    Applique un cap (%) et renormalise à 100% en EXCLUANT les catégories verrouillées.
    - Les catégories verrouillées sont forcées à 0% et jamais renormalisées.
    - Tout le 100% est réparti entre les catégories non verrouillées.
    """
    # 1) Verrou = 0
    out = {c: (0.0 if c in locked else max(0.0, p)) for c, p in pcts.items()}

    # 2) Espace libre = catégories non verrouillées
    free = [c for c in out.keys() if c not in locked]
    if not free:
        return out  # tout verrouillé -> tout à 0

    # 3) Cap sur les "free"
    if cap_pct < 100.0:
        for c in free:
            out[c] = min(out[c], cap_pct)

    # 4) Renormalisation des "free" vers 100%
    total_free = sum(out[c] for c in free)
    if total_free <= 0:
        # Si l'utilisateur a mis 0 partout, on répartit équitablement entre free
        eq = 100.0 / len(free)
        for c in free:
            out[c] = round(eq, 1)
        return out

    for c in free:
        out[c] = round(out[c] / total_free * 100.0, 1)

    # locked restent à 0
    for c in locked:
        out[c] = 0.0

    return out


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
    """Construit la table résultat (par catégorie)."""
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
    df = df[df["Part Répartition (%)"] > 0].copy()
    df = df.sort_values("Ajustement Coût (CHF)", ascending=False)
    return df


def _export_scenario_excel(scen_name: str, scen_payload: dict) -> tuple[bytes, str, str]:
    """
    Tente d'exporter en XLSX (xlsxwriter, puis openpyxl en fallback).
    Si les deux moteurs ne sont pas dispo, exporte un CSV de secours.
    Retourne: (bytes, extension, mime)
    """
    def _build_writer(writer):
        # Résultats
        if "results" in scen_payload and isinstance(scen_payload["results"], pd.DataFrame):
            scen_payload["results"].to_excel(writer, sheet_name="Résultats", index=False)

        # Hypothèses
        hyp = {
            "Objectif (CHF)": [scen_payload.get("target_adjustment", 0.0)],
            "Arrondi": [scen_payload.get("rounding", "")],
            "Cap (%)": [scen_payload.get("cap_pct", 100.0)],
        }
        pd.DataFrame(hyp).to_excel(writer, sheet_name="Hypothèses", index=False)

        # Répartition
        distrib = scen_payload.get("distribution", {})
        if isinstance(distrib, dict) and distrib:
            df_distrib = pd.DataFrame([{"Catégorie": k, "Part (%)": v} for k, v in distrib.items()])
            df_distrib.to_excel(writer, sheet_name="Répartition", index=False)

    # 1) Essai avec xlsxwriter
    try:
        out = io.BytesIO()
        with pd.ExcelWriter(out, engine="xlsxwriter") as xw:
            _build_writer(xw)
        out.seek(0)
        return out.read(), "xlsx", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    except Exception:
        pass

    # 2) Fallback openpyxl
    try:
        out = io.BytesIO()
        with pd.ExcelWriter(out, engine="openpyxl") as xw:
            _build_writer(xw)
        out.seek(0)
        return out.read(), "xlsx", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    except Exception:
        pass

    # 3) Ultime fallback CSV (exporte uniquement la feuille 'Résultats')
    try:
        results = scen_payload.get("results")
        if isinstance(results, pd.DataFrame) and not results.empty:
            csv_bytes = results.to_csv(index=False).encode("utf-8")
            return csv_bytes, "csv", "text/csv"
    except Exception:
        pass

    st.error("Impossible de générer un fichier d’export (XLSX/CSV).")
    return b"", "bin", "application/octet-stream"


def _import_scenario_from_file(uploaded_file) -> dict | None:
    """
    Importe un scénario depuis un fichier Excel ou CSV exporté.
    Retourne un dict avec: {
        'target_adjustment': float,
        'distribution': dict[str, float],
        'rounding': str,
        'cap_pct': float,
        'results': pd.DataFrame
    }
    Retourne None en cas d'erreur.
    """
    try:
        filename = uploaded_file.name.lower()

        if filename.endswith('.xlsx') or filename.endswith('.xls'):
            # Lire le fichier Excel (3 feuilles attendues)
            excel_file = pd.ExcelFile(uploaded_file)

            # Feuille 1: Résultats
            if "Résultats" in excel_file.sheet_names:
                results_df = pd.read_excel(excel_file, sheet_name="Résultats")
            else:
                st.error("Feuille 'Résultats' introuvable dans le fichier Excel.")
                return None

            # Feuille 2: Hypothèses
            if "Hypothèses" in excel_file.sheet_names:
                hyp_df = pd.read_excel(excel_file, sheet_name="Hypothèses")
                target_adjustment = float(hyp_df.iloc[0]["Objectif (CHF)"])
                rounding = str(hyp_df.iloc[0]["Arrondi"])
                cap_pct = float(hyp_df.iloc[0]["Cap (%)"])
            else:
                st.warning("Feuille 'Hypothèses' introuvable. Valeurs par défaut utilisées.")
                target_adjustment = 0.0
                rounding = "Au plus proche"
                cap_pct = 100.0

            # Feuille 3: Répartition
            if "Répartition" in excel_file.sheet_names:
                distrib_df = pd.read_excel(excel_file, sheet_name="Répartition")
                distribution = {
                    str(row["Catégorie"]): float(row["Part (%)"])
                    for _, row in distrib_df.iterrows()
                }
            else:
                st.warning("Feuille 'Répartition' introuvable. Reconstruction depuis Résultats.")
                distribution = {
                    str(row["Catégorie"]): float(row.get("Part Répartition (%)", 0))
                    for _, row in results_df.iterrows()
                }

        elif filename.endswith('.csv'):
            # Lire CSV (contient uniquement les résultats)
            results_df = pd.read_csv(uploaded_file)

            # Reconstruire les métadonnées depuis les résultats
            if "Part Répartition (%)" in results_df.columns:
                distribution = {
                    str(row["Catégorie"]): float(row["Part Répartition (%)"])
                    for _, row in results_df.iterrows()
                }
            else:
                st.error("Colonne 'Part Répartition (%)' introuvable dans le CSV.")
                return None

            # Calculer target_adjustment depuis les résultats
            if "Ajustement Coût (CHF)" in results_df.columns:
                target_adjustment = float(results_df["Ajustement Coût (CHF)"].sum())
            else:
                st.error("Colonne 'Ajustement Coût (CHF)' introuvable dans le CSV.")
                return None

            # Valeurs par défaut pour les autres paramètres
            rounding = "Au plus proche"
            cap_pct = 100.0
            st.info("Format CSV détecté. Hypothèses par défaut: Arrondi='Au plus proche', Cap=100%")

        else:
            st.error(f"Format de fichier non supporté: {filename}. Utilisez .xlsx, .xls ou .csv")
            return None

        # Validation des résultats
        required_cols = ["Catégorie", "Part Répartition (%)", "Ajustement Coût (CHF)"]
        missing_cols = [col for col in required_cols if col not in results_df.columns]
        if missing_cols:
            st.error(f"Colonnes manquantes dans le fichier: {', '.join(missing_cols)}")
            return None

        return {
            'target_adjustment': target_adjustment,
            'distribution': distribution,
            'rounding': rounding,
            'cap_pct': cap_pct,
            'results': results_df
        }

    except Exception as e:
        st.error(f"Erreur lors de l'import du fichier: {e}")
        return None


def _auto_create_ajustement_propose(results_df: pd.DataFrame,
                                     target_adjustment: float) -> None:
    """
    Crée automatiquement l'ajustement_propose pour l'Assistant Besoin Jour
    à partir des résultats du simulateur.
    """
    from datetime import datetime
    from models.suggestion import AjustementPropose

    # Créer la distribution à partir du DataFrame résultats
    distribution = {}
    for _, row in results_df.iterrows():
        cat = str(row['Catégorie'])
        delta_h = row.get('Ajustement Heures (h)', 0)
        delta_c = row.get('Ajustement Coût (CHF)', 0)
        part_p = row.get('Part Répartition (%)', 0)

        # Gérer les NaN
        delta_h = float(delta_h) if pd.notna(delta_h) else 0.0
        delta_c = float(delta_c) if pd.notna(delta_c) else 0.0
        part_p = float(part_p) if pd.notna(part_p) else 0.0

        distribution[cat] = {
            'delta_hours': delta_h,
            'delta_chf': delta_c,
            'percentage': part_p
        }

    total_hours = results_df['Ajustement Heures (h)'].fillna(0).sum()

    # Récupérer les verrous si définis
    locked_perimetres = st.session_state.get('locked_perimetres_assist', [])

    ajustement = AjustementPropose(
        total_delta_hours=float(total_hours),
        total_delta_chf=float(target_adjustment),
        distribution=distribution,
        locks={
            'categories': [],
            'perimetres': locked_perimetres,
            'dates': []
        },
        timestamp=datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    )

    # Stocker dans session_state
    st.session_state.ajustement_propose = ajustement


def _save_simulator_results_to_session(results_df: pd.DataFrame,
                                       target_adjustment: float,
                                       distribution_pct: dict[str, float],
                                       rounding: str,
                                       cap_pct: float) -> None:
    """
    Sauvegarde les résultats du simulateur dans st.session_state
    pour consommation par l'assistant Besoin Jour.
    Crée aussi automatiquement l'ajustement_propose pour l'Assistant.
    """
    if results_df is None or results_df.empty:
        st.session_state.pop("simulateur_objectif_results", None)
        st.session_state.pop("simulateur_objectif_meta", None)
        return

    df = results_df.copy()
    if "Catégorie" in df.columns:
        df["Catégorie"] = df["Catégorie"].astype(str)

    st.session_state["simulateur_objectif_results"] = df
    st.session_state["simulateur_objectif_meta"] = {
        "target_adjustment": float(target_adjustment),
        "distribution_pct": {k: float(v) for k, v in distribution_pct.items()},
        "rounding": str(rounding),
        "cap_pct": float(cap_pct),
        "saved_at": pd.Timestamp.now().isoformat(timespec="seconds")
    }

    # Créer automatiquement l'ajustement_propose pour l'Assistant
    _auto_create_ajustement_propose(df, target_adjustment)


# =========================
# Page principale
# =========================

def render_simulateur_objectif_page():
    """Affiche la page Simulateur Objectif (version améliorée)."""

    st.title("Simulateur d'Objectif de Coût")
    st.markdown(
        "Simulez l'impact en heures d'un **ajustement de coût global** (augmentation/réduction) "
        "en le répartissant sur les catégories. *Ce simulateur n'applique pas les règles Besoin Jour.*"
    )

    # Pré-requis : Budget généré
    bs = st.session_state.get("budget_state", {}) or {}
    if not bs or "year" not in bs or "calendar_df" not in bs or bs["calendar_df"] is None or bs["calendar_df"].empty:
        st.warning("⚠️ Aucun budget annuel valide en mémoire. "
                   "Veuillez d'abord en générer un via la page **Budget Annuel**.")
        st.stop()

    # Base de référence (cohérente avec Analyse / Budget Annuel)
    base_cost_total = _base_cost_total_with_training()

    # Initialize session state keys for widgets (avoid value/session_state conflict)
    if "sim_target_adjustment" not in st.session_state:
        st.session_state.sim_target_adjustment = 0.0
    if "sim_target_percent" not in st.session_state:
        st.session_state.sim_target_percent = 0.0

    # Gérer l'import de scénario (avant la création des widgets)
    if 'pending_scenario_import' in st.session_state:
        imported_data = st.session_state.pending_scenario_import

        # Supprimer les clés liées aux widgets pour pouvoir les réassigner
        for key in ['sim_target_adjustment', 'sim_target_percent']:
            if key in st.session_state:
                del st.session_state[key]

        # Assigner les nouvelles valeurs
        st.session_state.sim_target_adjustment = imported_data['target_adjustment']
        st.session_state.sim_target_percent = (
            imported_data['target_adjustment'] / base_cost_total * 100.0
            if base_cost_total > 0 else 0.0
        )

        # Restaurer la distribution
        for cat, pct in imported_data['distribution'].items():
            key = f"distrib_pct_{cat}"
            if key in st.session_state:
                del st.session_state[key]
            st.session_state[key] = float(pct)

        # Restaurer les résultats
        _save_simulator_results_to_session(
            results_df=imported_data['results'],
            target_adjustment=imported_data['target_adjustment'],
            distribution_pct=imported_data['distribution'],
            rounding=imported_data['rounding'],
            cap_pct=imported_data['cap_pct']
        )

        # Nettoyer la clé temporaire
        del st.session_state.pending_scenario_import

        st.success(f"✅ Scénario chargé avec succès ! Objectif: {imported_data['target_adjustment']:,.0f} CHF")
        st.rerun()

    # ==== Import de scénario (disponible dès le départ) ====
    st.markdown("---")
    with st.expander("📁 Charger un scénario depuis un fichier"):
        st.markdown("Importez un scénario exporté précédemment pour le réutiliser.")
        uploaded_file = st.file_uploader(
            "Sélectionner un fichier de scénario (Excel ou CSV)",
            type=["xlsx", "xls", "csv"],
            key="scenario_uploader",
            help="Chargez un scénario exporté précédemment pour le réutiliser"
        )

        if uploaded_file is not None:
            if st.button("⬆️ Charger ce scénario", key="load_scenario_btn", type="primary"):
                imported_data = _import_scenario_from_file(uploaded_file)

                if imported_data:
                    # Stocker dans une clé temporaire pour traitement au prochain rendu
                    st.session_state.pending_scenario_import = imported_data
                    st.rerun()

    st.markdown("---")
    with st.container(border=True):
        st.subheader("Simulation d'Objectif de Coût Annuel")
        st.metric("Budget Annuel de Base (avec formation)", f"{base_cost_total:,.0f} CHF")

        # ==== Presets d'objectif ====
        st.markdown("**Ajustements rapides**")
        col_spacer1, colp1, colp2, colp3, colp4, colp5, col_spacer2 = st.columns([1, 1, 1, 1, 1, 1.5, 1])
        with colp1:
            if st.button("−2%", use_container_width=True):
                st.session_state.sim_target_adjustment = round(-0.02 * base_cost_total, 0)
                st.session_state.sim_target_percent = -2.0
        with colp2:
            if st.button("−5%", use_container_width=True):
                st.session_state.sim_target_adjustment = round(-0.05 * base_cost_total, 0)
                st.session_state.sim_target_percent = -5.0
        with colp3:
            if st.button("−10%", use_container_width=True):
                st.session_state.sim_target_adjustment = round(-0.10 * base_cost_total, 0)
                st.session_state.sim_target_percent = -10.0
        with colp4:
            if st.button("+2%", use_container_width=True):
                st.session_state.sim_target_adjustment = round(+0.02 * base_cost_total, 0)
                st.session_state.sim_target_percent = +2.0
        with colp5:
            if st.button("↺ Reset", use_container_width=True):
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
                step=1000.0,
                format="%.0f",
                key="sim_target_adjustment",
                help="Saisir un montant total à répartir entre les catégories (ex: -150000 pour réduire de 150k).",
            )
        else:
            # % manuel appliqué à la base (avec formation)
            target_percent = st.number_input(
                "Objectif d'ajustement (%) — négatif pour réduire",
                step=0.5,
                format="%.1f",
                key="sim_target_percent",
                help="Ex: -5.0 pour réduire de 5% le budget annuel (avec formation).",
            )
            target_adjustment = round(base_cost_total * (target_percent / 100.0), 0)

        st.divider()

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
                                         options=cats, default=[], help="Les % verrouillés restent à 0% et ne sont jamais renormalisés.")

        # ==== Saisie des pourcentages ====
        distrib_pct = {}
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

        # Normalisations (verrous + cap + 100%)
        distrib_pct = _apply_cap_and_normalize(distrib_pct, cap_pct, set(locked_cats))
        total_pct = sum(distrib_pct.values())

        # Bandeau d’état (après normalisation)
        rates, missing_rates = _hourly_rates_by_category()
        st.info(
            f"État: Répartition normalisée={total_pct:.1f}% | Arrondi={rounding} | Cap={cap_pct:.0f}% | "
            f"Catégories verrouillées: {len(locked_cats)} | Sans tarif: {len(missing_rates)}"
        )
        if missing_rates:
            st.warning("Tarifs manquants/invalides dans **Configuration → Personnel** : " + ", ".join(missing_rates))
        if abs(total_pct - 100.0) > 0.1:
            st.warning(f"Le total est **{total_pct:.1f}%**. La normalisation automatique a été appliquée.")

        st.divider()

        # ==== Calcul & affichages ====
        # Vérifier si on a des résultats sauvegardés à afficher
        has_saved_results = (
            "simulateur_objectif_results" in st.session_state and
            st.session_state["simulateur_objectif_results"] is not None and
            not st.session_state["simulateur_objectif_results"].empty
        )

        if target_adjustment == 0:
            # Si pas d'objectif actuel mais résultats sauvegardés, les afficher
            if has_saved_results:
                col_info, col_clear = st.columns([4, 1])
                with col_info:
                    st.info("📋 Affichage des résultats précédents (ajustez l'objectif pour recalculer)")
                with col_clear:
                    if st.button("🗑️ Effacer", help="Effacer les résultats sauvegardés"):
                        st.session_state.pop("simulateur_objectif_results", None)
                        st.session_state.pop("simulateur_objectif_meta", None)
                        st.rerun()

                results_df = st.session_state["simulateur_objectif_results"].copy()
                saved_meta = st.session_state.get("simulateur_objectif_meta", {})
                saved_target = saved_meta.get("target_adjustment", 0)

                # Restaurer automatiquement l'ajustement_propose pour l'Assistant
                _auto_create_ajustement_propose(results_df, saved_target)

                # Afficher métadonnées
                if saved_meta:
                    col_meta1, col_meta2, col_meta3 = st.columns(3)
                    with col_meta1:
                        st.metric("Objectif précédent", f"{saved_target:,.0f} CHF")
                    with col_meta2:
                        st.caption(f"Arrondi: {saved_meta.get('rounding', 'N/A')}")
                    with col_meta3:
                        st.caption(f"Sauvegardé: {saved_meta.get('saved_at', 'N/A')}")
            else:
                st.info("Saisissez un objectif d'ajustement non nul pour lancer la simulation.")
                return
        else:
            # Calculer de nouveaux résultats
            results_df = _results_table(target_adjustment, distrib_pct, rates, rounding)

            # ⬇️ Enregistrement automatique pour l'assistant Besoin Jour
            _save_simulator_results_to_session(
                results_df=results_df,
                target_adjustment=target_adjustment,
                distribution_pct=distrib_pct,
                rounding=rounding,
                cap_pct=cap_pct
            )

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
            tot_hours = results_df["Ajustement Heures (h)"].fillna(0).sum()
            st.metric("Variation estimée d'heures", f"{tot_hours:,.0f} h")

        # ==== Visualisations ====
        st.markdown("### Visualisations")
        if not results_df.empty:
            top = results_df.sort_values("Ajustement Coût (CHF)", ascending=False)

            # Barres (CHF)
            # Remarque : Altair v5 exige des noms de champs valides et types corrects.
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

            # (optionnel) rafraîchir l’état partagé pour l’assistant :
            _save_simulator_results_to_session(
                results_df=results_df,
                target_adjustment=target_adjustment,
                distribution_pct=distrib_pct,
                rounding=rounding,
                cap_pct=cap_pct
            )

        # Export du scénario courant (avec fallback automatique)
        if not results_df.empty:
            file_bytes, ext, mime = _export_scenario_excel(sc_name, {
                "target_adjustment": float(target_adjustment),
                "distribution": {c: float(distrib_pct.get(c, 0.0)) for c in _get_all_categories()},
                "rounding": rounding,
                "cap_pct": float(cap_pct),
                "results": results_df.copy(),
            })

            label = "⬇️ Exporter ce scénario"
            if ext == "csv":
                label += " (CSV – fallback)"
            else:
                label += " (Excel)"

            st.download_button(
                label,
                data=file_bytes,
                file_name=f"simulateur_objectif_{sc_name}.{ext}",
                mime=mime
            )

        st.divider()

        # === Comparaison de scénarios (robuste) ===
        scen_keys = list(st.session_state.get("sim_scenarios", {}).keys())
        if len(scen_keys) >= 2:
            colc1, colc2 = st.columns(2)
            with colc1:
                sA = st.selectbox("Scénario A", scen_keys, key="cmpA")
            with colc2:
                sB = st.selectbox("Scénario B", scen_keys, key="cmpB")
        
            if sA and sB and sA != sB:
                try:
                    A = st.session_state.sim_scenarios[sA]["results"].copy()
                    B = st.session_state.sim_scenarios[sB]["results"].copy()
        
                    # Garantir la présence des colonnes et numeric
                    for df_ in (A, B):
                        for col in ["Ajustement Coût (CHF)", "Ajustement Heures (h)"]:
                            if col not in df_.columns:
                                df_[col] = 0.0
                            df_[col] = pd.to_numeric(df_[col], errors="coerce")
        
                    # Merge et deltas
                    cmp = A.merge(B, on="Catégorie", how="outer", suffixes=("_A", "_B"))
                    cmp["Delta_Cout"] = (
                        cmp["Ajustement Coût (CHF)_B"].fillna(0.0) - cmp["Ajustement Coût (CHF)_A"].fillna(0.0)
                    ).astype(float)
                    cmp["Delta_Heures"] = (
                        cmp["Ajustement Heures (h)_B"].fillna(0.0) - cmp["Ajustement Heures (h)_A"].fillna(0.0)
                    ).astype(float)
        
                    # Affichage tableau comparaison
                    cmp_display = cmp[[
                        "Catégorie",
                        "Ajustement Coût (CHF)_A", "Ajustement Coût (CHF)_B", "Delta_Cout",
                        "Ajustement Heures (h)_A", "Ajustement Heures (h)_B", "Delta_Heures",
                    ]].copy()
        
                    st.markdown("#### Comparaison A vs B")
                    st.dataframe(
                        cmp_display,
                        use_container_width=True,
                        hide_index=True,
                        column_config={
                            "Ajustement Coût (CHF)_A": st.column_config.NumberColumn("Coût (A)", format="%.0f"),
                            "Ajustement Coût (CHF)_B": st.column_config.NumberColumn("Coût (B)", format="%.0f"),
                            "Delta_Cout": st.column_config.NumberColumn("Δ Coût (B−A)", format="%.0f"),
                            "Ajustement Heures (h)_A": st.column_config.NumberColumn("Heures (A)", format="%.0f"),
                            "Ajustement Heures (h)_B": st.column_config.NumberColumn("Heures (B)", format="%.0f"),
                            "Delta_Heures": st.column_config.NumberColumn("Δ Heures (B−A)", format="%.0f"),
                        },
                    )
        
                    # Long format propre pour Altair
                    long = cmp.melt(
                        id_vars="Catégorie",
                        value_vars=["Delta_Cout", "Delta_Heures"],
                        var_name="Type",
                        value_name="Delta",
                    )
                    long = long[pd.notna(long["Delta"])].copy()
                    long["Delta"] = long["Delta"].astype(float)
                    long["Type"] = long["Type"].map({
                        "Delta_Cout": "Δ Coût (B−A)",
                        "Delta_Heures": "Δ Heures (B−A)",
                    })
        
                    # Barres des deltas
                    if not long.empty:
                        cmp_bar = alt.Chart(long).mark_bar().encode(
                            x=alt.X("Delta:Q", title="Delta (B−A)"),
                            y=alt.Y("Catégorie:N", sort='-x'),
                            color=alt.Color("Type:N", legend=alt.Legend(title="Mesure")),
                            tooltip=[
                                alt.Tooltip("Catégorie:N"),
                                alt.Tooltip("Type:N"),
                                alt.Tooltip("Delta:Q", format=","),
                            ],
                        ).properties(height=320)
                        st.altair_chart(cmp_bar, use_container_width=True)
                    else:
                        st.info("Aucun delta à afficher.")
        
                except Exception as e:
                    st.warning(f"Comparaison : affichage du graphique indisponible ({e}).")
                    # On n'empêche pas la page de fonctionner — le tableau ci-dessus reste utile.

        st.divider()

        # ==== Intégration Assistant Besoin Jour ====
        st.subheader("🤖 Assistant Besoin Jour")

        # Vérifier si ajustement est disponible
        if 'ajustement_propose' in st.session_state and st.session_state.ajustement_propose:
            st.success(
                "✅ Ajustement automatiquement disponible pour l'Assistant Besoin Jour ! "
                "Rendez-vous sur la page **Assistant Besoin Jour** pour générer les suggestions."
            )

            # Afficher info sur l'ajustement
            ajust = st.session_state.ajustement_propose
            col_info1, col_info2 = st.columns(2)
            with col_info1:
                st.caption(f"📊 Total: {ajust.total_delta_chf:+,.0f} CHF / {ajust.total_delta_hours:+,.1f} h")
            with col_info2:
                nb_categories = len([k for k, v in ajust.distribution.items() if v.get('delta_chf', 0) != 0])
                st.caption(f"📂 {nb_categories} catégorie(s) impactée(s)")
        else:
            st.info("Aucun ajustement en attente pour l'Assistant.")

        # Options avancées (verrous)
        with st.expander("⚙️ Options Avancées (Verrous)"):
            st.markdown(
                "Les verrous empêchent l'assistant de modifier certains "
                "périmètres ou dates spécifiques."
            )
            locked_perimetres_assist = st.multiselect(
                "Verrouiller des périmètres (AT)",
                options=st.session_state.get("perimetres", {}).get("AT", []),
                default=st.session_state.get('locked_perimetres_assist', []),
                key="locked_perimetres_assist"
            )

            # Mettre à jour les verrous dans l'ajustement si modifiés
            if 'ajustement_propose' in st.session_state and st.session_state.ajustement_propose:
                st.session_state.ajustement_propose.locks['perimetres'] = locked_perimetres_assist


    # Aide
    with st.expander("ℹ️ Aide & Hypothèses"):
        st.markdown("""
- **Ce simulateur n’applique pas les règles opérationnelles** (*Besoin Jour*). Il sert à estimer
  l'impact **macro** d’un objectif de coût, converti en heures via les tarifs.
- Utilisez les **presets** pour gagner du temps (±2/5/10 %), puis affinez avec la **répartition**.
- Les **verrous** conservent la catégorie à **0%** (pas d’impact) et elle n’est pas renormalisée.
- Le **cap** limite la part maximale de l’objectif assignable par catégorie.
- L’**arrondi** s’applique aux montants et aux heures.
- Enregistrez des **scénarios** pour comparer les impacts et **exportez** vers Excel (ou CSV fallback).
""")


if __name__ == "__main__":
    render_simulateur_objectif_page()
