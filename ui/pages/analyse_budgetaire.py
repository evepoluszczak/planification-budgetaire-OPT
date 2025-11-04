"""
Page Analyse Budgétaire - Comparaison Budget Annuel vs Modifié vs Réalisé
"""
import datetime as dt
from pathlib import Path
import re
import pandas as pd
import streamlit as st
import altair as alt

from config.constants import FACTU_AT_DIR, FACTU_AT_GLOB, TIME_SLOTS
from core.planning import _ensure_grid, _apply_ops_to_grid

# IMPORTANT : ces utilitaires doivent être présents dans utils/pdf_parser.py
# - load_pdf_facturation_data(dir_path, year) -> DataFrame avec au moins: Date, (Heures_* / Coût_* par catégorie) + éventuellement InvoiceKey/InvoiceFile
# - get_category_mapping_for_pdf(pdf_categories, app_categories) -> dict auto
# - apply_category_mapping(pdf_df, mapping) -> renvoie un DF avec Heures_/Coût_ remappés vers les catégories de l'app
# - PDF_AVAILABLE bool
from utils.pdf_parser import (
    load_pdf_facturation_data,
    get_category_mapping_for_pdf,
    apply_category_mapping,
    PDF_AVAILABLE
)


# ========================== CHARGEMENT FACTURATION ==========================

def load_facturation_data_for_year(year: int) -> pd.DataFrame:
    """
    Charge et agrège tous les fichiers de facturation pour une année donnée.
    - Excel « Facturation Lot A mm.yyyy.xlsx » (ancien format)
    - PDF structurés par mois (nouveau format via utils/pdf_parser)
    Retour:
        DataFrame normalisé contenant au minimum:
        Date, Heures_Total, Cout_Total
        + (éventuellement) Heures_<Cat>, Coût_<Cat> par catégorie.
    """
    factu_dir = Path(FACTU_AT_DIR)
    if not factu_dir.exists():
        st.error(f"Le répertoire de facturation n'existe pas: {factu_dir}")
        return pd.DataFrame()

    # ---- Excel (ancien format)
    excel_data = _load_excel_facturation(year, factu_dir)

    # ---- PDF (nouveau format)
    pdf_data = pd.DataFrame()
    if PDF_AVAILABLE:
        try:
            pdf_data = load_pdf_facturation_data(factu_dir, year)
            if not pdf_data.empty:
                # déduplication forte sur (InvoiceKey, Date, Libellé/Quantité/Prix/Montant) si utils renvoie du détail
                # sinon on déduplique sur (InvoiceKey, Date) si présent
                pdf_data = _dedupe_pdf_rows(pdf_data)

                # mapping par facture si possible, sinon global
                pdf_data = _apply_pdf_category_mapping(pdf_data)
                # normalisation des totaux
                pdf_data = _ensure_totals_columns(pdf_data)
        except Exception as e:
            st.warning(f"Erreur lors du chargement des PDFs: {e}")

    # ---- Fusion propre (priorité PDF sur Excel mois chevauchants)
    if excel_data.empty and pdf_data.empty:
        return pd.DataFrame()

    if not excel_data.empty:
        excel_data['Date'] = pd.to_datetime(excel_data['Date'], errors='coerce')
    if not pdf_data.empty:
        pdf_data['Date'] = pd.to_datetime(pdf_data['Date'], errors='coerce')

    if excel_data.empty:
        return pdf_data
    if pdf_data.empty:
        return excel_data

    excel_months = set(excel_data['Date'].dropna().dt.to_period('M'))
    pdf_months = set(pdf_data['Date'].dropna().dt.to_period('M'))
    common_months = excel_months & pdf_months

    if common_months:
        st.warning(
            f"⚠️ Données trouvées à la fois en Excel et PDF pour {len(common_months)} mois. "
            f"Les données PDF (plus récentes) sont privilégiées."
        )
        excel_data = excel_data[~excel_data['Date'].dt.to_period('M').isin(pdf_months)].copy()

    result = pd.concat([excel_data, pdf_data], ignore_index=True)
    result = result.dropna(subset=['Date']).sort_values('Date').reset_index(drop=True)

    # sécuriser les colonnes numériques
    for c in result.columns:
        if c.startswith('Heures_') or c.startswith('Coût_') or c in ('Heures_Total', 'Cout_Total'):
            result[c] = pd.to_numeric(result[c], errors='coerce').fillna(0.0)

    return result


def _load_excel_facturation(year: int, factu_dir: Path) -> pd.DataFrame:
    """
    Charge les fichiers Excel historiques 'Facturation Lot A MM.YYYY.xlsx' pour l'année donnée,
    et renvoie un DF normalisé sur Date, Heures_Total (+ décomposition si dispo).
    """
    pattern = re.compile(r'Facturation Lot A (\d{2})\.(\d{4})\.xlsx')
    all_data = []

    for file_path in factu_dir.glob(FACTU_AT_GLOB):
        m = pattern.match(file_path.name)
        if not m:
            continue
        month_str, year_str = m.groups()
        if int(year_str) != year:
            continue

        try:
            df_raw = pd.read_excel(file_path, header=None)
            header_row = None
            for idx, row in df_raw.iterrows():
                if any("Date ouvrable" in str(v) for v in row.values):
                    header_row = idx
                    break
            if header_row is None:
                st.warning(f"Structure non reconnue dans {file_path.name}")
                continue

            df = pd.read_excel(file_path, header=header_row)
            if 'Date ouvrable' not in df.columns or 'Heures' not in df.columns:
                st.warning(f"Colonnes manquantes dans {file_path.name}")
                continue

            # On garde la ligne 'Total dd.mm.yyyy'
            df = df[df['Date ouvrable'].astype(str).str.contains('Total', na=False)].copy()
            df['Date_str'] = df['Date ouvrable'].astype(str).str.extract(r'(\d{2}\.\d{2}\.\d{4})')
            df['Date'] = pd.to_datetime(df['Date_str'], format='%d.%m.%Y', errors='coerce')

            df = df.dropna(subset=['Date'])
            df['Heures'] = pd.to_numeric(df['Heures'], errors='coerce').fillna(0.0)

            # Coordinateurs éventuel
            if 'Coordinateurs' in df.columns:
                df['Heures_Coordinateurs'] = pd.to_numeric(df['Coordinateurs'], errors='coerce').fillna(0.0)
            else:
                df['Heures_Coordinateurs'] = 0.0

            df['Heures_Total'] = df['Heures'] + df['Heures_Coordinateurs']

            keep = df[['Date', 'Heures', 'Heures_Coordinateurs', 'Heures_Total']].copy()
            # Harmonisation pour la suite (équivalent PDF)
            keep.rename(columns={'Heures': 'Heures_AT'}, inplace=True)
            all_data.append(keep)

        except Exception as e:
            st.warning(f"Erreur lors du chargement de {file_path.name}: {e}")
            continue

    if not all_data:
        return pd.DataFrame()

    out = pd.concat(all_data, ignore_index=True).sort_values('Date').reset_index(drop=True)
    # sécuriser num
    for c in out.columns:
        if c.startswith('Heures_') or c in ('Heures_Total',):
            out[c] = pd.to_numeric(out[c], errors='coerce').fillna(0.0)
    return out


def _dedupe_pdf_rows(pdf_df: pd.DataFrame) -> pd.DataFrame:
    """
    Déduplication côté PDF pour éviter la double addition (table détail + récap imprimé, etc.)
    - Si colonnes de détail (Libellé/Quantité/Prix/Montant) existent: drop_duplicates dessus + Date/InvoiceKey
    - Sinon: drop_duplicates sur (InvoiceKey, Date)
    """
    df = pdf_df.copy()
    key_cols = []
    if 'InvoiceKey' in df.columns:
        key_cols.append('InvoiceKey')
    elif 'InvoiceFile' in df.columns:
        key_cols.append('InvoiceFile')
    if 'Date' in df.columns:
        key_cols.append('Date')

    if all(c in df.columns for c in ('Libellé', 'Quantité', 'Prix', 'Montant')):
        dedupe_cols = key_cols + ['Libellé', 'Quantité', 'Prix', 'Montant']
        df = df.drop_duplicates(subset=dedupe_cols)
    elif key_cols:
        df = df.drop_duplicates(subset=key_cols)
    else:
        df = df.drop_duplicates()

    return df


def _ensure_totals_columns(df: pd.DataFrame) -> pd.DataFrame:
    """Garantit la présence de Heures_Total / Cout_Total (sommes lignes par date)."""
    out = df.copy()

    # Si déjà présents, rien à faire
    if 'Heures_Total' not in out.columns:
        heure_cols = [c for c in out.columns if c.startswith('Heures_') and c != 'Heures_Total']
        if heure_cols:
            out['Heures_Total'] = out[heure_cols].sum(axis=1, numeric_only=True)
        elif 'Quantité' in out.columns:
            out['Heures_Total'] = pd.to_numeric(out['Quantité'], errors='coerce').fillna(0.0)
        else:
            out['Heures_Total'] = 0.0

    if 'Cout_Total' not in out.columns:
        cout_cols = [c for c in out.columns if c.lower().startswith('coût_') or c.lower().startswith('cout_')]
        if cout_cols:
            out['Cout_Total'] = out[cout_cols].sum(axis=1, numeric_only=True)
        elif {'Quantité', 'Prix'}.issubset(out.columns):
            qty = pd.to_numeric(out['Quantité'], errors='coerce').fillna(0.0)
            pu = pd.to_numeric(out['Prix'], errors='coerce').fillna(0.0)
            out['Cout_Total'] = (qty * pu).round(2)
        else:
            out['Cout_Total'] = 0.0

    out['Heures_Total'] = pd.to_numeric(out['Heures_Total'], errors='coerce').fillna(0.0)
    out['Cout_Total'] = pd.to_numeric(out['Cout_Total'], errors='coerce').fillna(0.0)
    return out


def _apply_pdf_category_mapping(pdf_df: pd.DataFrame) -> pd.DataFrame:
    """
    Mapping PDF -> catégories de l'app. Supporte le mapping par facture si `InvoiceKey`/`InvoiceFile` est fourni.
    Fallback: mapping global (comme avant).
    """
    df = pdf_df.copy()

    # liste catégories PDF présentes (ex: 'AT', 'CSC', 'ATF', 'Gestion d\'accès', etc.)
    pdf_categories = []
    for col in df.columns:
        if col.startswith('Heures_') and col != 'Heures_Total':
            pdf_categories.append(col.replace('Heures_', ''))

    if not pdf_categories:
        return _ensure_totals_columns(df)

    # catégories de l'app = types de personnel
    app_categories = []
    if 'personnel' in st.session_state and not st.session_state.personnel.empty:
        app_categories = st.session_state.personnel['Type'].dropna().unique().tolist()

    # Dictionnaires de mapping dans session_state
    # - global : st.session_state.pdf_category_mapping  -> { 'Visitor Center': 'AT', ... }
    # - par facture : st.session_state.pdf_mapping_by_invoice[InvoiceKey] -> dict(...)
    mapping_global = st.session_state.get('pdf_category_mapping', {})
    mapping_by_invoice = st.session_state.get('pdf_mapping_by_invoice', {})

    # auto-proposition si manquant
    auto_global = get_category_mapping_for_pdf(pdf_categories, app_categories)

    def _resolve_mapping_for(invoice_key: str | None) -> dict:
        """Fusionne: manuel par facture > global manuel > auto."""
        base = {}
        if auto_global:
            base.update(auto_global)
        if mapping_global:
            base.update({k: v for k, v in mapping_global.items() if v})
        if invoice_key and invoice_key in mapping_by_invoice:
            base.update({k: v for k, v in mapping_by_invoice[invoice_key].items() if v})
        # restes à None si non mappés
        for cat in pdf_categories:
            base.setdefault(cat, None)
        return base

    # applique par bloc de facture si possible
    if 'InvoiceKey' in df.columns or 'InvoiceFile' in df.columns:
        key = 'InvoiceKey' if 'InvoiceKey' in df.columns else 'InvoiceFile'
        blocks = []
        for inv, part in df.groupby(key):
            mapping = _resolve_mapping_for(str(inv))
            blocks.append(apply_category_mapping(part.copy(), mapping))
        out = pd.concat(blocks, ignore_index=True)
    else:
        # fallback global
        mapping = _resolve_mapping_for(None)
        out = apply_category_mapping(df, mapping)

    # info catégories non mappées
    unresolved = []
    for col in out.columns:
        if col.startswith('Heures_') and col != 'Heures_Total':
            cat = col.replace('Heures_', '')
            # si une catégorie est restée orpheline car non dans app -> on considère ok (comptera en heures mais pas en coût si pas de tarif)
            # on peut prévenir:
            if 'personnel' in st.session_state and not (st.session_state.personnel['Type'] == cat).any():
                unresolved.append(cat)
    if unresolved:
        st.info(
            "Certaines catégories issues des factures ne correspondent pas à un type de personnel existant: "
            + ", ".join(sorted(set(unresolved)))
            + ". Configure le mapping par facture dans Configuration si nécessaire."
        )

    return _ensure_totals_columns(out)


# ========================== LOGIQUE BUDGET MODIFIÉ ==========================

def calculate_budget_modifie(year: int):
    """
    Calcule le budget modifié (intègre ajustements "Besoin Jour").
    Renvoie: {'heures_total','cout_total','calendar_df'}
    """
    bs = st.session_state.get('budget_state', {})
    if not bs or bs.get('year') != year or 'calendar_df' not in bs:
        return None

    try:
        calendar_dyn = bs['calendar_df'].copy()

        # Tarif AT
        tarif_at = 0.0
        personnel_type_at = st.session_state.get('cost_mapping', {}).get("AT")
        if personnel_type_at:
            personnel_df = st.session_state.get('personnel', pd.DataFrame())
            if not personnel_df.empty:
                row_tarif = personnel_df[personnel_df['Type'] == personnel_type_at]
                if not row_tarif.empty:
                    tarif_at = float(row_tarif['Coût Horaire'].iloc[0])

        perimetres_AT = st.session_state.perimetres.get("AT", [])
        time_slots_default = TIME_SLOTS
        planning_dict_at = st.session_state.planning_data.get("AT", {})

        heures_vals_at_recalc, costs_vals_at_recalc = [], []

        for _, r in calendar_dyn.iterrows():
            jour, saison, date_ = r['Jour'], r['Saison'], r['Date'].date()
            jtg = r['Jour_Type_Global']

            _, base_df_at = _ensure_grid(planning_dict_at, jtg, perimetres_AT, time_slots_default)
            eff_df_at = _apply_ops_to_grid(base_df_at, date_, jour, saison, category="AT")

            day_hours = eff_df_at.values.sum() * 0.5
            heures_vals_at_recalc.append(day_hours)
            costs_vals_at_recalc.append(day_hours * tarif_at)

        calendar_dyn["Heures_AT"] = heures_vals_at_recalc
        calendar_dyn["Coût_AT"] = costs_vals_at_recalc

        heure_cols = [c for c in calendar_dyn.columns if c.startswith('Heures_') and c != 'Heures_Total_Jour']
        cout_cols  = [c for c in calendar_dyn.columns if c.startswith('Coût_') and c != 'Coût_Total_Jour']

        calendar_dyn['Heures_Total_Jour'] = calendar_dyn[heure_cols].sum(axis=1) if heure_cols else 0.0
        calendar_dyn['Coût_Total_Jour']   = calendar_dyn[cout_cols].sum(axis=1) if cout_cols else 0.0

        return {
            'heures_total': float(calendar_dyn['Heures_Total_Jour'].sum()),
            'cout_total': float(calendar_dyn['Coût_Total_Jour'].sum()),
            'calendar_df': calendar_dyn
        }

    except Exception as e:
        st.error(f"Erreur lors du calcul du budget modifié: {e}")
        import traceback
        st.error(traceback.format_exc())
        return None


# ========================== PAGE RENDER ==========================

def render_analyse_budgetaire_page():
    st.title("Analyse Budgétaire")
    st.markdown(
        "Comparaison entre le **Budget Annuel** (prévision), "
        "le **Budget Modifié** (après ajustements) et le **Réalisé** (facturation)."
    )

    bs = st.session_state.get('budget_state', {})
    default_year = bs.get('year', dt.date.today().year)

    year = st.number_input(
        "Année d'analyse :",
        value=default_year, min_value=2023, max_value=2050, key="analyse_budget_year"
    )

    if not bs or bs.get('year') != year:
        st.warning(f"⚠️ Aucun budget annuel généré pour {year}. Génère d’abord le budget dans **Budget Annuel**.")
        st.stop()

    # --- Chargements
    with st.spinner("Chargement des données de facturation..."):
        df_factu = load_facturation_data_for_year(year)

    with st.spinner("Calcul du budget modifié avec ajustements..."):
        budget_modifie = calculate_budget_modifie(year)
    if budget_modifie is None:
        st.error("Impossible de calculer le budget modifié.")
        st.stop()

    # --- Budget Annuel (prévision initiale)
    calendar_df_annuel = bs.get('calendar_df', pd.DataFrame())
    totals_annuel = bs.get('totals', {})
    heures_annuel = float(totals_annuel.get('heures_annuel', 0.0))
    cout_annuel   = float(totals_annuel.get('cout_annuel', 0.0))

    # --- Budget Modifié
    heures_modifie = float(budget_modifie.get('heures_total', 0.0))
    cout_modifie   = float(budget_modifie.get('cout_total', 0.0))

    # --- Réalisé (depuis factures PDF/Excel)
    heures_realise = 0.0
    cout_realise   = 0.0
    if not df_factu.empty:
        heures_realise = float(pd.to_numeric(df_factu['Heures_Total'], errors='coerce').fillna(0.0).sum())
        if 'Cout_Total' in df_factu.columns:
            cout_realise = float(pd.to_numeric(df_factu['Cout_Total'], errors='coerce').fillna(0.0).sum())
        else:
            # Fallback (ancien comportement si Excel sans prix unitaire)
            tarif_at = 0.0
            personnel_type_at = st.session_state.get('cost_mapping', {}).get("AT")
            if personnel_type_at:
                personnel_df = st.session_state.get('personnel', pd.DataFrame())
                if not personnel_df.empty:
                    row_tarif = personnel_df[personnel_df['Type'] == personnel_type_at]
                    if not row_tarif.empty:
                        tarif_at = float(row_tarif['Coût Horaire'].iloc[0])
            cout_realise = heures_realise * tarif_at

    # --- Écarts
    ecart_heures_mod_ann      = heures_modifie - heures_annuel
    ecart_heures_mod_ann_pct  = (ecart_heures_mod_ann / heures_annuel * 100) if heures_annuel else 0.0
    ecart_cout_mod_ann        = cout_modifie - cout_annuel
    ecart_cout_mod_ann_pct    = (ecart_cout_mod_ann / cout_annuel * 100) if cout_annuel else 0.0

    ecart_heures_real_mod     = heures_realise - heures_modifie
    ecart_heures_real_mod_pct = (ecart_heures_real_mod / heures_modifie * 100) if heures_modifie else 0.0
    ecart_cout_real_mod       = cout_realise - cout_modifie
    ecart_cout_real_mod_pct   = (ecart_cout_real_mod / cout_modifie * 100) if cout_modifie else 0.0

    # =================== KPI Coûts ===================
    st.markdown("---")
    st.subheader(f"💰 Synthèse {year} - Coûts (CHF)")
    c1, c2, c3 = st.columns(3)

    with c1:
        st.markdown(
            f"""<div class="kpi-card kpi-blue">
                <div class="label">Budget Annuel</div>
                <div class="value">{cout_annuel:,.0f} CHF</div>
                <div class="delta">Prévision initiale</div>
            </div>""",
            unsafe_allow_html=True,
        )

    with c2:
        color = "kpi-green" if ecart_cout_mod_ann <= 0 else "kpi-amber"
        sym   = "▼" if ecart_cout_mod_ann < 0 else "▲"
        st.markdown(
            f"""<div class="kpi-card {color}">
                <div class="label">Budget Modifié</div>
                <div class="value">{cout_modifie:,.0f} CHF</div>
                <div class="delta">{sym} {abs(ecart_cout_mod_ann):,.0f} CHF ({ecart_cout_mod_ann_pct:+.1f}%)</div>
            </div>""",
            unsafe_allow_html=True,
        )

    with c3:
        if df_factu.empty:
            st.markdown(
                """<div class="kpi-card kpi-amber">
                    <div class="label">Réalisé</div>
                    <div class="value">— CHF</div>
                    <div class="delta">Aucune donnée de facturation</div>
                </div>""",
                unsafe_allow_html=True,
            )
        else:
            color = "kpi-green" if ecart_cout_real_mod <= 0 else "kpi-red"
            sym   = "▼" if ecart_cout_real_mod < 0 else "▲"
            st.markdown(
                f"""<div class="kpi-card {color}">
                    <div class="label">Réalisé</div>
                    <div class="value">{cout_realise:,.0f} CHF</div>
                    <div class="delta">{sym} {abs(ecart_cout_real_mod):,.0f} CHF ({ecart_cout_real_mod_pct:+.1f}%)</div>
                </div>""",
                unsafe_allow_html=True,
            )

    # =================== KPI Heures ===================
    st.markdown("---")
    st.subheader(f"⏱️ Synthèse {year} - Heures")
    h1, h2, h3 = st.columns(3)

    with h1:
        st.markdown(
            f"""<div class="kpi-card kpi-blue">
                <div class="label">Budget Annuel</div>
                <div class="value">{heures_annuel:,.0f} h</div>
                <div class="delta">Prévision initiale</div>
            </div>""",
            unsafe_allow_html=True,
        )

    with h2:
        color = "kpi-green" if ecart_heures_mod_ann <= 0 else "kpi-amber"
        sym   = "▼" if ecart_heures_mod_ann < 0 else "▲"
        st.markdown(
            f"""<div class="kpi-card {color}">
                <div class="label">Budget Modifié</div>
                <div class="value">{heures_modifie:,.0f} h</div>
                <div class="delta">{sym} {abs(ecart_heures_mod_ann):,.0f} h ({ecart_heures_mod_ann_pct:+.1f}%)</div>
            </div>""",
            unsafe_allow_html=True,
        )

    with h3:
        if df_factu.empty:
            st.markdown(
                """<div class="kpi-card kpi-amber">
                    <div class="label">Réalisé</div>
                    <div class="value">— h</div>
                    <div class="delta">Aucune donnée de facturation</div>
                </div>""",
                unsafe_allow_html=True,
            )
        else:
            color = "kpi-green" if ecart_heures_real_mod <= 0 else "kpi-red"
            sym   = "▼" if ecart_heures_real_mod < 0 else "▲"
            st.markdown(
                f"""<div class="kpi-card {color}">
                    <div class="label">Réalisé</div>
                    <div class="value">{heures_realise:,.0f} h</div>
                    <div class="delta">{sym} {abs(ecart_heures_real_mod):,.0f} h ({ecart_heures_real_mod_pct:+.1f}%)</div>
                </div>""",
                unsafe_allow_html=True,
            )

    # =================== Évolutions cumulées ===================
    st.markdown("---")
    st.subheader(f"📈 Évolution Cumulée {year}")

    calendar_with_modif = budget_modifie.get('calendar_df', pd.DataFrame())
    if not calendar_with_modif.empty:
        try:
            # Annuel
            calA = calendar_df_annuel.copy()
            calA['Date'] = pd.to_datetime(calA['Date'])
            calA['Mois'] = calA['Date'].dt.to_period('M')
            monA = calA.groupby('Mois', as_index=False)[['Heures_Total_Jour','Coût_Total_Jour']].sum()
            monA.rename(columns={'Heures_Total_Jour':'Heures_Annuel','Coût_Total_Jour':'Cout_Annuel'}, inplace=True)

            # Modifié
            calM = calendar_with_modif.copy()
            calM['Date'] = pd.to_datetime(calM['Date'])
            calM['Mois'] = calM['Date'].dt.to_period('M')
            monM = calM.groupby('Mois', as_index=False)[['Heures_Total_Jour','Coût_Total_Jour']].sum()
            monM.rename(columns={'Heures_Total_Jour':'Heures_Modifie','Coût_Total_Jour':'Cout_Modifie'}, inplace=True)

            monthly_budget = monA.merge(monM, on='Mois', how='outer').sort_values('Mois')
            monthly_budget['Mois_str'] = monthly_budget['Mois'].astype(str)
            monthly_budget['Mois_dt']  = monthly_budget['Mois'].apply(lambda x: x.to_timestamp())

            # cumul
            for c in ['Heures_Annuel','Cout_Annuel','Heures_Modifie','Cout_Modifie']:
                monthly_budget[c] = pd.to_numeric(monthly_budget[c], errors='coerce').fillna(0.0)
            monthly_budget['Heures_Annuel_Cumul'] = monthly_budget['Heures_Annuel'].cumsum()
            monthly_budget['Cout_Annuel_Cumul']   = monthly_budget['Cout_Annuel'].cumsum()
            monthly_budget['Heures_Modifie_Cumul'] = monthly_budget['Heures_Modifie'].cumsum()
            monthly_budget['Cout_Modifie_Cumul']   = monthly_budget['Cout_Modifie'].cumsum()

            # Réalisé depuis factures
            if not df_factu.empty:
                df_factu2 = df_factu.copy()
                df_factu2['Date'] = pd.to_datetime(df_factu2['Date'])
                df_factu2['Mois'] = df_factu2['Date'].dt.to_period('M')
                monR = df_factu2.groupby('Mois', as_index=False)[['Heures_Total','Cout_Total']].sum()
                monR['Mois_str'] = monR['Mois'].astype(str)
                monR['Mois_dt']  = monR['Mois'].apply(lambda x: x.to_timestamp())
                monR['Heures_Realise_Cumul'] = monR['Heures_Total'].cumsum()
                monR['Cout_Realise_Cumul']   = monR['Cout_Total'].cumsum()

                monthly_combined = monthly_budget.merge(
                    monR[['Mois_str','Heures_Realise_Cumul','Cout_Realise_Cumul']],
                    on='Mois_str', how='left'
                )
            else:
                monthly_combined = monthly_budget.copy()
                monthly_combined['Heures_Realise_Cumul'] = pd.NA
                monthly_combined['Cout_Realise_Cumul']   = pd.NA

            # data long pour charts
            # Heures
            df_heures_plot = pd.DataFrame({
                'Mois': monthly_combined['Mois_dt'].tolist()*3,
                'Type': (['Budget Annuel']*len(monthly_combined)
                         + ['Budget Modifié']*len(monthly_combined)
                         + ['Réalisé']*len(monthly_combined)),
                'Heures_Cumul': (monthly_combined['Heures_Annuel_Cumul'].tolist()
                                 + monthly_combined['Heures_Modifie_Cumul'].tolist()
                                 + monthly_combined['Heures_Realise_Cumul'].tolist())
            }).dropna(subset=['Heures_Cumul'])

            # Coûts
            df_cout_plot = pd.DataFrame({
                'Mois': monthly_combined['Mois_dt'].tolist()*3,
                'Type': (['Budget Annuel']*len(monthly_combined)
                         + ['Budget Modifié']*len(monthly_combined)
                         + ['Réalisé']*len(monthly_combined)),
                'Cout_Cumul': (monthly_combined['Cout_Annuel_Cumul'].tolist()
                               + monthly_combined['Cout_Modifie_Cumul'].tolist()
                               + monthly_combined['Cout_Realise_Cumul'].tolist())
            }).dropna(subset=['Cout_Cumul'])

            tab_cout, tab_heures = st.tabs(["💶 Coûts Cumulés (CHF)", "⏱️ Heures Cumulées"])

            with tab_cout:
                if not df_cout_plot.empty:
                    chart = alt.Chart(df_cout_plot).mark_line(point=True, strokeWidth=3).encode(
                        x=alt.X('Mois:T', title='Mois', axis=alt.Axis(format='%b %Y')),
                        y=alt.Y('Cout_Cumul:Q', title='Coût Cumulé (CHF)'),
                        color=alt.Color('Type:N',
                            scale=alt.Scale(
                                domain=['Budget Annuel','Budget Modifié','Réalisé'],
                                range=['#0076aa','#ffa500','#dc143c']),
                            legend=alt.Legend(title='Type')
                        ),
                        tooltip=[
                            alt.Tooltip('Mois:T', title='Mois', format='%B %Y'),
                            alt.Tooltip('Type:N', title='Série'),
                            alt.Tooltip('Cout_Cumul:Q', title='Coût Cumulé', format=',.0f')
                        ]
                    ).properties(height=400).interactive()
                    st.altair_chart(chart, use_container_width=True)
                else:
                    st.info("Pas de données suffisantes pour tracer la courbe des coûts.")

            with tab_heures:
                if not df_heures_plot.empty:
                    chart = alt.Chart(df_heures_plot).mark_line(point=True, strokeWidth=3).encode(
                        x=alt.X('Mois:T', title='Mois', axis=alt.Axis(format='%b %Y')),
                        y=alt.Y('Heures_Cumul:Q', title='Heures Cumulées'),
                        color=alt.Color('Type:N',
                            scale=alt.Scale(
                                domain=['Budget Annuel','Budget Modifié','Réalisé'],
                                range=['#0076aa','#ffa500','#dc143c']),
                            legend=alt.Legend(title='Type')
                        ),
                        tooltip=[
                            alt.Tooltip('Mois:T', title='Mois', format='%B %Y'),
                            alt.Tooltip('Type:N', title='Série'),
                            alt.Tooltip('Heures_Cumul:Q', title='Heures Cumulées', format=',.0f')
                        ]
                    ).properties(height=400).interactive()
                    st.altair_chart(chart, use_container_width=True)
                else:
                    st.info("Pas de données suffisantes pour tracer la courbe des heures.")
        except Exception as e:
            st.error(f"Erreur lors de la création des graphiques cumulés: {e}")
            import traceback
            st.error(traceback.format_exc())

    # =================== Tableau mensuel ===================
    st.markdown("---")
    st.subheader("📋 Détail Mensuel")

    if not calendar_with_modif.empty:
        try:
            # Base mensuelle Annuel/Modifié
            calA = calendar_df_annuel.copy()
            calA['Date'] = pd.to_datetime(calA['Date'])
            calA['Mois'] = calA['Date'].dt.to_period('M')
            monA = calA.groupby('Mois', as_index=False)[['Heures_Total_Jour','Coût_Total_Jour']].sum()
            monA.rename(columns={'Heures_Total_Jour':'Heures Annuel','Coût_Total_Jour':'Coût Annuel (CHF)'}, inplace=True)

            calM = calendar_with_modif.copy()
            calM['Date'] = pd.to_datetime(calM['Date'])
            calM['Mois'] = calM['Date'].dt.to_period('M')
            monM = calM.groupby('Mois', as_index=False)[['Heures_Total_Jour','Coût_Total_Jour']].sum()
            monM.rename(columns={'Heures_Total_Jour':'Heures Modifié','Coût_Total_Jour':'Coût Modifié (CHF)'}, inplace=True)

            monthly_table = monA.merge(monM, on='Mois', how='outer').sort_values('Mois')
            monthly_table['Mois_str'] = monthly_table['Mois'].astype(str)

            # Réalisé mensuel (heures + coût) depuis factures
            if not df_factu.empty:
                df_factu2 = df_factu.copy()
                df_factu2['Date'] = pd.to_datetime(df_factu2['Date'])
                df_factu2['Mois'] = df_factu2['Date'].dt.to_period('M')
                monR = df_factu2.groupby('Mois', as_index=False)[['Heures_Total','Cout_Total']].sum()
                monR['Mois_str'] = monR['Mois'].astype(str)

                monthly_table = monthly_table.merge(
                    monR[['Mois_str','Heures_Total','Cout_Total']],
                    on='Mois_str', how='left'
                )
                monthly_table.rename(columns={'Heures_Total':'Heures Réalisé', 'Cout_Total':'Coût Réalisé (CHF)'}, inplace=True)

            # Affichage
            show_cols = ['Mois_str','Heures Annuel','Heures Modifié','Heures Réalisé',
                         'Coût Annuel (CHF)','Coût Modifié (CHF)','Coût Réalisé (CHF)']
            show_cols = [c for c in show_cols if c in monthly_table.columns]

            df_display = monthly_table[show_cols].copy()
            df_display.rename(columns={'Mois_str':'Mois'}, inplace=True)

            col_config = {
                'Mois': st.column_config.TextColumn('Mois')
            }
            if 'Heures Annuel' in df_display.columns:
                col_config['Heures Annuel'] = st.column_config.NumberColumn('Heures Annuel', format='%.0f h')
            if 'Heures Modifié' in df_display.columns:
                col_config['Heures Modifié'] = st.column_config.NumberColumn('Heures Modifié', format='%.0f h')
            if 'Heures Réalisé' in df_display.columns:
                col_config['Heures Réalisé'] = st.column_config.NumberColumn('Heures Réalisé', format='%.0f h')
            if 'Coût Annuel (CHF)' in df_display.columns:
                col_config['Coût Annuel (CHF)'] = st.column_config.NumberColumn('Coût Annuel', format='%.0f CHF')
            if 'Coût Modifié (CHF)' in df_display.columns:
                col_config['Coût Modifié (CHF)'] = st.column_config.NumberColumn('Coût Modifié', format='%.0f CHF')
            if 'Coût Réalisé (CHF)' in df_display.columns:
                col_config['Coût Réalisé (CHF)'] = st.column_config.NumberColumn('Coût Réalisé', format='%.0f CHF')

            st.dataframe(df_display, column_config=col_config, hide_index=True, use_container_width=True)

        except Exception as e:
            st.error(f"Erreur lors de la création du tableau mensuel: {e}")
            import traceback
            st.error(traceback.format_exc())

    # =================== Infos ===================
    with st.expander("ℹ️ Informations"):
        st.markdown("""
        - **Réalisé (CHF)** est désormais directement issu des montants PDF (`Cout_Total`),
          ce qui évite toute approximation par tarif horaire.
        - Les PDF sont **dédupliqués** pour éviter le double comptage (répétitions / tableaux récap).
        - Le **mapping par facture** est supporté si `load_pdf_facturation_data` fournit `InvoiceKey`/`InvoiceFile`.
          Sinon, le mapping **global** est utilisé.
        - En cas de chevauchement **Excel/PDF** sur un mois, le **PDF** est prioritaire.
        """)

# =============================================================================
# Fin du module
# =============================================================================
