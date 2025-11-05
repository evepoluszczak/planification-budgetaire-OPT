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

    # Charger les fichiers Excel (ancien et nouveau format)
    excel_data = _load_excel_facturation(year, factu_dir)

    if excel_data.empty:
        return pd.DataFrame()

    # Normaliser la colonne Date en datetime
    if 'Date' in excel_data.columns:
        excel_data['Date'] = pd.to_datetime(excel_data['Date'], errors='coerce')
        excel_data = excel_data.dropna(subset=['Date'])
        excel_data = excel_data.sort_values('Date', na_position='last').reset_index(drop=True)
        excel_data = excel_data.fillna(0)

    return excel_data


def _load_excel_facturation(year: int, factu_dir: Path) -> pd.DataFrame:
    """
    Charge les fichiers Excel de facturation pour une année donnée.
    Supporte 2 formats:
    - ANCIEN (avant sept 2025): Date ouvrable, Heures, Coordinateurs
    - NOUVEAU (depuis sept 2025): Libellé, Quantité, Prix, Montant
    """
    pattern = re.compile(r'Facturation Lot A (\d{2})\.(\d{4})\.xlsx')

    all_data = []

    for file_path in factu_dir.glob(FACTU_AT_GLOB):
        match = pattern.match(file_path.name)
        if match:
            month_str, year_str = match.groups()
            file_month = int(month_str)
            file_year = int(year_str)

            # Ne charger que les fichiers de l'année sélectionnée
            if file_year != year:
                continue

            try:
                # Lire le fichier Excel pour détecter le format
                df_raw = pd.read_excel(file_path, header=None)

                # Détecter le format (nouveau vs ancien)
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

                # Seuil: septembre 2025 = changement de format
                is_new_format = (file_year > 2025) or (file_year == 2025 and file_month >= 9)

                # Forcer la détection si les colonnes sont trouvées
                if has_libelle_col:
                    is_new_format = True
                elif has_date_ouvrable:
                    is_new_format = False

                if is_new_format:
                    # === NOUVEAU FORMAT (depuis sept 2025) ===
                    df_result = _parse_new_excel_format(file_path, file_year, file_month)
                else:
                    # === ANCIEN FORMAT (avant sept 2025) ===
                    df_result = _parse_old_excel_format(file_path, file_year, file_month)

                if not df_result.empty:
                    all_data.append(df_result)

            except Exception as e:
                st.warning(f"⚠️ Erreur lors du chargement de {file_path.name}: {e}")
                import traceback
                st.error(traceback.format_exc())
                continue

    if not all_data:
        return pd.DataFrame()

    # Concaténer tous les mois
    result = pd.concat(all_data, ignore_index=True)

    # Normaliser la colonne Date avant le tri pour éviter les erreurs de type
    if 'Date' in result.columns:
        result['Date'] = pd.to_datetime(result['Date'], errors='coerce')
        result = result.dropna(subset=['Date'])

    result = result.sort_values('Date', na_position='last').reset_index(drop=True)

    return result


# ============================================================
# Parseurs : Ancien & Nouveau formats (utilisés aussi par la vue mensuelle)
# ============================================================

def _parse_old_excel_format(file_path: Path, file_year: int, file_month: int) -> pd.DataFrame:
    """
    Parse l'ancien format Excel (avant sept 2025):
    - Colonnes: Date ouvrable, Heures, Coordinateurs
    """
    # Lire le fichier Excel sans header pour analyser la structure
    df_raw = pd.read_excel(file_path, header=None)

    # Trouver la ligne d'en-tête (qui contient "Date ouvrable", "Heures", etc.)
    header_row = None
    for idx, row in df_raw.iterrows():
        if 'Date ouvrable' in str(row.values):
            header_row = idx
            break

    if header_row is None:
        st.warning(f"⚠️ Structure ancien format non reconnue dans {file_path.name}")
        return pd.DataFrame()

    # Lire à partir de la ligne suivante avec les bonnes colonnes
    df = pd.read_excel(file_path, header=header_row)

    # Vérifier les colonnes nécessaires
    if 'Date ouvrable' not in df.columns or 'Heures' not in df.columns:
        st.warning(f"⚠️ Colonnes manquantes dans {file_path.name}")
        return pd.DataFrame()

    # Filtrer les lignes valides (qui contiennent "Total")
    df = df[df['Date ouvrable'].astype(str).str.contains('Total', na=False)].copy()

    # Extraire la date du format "Total DD.MM.YYYY"
    df['Date_str'] = df['Date ouvrable'].astype(str).str.extract(r'(\d{2}\.\d{2}\.\d{4})')
    df['Date'] = pd.to_datetime(df['Date_str'], format='%d.%m.%Y', errors='coerce')

    # Nettoyer les données
    df = df.dropna(subset=['Date'])
    df['Heures'] = pd.to_numeric(df['Heures'], errors='coerce').fillna(0)

    # Ajouter les heures de coordination si disponible
    if 'Coordinateurs' in df.columns:
        df['Heures_Coordinateurs'] = pd.to_numeric(
            df['Coordinateurs'], errors='coerce'
        ).fillna(0)
    else:
        df['Heures_Coordinateurs'] = 0

    # Calculer le total des heures (AT + Coordinateurs)
    df['Heures_Total'] = df['Heures'] + df['Heures_Coordinateurs']

    # Sélectionner les colonnes finales
    df_clean = df[['Date', 'Heures', 'Heures_Coordinateurs', 'Heures_Total']].copy()

    # Expander informatif (vue détaillée)
    total_heures_at = df_clean['Heures'].sum()
    total_heures_coord = df_clean['Heures_Coordinateurs'].sum()
    total_heures = df_clean['Heures_Total'].sum()

    with st.expander(f"✓ {file_path.name} (ancien format): {len(df_clean)} jours"):
        st.caption(f"**Mois**: {file_month:02d}/{file_year}")
        st.caption(f"**Total**: {total_heures:,.0f} heures")

        # Tableau par type (info)
        detail_rows = []
        if total_heures_at > 0:
            detail_rows.append({
                'Type': 'AT',
                'Heures': total_heures_at,
                'Jours': len(df_clean[df_clean['Heures'] > 0])
            })
        if total_heures_coord > 0:
            detail_rows.append({
                'Type': 'Coordinateurs',
                'Heures': total_heures_coord,
                'Jours': len(df_clean[df_clean['Heures_Coordinateurs'] > 0])
            })

        if detail_rows:
            df_detail = pd.DataFrame(detail_rows)
            st.dataframe(
                df_detail,
                column_config={
                    'Type': st.column_config.TextColumn('Type', width='medium'),
                    'Heures': st.column_config.NumberColumn('Heures', format='%.1f h'),
                    'Jours': st.column_config.NumberColumn('Jours', format='%d')
                },
                hide_index=True,
                use_container_width=True
            )

    return df_clean


def _parse_new_excel_format(file_path: Path, file_year: int, file_month: int) -> pd.DataFrame:
    """
    Parse le nouveau format Excel (depuis sept 2025):
    - Colonnes: Libellé, Quantité, Prix, Montant
    - Libellé: "Heures AT", "Heures ATR", etc.
    - Quantité: nombre d'heures
    - Prix: coût horaire
    - Montant: coût total (Quantité × Prix)
    """
    # Lire le fichier Excel sans header pour trouver les en-têtes
    df_raw = pd.read_excel(file_path, header=None)

    # Trouver la ligne d'en-tête
    header_row = None
    for idx, row in df_raw.iterrows():
        row_str = ' '.join([str(x) for x in row.values if pd.notna(x)]).lower()
        if 'libellé' in row_str and 'quantité' in row_str:
            header_row = idx
            break

    if header_row is None:
        st.warning(f"⚠️ En-têtes nouveau format non trouvés dans {file_path.name}")
        return pd.DataFrame()

    # Lire avec les bonnes en-têtes
    df = pd.read_excel(file_path, header=header_row)

    # Normaliser les noms de colonnes
    df.columns = [str(col).strip() for col in df.columns]

    # Vérifier les colonnes requises
    required_cols = ['Libellé', 'Quantité', 'Prix', 'Montant']
    missing_cols = [col for col in required_cols if col not in df.columns]

    if missing_cols:
        st.warning(f"⚠️ Colonnes manquantes dans {file_path.name}: {missing_cols}")
        return pd.DataFrame()

    # Filtrer les lignes valides (avec libellé et quantité > 0)
    df = df[df['Libellé'].notna() & (df['Libellé'] != '')].copy()
    df['Quantité'] = pd.to_numeric(df['Quantité'], errors='coerce').fillna(0)
    df['Prix'] = pd.to_numeric(df['Prix'], errors='coerce').fillna(0)
    df['Montant'] = pd.to_numeric(df['Montant'], errors='coerce').fillna(0)

    # Filtrer les lignes avec quantité > 0
    df = df[df['Quantité'] > 0].copy()

    if df.empty:
        return pd.DataFrame()

    # Extraire le type de personnel depuis le libellé
    def extract_type_personnel(libelle: str) -> str:
        """Extrait le type de personnel depuis 'Heures AT', 'Heures ATR', etc."""
        libelle = str(libelle).strip()

        # Pattern: "Heures XXX" ou "Heure XXX"
        match = re.search(r'(?:Heures?)\s+(.+)', libelle, re.IGNORECASE)
        if match:
            type_str = match.group(1).strip()
        else:
            # Fallback: prendre tout le libellé
            type_str = libelle

        type_lower = type_str.lower()

        # Mappings connus
        if 'atf' in type_lower or 'formateur' in type_lower:
            return 'ATF'
        if 'atr' in type_lower:
            return 'ATR'
        if 'coordinateur' in type_lower:
            return 'Coordinateurs'
        if 'csc' in type_lower:
            return 'CSC'
        if "gestion d'accès" in type_lower or 'gestion acces' in type_lower:
            return 'Gestion d\'accès'
        if 'visitor' in type_lower:
            return 'Visitor Center'
        if re.search(r'\bat\b', type_lower):  # mot isolé "AT"
            return 'AT'

        # Types inconnus → catégorie "extra"
        return 'extra'

    df['Type'] = df['Libellé'].apply(extract_type_personnel)

    # Vérifier les prix avec la configuration si disponible
    if 'personnel' in st.session_state and not st.session_state.personnel.empty:
        personnel_df = st.session_state.personnel

        for _, row in df.iterrows():
            type_pers = row['Type']
            prix_facture = row['Prix']

            # Chercher le coût horaire configuré
            matching = personnel_df[personnel_df['Type'] == type_pers]
            if not matching.empty:
                cout_config = float(matching['Coût Horaire'].iloc[0])
                # Tolérance de 1% pour comparaison
                if abs(prix_facture - cout_config) > cout_config * 0.01:
                    st.warning(
                        f"⚠️ {file_path.name}: Prix facturé pour {type_pers} ({prix_facture:.2f} CHF/h) "
                        f"diffère de la configuration ({cout_config:.2f} CHF/h)"
                    )

    # Créer une ligne par mois avec toutes les catégories
    date = dt.date(file_year, file_month, 1)
    row_data = {'Date': date}

    total_heures = 0.0
    total_cout = 0.0

    # Grouper par type
    for type_pers, group in df.groupby('Type'):
        heures = group['Quantité'].sum()
        cout = group['Montant'].sum()

        row_data[f'Heures_{type_pers}'] = heures
        row_data[f'Cout_{type_pers}'] = cout

        total_heures += heures
        total_cout += cout

    row_data['Heures_Total'] = total_heures
    row_data['Cout_Total'] = total_cout

    # Créer le DataFrame final
    result_df = pd.DataFrame([row_data])

    # Expander informatif (vue détaillée)
    with st.expander(f"✓ {file_path.name} (nouveau format): {len(df)} lignes, {len(df['Type'].unique())} types"):
        st.caption(f"**Mois**: {file_month:02d}/{file_year}")
        st.caption(f"**Total**: {total_heures:,.0f} heures · {total_cout:,.2f} CHF")

        # Tableau détaillé par type
        detail_rows = []
        for type_pers, group in df.groupby('Type'):
            detail_rows.append({
                'Type': type_pers,
                'Heures': group['Quantité'].sum(),
                'Coût Total (CHF)': group['Montant'].sum(),
                'Coût Horaire Moyen (CHF)': group['Montant'].sum() / group['Quantité'].sum() if group['Quantité'].sum() > 0 else 0,
                'Lignes': len(group)
            })

        df_detail = pd.DataFrame(detail_rows).sort_values('Heures', ascending=False)
        st.dataframe(
            df_detail,
            column_config={
                'Type': st.column_config.TextColumn('Type', width='medium'),
                'Heures': st.column_config.NumberColumn('Heures', format='%.1f h'),
                'Coût Total (CHF)': st.column_config.NumberColumn('Coût Total', format='%.2f CHF'),
                'Coût Horaire Moyen (CHF)': st.column_config.NumberColumn('Coût/h', format='%.2f CHF/h'),
                'Lignes': st.column_config.NumberColumn('Lignes', format='%d')
            },
            hide_index=True,
            use_container_width=True
        )

    return result_df


# ============================================================
# Budget Modifié : recalcul identique à besoin_jour.py
# ============================================================

def calculate_budget_modifie(year: int):
    """
    Calcule le budget modifié pour l'année (Budget Annuel + ajustements Besoin Jour).
    IMPORTANT: Cette fonction DOIT utiliser exactement la même logique que besoin_jour.py
    pour garantir la cohérence des résultats.

    Returns:
        dict avec 'heures_total', 'cout_total' et 'calendar_df'
    """
    bs = st.session_state.get('budget_state', {})
    if not bs or bs.get('year') != year or 'calendar_df' not in bs:
        return None

    try:
        # EXACTEMENT comme dans besoin_jour.py
        calendar_dyn = bs['calendar_df'].copy()

        # Tarif AT (même logique)
        tarif_at = 0.0
        personnel_type_at = st.session_state.get('cost_mapping', {}).get("AT")
        if personnel_type_at:
            personnel_df = st.session_state.get('personnel', pd.DataFrame())
            if not personnel_df.empty:
                row_tarif = personnel_df[personnel_df['Type'] == personnel_type_at]
                if not row_tarif.empty:
                    tarif_at = float(row_tarif['Coût Horaire'].iloc[0])

        # Préparer les données AT (même logique)
        perimetres_AT = st.session_state.perimetres.get("AT", [])
        time_slots_default = TIME_SLOTS
        planning_dict_at = st.session_state.planning_data.get("AT", {})

        heures_vals_at_recalc = []
        costs_vals_at_recalc = []

        # Recalculer AT avec ajustements (même logique)
        for _, r in calendar_dyn.iterrows():
            jour, saison, date_ = r['Jour'], r['Saison'], r['Date'].date()
            jtg = r['Jour_Type_Global']

            _, base_df_at = _ensure_grid(
                planning_dict_at, jtg, perimetres_AT, time_slots_default
            )

            # Appliquer les ajustements Besoin Jour
            eff_df_at = _apply_ops_to_grid(
                base_df_at, date_, jour, saison, category="AT"
            )

            day_hours = eff_df_at.values.sum() * 0.5
            heures_vals_at_recalc.append(day_hours)
            costs_vals_at_recalc.append(day_hours * tarif_at)

        # Remplacer DIRECTEMENT les colonnes AT
        calendar_dyn["Heures_AT"] = heures_vals_at_recalc
        calendar_dyn["Coût_AT"] = costs_vals_at_recalc

        # Recalculer les totaux
        heure_cols_categories = [c for c in calendar_dyn.columns if c.startswith('Heures_') and c != 'Heures_Total_Jour']
        cout_cols_categories = [c for c in calendar_dyn.columns if c.startswith('Coût_') and c != 'Coût_Total_Jour']

        calendar_dyn['Heures_Total_Jour'] = calendar_dyn[heure_cols_categories].sum(axis=1) if heure_cols_categories else 0.0
        calendar_dyn['Coût_Total_Jour'] = calendar_dyn[cout_cols_categories].sum(axis=1) if cout_cols_categories else 0.0

        # Totaux annuels
        cur_hours_recalc = calendar_dyn['Heures_Total_Jour'].sum()
        cur_cost_recalc = calendar_dyn['Coût_Total_Jour'].sum()

        return {
            'heures_total': cur_hours_recalc,
            'cout_total': cur_cost_recalc,
            'calendar_df': calendar_dyn
        }

    except Exception as e:
        st.error(f"Erreur lors du calcul du budget modifié: {e}")
        import traceback
        st.error(traceback.format_exc())
        return None


# ============================================================
# Helpers d'affichage / formatage
# ============================================================

def _fmt_chf(x) -> str:
    if x is None or pd.isna(x):
        return "—"
    try:
        return f"{float(x):,.2f} CHF".replace(",", " ")
    except Exception:
        return str(x)

def _fmt_float(x) -> str:
    if x is None or pd.isna(x):
        return "—"
    try:
        return f"{float(x):,.2f}".replace(",", " ")
    except Exception:
        return str(x)

def _month_selector(label: str, default_month: int) -> int:
    months = list(range(1, 13))
    month_names = [f"{m:02d} - {calendar.month_name[m]}" for m in months]
    idx = months.index(default_month if default_month in months else dt.date.today().month)
    pick = st.selectbox(label, options=list(zip(months, month_names)), index=idx, format_func=lambda t: t[1])
    return pick[0]

def _scalar_from_df(df: pd.DataFrame, col: str, default: float = 0.0) -> float:
    """Récupère proprement un scalaire depuis la 1re ligne d'une colonne."""
    if isinstance(df, pd.DataFrame) and col in df.columns and len(df) > 0:
        return float(pd.to_numeric(df[col], errors='coerce').fillna(0).iloc[0])
    return float(default)


# ============================================================
# Viewer d'UNE facture mensuelle (sans impact sur le reste)
# ============================================================

def _detect_invoice_format(file_path: Path) -> str:
    """
    Détecte le format pour un fichier mensuel donné.
    Retourne "new" (Libellé/Quantité/Prix/Montant), "old" (Date ouvrable/Heures) ou "none".
    """
    if not file_path.exists():
        return "none"

    try:
        df_raw = pd.read_excel(file_path, header=None, nrows=20)
    except Exception:
        return "none"

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

    if has_libelle_col:
        return "new"
    if has_date_ouvrable:
        return "old"
    return "none"


def _view_single_invoice(year: int, month: int, factu_dir: Path):
    """
    Visualisation d'UNE facture mensuelle choisie par l'utilisateur.
    ⚠️ Cette fonction n'altère aucune variable globale de la page
       (n'impacte pas les calculs / graphes).
    """
    file_path = factu_dir / f"Facturation Lot A {month:02d}.{year}.xlsx"
    if not file_path.exists():
        st.info(f"Aucune facture trouvée pour {month:02d}/{year} ({file_path.name}).")
        return

    fmt = _detect_invoice_format(file_path)
    if fmt == "none":
        st.warning(f"Format non reconnu pour {file_path.name}.")
        return

    # Réutilise les parseurs existants (affichent aussi un expander de détail)
    if fmt == "new":
        df_one = _parse_new_excel_format(file_path, year, month)
        if df_one.empty:
            st.info("Le fichier ne contient aucune ligne exploitable (nouveau format).")
            return

        st.caption("Format: **Nouveau** (Libellé / Quantité / Prix / Montant)")
        st.dataframe(df_one, use_container_width=True, hide_index=True)

        # KPI sûrs (scalars)
        heures_total = _scalar_from_df(df_one, 'Heures_Total', 0.0)
        cout_total = _scalar_from_df(df_one, 'Cout_Total', 0.0)

        c1, c2 = st.columns(2)
        c1.metric("Heures (mois)", f"{heures_total:,.1f}".replace(",", " ") + " h")
        c2.metric("Coût (mois)", f"{cout_total:,.2f}".replace(",", " ") + " CHF")

    elif fmt == "old":
        df_one = _parse_old_excel_format(file_path, year, month)
        if df_one.empty:
            st.info("Le fichier ne contient aucune ligne exploitable (ancien format).")
            return

        st.caption("Format: **Ancien** (Date ouvrable / Heures)")
        st.dataframe(df_one, use_container_width=True, hide_index=True)

        heures_total = float(
            pd.to_numeric(
                df_one['Heures_Total'] if 'Heures_Total' in df_one.columns else df_one['Heures'],
                errors='coerce'
            ).fillna(0).sum()
        )
        st.metric("Heures (mois)", f"{heures_total:,.1f}".replace(",", " ") + " h")


# ============================================================
# PAGE PRINCIPALE
# ============================================================

def render_analyse_budgetaire_page():
    """Affiche la page d'Analyse Budgétaire"""
    st.title("Analyse Budgétaire")
    st.markdown(
        "Comparaison entre le **Budget Annuel** (prévision initiale), "
        "le **Budget Modifié** (après ajustements Besoin Jour) et "
        "le **Réalisé** (facturation effective)."
    )

    # Sélection de l'année
    bs = st.session_state.get('budget_state', {})
    default_year = bs.get('year', dt.date.today().year)

    year = st.number_input(
        "Année d'analyse :",
        value=default_year,
        min_value=2023,
        max_value=2050,
        key="analyse_budget_year"
    )

    # === Filtre optionnel de visualisation d'une facture mensuelle (sans impact) ===
    with st.expander("🔎 Visualiser une facture mensuelle (optionnel, n'affecte pas les calculs)"):
        col_m1, col_m2 = st.columns([2, 1])
        with col_m1:
            month_view = st.selectbox(
                "Mois à afficher",
                options=list(range(1, 13)),
                format_func=lambda m: f"{m:02d} - {calendar.month_name[m]}",
                key="ab_invoice_view_month",
            )
        with col_m2:
            if st.button("Afficher la facture", key="ab_invoice_view_btn"):
                _view_single_invoice(int(year), int(month_view), Path(FACTU_AT_DIR))

    # Vérifier que le budget existe pour cette année
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

    # =================== Extraction des données Budget Annuel ===================

    calendar_df = bs.get('calendar_df', pd.DataFrame())
    totals_annuel = bs.get('totals', {})
    heures_annuel = totals_annuel.get('heures_annuel', 0.0)
    cout_annuel = totals_annuel.get('cout_annuel', 0.0)

    # =================== Extraction des données Budget Modifié ===================

    heures_modifie = budget_modifie.get('heures_total', 0.0)
    cout_modifie = budget_modifie.get('cout_total', 0.0)

    # =================== Extraction des données Réalisé ===================

    heures_realise = 0.0
    cout_realise = 0.0

    if not df_factu.empty:
        heures_realise = df_factu['Heures_Total'].sum()

        # Calculer le coût réalisé en utilisant le tarif AT
        tarif_at = 0.0
        personnel_type_at = st.session_state.get('cost_mapping', {}).get("AT")
        if personnel_type_at:
            personnel_df = st.session_state.get('personnel', pd.DataFrame())
            if not personnel_df.empty:
                row_tarif = personnel_df[personnel_df['Type'] == personnel_type_at]
                if not row_tarif.empty:
                    tarif_at = float(row_tarif['Coût Horaire'].iloc[0])

        cout_realise = heures_realise * tarif_at

    # =================== Calcul des écarts ===================

    # Écarts Modifié vs Annuel
    ecart_heures_mod_ann = heures_modifie - heures_annuel
    ecart_heures_mod_ann_pct = (ecart_heures_mod_ann / heures_annuel * 100) if heures_annuel != 0 else 0
    ecart_cout_mod_ann = cout_modifie - cout_annuel
    ecart_cout_mod_ann_pct = (ecart_cout_mod_ann / cout_annuel * 100) if cout_annuel != 0 else 0

    # Écarts Réalisé vs Modifié
    ecart_heures_real_mod = heures_realise - heures_modifie
    ecart_heures_real_mod_pct = (ecart_heures_real_mod / heures_modifie * 100) if heures_modifie != 0 else 0
    ecart_cout_real_mod = cout_realise - cout_modifie
    ecart_cout_real_mod_pct = (ecart_cout_real_mod / cout_modifie * 100) if cout_modifie != 0 else 0

    # =================== Affichage : Synthèse CHF ===================

    st.markdown("---")
    st.subheader(f"📊 Synthèse {year} - Coûts (CHF)")

    col1, col2, col3 = st.columns(3)

    with col1:
        st.markdown(
            f"""<div class="kpi-card kpi-blue">
            <div class="label">Budget Annuel</div>
            <div class="value">{cout_annuel:,.0f} CHF</div>
            <div class="delta">Prévision initiale</div>
            </div>""",
            unsafe_allow_html=True
        )

    with col2:
        ecart_color = "kpi-green" if ecart_cout_mod_ann <= 0 else "kpi-amber"
        ecart_symbol = "▼" if ecart_cout_mod_ann < 0 else "▲"
        st.markdown(
            f"""<div class="kpi-card {ecart_color}">
            <div class="label">Budget Modifié</div>
            <div class="value">{cout_modifie:,.0f} CHF</div>
            <div class="delta">{ecart_symbol} {abs(ecart_cout_mod_ann):,.0f} CHF ({ecart_cout_mod_ann_pct:+.1f}%)</div>
            </div>""",
            unsafe_allow_html=True
        )

    with col3:
        ecart_color_real = "kpi-green" if ecart_cout_real_mod <= 0 else "kpi-red"
        ecart_symbol_real = "▼" if ecart_cout_real_mod < 0 else "▲"

        if df_factu.empty:
            st.markdown(
                f"""<div class="kpi-card kpi-amber">
                <div class="label">Réalisé</div>
                <div class="value">— CHF</div>
                <div class="delta">Aucune donnée de facturation pour {year}</div>
                </div>""",
                unsafe_allow_html=True
            )
        else:
            st.markdown(
                f"""<div class="kpi-card {ecart_color_real}">
                <div class="label">Réalisé</div>
                <div class="value">{cout_realise:,.0f} CHF</div>
                <div class="delta">{ecart_symbol_real} {abs(ecart_cout_real_mod):,.0f} CHF ({ecart_cout_real_mod_pct:+.1f}%)</div>
                </div>""",
                unsafe_allow_html=True
            )

    # =================== Affichage : Synthèse Heures ===================

    st.markdown("---")
    st.subheader(f"⏱️ Synthèse {year} - Heures")

    col1, col2, col3 = st.columns(3)

    with col1:
        st.markdown(
            f"""<div class="kpi-card kpi-blue">
            <div class="label">Budget Annuel</div>
            <div class="value">{heures_annuel:,.0f} h</div>
            <div class="delta">Prévision initiale</div>
            </div>""",
            unsafe_allow_html=True
        )

    with col2:
        ecart_color = "kpi-green" if ecart_heures_mod_ann <= 0 else "kpi-amber"
        ecart_symbol = "▼" if ecart_heures_mod_ann < 0 else "▲"
        st.markdown(
            f"""<div class="kpi-card {ecart_color}">
            <div class="label">Budget Modifié</div>
            <div class="value">{heures_modifie:,.0f} h</div>
            <div class="delta">{ecart_symbol} {abs(ecart_heures_mod_ann):,.0f} h ({ecart_heures_mod_ann_pct:+.1f}%)</div>
            </div>""",
            unsafe_allow_html=True
        )

    with col3:
        ecart_color_real = "kpi-green" if ecart_heures_real_mod <= 0 else "kpi-red"
        ecart_symbol_real = "▼" if ecart_heures_real_mod < 0 else "▲"

        if df_factu.empty:
            st.markdown(
                f"""<div class="kpi-card kpi-amber">
                <div class="label">Réalisé</div>
                <div class="value">— h</div>
                <div class="delta">Aucune donnée de facturation pour {year}</div>
                </div>""",
                unsafe_allow_html=True
            )
        else:
            st.markdown(
                f"""<div class="kpi-card {ecart_color_real}">
                <div class="label">Réalisé</div>
                <div class="value">{heures_realise:,.0f} h</div>
                <div class="delta">{ecart_symbol_real} {abs(ecart_heures_real_mod):,.0f} h ({ecart_heures_real_mod_pct:+.1f}%)</div>
                </div>""",
                unsafe_allow_html=True
            )

    # =================== Affichage : Courbes Cumulées ===================

    st.markdown("---")
    st.subheader(f"📈 Évolution Cumulée {year}")

    # Préparer les données mensuelles
    calendar_with_modif = budget_modifie.get('calendar_df', pd.DataFrame())

    if not calendar_with_modif.empty:
        try:
            # S'assurer que Date est au bon format
            calendar_with_modif['Date'] = pd.to_datetime(calendar_with_modif['Date'])
            calendar_with_modif['Mois'] = calendar_with_modif['Date'].dt.to_period('M')

            # Récupérer aussi le calendar_df ORIGINAL (Budget Annuel non modifié)
            calendar_annuel = bs.get('calendar_df', pd.DataFrame()).copy()
            calendar_annuel['Date'] = pd.to_datetime(calendar_annuel['Date'])
            calendar_annuel['Mois'] = calendar_annuel['Date'].dt.to_period('M')

            # Agréger par mois - Budget Annuel (original, sans ajustements)
            monthly_annuel = calendar_annuel.groupby('Mois').agg({
                'Heures_Total_Jour': 'sum',
                'Coût_Total_Jour': 'sum'
            }).reset_index()
            monthly_annuel.rename(columns={
                'Heures_Total_Jour': 'Heures_Annuel',
                'Coût_Total_Jour': 'Cout_Annuel'
            }, inplace=True)

            # Agréger par mois - Budget Modifié (avec ajustements)
            monthly_modifie = calendar_with_modif.groupby('Mois').agg({
                'Heures_Total_Jour': 'sum',
                'Coût_Total_Jour': 'sum'
            }).reset_index()
            monthly_modifie.rename(columns={
                'Heures_Total_Jour': 'Heures_Modifie',
                'Coût_Total_Jour': 'Cout_Modifie'
            }, inplace=True)

            # Fusionner Annuel et Modifié
            monthly_budget = monthly_annuel.merge(monthly_modifie, on='Mois', how='outer')

            monthly_budget['Mois_str'] = monthly_budget['Mois'].astype(str)
            monthly_budget['Mois_dt'] = monthly_budget['Mois'].apply(lambda x: x.to_timestamp())

            # Calcul cumulé
            monthly_budget['Heures_Annuel_Cumul'] = monthly_budget['Heures_Annuel'].cumsum()
            monthly_budget['Cout_Annuel_Cumul'] = monthly_budget['Cout_Annuel'].cumsum()
            monthly_budget['Heures_Modifie_Cumul'] = monthly_budget['Heures_Modifie'].cumsum()
            monthly_budget['Cout_Modifie_Cumul'] = monthly_budget['Cout_Modifie'].cumsum()

            # Agréger les données de facturation par mois si disponibles
            if not df_factu.empty:
                df_factu['Mois'] = pd.to_datetime(df_factu['Date']).dt.to_period('M')
                monthly_factu = df_factu.groupby('Mois').agg({
                    'Heures_Total': 'sum'
                }).reset_index()
                monthly_factu['Mois_str'] = monthly_factu['Mois'].astype(str)
                monthly_factu['Mois_dt'] = monthly_factu['Mois'].apply(lambda x: x.to_timestamp())
                monthly_factu['Heures_Realise_Cumul'] = monthly_factu['Heures_Total'].cumsum()

                # Calculer le coût réalisé cumulé
                tarif_at = 0.0
                personnel_type_at = st.session_state.get('cost_mapping', {}).get("AT")
                if personnel_type_at:
                    personnel_df = st.session_state.get('personnel', pd.DataFrame())
                    if not personnel_df.empty:
                        row_tarif = personnel_df[personnel_df['Type'] == personnel_type_at]
                        if not row_tarif.empty:
                            tarif_at = float(row_tarif['Coût Horaire'].iloc[0])

                monthly_factu['Cout_Realise'] = monthly_factu['Heures_Total'] * tarif_at
                monthly_factu['Cout_Realise_Cumul'] = monthly_factu['Cout_Realise'].cumsum()

                # Fusionner les données
                monthly_combined = monthly_budget.merge(
                    monthly_factu[['Mois_str', 'Heures_Realise_Cumul', 'Cout_Realise_Cumul']],
                    on='Mois_str',
                    how='left'
                )
            else:
                monthly_combined = monthly_budget.copy()
                monthly_combined['Heures_Realise_Cumul'] = None
                monthly_combined['Cout_Realise_Cumul'] = None

            # Préparer les données pour Altair (format long)
            # Heures
            df_heures_plot = pd.DataFrame({
                'Mois': monthly_combined['Mois_dt'].tolist() * 3,
                'Type': (
                    ['Budget Annuel'] * len(monthly_combined) +
                    ['Budget Modifié'] * len(monthly_combined) +
                    ['Réalisé'] * len(monthly_combined)
                ),
                'Heures_Cumul': (
                    monthly_combined['Heures_Annuel_Cumul'].tolist() +
                    monthly_combined['Heures_Modifie_Cumul'].tolist() +
                    monthly_combined['Heures_Realise_Cumul'].tolist()
                )
            })

            # Coûts
            df_cout_plot = pd.DataFrame({
                'Mois': monthly_combined['Mois_dt'].tolist() * 3,
                'Type': (
                    ['Budget Annuel'] * len(monthly_combined) +
                    ['Budget Modifié'] * len(monthly_combined) +
                    ['Réalisé'] * len(monthly_combined)
                ),
                'Cout_Cumul': (
                    monthly_combined['Cout_Annuel_Cumul'].tolist() +
                    monthly_combined['Cout_Modifie_Cumul'].tolist() +
                    monthly_combined['Cout_Realise_Cumul'].tolist()
                )
            })

            # Supprimer les lignes avec NaN pour le Réalisé
            df_heures_plot = df_heures_plot.dropna(subset=['Heures_Cumul'])
            df_cout_plot = df_cout_plot.dropna(subset=['Cout_Cumul'])

            # Graphiques
            tab_cout, tab_heures = st.tabs(["💰 Coûts Cumulés (CHF)", "⏱️ Heures Cumulées"])

            with tab_cout:
                if not df_cout_plot.empty:
                    chart_cout = alt.Chart(df_cout_plot).mark_line(
                        point=True, strokeWidth=3
                    ).encode(
                        x=alt.X('Mois:T', title='Mois', axis=alt.Axis(format='%b %Y')),
                        y=alt.Y('Cout_Cumul:Q', title='Coût Cumulé (CHF)'),
                        color=alt.Color(
                            'Type:N',
                            scale=alt.Scale(
                                domain=['Budget Annuel', 'Budget Modifié', 'Réalisé'],
                                range=['#0076aa', '#ffa500', '#dc143c']
                            ),
                            legend=alt.Legend(title='Type de Budget')
                        ),
                        tooltip=[
                            alt.Tooltip('Mois:T', title='Mois', format='%B %Y'),
                            alt.Tooltip('Type:N', title='Type'),
                            alt.Tooltip('Cout_Cumul:Q', title='Coût Cumulé', format=',.0f')
                        ]
                    ).properties(
                        height=400
                    ).interactive()

                    st.altair_chart(chart_cout, use_container_width=True)
                else:
                    st.info("Pas de données disponibles pour tracer la courbe des coûts.")

            with tab_heures:
                if not df_heures_plot.empty:
                    chart_heures = alt.Chart(df_heures_plot).mark_line(
                        point=True, strokeWidth=3
                    ).encode(
                        x=alt.X('Mois:T', title='Mois', axis=alt.Axis(format='%b %Y')),
                        y=alt.Y('Heures_Cumul:Q', title='Heures Cumulées'),
                        color=alt.Color(
                            'Type:N',
                            scale=alt.Scale(
                                domain=['Budget Annuel', 'Budget Modifié', 'Réalisé'],
                                range=['#0076aa', '#ffa500', '#dc143c']
                            ),
                            legend=alt.Legend(title='Type de Budget')
                        ),
                        tooltip=[
                            alt.Tooltip('Mois:T', title='Mois', format='%B %Y'),
                            alt.Tooltip('Type:N', title='Type'),
                            alt.Tooltip('Heures_Cumul:Q', title='Heures Cumulées', format=',.0f')
                        ]
                    ).properties(
                        height=400
                    ).interactive()

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
            # Préparer un tableau récapitulatif mensuel
            monthly_table = monthly_combined.copy()
            monthly_table['Mois'] = monthly_table['Mois_str']

            # Colonnes standard
            columns_to_show = {
                'Mois': 'Mois',
                'Heures_Annuel': 'Heures Annuel',
                'Heures_Modifie': 'Heures Modifié',
                'Cout_Annuel': 'Coût Annuel (CHF)',
                'Cout_Modifie': 'Coût Modifié (CHF)'
            }

            # Si réalisé présent (heures) → calcule coût réalisé via tarif AT
            if 'Heures_Total' in monthly_table.columns:
                if not df_factu.empty:
                    monthly_factu_raw = df_factu.groupby('Mois').agg({
                        'Heures_Total': 'sum'
                    }).reset_index()
                    monthly_factu_raw['Mois_str'] = monthly_factu_raw['Mois'].astype(str)

                    tarif_at = 0.0
                    personnel_type_at = st.session_state.get('cost_mapping', {}).get("AT")
                    if personnel_type_at:
                        personnel_df = st.session_state.get('personnel', pd.DataFrame())
                        if not personnel_df.empty:
                            row_tarif = personnel_df[personnel_df['Type'] == personnel_type_at]
                            if not row_tarif.empty:
                                tarif_at = float(row_tarif['Coût Horaire'].iloc[0])

                    monthly_factu_raw['Cout_Realise'] = monthly_factu_raw['Heures_Total'] * tarif_at

                    monthly_table = monthly_table.merge(
                        monthly_factu_raw[['Mois_str', 'Heures_Total', 'Cout_Realise']],
                        left_on='Mois',
                        right_on='Mois_str',
                        how='left'
                    )

                    columns_to_show['Heures_Total'] = 'Heures Réalisé'
                    columns_to_show['Cout_Realise'] = 'Coût Réalisé (CHF)'

            # DataFrame final
            df_monthly_display = monthly_table[list(columns_to_show.keys())].copy()
            df_monthly_display.columns = list(columns_to_show.values())

            # Config colonnes
            col_config = {
                'Mois': st.column_config.TextColumn('Mois'),
                'Heures Annuel': st.column_config.NumberColumn('Heures Annuel', format='%.0f h'),
                'Heures Modifié': st.column_config.NumberColumn('Heures Modifié', format='%.0f h'),
                'Coût Annuel (CHF)': st.column_config.NumberColumn('Coût Annuel', format='%.0f CHF'),
                'Coût Modifié (CHF)': st.column_config.NumberColumn('Coût Modifié', format='%.0f CHF')
            }

            if 'Heures Réalisé' in df_monthly_display.columns:
                col_config['Heures Réalisé'] = st.column_config.NumberColumn('Heures Réalisé', format='%.0f h')
                col_config['Coût Réalisé (CHF)'] = st.column_config.NumberColumn('Coût Réalisé', format='%.0f CHF')

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

    # =================== Notes & Informations ===================

    with st.expander("ℹ️ Informations sur l'Analyse Budgétaire"):
        st.markdown("""
        ### Définitions

        - **Budget Annuel** : Budget prévisionnel initial basé sur les jours-types et le calendrier des saisons.

        - **Budget Modifié** : Budget ajusté intégrant tous les ajustements ponctuels définis dans 
          la page "Besoin Jour" (événements, modifications temporaires, etc.).

        - **Réalisé** : Heures et coûts effectifs basés sur les fichiers de facturation 
          (dossier `input_files/facturation/`).

        ### Calcul des écarts

        - **Modifié vs Annuel** : Mesure l'impact des ajustements ponctuels sur le budget initial.

        - **Réalisé vs Modifié** : Mesure l'écart entre ce qui était prévu (après ajustements) 
          et ce qui a été effectivement réalisé.

        ### Sources de données

        - **Budget Annuel** : Généré dans la page "Budget Annuel"
        - **Ajustements** : Définis dans la page "Besoin Jour"
        - **Facturation** : Fichiers Excel dans `input_files/facturation/`
          (format: `Facturation Lot A MM.YYYY.xlsx`)
        """)


# (Optionnel) Lancer cette page seule
if __name__ == "__main__":
    render_analyse_budgetaire_page()
