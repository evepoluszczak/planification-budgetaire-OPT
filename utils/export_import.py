"""
Fonctions pour l'export et l'import de données Excel
"""
import io
import pandas as pd
import streamlit as st
from utils.helpers import sync_all_planning_grids_from_widgets
from utils.date_utils import _date_to_str, _str_to_date
from core.rules import save_rules_to_json, load_rules_from_json
from core.budget import generate_budget_state
from config.constants import RULES_BESOIN_JOUR_PATH


def _sync_budget_annuel_state():
    """Synchronise l'état du budget annuel (convertit les dates)"""
    if 'adjusted_saisons' in st.session_state:
        df = st.session_state.adjusted_saisons
        if isinstance(df, pd.DataFrame) and not df.empty:
            if 'Date Début' in df.columns:
                df['Date Début'] = pd.to_datetime(df['Date Début']).dt.date
            if 'Date Fin' in df.columns:
                df['Date Fin'] = pd.to_datetime(df['Date Fin']).dt.date
            st.session_state.adjusted_saisons = df

    # Synchroniser les tables Formation/Formateurs depuis les widgets si disponibles
    if 'editor_formation_at' in st.session_state:
        # Le widget data_editor stocke son état dans session_state avec sa clé
        widget_data = st.session_state.get('editor_formation_at')
        if widget_data is not None and isinstance(widget_data, pd.DataFrame):
            st.session_state.budget_formation_at = widget_data.copy()

    if 'editor_formateurs_at' in st.session_state:
        widget_data = st.session_state.get('editor_formateurs_at')
        if widget_data is not None and isinstance(widget_data, pd.DataFrame):
            st.session_state.budget_formateurs_at = widget_data.copy()


def export_full_state():
    """Exporte l'état complet de l'application vers un fichier Excel"""
    sync_all_planning_grids_from_widgets()
    _sync_budget_annuel_state()

    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        # Feuilles de base
        st.session_state.personnel.to_excel(writer, sheet_name='Personnel_Tarifs', index=False)
        st.session_state.saisons.to_excel(writer, sheet_name='Saisons', index=False)

        # Saisons ajustées
        if 'adjusted_saisons' in st.session_state and \
           isinstance(st.session_state.adjusted_saisons, pd.DataFrame) and \
           not st.session_state.adjusted_saisons.empty:
            st.session_state.adjusted_saisons.to_excel(
                writer, sheet_name='Saisons_Ajustees', index=False
            )

        # Périmètres
        perimetres_list = [
            {'Categorie': cat, 'Perimetre': p}
            for cat, items in st.session_state.perimetres.items()
            for p in items
        ]
        pd.DataFrame(perimetres_list).to_excel(writer, sheet_name='Perimetres', index=False)

        # Mapping des coûts
        if 'cost_mapping' in st.session_state and st.session_state.cost_mapping:
            pd.DataFrame([
                {'Categorie': k, 'Type_Personnel': v}
                for k, v in st.session_state.cost_mapping.items()
            ]).to_excel(writer, sheet_name='Cost_Mapping', index=False)

        # Grilles de planification
        for category, day_types_dict in st.session_state.planning_data.items():
            for day_type_name, grid_df in day_types_dict.items():
                sheet_name = f"JT_{category}_{day_type_name}"
                if grid_df.index.name is None:
                    grid_df.index.name = "Perimetre"
                df_to_write = grid_df.reset_index()
                df_to_write.to_excel(writer, sheet_name=sheet_name, index=False)

        # Règles Besoin Jour
        if 'besoin_jour_ops' in st.session_state and st.session_state.besoin_jour_ops:
            rules_export_list = []
            for op in st.session_state.besoin_jour_ops:
                op_export = op.copy()
                op_export['start'] = _date_to_str(op.get('start'))
                op_export['end'] = _date_to_str(op.get('end'))
                op_export['jours'] = ",".join(op.get('jours', []))
                op_export['saisons'] = ",".join(op.get('saisons', []))
                op_export['rows'] = ",".join(op.get('rows', []))
                rules_export_list.append(op_export)

            rules_df = pd.DataFrame(rules_export_list)
            column_order = ['category', 'start', 'end', 'jours', 'saisons', 'rows',
                           'start_col', 'end_col', 'value']
            rules_df = rules_df.reindex(columns=column_order, fill_value="")
            rules_df.to_excel(writer, sheet_name='Besoin_Jour_Regles', index=False)

        # Tables Formation/Doublure AT et Shift AT Formateurs
        if 'budget_formation_at' in st.session_state and \
           isinstance(st.session_state.budget_formation_at, pd.DataFrame) and \
           not st.session_state.budget_formation_at.empty:
            df_formation_export = st.session_state.budget_formation_at.reset_index(drop=True)
            df_formation_export.to_excel(
                writer, sheet_name='Budget_Formation_AT', index=False
            )
            st.info(f"✓ {len(df_formation_export)} lignes exportées pour Formation/Doublure AT")

        if 'budget_formateurs_at' in st.session_state and \
           isinstance(st.session_state.budget_formateurs_at, pd.DataFrame) and \
           not st.session_state.budget_formateurs_at.empty:
            df_formateurs_export = st.session_state.budget_formateurs_at.reset_index(drop=True)
            df_formateurs_export.to_excel(
                writer, sheet_name='Budget_Formateurs_AT', index=False
            )
            st.info(f"✓ {len(df_formateurs_export)} lignes exportées pour Shift AT Formateurs")

    return output.getvalue()


def load_data_from_excel(uploaded_file):
    """Charge les données depuis un fichier Excel"""
    try:
        xls = pd.ExcelFile(uploaded_file)

        # Personnel
        st.session_state.personnel = pd.read_excel(xls, 'Personnel_Tarifs')

        # Saisons de référence
        saisons_df = pd.read_excel(xls, 'Saisons')
        saisons_df['Date Début'] = pd.to_datetime(saisons_df['Date Début']).dt.date
        saisons_df['Date Fin'] = pd.to_datetime(saisons_df['Date Fin']).dt.date
        st.session_state.saisons = saisons_df
        st.session_state.reference_year_saisons = saisons_df['Date Début'].iloc[0].year

        # Périmètres
        perimetres_df = pd.read_excel(xls, 'Perimetres')
        st.session_state.perimetres = (
            perimetres_df.groupby('Categorie')['Perimetre'].apply(list).to_dict()
        )

        # Planification
        st.session_state.planning_data = {
            cat: {} for cat in st.session_state.perimetres.keys()
        }
        jt_sheets = [s for s in xls.sheet_names if s.startswith('JT_')]

        from config.constants import TIME_SLOTS
        for sheet_name in jt_sheets:
            try:
                parts = sheet_name.split('_')
                if len(parts) >= 3:
                    category = parts[1]
                    day_type_name = "_".join(parts[2:])
                    df = pd.read_excel(xls, sheet_name)

                    if 'Perimetre' in df.columns:
                        df = df.set_index('Perimetre')
                        if category in st.session_state.planning_data:
                            df = df.reindex(columns=TIME_SLOTS, fill_value=0)
                            st.session_state.planning_data[category][day_type_name] = (
                                df.fillna(0).astype(int).clip(0, 1)
                            )
                    else:
                        st.warning(
                            f"La feuille '{sheet_name}' n'a pas de colonne 'Perimetre'. "
                            "Elle est ignorée."
                        )
                else:
                    st.warning(f"Nom de feuille invalide ignoré: '{sheet_name}'")
            except Exception as e_jt:
                st.warning(f"Erreur lors de la lecture de '{sheet_name}': {e_jt}")

        # Cost Mapping
        if 'Cost_Mapping' in xls.sheet_names:
            cm = pd.read_excel(xls, 'Cost_Mapping')
            st.session_state.cost_mapping = {
                row['Categorie']: row['Type_Personnel']
                for _, row in cm.iterrows()
            }
        else:
            st.session_state.cost_mapping = {}

        # Saisons ajustées
        if 'Saisons_Ajustees' in xls.sheet_names:
            adj = pd.read_excel(xls, 'Saisons_Ajustees')
            adj['Date Début'] = pd.to_datetime(adj['Date Début']).dt.date
            adj['Date Fin'] = pd.to_datetime(adj['Date Fin']).dt.date
            st.session_state.adjusted_saisons = adj
            st.session_state.adjusted_saisons_year = adj['Date Début'].iloc[0].year
        else:
            if 'adjusted_saisons' in st.session_state:
                del st.session_state['adjusted_saisons']
            if 'adjusted_saisons_year' in st.session_state:
                del st.session_state['adjusted_saisons_year']

        # Règles Besoin Jour
        if 'Besoin_Jour_Regles' in xls.sheet_names:
            rules_df = pd.read_excel(xls, 'Besoin_Jour_Regles')
            loaded_rules = []
            rules_df = rules_df.fillna("")

            for _, row in rules_df.iterrows():
                try:
                    op = row.to_dict()
                    op['start'] = _str_to_date(op.get('start'))
                    op['end'] = _str_to_date(op.get('end'))
                    op['jours'] = [
                        j.strip() for j in str(op.get('jours', '')).split(',') if j.strip()
                    ]
                    op['saisons'] = [
                        s.strip() for s in str(op.get('saisons', '')).split(',') if s.strip()
                    ]
                    op['rows'] = [
                        r.strip() for r in str(op.get('rows', '')).split(',') if r.strip()
                    ]

                    try:
                        op['value'] = int(op.get('value', 0))
                    except (ValueError, TypeError):
                        op['value'] = 0

                    # Validation
                    if op['start'] and op['end'] and op['start'] <= op['end'] and \
                       op['rows'] and op['start_col'] and op['end_col']:
                        loaded_rules.append(op)
                    else:
                        st.warning(f"Règle Besoin Jour ignorée (invalide) : {op}")
                except Exception as e_rule:
                    st.warning(f"Erreur lecture règle Besoin Jour: {e_rule}")

            st.session_state.besoin_jour_ops = loaded_rules
            st.info(f"{len(loaded_rules)} règles Besoin Jour chargées.")
        else:
            # Fallback: charger depuis JSON
            st.session_state.besoin_jour_ops = load_rules_from_json(RULES_BESOIN_JOUR_PATH)
            st.info("Règles chargées depuis JSON local.")

        # Tables Formation/Doublure AT et Shift AT Formateurs
        if 'Budget_Formation_AT' in xls.sheet_names:
            formation_df = pd.read_excel(xls, 'Budget_Formation_AT')
            # Normaliser les types de données
            if 'Effectif (pers.)' in formation_df.columns:
                formation_df['Effectif (pers.)'] = pd.to_numeric(
                    formation_df['Effectif (pers.)'], errors='coerce'
                ).fillna(0).astype(int)
            if 'Heures' in formation_df.columns:
                formation_df['Heures'] = pd.to_numeric(
                    formation_df['Heures'], errors='coerce'
                ).fillna(0.0)
            if 'Nbre de shifts' in formation_df.columns:
                formation_df['Nbre de shifts'] = pd.to_numeric(
                    formation_df['Nbre de shifts'], errors='coerce'
                ).fillna(0).astype(int)
            st.session_state.budget_formation_at = formation_df
            st.info(f"Table Formation/Doublure AT chargée ({len(formation_df)} lignes).")

        if 'Budget_Formateurs_AT' in xls.sheet_names:
            formateurs_df = pd.read_excel(xls, 'Budget_Formateurs_AT')
            # Normaliser les types de données
            if 'Effectif (pers.)' in formateurs_df.columns:
                formateurs_df['Effectif (pers.)'] = pd.to_numeric(
                    formateurs_df['Effectif (pers.)'], errors='coerce'
                ).fillna(0).astype(int)
            if 'Heures' in formateurs_df.columns:
                formateurs_df['Heures'] = pd.to_numeric(
                    formateurs_df['Heures'], errors='coerce'
                ).fillna(0.0)
            if 'Nbre de shifts' in formateurs_df.columns:
                formateurs_df['Nbre de shifts'] = pd.to_numeric(
                    formateurs_df['Nbre de shifts'], errors='coerce'
                ).fillna(0).astype(int)
            st.session_state.budget_formateurs_at = formateurs_df
            st.info(f"Table Shift AT Formateurs chargée ({len(formateurs_df)} lignes).")

        # Générer le budget automatiquement
        try:
            year_to_generate = int(
                st.session_state.get('adjusted_saisons_year',
                                    st.session_state.saisons['Date Début'].iloc[0].year)
            )
            generate_budget_state(year_to_generate)
            st.success(f"Budget {year_to_generate} généré automatiquement.")
        except Exception as _e:
            st.warning(f"Budget non généré automatiquement après chargement : {_e}")

        st.session_state.data_loaded = True
        return True, "Fichier chargé avec succès !"

    except Exception as e:
        # Nettoyer l'état en cas d'erreur
        st.session_state.data_loaded = False
        for key in ['personnel', 'saisons', 'perimetres', 'planning_data',
                   'cost_mapping', 'adjusted_saisons', 'besoin_jour_ops', 'budget_state']:
            st.session_state.pop(key, None)
        return False, f"Erreur critique lors de la lecture du fichier Excel : {e}"
