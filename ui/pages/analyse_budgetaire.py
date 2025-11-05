# ui/pages/analyse_budgetaire.py
"""
Page Analyse Budgétaire - Comparaison Budget Annuel vs Modifié vs Réalisé
"""
from __future__ import annotations

import datetime as dt
import calendar
from pathlib import Path
import re
import pandas as pd
import streamlit as st
import altair as alt

from config.constants import FACTU_AT_DIR, FACTU_AT_GLOB, TIME_SLOTS
from core.planning import _ensure_grid, _apply_ops_to_grid


# ============================================================
# Chargement & Parsing Facturation (année complète)
# ============================================================

def load_facturation_data_for_year(year: int):
    """
    Charge et agrège tous les fichiers de facturation Excel pour une année donnée.
    Supporte 2 formats:
    - ANCIEN (avant sept 2025): Date ouvrable, Heures, Coordinateurs
    - NOUVEAU (depuis sept 2025): Libellé, Quantité, Prix, Montant

    Returns:
        DataFrame avec colonnes: Date, Heures_[CATEGORY], Cout_[CATEGORY], Heures_Total, Cout_Total
    """
    factu_dir = Path(FACTU_AT_DIR)
    if not factu_dir.exists():
        st.error(f"Le répertoire de facturation n'existe pas: {factu_dir}")
        return pd.DataFrame()

    excel_data = _load_excel_facturation(year, factu_dir)
    if excel_data.empty:
        return pd.DataFrame()

    if 'Date' in excel_data.columns:
        excel_data['Date'] = pd.to_datetime(excel_data['Date'], errors='coerce')
        excel_data = excel_data.dropna(subset=['Date'])
        excel_data = excel_data.sort_values('Date', na_position='last').reset_index(drop=True)
        excel_data = excel_data.fillna(0)

    return excel_data


def _load_excel_facturation(year: int, factu_dir: Path) -> pd.DataFrame:
    """
    Charge les fichiers Excel de facturation pour une année donnée.
    (AUCUNE sortie visuelle ici.)
    """
    pattern = re.compile(r'Facturation Lot A (\d{2})\.(\d{4})\.xlsx')
    all_data = []

    for file_path in factu_dir.glob(FACTU_AT_GLOB):
        m = pattern.match(file_path.name)
        if not m:
            continue
        file_month = int(m.group(1))
        file_year = int(m.group(2))
        if file_year != year:
            continue

        try:
            df_raw = pd.read_excel(file_path, header=None)
            has_libelle_col = False
            has_date_ouvrable = False
            for _, row in df_raw.iterrows():
                row_str = ' '.join([str(x) for x in row.values if pd.notna(x)]).lower()
                if 'libellé' in row_str and 'quantité' in row_str and 'prix' in row_str:
                    has_libelle_col = True
                    break
                if 'date ouvrable' in row_str:
                    has_date_ouvrable = True
                    break

            # Seuil historique
            is_new_format = (file_year > 2025) or (file_year == 2025 and file_month >= 9)
            if has_libelle_col:
                is_new_format = True
            elif has_date_ouvrable:
                is_new_format = False

            if is_new_format:
                df_result = _parse_new_excel_format(file_path, file_year, file_month, show_details=False)
            else:
                df_result = _parse_old_excel_format(file_path, file_year, file_month, show_details=False)

            if not df_result.empty:
                all_data.append(df_result)

        except Exception as e:
            st.warning(f"⚠️ Erreur lors du chargement de {file_path.name}: {e}")
            import traceback
            st.error(traceback.format_exc())
            continue

    if not all_data:
        return pd.DataFrame()

    result = pd.concat(all_data, ignore_index=True)
    if 'Date' in result.columns:
        result['Date'] = pd.to_datetime(result['Date'], errors='coerce')
        result = result.dropna(subset=['Date'])
    result = result.sort_values('Date', na_position='last').reset_index(drop=True)
    return result


# ============================================================
# Parseurs : Ancien & Nouveau formats
# ============================================================

def _parse_old_excel_format(file_path: Path, file_year: int, file_month: int, *, show_details: bool) -> pd.DataFrame:
    """Ancien format (Date ouvrable / Heures / Coordinateurs)."""
    df_raw = pd.read_excel(file_path, header=None)

    header_row = None
    for idx, row in df_raw.iterrows():
        if 'Date ouvrable' in str(row.values):
            header_row = idx
            break
    if header_row is None:
        st.warning(f"⚠️ Structure ancien format non reconnue dans {file_path.name}")
        return pd.DataFrame()

    df = pd.read_excel(file_path, header=header_row)
    if 'Date ouvrable' not in df.columns or 'Heures' not in df.columns:
        st.warning(f"⚠️ Colonnes manquantes dans {file_path.name}")
        return pd.DataFrame()

    df = df[df['Date ouvrable'].astype(str).str.contains('Total', na=False)].copy()
    df['Date_str'] = df['Date ouvrable'].astype(str).str.extract(r'(\d{2}\.\d{2}\.\d{4})')
    df['Date'] = pd.to_datetime(df['Date_str'], format='%d.%m.%Y', errors='coerce')
    df = df.dropna(subset=['Date'])
    df['Heures'] = pd.to_numeric(df['Heures'], errors='coerce').fillna(0)

    if 'Coordinateurs' in df.columns:
        df['Heures_Coordinateurs'] = pd.to_numeric(df['Coordinateurs'], errors='coerce').fillna(0)
    else:
        df['Heures_Coordinateurs'] = 0

    df['Heures_Total'] = df['Heures'] + df['Heures_Coordinateurs']
    df_clean = df[['Date', 'Heures', 'Heures_Coordinateurs', 'Heures_Total']].copy()

    # Affichage détaillé UNIQUEMENT quand demandé
    if show_details:
        total_heures_at = df_clean['Heures'].sum()
        total_heures_coord = df_clean['Heures_Coordinateurs'].sum()
        total_heures = df_clean['Heures_Total'].sum()

        with st.expander(f"✓ {file_path.name} (ancien format): {len(df_clean)} jours", expanded=False):
            st.caption(f"**Mois**: {file_month:02d}/{file_year}")
            st.caption(f"**Total**: {total_heures:,.0f} heures")
            rows = []
            if total_heures_at > 0:
                rows.append({'Type': 'AT', 'Heures': total_heures_at, 'Jours': len(df_clean[df_clean['Heures'] > 0])})
            if total_heures_coord > 0:
                rows.append({'Type': 'Coordinateurs', 'Heures': total_heures_coord, 'Jours': len(df_clean[df_clean['Heures_Coordinateurs'] > 0])})
            if rows:
                st.dataframe(pd.DataFrame(rows), hide_index=True, use_container_width=True)

    return df_clean


def _parse_new_excel_format(file_path: Path, file_year: int, file_month: int, *, show_details: bool) -> pd.DataFrame:
    """Nouveau format (Libellé / Quantité / Prix / Montant)."""
    df_raw = pd.read_excel(file_path, header=None)

    header_row = None
    for idx, row in df_raw.iterrows():
        row_str = ' '.join([str(x) for x in row.values if pd.notna(x)]).lower()
        if 'libellé' in row_str and 'quantité' in row_str:
            header_row = idx
            break
    if header_row is None:
        st.warning(f"⚠️ En-têtes nouveau format non trouvés dans {file_path.name}")
        return pd.DataFrame()

    df = pd.read_excel(file_path, header=header_row)
    df.columns = [str(col).strip() for col in df.columns]

    required = ['Libellé', 'Quantité', 'Prix', 'Montant']
    missing = [c for c in required if c not in df.columns]
    if missing:
        st.warning(f"⚠️ Colonnes manquantes dans {file_path.name}: {missing}")
        return pd.DataFrame()

    df = df[df['Libellé'].notna() & (df['Libellé'] != '')].copy()
    df['Quantité'] = pd.to_numeric(df['Quantité'], errors='coerce').fillna(0)
    df['Prix'] = pd.to_numeric(df['Prix'], errors='coerce').fillna(0)
    df['Montant'] = pd.to_numeric(df['Montant'], errors='coerce').fillna(0)
    df = df[df['Quantité'] > 0].copy()
    if df.empty:
        return pd.DataFrame()

    def extract_type_personnel(libelle: str) -> str:
        libelle = str(libelle).strip()
        m = re.search(r'(?:Heures?)\s+(.+)', libelle, re.IGNORECASE)
        type_str = m.group(1).strip() if m else libelle
        s = type_str.lower()
        if 'atf' in s or 'formateur' in s: return 'ATF'
        if 'atr' in s: return 'ATR'
        if 'coordinateur' in s: return 'Coordinateurs'
        if 'csc' in s: return 'CSC'
        if "gestion d'accès" in s or 'gestion acces' in s: return "Gestion d'accès"
        if 'visitor' in s: return 'Visitor Center'
        if re.search(r'\bat\b', s): return 'AT'
        return 'extra'

    df['Type'] = df['Libellé'].apply(extract_type_personnel)

    # Alerte de cohérence prix (si config perso)
    if 'personnel' in st.session_state and not st.session_state.personnel.empty:
        pers = st.session_state.personnel
        for _, r in df.iterrows():
            match = pers[pers['Type'] == r['Type']]
            if not match.empty:
                cfg = float(match['Coût Horaire'].iloc[0])
                if abs(r['Prix'] - cfg) > cfg * 0.01:
                    st.warning(f"⚠️ {file_path.name}: Prix {r['Type']} {r['Prix']:.2f} ≠ config {cfg:.2f} CHF/h")

    date = dt.date(file_year, file_month, 1)
    row = {'Date': date}
    th, tc = 0.0, 0.0
    for t, g in df.groupby('Type'):
        h = g['Quantité'].sum()
        c = g['Montant'].sum()
        row[f'Heures_{t}'] = h
        row[f'Cout_{t}'] = c
        th += h
        tc += c
    row['Heures_Total'] = th
    row['Cout_Total'] = tc
    result = pd.DataFrame([row])

    # Affichage détaillé UNIQUEMENT quand demandé
    if show_details:
        with st.expander(f"✓ {file_path.name} (nouveau format): {len(df)} lignes, {len(df['Type'].unique())} types", expanded=False):
            st.caption(f"**Mois**: {file_month:02d}/{file_year}")
            st.caption(f"**Total**: {th:,.0f} heures · {tc:,.2f} CHF")
            details = []
            for t, g in df.groupby('Type'):
                q = g['Quantité'].sum()
                mnt = g['Montant'].sum()
                details.append({
                    'Type': t,
                    'Heures': q,
                    'Coût Total (CHF)': mnt,
                    'Coût Horaire Moyen (CHF)': (mnt / q) if q > 0 else 0,
                    'Lignes': len(g)
                })
            st.dataframe(pd.DataFrame(details).sort_values('Heures', ascending=False),
                         hide_index=True, use_container_width=True)

    return result


# ============================================================
# Budget Modifié : recalcul identique à besoin_jour.py
# ============================================================

def calculate_budget_modifie(year: int):
    bs = st.session_state.get('budget_state', {})
    if not bs or bs.get('year') != year or 'calendar_df' not in bs:
        return None

    try:
        cal = bs['calendar_df'].copy()
        tarif_at = 0.0
        t_at = st.session_state.get('cost_mapping', {}).get("AT")
        if t_at:
            pers = st.session_state.get('personnel', pd.DataFrame())
            if not pers.empty:
                r = pers[pers['Type'] == t_at]
                if not r.empty:
                    tarif_at = float(r['Coût Horaire'].iloc[0])

        perims = st.session_state.perimetres.get("AT", [])
        slots = TIME_SLOTS
        plan_at = st.session_state.planning_data.get("AT", {})
        h_vals, c_vals = [], []

        for _, r in cal.iterrows():
            jour, saison, date_ = r['Jour'], r['Saison'], r['Date'].date()
            jtg = r['Jour_Type_Global']
            _, base_at = _ensure_grid(plan_at, jtg, perims, slots)
            eff_at = _apply_ops_to_grid(base_at, date_, jour, saison, category="AT")
            day_h = eff_at.values.sum() * 0.5
            h_vals.append(day_h)
            c_vals.append(day_h * tarif_at)

        cal["Heures_AT"] = h_vals
        cal["Coût_AT"] = c_vals

        h_cols = [c for c in cal.columns if c.startswith('Heures_') and c != 'Heures_Total_Jour']
        c_cols = [c for c in cal.columns if c.startswith('Coût_') and c != 'Coût_Total_Jour']
        cal['Heures_Total_Jour'] = cal[h_cols].sum(axis=1) if h_cols else 0.0
        cal['Coût_Total_Jour'] = cal[c_cols].sum(axis=1) if c_cols else 0.0

        return {
            'heures_total': cal['Heures_Total_Jour'].sum(),
            'cout_total': cal['Coût_Total_Jour'].sum(),
            'calendar_df': cal
        }
    except Exception as e:
        st.error(f"Erreur lors du calcul du budget modifié: {e}")
        import traceback
        st.error(traceback.format_exc())
        return None


# ============================================================
# Helpers
# ============================================================

def _scalar_from_df(df: pd.DataFrame, col: str, default: float = 0.0) -> float:
    if isinstance(df, pd.DataFrame) and col in df.columns and len(df) > 0:
        return float(pd.to_numeric(df[col], errors='coerce').fillna(0).iloc[0])
    return float(default)


def _detect_invoice_format(file_path: Path) -> str:
    if not file_path.exists():
        return "none"
    try:
        df_raw = pd.read_excel(file_path, header=None, nrows=20)
    except Exception:
        return "none"
    has_lib, has_date = False, False
    for _, row in df_raw.iterrows():
        s = ' '.join([str(x) for x in row.values if pd.notna(x)]).lower()
        if 'libellé' in s and 'quantité' in s and 'prix' in s:
            has_lib = True; break
        if 'date ouvrable' in s:
            has_date = True; break
    if has_lib: return "new"
    if has_date: return "old"
    return "none"


# ============================================================
# Viewer d'UNE facture mensuelle (UI seul endroit de visu)
# ============================================================

def _view_single_invoice(year: int, month: int, factu_dir: Path):
    """
    Visualise UNE facture mensuelle dans la zone dédiée.
    """
    file_path = factu_dir / f"Facturation Lot A {month:02d}.{year}.xlsx"
    if not file_path.exists():
        st.info(f"Aucune facture trouvée pour {month:02d}/{year} ({file_path.name}).")
        return

    fmt = _detect_invoice_format(file_path)
    if fmt == "none":
        st.warning(f"Format non reconnu pour {file_path.name}.")
        return

    # Résumé compact
    if fmt == "new":
        df_month = _parse_new_excel_format(file_path, year, month, show_details=False)
        st.caption("Format: **Nouveau** (Libellé / Quantité / Prix / Montant)")
        heures_total = _scalar_from_df(df_month, 'Heures_Total', 0.0)
        cout_total = _scalar_from_df(df_month, 'Cout_Total', 0.0)
    else:
        df_month = _parse_old_excel_format(file_path, year, month, show_details=False)
        st.caption("Format: **Ancien** (Date ouvrable / Heures)")
        heures_total = float(pd.to_numeric(
            df_month['Heures_Total'] if 'Heures_Total' in df_month.columns else df_month['Heures'],
            errors='coerce'
        ).fillna(0).sum())
        cout_total = None  # pas de montant dans l'ancien format

    # KPIs en 2 colonnes
    k1, k2 = st.columns(2)
    k1.metric("Heures (mois)", f"{heures_total:,.1f}".replace(",", " ") + " h")
    if cout_total is not None:
        k2.metric("Coût (mois)", f"{cout_total:,.2f}".replace(",", " ") + " CHF")

    # — Table détaillée PLEINE LARGEUR —
    # Pour le nouveau format, on réaffiche un détail par type (lisible)
    if fmt == "new":
        # Re-ouvre le fichier avec en-têtes pour la table lisible
        df_raw = pd.read_excel(file_path, header=None)
        header_row = None
        for idx, row in df_raw.iterrows():
            row_str = ' '.join([str(x) for x in row.values if pd.notna(x)]).lower()
            if 'libellé' in row_str and 'quantité' in row_str:
                header_row = idx
                break
        df = pd.read_excel(file_path, header=header_row)
        df.columns = [str(c).strip() for c in df.columns]
        df = df[df['Libellé'].notna() & (df['Libellé'] != '')].copy()
        df['Quantité'] = pd.to_numeric(df['Quantité'], errors='coerce').fillna(0)
        df['Prix'] = pd.to_numeric(df['Prix'], errors='coerce').fillna(0)
        df['Montant'] = pd.to_numeric(df['Montant'], errors='coerce').fillna(0)
        df = df[df['Quantité'] > 0].copy()

        # Détail par libellé pour la lisibilité
        df_display = df[['Libellé', 'Quantité', 'Prix', 'Montant']].copy()
        st.dataframe(
            df_display,
            hide_index=True,
            use_container_width=True,
            column_config={
                'Libellé': st.column_config.TextColumn('Libellé'),
                'Quantité': st.column_config.NumberColumn('Quantité', format='%.2f h'),
                'Prix': st.column_config.NumberColumn('Prix', format='%.2f CHF/h'),
                'Montant': st.column_config.NumberColumn('Montant', format='%.2f CHF'),
            }
        )
    else:
        # Ancien format : table des jours
        st.dataframe(
            df_month[['Date', 'Heures', 'Heures_Coordinateurs', 'Heures_Total']].copy(),
            hide_index=True,
            use_container_width=True,
            column_config={
                'Date': st.column_config.DatetimeColumn('Date', format='YYYY-MM-DD'),
                'Heures': st.column_config.NumberColumn('Heures AT', format='%.2f h'),
                'Heures_Coordinateurs': st.column_config.NumberColumn('Heures Coordinateurs', format='%.2f h'),
                'Heures_Total': st.column_config.NumberColumn('Total Heures', format='%.2f h'),
            }
        )


# ============================================================
# PAGE PRINCIPALE
# ============================================================

def render_analyse_budgetaire_page():
    st.title("Analyse Budgétaire")
    st.markdown(
        "Comparaison entre le **Budget Annuel** (prévision initiale), "
        "le **Budget Modifié** (après ajustements Besoin Jour) et "
        "le **Réalisé** (facturation effective)."
    )

    # Sélection de l'année
    bs = st.session_state.get('budget_state', {})
    default_year = bs.get('year', dt.date.today().year)
    year = st.number_input("Année d'analyse :", value=default_year, min_value=2023, max_value=2050, key="analyse_budget_year")

    # === Zone dédiée : Visualiser une facture mensuelle (n'affecte rien) ===
    with st.expander("🔎 Visualiser le détail d'une facture mensuelle", expanded=False):
        # Ligne de contrôle (mois + bouton)
        with st.form(key="invoice_viewer_form", clear_on_submit=False):
            c1, c2 = st.columns([3, 1])
            with c1:
                month_view = st.selectbox(
                    "Mois à afficher",
                    options=list(range(1, 13)),
                    format_func=lambda m: f"{m:02d} - {calendar.month_name[m]}",
                    key="ab_invoice_view_month",
                )
            with c2:
                submitted = st.form_submit_button("Afficher la facture")
        # Rendu plein écran sous la ligne de contrôle
        if submitted:
            _view_single_invoice(int(year), int(month_view), Path(FACTU_AT_DIR))

    # Vérification budget
    if not bs or bs.get('year') != year:
        st.warning(
            f"⚠️ Aucun budget annuel généré pour l'année {year}. "
            f"Veuillez d'abord générer le budget dans la page **Budget Annuel**."
        )
        st.stop()

    # =================== Chargement des données ===================
    with st.spinner("Chargement des données de facturation..."):
        df_factu = load_facturation_data_for_year(year)

    with st.spinner("Calcul du budget modifié avec ajustements..."):
        budget_modifie = calculate_budget_modifie(year)

    if budget_modifie is None:
        st.error("Impossible de calculer le budget modifié.")
        st.stop()

    # =================== Données Budget Annuel & Modifié ===================
    totals_annuel = bs.get('totals', {})
    heures_annuel_planif = totals_annuel.get('heures_annuel', 0.0)
    cout_annuel_planif = totals_annuel.get('cout_annuel', 0.0)
    heures_modifie_planif = budget_modifie.get('heures_total', 0.0)
    cout_modifie_planif = budget_modifie.get('cout_total', 0.0)

    # Calculer les heures/coûts de formation (même logique que Budget Annuel et Besoin Jour)
    total_heures_formation = 0.0
    total_cout_formation = 0.0
    cout_horaire_at = 45.50
    if 'personnel' in st.session_state and not st.session_state.personnel.empty:
        at_row = st.session_state.personnel[st.session_state.personnel['Type'] == 'AT']
        if not at_row.empty:
            try:
                cout_horaire_at = float(at_row['Coût Horaire'].iloc[0])
            except Exception:
                pass
    if 'budget_formation_at' in st.session_state:
        df_formation = st.session_state.budget_formation_at.copy()
        df_formation['Effectif (pers.)'] = pd.to_numeric(df_formation.get('Effectif (pers.)', 0), errors='coerce').fillna(0).astype(int).clip(lower=0)
        df_formation['Heures'] = df_formation.get('Heures', 0).apply(lambda x: float(str(x).replace(',', '.')) if pd.notna(x) else 0.0).clip(lower=0)
        df_formation['Nbre de shifts'] = pd.to_numeric(df_formation.get('Nbre de shifts', 0), errors='coerce').fillna(0).astype(int).clip(lower=0)
        df_formation['Total (heures)'] = (
            df_formation['Effectif (pers.)'] *
            df_formation['Heures'] *
            df_formation['Nbre de shifts']
        )
        total_heures_formation = df_formation['Total (heures)'].sum()
        total_cout_formation = total_heures_formation * cout_horaire_at

    # Calculer les heures/coûts des formateurs (ATF)
    total_heures_formateurs = 0.0
    total_cout_formateurs = 0.0
    cout_horaire_atf = 52.00
    if 'personnel' in st.session_state and not st.session_state.personnel.empty:
        atf_row = st.session_state.personnel[st.session_state.personnel['Type'] == 'ATF']
        if not atf_row.empty:
            try:
                cout_horaire_atf = float(atf_row['Coût Horaire'].iloc[0])
            except Exception:
                pass
    if 'budget_formateurs_at' in st.session_state:
        df_formateurs = st.session_state.budget_formateurs_at.copy()
        df_formateurs['Effectif (pers.)'] = pd.to_numeric(df_formateurs.get('Effectif (pers.)', 0), errors='coerce').fillna(0).astype(int).clip(lower=0)
        df_formateurs['Heures'] = df_formateurs.get('Heures', 0).apply(lambda x: float(str(x).replace(',', '.')) if pd.notna(x) else 0.0).clip(lower=0)
        df_formateurs['Nbre de shifts'] = pd.to_numeric(df_formateurs.get('Nbre de shifts', 0), errors='coerce').fillna(0).astype(int).clip(lower=0)
        df_formateurs['Total (heures)'] = (
            df_formateurs['Effectif (pers.)'] *
            df_formateurs['Heures'] *
            df_formateurs['Nbre de shifts']
        )
        total_heures_formateurs = df_formateurs['Total (heures)'].sum()
        total_cout_formateurs = total_heures_formateurs * cout_horaire_atf

    # Totaux avec formation (cohérent avec Budget Annuel et Besoin Jour)
    heures_annuel = heures_annuel_planif + total_heures_formation + total_heures_formateurs
    cout_annuel = cout_annuel_planif + total_cout_formation + total_cout_formateurs
    heures_modifie = heures_modifie_planif + total_heures_formation + total_heures_formateurs
    cout_modifie = cout_modifie_planif + total_cout_formation + total_cout_formateurs

    # =================== Données Réalisé ===================
    heures_realise = 0.0
    cout_realise = 0.0
    if not df_factu.empty:
        heures_realise = df_factu['Heures_Total'].sum()
        tarif_at = 0.0
        t_at = st.session_state.get('cost_mapping', {}).get("AT")
        if t_at:
            pers = st.session_state.get('personnel', pd.DataFrame())
            if not pers.empty:
                r = pers[pers['Type'] == t_at]
                if not r.empty:
                    tarif_at = float(r['Coût Horaire'].iloc[0])
        cout_realise = heures_realise * tarif_at

    # =================== KPI & Écarts ===================
    ecart_heures_mod_ann = heures_modifie - heures_annuel
    ecart_heures_mod_ann_pct = (ecart_heures_mod_ann / heures_annuel * 100) if heures_annuel != 0 else 0
    ecart_cout_mod_ann = cout_modifie - cout_annuel
    ecart_cout_mod_ann_pct = (ecart_cout_mod_ann / cout_annuel * 100) if cout_annuel != 0 else 0

    ecart_heures_real_mod = heures_realise - heures_modifie
    ecart_heures_real_mod_pct = (ecart_heures_real_mod / heures_modifie * 100) if heures_modifie != 0 else 0
    ecart_cout_real_mod = cout_realise - cout_modifie
    ecart_cout_real_mod_pct = (ecart_cout_real_mod / cout_modifie * 100) if cout_modifie != 0 else 0

    st.markdown("---")
    st.subheader(f"📊 Synthèse {year} - Coûts (CHF)")
    c1, c2, c3 = st.columns(3)
    with c1:
        st.markdown(f"""<div class="kpi-card kpi-blue"><div class="label">Budget Annuel</div>
        <div class="value">{cout_annuel:,.0f} CHF</div><div class="delta">Prévision initiale</div></div>""", unsafe_allow_html=True)
    with c2:
        color = "kpi-green" if ecart_cout_mod_ann <= 0 else "kpi-amber"
        symb = "▼" if ecart_cout_mod_ann < 0 else "▲"
        st.markdown(f"""<div class="kpi-card {color}"><div class="label">Budget Modifié</div>
        <div class="value">{cout_modifie:,.0f} CHF</div>
        <div class="delta">{symb} {abs(ecart_cout_mod_ann):,.0f} CHF ({ecart_cout_mod_ann_pct:+.1f}%)</div></div>""", unsafe_allow_html=True)
    with c3:
        if df_factu.empty:
            st.markdown(f"""<div class="kpi-card kpi-amber"><div class="label">Réalisé</div>
            <div class="value">— CHF</div><div class="delta">Aucune donnée de facturation pour {year}</div></div>""", unsafe_allow_html=True)
        else:
            color = "kpi-green" if ecart_cout_real_mod <= 0 else "kpi-red"
            symb = "▼" if ecart_cout_real_mod < 0 else "▲"
            st.markdown(f"""<div class="kpi-card {color}"><div class="label">Réalisé</div>
            <div class="value">{cout_realise:,.0f} CHF</div>
            <div class="delta">{symb} {abs(ecart_cout_real_mod):,.0f} CHF ({ecart_cout_real_mod_pct:+.1f}%)</div></div>""", unsafe_allow_html=True)

    st.markdown("---")
    st.subheader(f"⏱️ Synthèse {year} - Heures")
    c1, c2, c3 = st.columns(3)
    with c1:
        st.markdown(f"""<div class="kpi-card kpi-blue"><div class="label">Budget Annuel</div>
        <div class="value">{heures_annuel:,.0f} h</div><div class="delta">Prévision initiale</div></div>""", unsafe_allow_html=True)
    with c2:
        color = "kpi-green" if ecart_heures_mod_ann <= 0 else "kpi-amber"
        symb = "▼" if ecart_heures_mod_ann < 0 else "▲"
        st.markdown(f"""<div class="kpi-card {color}"><div class="label">Budget Modifié</div>
        <div class="value">{heures_modifie:,.0f} h</div>
        <div class="delta">{symb} {abs(ecart_heures_mod_ann):,.0f} h ({ecart_heures_mod_ann_pct:+.1f}%)</div></div>""", unsafe_allow_html=True)
    with c3:
        if df_factu.empty:
            st.markdown(f"""<div class="kpi-card kpi-amber"><div class="label">Réalisé</div>
            <div class="value">— h</div><div class="delta">Aucune donnée de facturation pour {year}</div></div>""", unsafe_allow_html=True)
        else:
            color = "kpi-green" if ecart_heures_real_mod <= 0 else "kpi-red"
            symb = "▼" if ecart_heures_real_mod < 0 else "▲"
            st.markdown(f"""<div class="kpi-card {color}"><div class="label">Réalisé</div>
            <div class="value">{heures_realise:,.0f} h</div>
            <div class="delta">{symb} {abs(ecart_heures_real_mod):,.0f} h ({ecart_heures_real_mod_pct:+.1f}%)</div></div>""", unsafe_allow_html=True)

    # =================== Évolution Mensuelle (Non Cumulée) ===================
    st.markdown("---")
    st.subheader(f"📊 Évolution Mensuelle {year}")

    calendar_with_modif = budget_modifie.get('calendar_df', pd.DataFrame())
    if not calendar_with_modif.empty:
        try:
            calendar_with_modif['Date'] = pd.to_datetime(calendar_with_modif['Date'])
            calendar_with_modif['Mois'] = calendar_with_modif['Date'].dt.to_period('M')

            calendar_annuel = bs.get('calendar_df', pd.DataFrame()).copy()
            calendar_annuel['Date'] = pd.to_datetime(calendar_annuel['Date'])
            calendar_annuel['Mois'] = calendar_annuel['Date'].dt.to_period('M')

            # Agrégation mensuelle (NON CUMULÉE)
            monthly_annuel = calendar_annuel.groupby('Mois').agg({
                'Heures_Total_Jour': 'sum', 'Coût_Total_Jour': 'sum'
            }).reset_index().rename(columns={'Heures_Total_Jour':'Heures_Annuel','Coût_Total_Jour':'Cout_Annuel'})

            monthly_modifie = calendar_with_modif.groupby('Mois').agg({
                'Heures_Total_Jour': 'sum', 'Coût_Total_Jour': 'sum'
            }).reset_index().rename(columns={'Heures_Total_Jour':'Heures_Modifie','Coût_Total_Jour':'Cout_Modifie'})

            monthly_budget = monthly_annuel.merge(monthly_modifie, on='Mois', how='outer')
            monthly_budget['Mois_str'] = monthly_budget['Mois'].astype(str)
            monthly_budget['Mois_dt'] = monthly_budget['Mois'].apply(lambda x: x.to_timestamp())

            # Ajouter les données de facturation si disponibles
            if not df_factu.empty:
                df_factu_temp = df_factu.copy()
                df_factu_temp['Mois'] = pd.to_datetime(df_factu_temp['Date']).dt.to_period('M')
                monthly_factu = df_factu_temp.groupby('Mois').agg({'Heures_Total':'sum'}).reset_index()
                monthly_factu['Mois_str'] = monthly_factu['Mois'].astype(str)
                monthly_factu['Mois_dt'] = monthly_factu['Mois'].apply(lambda x: x.to_timestamp())

                tarif_at = 0.0
                t_at = st.session_state.get('cost_mapping', {}).get("AT")
                if t_at:
                    pers = st.session_state.get('personnel', pd.DataFrame())
                    if not pers.empty:
                        r = pers[pers['Type'] == t_at]
                        if not r.empty:
                            tarif_at = float(r['Coût Horaire'].iloc[0])

                monthly_factu['Cout_Realise'] = monthly_factu['Heures_Total'] * tarif_at
                monthly_factu.rename(columns={'Heures_Total': 'Heures_Realise'}, inplace=True)

                monthly_combined = monthly_budget.merge(
                    monthly_factu[['Mois_str', 'Heures_Realise', 'Cout_Realise']],
                    on='Mois_str', how='left'
                )
            else:
                monthly_combined = monthly_budget.copy()
                monthly_combined['Heures_Realise'] = None
                monthly_combined['Cout_Realise'] = None

            # Préparer les données pour les graphiques mensuels (NON CUMULÉS)
            df_heures_mensuel = pd.DataFrame({
                'Mois': monthly_combined['Mois_dt'].tolist() * 3,
                'Type': (['Budget Annuel']*len(monthly_combined) + ['Budget Modifié']*len(monthly_combined) + ['Réalisé']*len(monthly_combined)),
                'Heures': (monthly_combined['Heures_Annuel'].tolist() + monthly_combined['Heures_Modifie'].tolist() + monthly_combined['Heures_Realise'].tolist())
            })
            df_cout_mensuel = pd.DataFrame({
                'Mois': monthly_combined['Mois_dt'].tolist() * 3,
                'Type': (['Budget Annuel']*len(monthly_combined) + ['Budget Modifié']*len(monthly_combined) + ['Réalisé']*len(monthly_combined)),
                'Cout': (monthly_combined['Cout_Annuel'].tolist() + monthly_combined['Cout_Modifie'].tolist() + monthly_combined['Cout_Realise'].tolist())
            })
            df_heures_mensuel = df_heures_mensuel.dropna(subset=['Heures'])
            df_cout_mensuel = df_cout_mensuel.dropna(subset=['Cout'])

            tab_cout_m, tab_heures_m = st.tabs(["💰 Coûts Mensuels (CHF)", "⏱️ Heures Mensuelles"])
            with tab_cout_m:
                if not df_cout_mensuel.empty:
                    chart_cout_m = alt.Chart(df_cout_mensuel).mark_bar().encode(
                        x=alt.X('Mois:T', title='Mois', axis=alt.Axis(format='%b %Y')),
                        y=alt.Y('Cout:Q', title='Coût Mensuel (CHF)'),
                        color=alt.Color('Type:N', scale=alt.Scale(domain=['Budget Annuel','Budget Modifié','Réalisé'],
                                                                  range=['#0076aa','#ffa500','#dc143c']),
                                        legend=alt.Legend(title='Type de Budget')),
                        xOffset=alt.XOffset('Type:N'),
                        tooltip=[alt.Tooltip('Mois:T', title='Mois', format='%B %Y'),
                                 alt.Tooltip('Type:N', title='Type'),
                                 alt.Tooltip('Cout:Q', title='Coût Mensuel', format=',.0f')]
                    ).properties(height=400).interactive()
                    st.altair_chart(chart_cout_m, use_container_width=True)
                else:
                    st.info("Pas de données disponibles pour tracer la courbe des coûts mensuels.")
            with tab_heures_m:
                if not df_heures_mensuel.empty:
                    chart_heures_m = alt.Chart(df_heures_mensuel).mark_bar().encode(
                        x=alt.X('Mois:T', title='Mois', axis=alt.Axis(format='%b %Y')),
                        y=alt.Y('Heures:Q', title='Heures Mensuelles'),
                        color=alt.Color('Type:N', scale=alt.Scale(domain=['Budget Annuel','Budget Modifié','Réalisé'],
                                                                  range=['#0076aa','#ffa500','#dc143c']),
                                        legend=alt.Legend(title='Type de Budget')),
                        xOffset=alt.XOffset('Type:N'),
                        tooltip=[alt.Tooltip('Mois:T', title='Mois', format='%B %Y'),
                                 alt.Tooltip('Type:N', title='Type'),
                                 alt.Tooltip('Heures:Q', title='Heures Mensuelles', format=',.0f')]
                    ).properties(height=400).interactive()
                    st.altair_chart(chart_heures_m, use_container_width=True)
                else:
                    st.info("Pas de données disponibles pour tracer la courbe des heures mensuelles.")
        except Exception as e:
            st.error(f"Erreur lors de la création des graphiques mensuels: {e}")
            import traceback
            st.error(traceback.format_exc())

    # =================== Évolution Cumulée ===================
    st.markdown("---")
    st.subheader(f"📈 Évolution Cumulée {year}")

    calendar_with_modif = budget_modifie.get('calendar_df', pd.DataFrame())
    if not calendar_with_modif.empty:
        try:
            calendar_with_modif['Date'] = pd.to_datetime(calendar_with_modif['Date'])
            calendar_with_modif['Mois'] = calendar_with_modif['Date'].dt.to_period('M')

            calendar_annuel = bs.get('calendar_df', pd.DataFrame()).copy()
            calendar_annuel['Date'] = pd.to_datetime(calendar_annuel['Date'])
            calendar_annuel['Mois'] = calendar_annuel['Date'].dt.to_period('M')

            monthly_annuel = calendar_annuel.groupby('Mois').agg({
                'Heures_Total_Jour': 'sum', 'Coût_Total_Jour': 'sum'
            }).reset_index().rename(columns={'Heures_Total_Jour':'Heures_Annuel','Coût_Total_Jour':'Cout_Annuel'})

            monthly_modifie = calendar_with_modif.groupby('Mois').agg({
                'Heures_Total_Jour': 'sum', 'Coût_Total_Jour': 'sum'
            }).reset_index().rename(columns={'Heures_Total_Jour':'Heures_Modifie','Coût_Total_Jour':'Cout_Modifie'})

            monthly_budget = monthly_annuel.merge(monthly_modifie, on='Mois', how='outer')
            monthly_budget['Mois_str'] = monthly_budget['Mois'].astype(str)
            monthly_budget['Mois_dt'] = monthly_budget['Mois'].apply(lambda x: x.to_timestamp())

            monthly_budget['Heures_Annuel_Cumul'] = monthly_budget['Heures_Annuel'].cumsum()
            monthly_budget['Cout_Annuel_Cumul'] = monthly_budget['Cout_Annuel'].cumsum()
            monthly_budget['Heures_Modifie_Cumul'] = monthly_budget['Heures_Modifie'].cumsum()
            monthly_budget['Cout_Modifie_Cumul'] = monthly_budget['Cout_Modifie'].cumsum()

            if not df_factu.empty:
                df_factu['Mois'] = pd.to_datetime(df_factu['Date']).dt.to_period('M')
                monthly_factu = df_factu.groupby('Mois').agg({'Heures_Total':'sum'}).reset_index()
                monthly_factu['Mois_str'] = monthly_factu['Mois'].astype(str)
                monthly_factu['Mois_dt'] = monthly_factu['Mois'].apply(lambda x: x.to_timestamp())
                monthly_factu['Heures_Realise_Cumul'] = monthly_factu['Heures_Total'].cumsum()

                tarif_at = 0.0
                t_at = st.session_state.get('cost_mapping', {}).get("AT")
                if t_at:
                    pers = st.session_state.get('personnel', pd.DataFrame())
                    if not pers.empty:
                        r = pers[pers['Type'] == t_at]
                        if not r.empty:
                            tarif_at = float(r['Coût Horaire'].iloc[0])

                monthly_factu['Cout_Realise'] = monthly_factu['Heures_Total'] * tarif_at
                monthly_factu['Cout_Realise_Cumul'] = monthly_factu['Cout_Realise'].cumsum()

                monthly_combined = monthly_budget.merge(
                    monthly_factu[['Mois_str','Heures_Realise_Cumul','Cout_Realise_Cumul']],
                    on='Mois_str', how='left'
                )
            else:
                monthly_combined = monthly_budget.copy()
                monthly_combined['Heures_Realise_Cumul'] = None
                monthly_combined['Cout_Realise_Cumul'] = None

            df_heures_plot = pd.DataFrame({
                'Mois': monthly_combined['Mois_dt'].tolist() * 3,
                'Type': (['Budget Annuel']*len(monthly_combined) + ['Budget Modifié']*len(monthly_combined) + ['Réalisé']*len(monthly_combined)),
                'Heures_Cumul': (monthly_combined['Heures_Annuel_Cumul'].tolist() + monthly_combined['Heures_Modifie_Cumul'].tolist() + monthly_combined['Heures_Realise_Cumul'].tolist())
            })
            df_cout_plot = pd.DataFrame({
                'Mois': monthly_combined['Mois_dt'].tolist() * 3,
                'Type': (['Budget Annuel']*len(monthly_combined) + ['Budget Modifié']*len(monthly_combined) + ['Réalisé']*len(monthly_combined)),
                'Cout_Cumul': (monthly_combined['Cout_Annuel_Cumul'].tolist() + monthly_combined['Cout_Modifie_Cumul'].tolist() + monthly_combined['Cout_Realise_Cumul'].tolist())
            })
            df_heures_plot = df_heures_plot.dropna(subset=['Heures_Cumul'])
            df_cout_plot = df_cout_plot.dropna(subset=['Cout_Cumul'])

            tab_cout, tab_heures = st.tabs(["💰 Coûts Cumulés (CHF)", "⏱️ Heures Cumulées"])
            with tab_cout:
                if not df_cout_plot.empty:
                    chart_cout = alt.Chart(df_cout_plot).mark_line(point=True, strokeWidth=3).encode(
                        x=alt.X('Mois:T', title='Mois', axis=alt.Axis(format='%b %Y')),
                        y=alt.Y('Cout_Cumul:Q', title='Coût Cumulé (CHF)'),
                        color=alt.Color('Type:N', scale=alt.Scale(domain=['Budget Annuel','Budget Modifié','Réalisé'],
                                                                  range=['#0076aa','#ffa500','#dc143c']),
                                        legend=alt.Legend(title='Type de Budget')),
                        tooltip=[alt.Tooltip('Mois:T', title='Mois', format='%B %Y'),
                                 alt.Tooltip('Type:N', title='Type'),
                                 alt.Tooltip('Cout_Cumul:Q', title='Coût Cumulé', format=',.0f')]
                    ).properties(height=400).interactive()
                    st.altair_chart(chart_cout, use_container_width=True)
                else:
                    st.info("Pas de données disponibles pour tracer la courbe des coûts.")
            with tab_heures:
                if not df_heures_plot.empty:
                    chart_heures = alt.Chart(df_heures_plot).mark_line(point=True, strokeWidth=3).encode(
                        x=alt.X('Mois:T', title='Mois', axis=alt.Axis(format='%b %Y')),
                        y=alt.Y('Heures_Cumul:Q', title='Heures Cumulées'),
                        color=alt.Color('Type:N', scale=alt.Scale(domain=['Budget Annuel','Budget Modifié','Réalisé'],
                                                                  range=['#0076aa','#ffa500','#dc143c']),
                                        legend=alt.Legend(title='Type de Budget')),
                        tooltip=[alt.Tooltip('Mois:T', title='Mois', format='%B %Y'),
                                 alt.Tooltip('Type:N', title='Type'),
                                 alt.Tooltip('Heures_Cumul:Q', title='Heures Cumulées', format=',.0f')]
                    ).properties(height=400).interactive()
                    st.altair_chart(chart_heures, use_container_width=True)
                else:
                    st.info("Pas de données disponibles pour tracer la courbe des heures.")
        except Exception as e:
            st.error(f"Erreur lors de la création des graphiques cumulés: {e}")
            import traceback
            st.error(traceback.format_exc())

    # =================== Tableau Détaillé Mensuel ===================
    
    st.markdown("---")
    st.subheader("📋 Détail Mensuel")
    
    if not calendar_with_modif.empty and 'monthly_combined' in locals():
        try:
            # Base : données Modifié
            monthly_table = monthly_combined.copy()
            monthly_table['Mois'] = monthly_table['Mois_str']
    
            # Colonnes Modifié (sécurité)
            monthly_table['Heures_Modifie'] = monthly_table.get('Heures_Modifie', 0).fillna(0)
            monthly_table['Cout_Modifie'] = monthly_table.get('Cout_Modifie', 0).fillna(0)
    
            # Ajout des colonnes "Facturées" (si factures dispo)
            if not df_factu.empty:
                monthly_factu_raw = df_factu.groupby('Mois').agg({'Heures_Total': 'sum'}).reset_index()
                # clef de jointure = texte AAAA-MM
                monthly_factu_raw['Mois_str'] = monthly_factu_raw['Mois'].astype(str)
    
                # Tarif AT pour valoriser le coût facturé
                tarif_at = 0.0
                personnel_type_at = st.session_state.get('cost_mapping', {}).get("AT")
                if personnel_type_at:
                    personnel_df = st.session_state.get('personnel', pd.DataFrame())
                    if not personnel_df.empty:
                        row_tarif = personnel_df[personnel_df['Type'] == personnel_type_at]
                        if not row_tarif.empty:
                            tarif_at = float(row_tarif['Coût Horaire'].iloc[0])
    
                monthly_factu_raw['Cout_Facture'] = monthly_factu_raw['Heures_Total'] * tarif_at
    
                # Pour éviter tout conflit de nom, on renomme la clef côté droit
                right = monthly_factu_raw[['Mois_str', 'Heures_Total', 'Cout_Facture']].rename(
                    columns={'Mois_str': '__MoisKey__'}
                )
    
                # Merge sur la clef texte
                monthly_table = monthly_table.merge(
                    right,
                    left_on='Mois',
                    right_on='__MoisKey__',
                    how='left'
                )
    
                # Nettoyage des colonnes techniques si elles existent
                if '__MoisKey__' in monthly_table.columns:
                    monthly_table.drop(columns='__MoisKey__', inplace=True)
    
                # Renommer pour l'affichage
                monthly_table.rename(columns={'Heures_Total': 'Heures_Facturees'}, inplace=True)
            else:
                # Colonnes vides si pas de factures
                monthly_table['Heures_Facturees'] = pd.NA
                monthly_table['Cout_Facture'] = pd.NA
    
            # Colonnes finales à afficher (sans Annuel)
            columns_to_show = [
                'Mois',
                'Heures_Modifie',
                'Cout_Modifie',
                'Heures_Facturees',
                'Cout_Facture'
            ]
    
            df_monthly_display = monthly_table[columns_to_show].copy()
            df_monthly_display.columns = [
                'Mois',
                'Heures Modifié',
                'Coût Modifié (CHF)',
                'Heures Facturées',
                'Coût Facturé (CHF)'
            ]
    
            # Configuration des colonnes
            col_config = {
                'Mois': st.column_config.TextColumn('Mois'),
                'Heures Modifié': st.column_config.NumberColumn('Heures Modifié', format='%.0f h'),
                'Coût Modifié (CHF)': st.column_config.NumberColumn('Coût Modifié', format='%.0f CHF'),
                'Heures Facturées': st.column_config.NumberColumn('Heures Facturées', format='%.0f h'),
                'Coût Facturé (CHF)': st.column_config.NumberColumn('Coût Facturé', format='%.0f CHF'),
            }
    
            st.dataframe(
                df_monthly_display,
                column_config=col_config,
                hide_index=True,
                use_container_width=True
            )
    
        except Exception as e:
            st.error(f"Erreur lors de la création du tableau mensuel: {e}")
            import traceback
            st.error(traceback.format_exc())



    # =================== Notes ===================
    with st.expander("ℹ️ Informations sur l'Analyse Budgétaire"):
        st.markdown("""
        - **Budget Annuel** : Prévision initiale basée sur les jours-types.
        - **Budget Modifié** : Intègre les ajustements de la page *Besoin Jour*.
        - **Réalisé** : Données des fichiers Excel (dossier `input_files/facturation/`).
        """)


if __name__ == "__main__":
    render_analyse_budgetaire_page()
