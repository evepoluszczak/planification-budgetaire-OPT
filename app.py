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
from utils.async_loader import start_pax_loading, check_pax_loading_status, get_pax_loading_info
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

# =================== Initialisation du chargement PAX ===================
# Initialiser l'état du chargement PAX si nécessaire
if 'pax_loading_status' not in st.session_state:
    st.session_state.pax_loading_status = 'idle'

# Note: Le chargement automatique PAX a été désactivé au profit du chargement manuel
# via le bouton dans la sidebar pour ne pas bloquer l'application au démarrage

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

        # =================== Section Chargement PAX ===================
        st.subheader("Données PAX")

        # Vérifier l'état du chargement
        loading_status = check_pax_loading_status()
        pax_info = get_pax_loading_info()

        if loading_status == 'idle':
            # Bouton pour lancer le chargement
            if st.button("🔄 Lancer le chargement PAX", use_container_width=True, type="secondary"):
                if PAX_DATA_FILE_PATH.exists():
                    start_pax_loading(PAX_DATA_FILE_PATH)
                    st.toast("Chargement PAX démarré en arrière-plan...", icon="🔄")
                    st.rerun()
                else:
                    st.error(f"Fichier non trouvé : {PAX_DATA_FILE_PATH}")

        elif loading_status == 'loading':
            # Afficher l'état de chargement avec barre de progression
            elapsed = pax_info.get('elapsed', 0)
            st.info(f"⏳ Chargement en cours... ({elapsed:.1f}s)")

            # Barre de progression indéterminée
            progress_bar = st.progress(0)
            # Animation de la barre (simule un chargement)
            import time
            progress_value = int((elapsed * 10) % 100)
            progress_bar.progress(progress_value)

            # Auto-refresh toutes les 0.5 secondes
            time.sleep(0.5)
            st.rerun()

        elif loading_status == 'success':
            # Afficher le succès
            st.success("✅ Données PAX chargées")

            # Afficher les statistiques
            if pax_info.get('forecast_status') == 'loaded':
                min_date = st.session_state.get('pax_forecast_min_date')
                max_date = st.session_state.get('pax_forecast_max_date')
                st.caption(f"📊 Forecast : {min_date} → {max_date}")

            if pax_info.get('historical_status') == 'loaded':
                min_date = st.session_state.get('pax_historical_min_date')
                max_date = st.session_state.get('pax_historical_max_date')
                st.caption(f"📈 Historique : {min_date} → {max_date}")

            # Bouton pour recharger
            if st.button("🔄 Recharger", use_container_width=True, type="secondary"):
                # Réinitialiser l'état
                st.session_state.pax_loading_status = 'idle'
                st.session_state.pop('pax_data_status', None)
                st.toast("Prêt à recharger les données", icon="🔄")
                st.rerun()

        elif loading_status == 'error':
            # Afficher l'erreur
            error_msg = pax_info.get('error', 'Erreur inconnue')
            st.error(f"❌ Erreur de chargement")
            st.caption(f"Détails : {error_msg}")

            # Bouton pour réessayer
            if st.button("🔄 Réessayer", use_container_width=True, type="secondary"):
                st.session_state.pax_loading_status = 'idle'
                st.rerun()

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
