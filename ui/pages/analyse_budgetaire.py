# ui/pages/analyse_budgetaire.py
# ============================================================
# Analyse Budgétaire (vue mensuelle et annuelle)
# - Priorité au nouveau format de facturation (Libellé/Quantité/Prix/Montant)
# - Fallback automatique sur l'ancien format (Date ouvrable/Heures) si besoin
# - Totaux mensuels = somme des Montants (nouveau format)
# - Répartition annuelle par Type
# - Calibration: comparaison Prix facturé vs Tarif App (si disponible)
# ============================================================

from __future__ import annotations

import calendar
import datetime as dt
from typing import Dict, Optional

import pandas as pd
import streamlit as st

from config.constants import FACTU_AT_DIR
from core.data_loader import (
    load_facturation_month_flexible,
    load_facturation_by_type_month,
    get_month_factu_total_amount,
    build_yearly_factu_summary,
)


# ---------- Helpers d'affichage ----------

def _fmt_chf(x: Optional[float]) -> str:
    if x is None:
        return "—"
    try:
        # Espace fin comme séparateur de milliers (remplace la virgule)
        return f"{float(x):,.2f} CHF".replace(",", " ")
    except Exception:
        return str(x)

def _fmt_float(x: Optional[float]) -> str:
    if x is None:
        return "—"
    try:
        return f"{float(x):,.2f}".replace(",", " ")
    except Exception:
        return str(x)

def _month_selector(label: str, default_month: int) -> int:
    # renvoie un int [1..12]
    months = list(range(1, 13))
    month_names = [f"{m:02d} - {calendar.month_name[m]}" for m in months]
    idx = months.index(default_month if default_month in months else dt.date.today().month)
    pick = st.selectbox(label, options=list(zip(months, month_names)), index=idx, format_func=lambda t: t[1])
    return pick[0]


# ---------- Calibration : récupération des tarifs applicatifs ----------

def _get_app_tarifs() -> Dict[str, float]:
    """
    Récupère un mapping {Type -> TarifHoraireApp} depuis:
      1) st.session_state['tarifs_type'] si présent (ex: {"AT": 45.5, "ATR": 52, ...})
      2) config.constants.TARIFS_TYPE si défini
      3) sinon, {}
    """
    # 1) session
    try:
        tarifs = st.session_state.get("tarifs_type")
        if isinstance(tarifs, dict) and tarifs:
            # normalise les clés (types) en uppercase
            return {str(k).strip().upper(): float(v) for k, v in tarifs.items() if v is not None}
    except Exception:
        pass

    # 2) constants
    try:
        from config.constants import TARIFS_TYPE  # optionnel
        if isinstance(TARIFS_TYPE, dict) and TARIFS_TYPE:
            return {str(k).strip().upper(): float(v) for k, v in TARIFS_TYPE.items() if v is not None}
    except Exception:
        pass

    # 3) défaut
    return {}


# ---------- Page principale ----------

def render_analyse_budgetaire_page():
    st.title("Analyse Budgétaire")

    # --- Sélecteurs de période ---
    colA, colB, colC = st.columns([1, 1, 2])
    with colA:
        year = st.number_input(
            "Année",
            value=st.session_state.get("ab_year", dt.date.today().year),
            min_value=2020,
            max_value=2050,
            step=1,
            help="Année d'analyse budgétaire"
        )
        st.session_state["ab_year"] = year

    with colB:
        month = _month_selector("Mois", st.session_state.get("ab_month", dt.date.today().month))
        st.session_state["ab_month"] = month

    with colC:
        st.caption(f"Période sélectionnée : **{calendar.month_name[month]} {int(year)}**")

    st.markdown("---")

    # --- Chargement mensuel (format flexible) ---
    df_factu, fmt = load_facturation_month_flexible(int(year), int(month), FACTU_AT_DIR)

    if fmt == "new":
        st.subheader(f"Facturation – {calendar.month_name[month]} {year} (nouveau format)")
        st.caption("Colonnes : **Type / Quantité / Prix / Montant**")
        # Mise en forme des colonnes numériques pour lecture confortable
        df_show = df_factu.copy()
        for col in ["Quantité", "Prix", "Montant", "Ecart_Calcule"]:
            if col in df_show.columns:
                if col == "Quantité":
                    df_show[col] = df_show[col].map(_fmt_float)
                elif col == "Prix":
                    df_show[col] = df_show[col].map(_fmt_float)
                else:
                    df_show[col] = df_show[col].map(_fmt_chf)
        st.dataframe(df_show, use_container_width=True, hide_index=True)

        # KPI total mensuel (somme des Montants)
        total_montant = get_month_factu_total_amount(int(year), int(month), FACTU_AT_DIR)
        st.metric("Total facturé (mois)", _fmt_chf(total_montant))

        # Alerte sur l'écart Q×P vs Montant
        if "Ecart_Calcule" in df_factu.columns:
            ecart_abs = float(pd.to_numeric(df_factu["Ecart_Calcule"], errors="coerce").abs().sum())
            if ecart_abs > 0.01:
                st.warning(
                    f"Écart cumulé **Quantité × Prix vs Montant** : **{_fmt_chf(ecart_abs)}**. "
                    f"Vérifie les colonnes source si l'écart paraît anormal."
                )

    elif fmt == "old":
        st.subheader(f"Facturation – {calendar.month_name[month]} {year} (ancien format)")
        st.caption("Colonnes : **Date ouvrable / Heures** (pas de 'Montant' disponible)")
        st.dataframe(df_factu, use_container_width=True)
        st.info("Ancien format : total du mois (CHF) non calculable ici, uniquement des heures par date.")

    else:
        st.warning(f"Aucun fichier de facturation détecté pour {calendar.month_name[month]} {year}.")
        st.stop()

    st.markdown("---")

    # --- Vue annuelle : un total par mois (si nouveau format) ---
    st.subheader(f"Vue annuelle – {int(year)}")

    df_year = build_yearly_factu_summary(int(year), FACTU_AT_DIR)
    # Mise en forme pour le tableau
    df_year_show = df_year.copy()
    if "Total_Montant_CHF" in df_year_show.columns:
        df_year_show["Total_Montant_CHF"] = df_year_show["Total_Montant_CHF"].map(
            lambda v: _fmt_chf(v) if pd.notna(v) else "—"
        )
    # Ajoute noms de mois lisibles
    df_year_show["Mois (Nom)"] = df_year_show["Mois"].astype(int).map(lambda m: calendar.month_name[m])
    df_year_show = df_year_show[["Mois", "Mois (Nom)", "Format", "Total_Montant_CHF"]]

    st.dataframe(df_year_show, use_container_width=True, hide_index=True)

    # Graphique annuel si on a des montants
    df_plot = df_year.dropna(subset=["Total_Montant_CHF"]).copy()
    if not df_plot.empty:
        df_plot["MoisLabel"] = df_plot["Mois"].astype(int).map(lambda m: f"{m:02d}-{calendar.month_abbr[m]}")
        chart_data = df_plot.set_index("MoisLabel")["Total_Montant_CHF"]
        st.bar_chart(chart_data)
    else:
        st.info("Aucun mois au nouveau format (Montant) pour tracer un graphique annuel.")

    st.markdown("---")

    # --- Répartition annuelle par Type (nouveau format uniquement) ---
    st.subheader(f"Répartition annuelle par Type – {int(year)} (nouveau format)")

    agg_type = []
    for m in range(1, 13):
        df_type = load_facturation_by_type_month(int(year), m, FACTU_AT_DIR)
        if df_type is None or df_type.empty:
            continue
        # On garde uniquement Type et Montant
        tmp = df_type[["Type", "Montant"]].copy()
        tmp["Mois"] = m
        agg_type.append(tmp)

    if agg_type:
        df_types_year = pd.concat(agg_type, ignore_index=True)

        # Totaux annuels par Type
        df_types_total = (
            df_types_year
            .groupby("Type", as_index=False)["Montant"]
            .sum()
            .sort_values("Montant", ascending=False)
        )

        # Affichage tableau formaté
        df_types_total_show = df_types_total.copy()
        df_types_total_show["Montant"] = df_types_total_show["Montant"].map(_fmt_chf)
        st.dataframe(df_types_total_show, use_container_width=True, hide_index=True)

        # Graphique barres
        st.bar_chart(df_types_total.set_index("Type")["Montant"])
    else:
        st.info("Aucune donnée au nouveau format pour afficher la répartition annuelle par Type.")

    st.markdown("---")

    # --- Calibration : Tarifs App vs Prix facturé (mois sélectionné) ---
    st.subheader("Calibration tarifs (App) vs Prix facturé – Mois sélectionné")

    if fmt == "new":
        app_tarifs = _get_app_tarifs()  # mapping {Type -> TarifHoraireApp}
        if not app_tarifs:
            st.info(
                "Aucun tarif applicatif détecté. "
                "Tu peux définir un dict dans `st.session_state['tarifs_type']` "
                "ou `config.constants.TARIFS_TYPE` (ex: {'AT': 45.5, 'ATR': 52})."
            )
        # Prépare comparaison
        comp = df_factu[["Type", "Prix"]].copy()
        comp = comp.groupby("Type", as_index=False)["Prix"].median()
        comp["Tarif_App"] = comp["Type"].map(app_tarifs).astype(float)
        comp["Ecart_(Facturé - App)"] = (comp["Prix"] - comp["Tarif_App"]).round(2)

        # Présentation lisible
        comp_show = comp.copy()
        comp_show["Prix"] = comp_show["Prix"].map(_fmt_float)
        comp_show["Tarif_App"] = comp_show["Tarif_App"].map(lambda v: _fmt_float(v) if pd.notna(v) else "—")
        comp_show["Ecart_(Facturé - App)"] = comp_show["Ecart_(Facturé - App)"].map(
            lambda v: _fmt_float(v) if pd.notna(v) else "—"
        )

        st.dataframe(
            comp_show.rename(columns={
                "Type": "Type",
                "Prix": "Prix (Facturé) – CHF/h",
                "Tarif_App": "Tarif App – CHF/h",
                "Ecart_(Facturé - App)": "Écart – CHF/h"
            }),
            use_container_width=True,
            hide_index=True
        )

        # Petit récap global si tarifs app présents
        if app_tarifs:
            ecart_abs_moy = float(
                pd.to_numeric(comp["Ecart_(Facturé - App)"], errors="coerce")
                .abs().dropna().mean()
            ) if not comp.empty else 0.0
            st.caption(f"Écart moyen absolu (CHF/h) : **{_fmt_float(ecart_abs_moy)}**")

    else:
        st.info("Calibration indisponible sur l'ancien format (pas de 'Prix').")


# Si tu utilises un routeur simple (optionnel)
if __name__ == "__main__":
    # Pour lancer cette page seule via `streamlit run ui/pages/analyse_budgetaire.py`
    render_analyse_budgetaire_page()
