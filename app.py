"""
Application Streamlit - Planificateur Budgétaire OPT
Version refactorisée et modulaire
"""
import datetime as dt
import re
import pandas as pd
import streamlit as st

# Imports des modules custom
from config.settings import configure_streamlit, render_gva_header
from config.constants import RULES_BESOIN_JOUR_PATH, PAX_DATA_FILE_PATH, FACTU_AT_DIR
from models.session_state import initialize_session_state_2026
from core.budget import generate_budget_state
from core.data_loader import load_pax_data
from core.rules import load_rules_from_json
from utils.export_import import export_full_state, load_data_from_excel
from ui.components import show_help_dialog, planning_editor_ui

# =================== Configuration initiale ===================
configure_streamlit()

# =================== Initialisation de l'état de session ===================
if 'data_loaded' not in st.session_state:
    st.session_state.data_loaded = False
if 'besoin_jour_ops' not in st.session_state:
    st.session_state.besoin_jour_ops = load_rules_from_json(RULES_BESOIN_JOUR_PATH)
if 'budget_state' not in st.session_state:
    st.session_state.budget_state = {}
if 'show_help_dialog' not in st.session_state:
    st.session_state.show_help_dialog = False

# =================== Chargement automatique des données PAX ===================
if st.session_state.data_loaded and 'pax_data_status' not in st.session_state:
    full_pax_data, overall_min_date, overall_max_date = load_pax_data(
        PAX_DATA_FILE_PATH, "Passagers"
    )

    st.session_state.pax_data_status = "attempted"

    if not full_pax_data.empty:
        st.session_state.pax_overall_min_date = overall_min_date
        st.session_state.pax_overall_max_date = overall_max_date

        today = dt.date.today()
        historical_data = full_pax_data[full_pax_data.index.date < today].copy()
        forecast_data = full_pax_data[full_pax_data.index.date >= today].copy()

        if not historical_data.empty:
            st.session_state.pax_historical_data = historical_data
            st.session_state.pax_historical_min_date = historical_data.index.min().date()
            st.session_state.pax_historical_max_date = historical_data.index.max().date()
            st.session_state.pax_historical_status = "loaded"
        else:
            st.session_state.pax_historical_status = "no_data_found"

        if not forecast_data.empty:
            st.session_state.pax_forecast_data = forecast_data
            st.session_state.pax_forecast_min_date = forecast_data.index.min().date()
            st.session_state.pax_forecast_max_date = forecast_data.index.max().date()
            st.session_state.pax_forecast_status = "loaded"
        else:
            st.session_state.pax_forecast_status = "no_data_found"
    else:
        st.session_state.pax_historical_status = "not_loaded"
        st.session_state.pax_forecast_status = "not_loaded"

# =================== Affichage principal ===================
render_gva_header()

# Gestion de la dialog d'aide
if st.session_state.show_help_dialog:
    show_help_dialog()
    st.session_state.show_help_dialog = False

# =================== Écran d'accueil (si données non chargées) ===================
if not st.session_state.data_loaded:
    if st.button("Ouvrir le Mode d'emploi"):
        st.session_state.show_help_dialog = True
        st.rerun()

    st.header("Choisissez une option pour démarrer")
    col1, col2 = st.columns(2)

    with col1:
        with st.container(border=True):
            st.subheader("Démarrer avec la base 2026")
            st.markdown("Charge les données de référence de 2026 pour commencer une nouvelle planification.")
            if st.button("Démarrer avec la base 2026", use_container_width=True, type="primary"):
                try:
                    initialize_session_state_2026()
                    st.success("Données de base 2026 chargées.")
                except Exception as e:
                    st.error(f"Erreur lors de l'initialisation des données 2026: {e}")

    with col2:
        with st.container(border=True):
            st.subheader("Charger un scénario existant")
            st.markdown("Chargez un fichier `.xlsx` que vous avez précédemment sauvegardé.")
            uploaded_file = st.file_uploader(
                "Choisissez un fichier Excel", type="xlsx", label_visibility="collapsed"
            )
            if uploaded_file is not None:
                success, message = load_data_from_excel(uploaded_file)
                if success:
                    st.success(message)
                    st.rerun()
                else:
                    st.error(message)

else:
    # =================== Interface principale (données chargées) ===================

    # Sidebar : Navigation et Export
    with st.sidebar:
        st.title("Navigation")

        page = st.radio(
            "Navigation",
            ["Configuration", "Planification", "Budget Annuel", "Besoin Jour",
             "Comparaison Historique", "Simulateur Objectif"],
            label_visibility="hidden"
        )

        # Bouton Mode d'emploi
        if st.button("❔ Mode d'emploi", use_container_width=True):
            show_help_dialog()

        st.divider()
        st.subheader("Exporter le Scénario")

        # Formulaire d'export
        with st.form("export_form"):
            default_filename = f"scenario_planificateur_{dt.date.today()}"
            file_label = st.text_input(
                "Nom du fichier (sans .xlsx) :",
                value=st.session_state.get("file_label_export", default_filename),
                key="file_label_export"
            )
            submitted = st.form_submit_button("Préparer le Fichier", use_container_width=True, type="primary")

            if submitted:
                clean_label = re.sub(r'[^\w\-]+', '_', file_label)
                filename = f"{clean_label}.xlsx"
                try:
                    st.session_state["export_bytes"] = export_full_state()
                    st.session_state["export_filename"] = filename
                    st.success(f"Fichier '{filename}' prêt. Cliquez sur 'Télécharger'.")
                except Exception as e:
                    st.error(f"Erreur lors de la préparation de l'export: {e}")
                    st.session_state.pop("export_bytes", None)
                    st.session_state.pop("export_filename", None)

        # Bouton de téléchargement
        if "export_bytes" in st.session_state and "export_filename" in st.session_state:
            st.download_button(
                label="Télécharger le Scénario (.xlsx)",
                data=st.session_state["export_bytes"],
                file_name=st.session_state["export_filename"],
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                use_container_width=True,
                key="download_button"
            )

    # =================== Affichage des pages ===================

    # Les pages sont importées depuis des modules séparés ou définies inline
    # Pour simplifier, on garde certaines pages inline mais bien structurées

    if page == "Configuration":
        from ui.pages.configuration import render_configuration_page
        render_configuration_page()

    elif page == "Planification":
        st.title("Planification des Jours-Types")
        st.markdown("Définissez les grilles de présence pour chaque jour-type.")

        if 'perimetres' not in st.session_state or not st.session_state.perimetres:
            st.error("Les périmètres ne sont pas définis. Allez à 'Configuration'.")
        elif 'planning_data' not in st.session_state:
            st.error("Les données de planification ne sont pas initialisées.")
        else:
            category_tabs = sorted(list(st.session_state.perimetres.keys()))
            if category_tabs:
                plan_tabs = st.tabs(category_tabs)
                for i, cat_key in enumerate(category_tabs):
                    with plan_tabs[i]:
                        with st.container():
                            planning_editor_ui(cat_key, cat_key)
            else:
                st.warning("Aucune catégorie de périmètre définie.")

    elif page == "Budget Annuel":
        from ui.pages.budget_annuel import render_budget_annuel_page
        render_budget_annuel_page()

    elif page == "Besoin Jour":
        from ui.pages.besoin_jour import render_besoin_jour_page
        render_besoin_jour_page()

    elif page == "Comparaison Historique":
        from ui.pages.comparaison_historique import render_comparaison_historique_page
        render_comparaison_historique_page()

    elif page == "Simulateur Objectif":
        from ui.pages.simulateur_objectif import render_simulateur_objectif_page
        render_simulateur_objectif_page()
