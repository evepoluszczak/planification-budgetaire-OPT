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
from utils.async_loader import (
    start_pax_loading, check_pax_loading_status, get_pax_loading_info,
    is_pax_data_cached_today, get_pax_cache_info, clear_pax_cache,
    load_pax_data_from_cache
)
from utils.autosave import (save_session_state_auto, load_session_state_auto, autosave_exists,
                             get_autosave_info, list_all_autosaves, has_session_changed)
from ui.components import show_help_dialog, planning_editor_ui
from zoneinfo import ZoneInfo

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
    # Masquer la sidebar sur l'écran d'accueil
    st.markdown("""
        <style>
        [data-testid="stSidebar"] {
            display: none;
        }
        [data-testid="collapsedControl"] {
            display: none;
        }
        </style>
    """, unsafe_allow_html=True)

    if st.button("Ouvrir le Mode d'emploi"):
        st.session_state.show_help_dialog = True
        st.rerun()

    st.header("Choisissez une option pour démarrer")

    # Vérifier si une sauvegarde automatique existe
    has_autosave = autosave_exists()
    autosave_info = get_autosave_info() if has_autosave else None

    # Afficher 2 ou 3 colonnes selon la présence d'une sauvegarde automatique
    if has_autosave:
        col1, col2, col3 = st.columns(3)
    else:
        col1, col2 = st.columns(2)

    with col1:
        with st.container(border=True):
            st.subheader("Démarrer avec la base 2026")
            st.markdown("Charge les données de référence de 2026 pour commencer une nouvelle planification.")
            if st.button("Démarrer avec la base 2026", use_container_width=True, type="primary"):
                try:
                    initialize_session_state_2026()
                    st.success("Données de base 2026 chargées.")
                    st.rerun()
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

    # Option de sauvegarde automatique (uniquement si elle existe)
    if has_autosave:
        with col3:
            with st.container(border=True):
                st.subheader("Reprendre la session")
                st.markdown("Restaurez votre dernière session sauvegardée automatiquement.")

                # Récupérer toutes les sauvegardes disponibles
                all_autosaves = list_all_autosaves()

                if all_autosaves:
                    # Afficher les infos de la plus récente
                    latest_save = all_autosaves[0]
                    st.caption(f"📅 Sauvegardé le : {latest_save.get('saved_at', 'inconnu')}")
                    st.caption(f"📊 Taille : {latest_save.get('file_size', 0) / 1024:.1f} Ko")

                    # Avertissement si la sauvegarde est ancienne (> 7 jours)
                    days_old = latest_save.get('days_old', 0)
                    if days_old > 7:
                        st.warning(f"⚠️ Cette sauvegarde date de **{days_old} jours**")
                    elif days_old > 1:
                        st.info(f"ℹ️ Sauvegarde d'il y a {days_old} jours")

                    # Si plusieurs sauvegardes disponibles, permettre la sélection
                    selected_save_path = None
                    if len(all_autosaves) > 1:
                        with st.expander(f"📂 {len(all_autosaves)} sauvegardes disponibles"):
                            st.caption("Sélectionnez une sauvegarde à restaurer :")
                            for idx, save_info in enumerate(all_autosaves):
                                label = save_info.get('saved_at', 'inconnu')
                                if save_info.get('is_current', False):
                                    label += " (actuelle)"
                                age = save_info.get('days_old', 0)
                                if age == 0:
                                    age_str = "aujourd'hui"
                                elif age == 1:
                                    age_str = "hier"
                                else:
                                    age_str = f"il y a {age} jours"

                                if st.button(
                                    f"{label} - {age_str}",
                                    key=f"load_save_{idx}",
                                    use_container_width=True,
                                    type="primary" if idx == 0 else "secondary"
                                ):
                                    selected_save_path = save_info.get('file_path')
                                    break

                    # Bouton principal pour charger la plus récente
                    if st.button("Reprendre la session", use_container_width=True, type="secondary"):
                        selected_save_path = latest_save.get('file_path')

                    # Charger la sauvegarde sélectionnée
                    if selected_save_path:
                        success, message = load_session_state_auto(selected_save_path)
                        if success:
                            st.success(message)
                            st.rerun()
                        else:
                            st.error(message)

else:
    # =================== Interface principale (données chargées) ===================

    # Fragment pour la sauvegarde automatique périodique (toutes les 2 minutes)
    @st.fragment(run_every="120s")
    def autosave_fragment():
        """Fragment qui sauvegarde automatiquement l'état toutes les 2 minutes SI des changements sont détectés"""
        if st.session_state.get('data_loaded', False):
            try:
                # Sauvegarder UNIQUEMENT si des changements sont détectés
                if has_session_changed():
                    save_session_state_auto()
                    # Mettre à jour un timestamp pour tracking
                    st.session_state.last_autosave = dt.datetime.now().isoformat()
                    st.session_state.last_autosave_status = "✓ Modifié"
                else:
                    # Indiquer qu'aucun changement n'a été détecté
                    st.session_state.last_autosave_status = "○ Aucun changement"
            except Exception as e:
                # Ne pas perturber l'utilisateur avec les erreurs d'autosave
                st.session_state.last_autosave_status = "✗ Erreur"
                pass

    # Lancer le fragment d'autosave
    autosave_fragment()

    # Fonction helper pour changer de page SANS autosave
    def change_page(page_name):
        """Change de page sans déclencher de sauvegarde (sauvegarde auto toutes les 2 min si changements)"""
        st.session_state.selected_page = page_name
        st.rerun()

    # Sidebar : Navigation et Export

    with st.sidebar:
        st.title("Navigation")

        # Initialiser la page sélectionnée si nécessaire
        if 'selected_page' not in st.session_state:
            st.session_state.selected_page = "Configuration"

        # Configuration Générale
        st.markdown("#### Configuration Générale")
        if st.button("Configuration", use_container_width=True,
                     type="primary" if st.session_state.selected_page == "Configuration" else "secondary"):
            change_page("Configuration")
        if st.button("Planification", use_container_width=True,
                     type="primary" if st.session_state.selected_page == "Planification" else "secondary"):
            change_page("Planification")

        st.divider()

        # Gestion du Budget
        st.markdown("#### Gestion du Budget")
        if st.button("Budget Annuel", use_container_width=True,
                     type="primary" if st.session_state.selected_page == "Budget Annuel" else "secondary"):
            change_page("Budget Annuel")
        if st.button("Besoin Jour", use_container_width=True,
                     type="primary" if st.session_state.selected_page == "Besoin Jour" else "secondary"):
            change_page("Besoin Jour")
        if st.button("📅 Événements Spéciaux", use_container_width=True,
                     type="primary" if st.session_state.selected_page == "Événements Spéciaux" else "secondary"):
            change_page("Événements Spéciaux")
        if st.button("Analyse Budgétaire", use_container_width=True,
                     type="primary" if st.session_state.selected_page == "Analyse Budgétaire" else "secondary"):
            change_page("Analyse Budgétaire")

        st.divider()

        # Outils
        st.markdown("#### Outils")
        if st.button("Comparaison Historique", use_container_width=True,
                     type="primary" if st.session_state.selected_page == "Comparaison Historique" else "secondary"):
            change_page("Comparaison Historique")
        if st.button("Simulateur Objectif", use_container_width=True,
                     type="primary" if st.session_state.selected_page == "Simulateur Objectif" else "secondary"):
            change_page("Simulateur Objectif")
        if st.button("🤖 Assistant Besoin Jour", use_container_width=True,
                     type="primary" if st.session_state.selected_page == "Assistant Besoin Jour" else "secondary"):
            change_page("Assistant Besoin Jour")

        page = st.session_state.selected_page

        # Bouton Mode d'emploi
        if st.button("❔ Mode d'emploi", use_container_width=True):
            show_help_dialog()

        st.divider()

        # Indicateur de sauvegarde automatique
        if 'last_autosave' in st.session_state:
            try:
                # Convertir en fuseau horaire Paris
                last_save = dt.datetime.fromisoformat(st.session_state.last_autosave)
                paris_tz = ZoneInfo("Europe/Paris")
                # Si last_save est naïf (pas de timezone), on l'assigne au fuseau local
                if last_save.tzinfo is None:
                    last_save = last_save.replace(tzinfo=ZoneInfo("UTC")).astimezone(paris_tz)
                else:
                    last_save = last_save.astimezone(paris_tz)

                last_save_str = last_save.strftime('%H:%M:%S')
                status = st.session_state.get('last_autosave_status', '')
                st.caption(f"💾 Dernière vérification : {last_save_str} {status}")
            except Exception:
                st.caption("💾 Sauvegarde auto (sur modifications)")
        else:
            st.caption("💾 Sauvegarde auto (sur modifications)")

        st.divider()

        # =================== Section Chargement PAX ===================
        st.subheader("Données PAX")

        # Chargement automatique si pas en cache aujourd'hui
        # La fonction is_pax_data_cached_today() vérifie le fichier cache local
        # qui persiste entre les refreshs. Si elle retourne True, on ne charge JAMAIS.
        cache_info = get_pax_cache_info()
        is_cached = cache_info['is_cached']

        # Si en cache, restaurer les données depuis le disque si pas dans session_state
        if is_cached:
            # Vérifier si les données sont déjà dans session_state
            has_data_in_session = (
                st.session_state.get('pax_forecast_status') == 'loaded' or
                st.session_state.get('pax_historical_status') == 'loaded'
            )
            if not has_data_in_session:
                # Charger depuis le cache disque
                loaded_from_cache = load_pax_data_from_cache()
                if not loaded_from_cache:
                    # Le cache est corrompu, forcer le rechargement
                    is_cached = False

        if not is_cached:
            # Pas en cache (ou cache corrompu), vérifier si on doit lancer le chargement
            loading_status = st.session_state.get('pax_loading_status', 'idle')

            # Ne lancer que si status est idle (pas déjà en cours de chargement)
            if loading_status == 'idle':
                forecast_exists = PAX_FORECAST_FILE_PATH.exists()
                historical_exists = PAX_HISTORICAL_FILE_PATH.exists()

                if forecast_exists or historical_exists:
                    start_pax_loading(PAX_FORECAST_FILE_PATH, PAX_HISTORICAL_FILE_PATH)
                    st.toast("Chargement automatique des données PAX...", icon="🔄")

        # Afficher info de cache
        if is_cached:
            loaded_dt = cache_info.get('loaded_datetime')
            if loaded_dt:
                # Afficher l'heure (déjà en timezone Europe/Paris)
                st.caption(f"✅ Données en cache (chargées à {loaded_dt.strftime('%H:%M')})")
            else:
                st.caption("✅ Données en cache (chargées aujourd'hui)")

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

            elif loading_status in ['success', 'partial', 'error']:
                # Chargement terminé - forcer un rerun pour afficher les dates
                if st.session_state.get('pax_needs_rerun', False):
                    st.session_state.pax_needs_rerun = False
                    st.rerun()

                # Afficher le résultat
                if loading_status == 'success':
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
        # Réutiliser la variable is_cached calculée plus haut

        if loading_status == 'idle':
            # Bouton pour lancer le chargement (ou rechargement si en cache)
            button_label = "🔄 Forcer le rechargement" if is_cached else "🔄 Lancer le chargement PAX"
            button_type = "secondary" if is_cached else "primary"

            if st.button(button_label, use_container_width=True, type=button_type):
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

                    # Supprimer le cache pour forcer le rechargement
                    clear_pax_cache()
                    start_pax_loading(PAX_FORECAST_FILE_PATH, PAX_HISTORICAL_FILE_PATH)
                    st.toast("Chargement PAX démarré en arrière-plan...", icon="🔄")
                    st.rerun()

        elif loading_status in ['success', 'partial', 'error']:
            # Bouton pour recharger
            button_label = "🔄 Recharger" if not is_cached else "🔄 Forcer le rechargement"

            if st.button(button_label, use_container_width=True, type="secondary"):
                # Supprimer le cache pour permettre le rechargement
                clear_pax_cache()
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

    elif page == "Événements Spéciaux":
        from ui.pages.evenements import render_evenements_page
        render_evenements_page()

    elif page == "Analyse Budgétaire":
        from ui.pages.analyse_budgetaire import render_analyse_budgetaire_page
        render_analyse_budgetaire_page()

    elif page == "Comparaison Historique":
        from ui.pages.comparaison_historique import render_comparaison_historique_page
        render_comparaison_historique_page()

    elif page == "Simulateur Objectif":
        from ui.pages.simulateur_objectif import render_simulateur_objectif_page
        render_simulateur_objectif_page()

    elif page == "Assistant Besoin Jour":
        from ui.pages.assistant_besoin_jour import render_assistant_besoin_jour_page
        render_assistant_besoin_jour_page()

