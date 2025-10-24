import datetime as dt
import re
import pandas as pd
import streamlit as st

# Imports des modules custom
from config.settings import configure_streamlit, render_gva_header
from config.constants import (RULES_BESOIN_JOUR_PATH, PAX_DATA_FILE_PATH, FACTU_AT_DIR,
                              PAX_FORECAST_FILE_PATH, PAX_HISTORICAL_FILE_PATH)
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
            [ "Configuration", "Planification", "Budget Annuel", "Besoin Jour",
             "Comparaison Historique", "Simulateur Objectif", "Analyse Budgétaire"],
            label_visibility="hidden"
        )

        # Bouton Mode d'emploi
        if st.button("❔ Mode d'emploi", use_container_width=True):
            show_help_dialog()

        st.divider()

        # =================== Section Chargement PAX ===================
        st.subheader("Données PAX")

        # Fragment pour le polling auto-refresh (ne bloque pas l'app)
        @st.fragment(run_every="0.5s")
        def pax_loading_status_fragment():
            """Fragment qui se rafraîchit automatiquement pour surveiller le chargement"""
            loading_status = check_pax_loading_status()
            pax_info = get_pax_loading_info()

            if loading_status == 'loading':
                # Afficher l'état de chargement avec barre de progression
                elapsed = pax_info.get('elapsed', 0)
                progress = pax_info.get('progress', {})
                current_file = progress.get('current_file', '...')
                percent = progress.get('percent', 0)

                st.info(f"⏳ Chargement {current_file}... ({elapsed:.1f}s)")
                st.progress(percent / 100 if percent > 0 else 0)

            elif loading_status == 'success':
                st.success("✅ Données PAX chargées")

            elif loading_status == 'partial':
                st.warning("⚠️ Chargement partiel")
                if pax_info.get('error'):
                    with st.expander("Détails des erreurs"):
                        st.error(pax_info.get('error'))

            elif loading_status == 'error':
                error_msg = pax_info.get('error', 'Erreur inconnue')
            
                # Drapeau de masquage
                if "pax_error_dismissed" not in st.session_state:
                    st.session_state.pax_error_dismissed = False
            
                if not st.session_state.pax_error_dismissed:
                    with st.container(border=True):
                        st.error("❌ Erreur de chargement")
                        st.caption(f"Détails : {error_msg}")
                        cols = st.columns([1,1])
                        with cols[0]:
                            if st.button("Masquer", key="hide_pax_error_btn"):
                                st.session_state.pax_error_dismissed = True
                        with cols[1]:
                            if st.button("Voir tracebacks", key="show_tracebacks_btn"):
                                tb = pax_info.get('tracebacks', {})
                                if tb:
                                    with st.expander("Traceback (debug)"):
                                        for k, v in tb.items():
                                            st.markdown(f"**{k}**")
                                            st.code(v or "—", language="python")
                else:
                    st.caption("Erreur de chargement masquée (cliquez Recharger pour réessayer).")


        # Afficher le fragment de polling
        pax_loading_status_fragment()

        # Afficher les informations de dates (toujours visible)
        pax_info = get_pax_loading_info()

        # Forecast
        if pax_info.get('forecast_status') == 'loaded':
            fc_min = pax_info.get('forecast_min')
            fc_max = pax_info.get('forecast_max')
            st.caption(f"📊 Forecast : {fc_min} → {fc_max}")
        else:
            st.caption(f"📊 Forecast : non chargé")

        # Historic
        if pax_info.get('historical_status') == 'loaded':
            hist_min = pax_info.get('historical_min')
            hist_max = pax_info.get('historical_max')
            st.caption(f"📈 Historique : {hist_min} → {hist_max}")
        else:
            st.caption(f"📈 Historique : non chargé")

        # Boutons d'action selon l'état
        loading_status = st.session_state.get('pax_loading_status', 'idle')

        if loading_status == 'idle':
            # Bouton pour lancer le chargement
            if st.button("🔄 Lancer le chargement PAX", use_container_width=True, type="secondary"):
                # Vérifier que les fichiers existent
                forecast_exists = PAX_FORECAST_FILE_PATH.exists()
                historical_exists = PAX_HISTORICAL_FILE_PATH.exists()

                if not forecast_exists and not historical_exists:
                    st.error(f"Aucun fichier PAX trouvé dans input_files/")
                else:
                    if not forecast_exists:
                        st.warning(f"Forecast_pax.xlsx non trouvé, chargement Historic uniquement")
                    if not historical_exists:
                        st.warning(f"Historic_pax.xlsx non trouvé, chargement Forecast uniquement")

                    start_pax_loading(PAX_FORECAST_FILE_PATH, PAX_HISTORICAL_FILE_PATH)
                    st.toast("Chargement PAX démarré en arrière-plan...", icon="🔄")
                    st.rerun()

        elif loading_status in ['success', 'partial', 'error']:
            # Bouton pour recharger
            if st.button("🔄 Recharger", use_container_width=True, type="secondary"):
                st.session_state.pax_loading_status = 'idle'
                st.session_state.pop('pax_data_status', None)
                st.toast("Prêt à recharger les données", icon="🔄")
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

    elif page == "Analyse Budgétaire":
        import importlib, traceback, streamlit as st
        try:
            ab = importlib.import_module("ui.pages.analyse_budgetaire")
            render_analyse_budgetaire_page = getattr(ab, "render_analyse_budgetaire_page")
        except Exception:
            st.error("❌ Erreur lors du chargement de la page Analyse Budgétaire")
            st.code(traceback.format_exc())
            st.stop()
        render_analyse_budgetaire_page()

