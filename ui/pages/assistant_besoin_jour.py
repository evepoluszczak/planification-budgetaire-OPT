"""
Page Assistant Besoin Jour - Suggestions intelligentes d'ajustement
"""
import streamlit as st
import pandas as pd
from datetime import datetime, date
from typing import List, Dict

from models.suggestion import (
    Suggestion, SuggestionConfig, AjustementPropose, ApplicationLog
)
from core.suggestions_engine import generate_suggestions, apply_suggestions
from utils.date_utils import _date_to_str


def render_assistant_besoin_jour_page():
    """Affiche la page Assistant Besoin Jour"""
    st.title("🤖 Assistant Besoin Jour - Suggestions Intelligentes")
    st.markdown(
        "L'assistant analyse vos objectifs du Simulateur et propose automatiquement "
        "des ajustements optimaux basés sur les prévisions PAX et la planification actuelle."
    )

    # Pré-requis : Budget généré
    bs = st.session_state.get('budget_state', {})
    if not bs or 'year' not in bs or 'calendar_df' not in bs or bs['calendar_df'].empty:
        st.warning(
            "⚠️ Aucun budget annuel valide en mémoire. "
            "Veuillez d'abord en générer un via la page **Budget Annuel**."
        )
        st.stop()

    year = bs['year']

    # Vérifier si des données PAX sont disponibles
    if 'pax_forecast_data' not in st.session_state or \
       st.session_state.pax_forecast_data.empty:
        st.error(
            "⚠️ Aucune donnée PAX forecast chargée. "
            "Veuillez charger les données PAX dans la **Configuration**."
        )
        st.stop()

    # Section 1: Réception des ajustements depuis Simulateur
    with st.container(border=True):
        st.subheader("📥 Objectif d'Ajustement")

        if 'ajustement_propose' not in st.session_state or \
           st.session_state.ajustement_propose is None:
            st.info(
                "Aucun ajustement en attente. Utilisez le **Simulateur d'Objectif** "
                "pour définir un objectif, puis cliquez sur 'Envoyer vers Assistant Besoin Jour'."
            )
            st.stop()
        else:
            ajustement: AjustementPropose = st.session_state.ajustement_propose

            # Afficher l'objectif reçu
            st.markdown(f"**Objectif Total:** {ajustement.total_delta_chf:+,.0f} CHF")
            st.caption(f"Reçu le: {ajustement.timestamp}")

            # Afficher la répartition par catégorie
            if ajustement.distribution:
                st.markdown("**Répartition par Catégorie:**")
                distrib_data = []
                for cat, data in ajustement.distribution.items():
                    distrib_data.append({
                        'Catégorie': cat,
                        'Ajustement CHF': f"{data['delta_chf']:+,.0f}",
                        'Ajustement Heures': f"{data['delta_hours']:+,.0f}",
                        'Part (%)': f"{data['percentage']:.1f}"
                    })
                distrib_df = pd.DataFrame(distrib_data)
                st.dataframe(distrib_df, hide_index=True, use_container_width=True)

            # Afficher les verrous
            if ajustement.locks:
                with st.expander("🔒 Verrous Actifs"):
                    locked_cats = ajustement.locks.get('categories', [])
                    locked_perims = ajustement.locks.get('perimetres', [])
                    locked_dates = ajustement.locks.get('dates', [])

                    if locked_cats:
                        st.markdown(f"**Catégories verrouillées:** {', '.join(locked_cats)}")
                    if locked_perims:
                        st.markdown(f"**Périmètres verrouillés:** {', '.join(locked_perims)}")
                    if locked_dates:
                        dates_str = [_date_to_str(d) for d in locked_dates[:5]]
                        if len(locked_dates) > 5:
                            dates_str.append(f"... (+{len(locked_dates)-5} autres)")
                        st.markdown(f"**Dates verrouillées:** {', '.join(dates_str)}")

            col1, col2 = st.columns([1, 1])
            with col1:
                if st.button("🗑️ Annuler cet Ajustement", type="secondary", use_container_width=True):
                    st.session_state.ajustement_propose = None
                    st.session_state.generated_suggestions = None
                    st.rerun()
            with col2:
                if st.button("🔄 Actualiser depuis Simulateur", type="secondary", use_container_width=True):
                    st.info("Retournez au Simulateur d'Objectif pour mettre à jour l'ajustement.")

    # Section 2: Configuration des Suggestions
    with st.container(border=True):
        st.subheader("⚙️ Configuration du Moteur de Suggestions")

        # Plage d'analyse
        st.markdown("**Plage d'Analyse:**")
        col_days1, col_days2 = st.columns(2)
        with col_days1:
            max_days = st.number_input(
                "Nombre de jours à analyser",
                min_value=1,
                max_value=365,
                value=30,
                step=1,
                key="config_max_days",
                help="Limiter à 30-60 jours pour de meilleures performances"
            )
        with col_days2:
            st.info(f"Analysera environ {max_days} jours × 48 slots × 5 périmètres = ~{max_days * 48 * 5:,} combinaisons")

        st.divider()

        with st.expander("Paramètres Avancés", expanded=False):
            col1, col2 = st.columns(2)

            with col1:
                st.markdown("**Contraintes Opérationnelles:**")
                min_agents = st.number_input(
                    "Minimum d'agents par slot (30min)",
                    min_value=0,
                    max_value=10,
                    value=1,
                    key="config_min_agents"
                )
                max_agents = st.number_input(
                    "Maximum d'agents par slot (0 = illimité)",
                    min_value=0,
                    max_value=50,
                    value=0,
                    key="config_max_agents"
                )
                max_agents_val = max_agents if max_agents > 0 else None

                min_block = st.number_input(
                    "Bloc minimum d'heures consécutives",
                    min_value=0.5,
                    max_value=8.0,
                    value=1.0,
                    step=0.5,
                    key="config_min_block"
                )

            with col2:
                st.markdown("**Pondérations des Critères (%):**")
                w_pax = st.slider(
                    "Intensité PAX",
                    min_value=0,
                    max_value=100,
                    value=40,
                    key="config_w_pax"
                )
                w_ratio = st.slider(
                    "Efficacité Ratio PAX/Agent",
                    min_value=0,
                    max_value=100,
                    value=35,
                    key="config_w_ratio"
                )
                w_var = st.slider(
                    "Stabilité (faible variance)",
                    min_value=0,
                    max_value=100,
                    value=25,
                    key="config_w_var"
                )

                total_weight = w_pax + w_ratio + w_var
                if total_weight != 100:
                    st.warning(f"Total des pondérations: {total_weight}% (devrait être 100%)")

            strict_delta = st.checkbox(
                "Respecter strictement le delta d'heures (sinon priorité au delta CHF)",
                value=False,
                key="config_strict_delta"
            )

    # Section 3: Génération des Suggestions
    with st.container(border=True):
        st.subheader("🧠 Génération des Suggestions")

        if st.button("🚀 Générer les Suggestions", type="primary", use_container_width=True):
            with st.spinner("Analyse des données PAX et génération des suggestions..."):
                try:
                    ajustement: AjustementPropose = st.session_state.ajustement_propose

                    # Construire la configuration
                    config = SuggestionConfig(
                        min_block_hours=min_block,
                        min_agents_per_slot=min_agents,
                        max_agents_per_slot=max_agents_val,
                        penalty_events=0.5,
                        weights={
                            'pax_intensity': w_pax / 100.0,
                            'ratio_efficiency': w_ratio / 100.0,
                            'variance_stability': w_var / 100.0
                        },
                        locked_categories=ajustement.locks.get('categories', []),
                        locked_perimetres=ajustement.locks.get('perimetres', []),
                        locked_dates=ajustement.locks.get('dates', []),
                        respect_strict_delta=strict_delta
                    )

                    # Générer les suggestions avec max_days
                    suggestions_dict = generate_suggestions(
                        ajustement,
                        config,
                        year,
                        max_days=max_days
                    )

                    # Stocker en session_state
                    st.session_state.generated_suggestions = suggestions_dict
                    st.session_state.suggestions_config = config

                    total_suggestions = sum(len(suggs) for suggs in suggestions_dict.values())
                    st.success(f"✅ {total_suggestions} suggestion(s) générée(s) avec succès!")
                    st.rerun()

                except Exception as e:
                    st.error(f"❌ Erreur lors de la génération des suggestions: {e}")
                    import traceback
                    st.code(traceback.format_exc())

    # Section 4: Affichage des Suggestions
    if 'generated_suggestions' in st.session_state and \
       st.session_state.generated_suggestions:

        suggestions_dict: Dict[str, List[Suggestion]] = st.session_state.generated_suggestions

        with st.container(border=True):
            st.subheader("📋 Suggestions Générées")

            # Tabs par catégorie
            categories = list(suggestions_dict.keys())
            if len(categories) == 0:
                st.info("Aucune suggestion générée.")
            else:
                tabs = st.tabs(categories)

                for idx, category in enumerate(categories):
                    with tabs[idx]:
                        suggestions = suggestions_dict[category]

                        if not suggestions:
                            st.info(f"Aucune suggestion pour la catégorie {category}.")
                            continue

                        # Calculer totaux
                        total_delta_hours = sum(s.delta_hours for s in suggestions)
                        total_delta_chf = sum(s.delta_chf for s in suggestions)

                        # Afficher totaux
                        col1, col2, col3 = st.columns(3)
                        with col1:
                            st.metric(
                                "Nombre de Suggestions",
                                len(suggestions)
                            )
                        with col2:
                            st.metric(
                                "Total Ajustement Heures",
                                f"{total_delta_hours:+,.1f} h"
                            )
                        with col3:
                            st.metric(
                                "Total Ajustement CHF",
                                f"{total_delta_chf:+,.0f} CHF"
                            )

                        st.divider()

                        # Afficher les suggestions sous forme de tableau interactif
                        display_data = []
                        for i, sugg in enumerate(suggestions):
                            display_data.append({
                                'ID': i + 1,
                                'Date': _date_to_str(sugg.date),
                                'Période': sugg.periode,
                                'Périmètre': sugg.perimetre,
                                'Δ Heures': f"{sugg.delta_hours:+.1f}",
                                'Δ CHF': f"{sugg.delta_chf:+,.0f}",
                                'Score': f"{sugg.score:.3f}",
                                'Motifs': " | ".join(sugg.motifs[:2]),  # Limiter à 2 motifs
                                'Conflits': " | ".join(sugg.conflits) if sugg.conflits else "—"
                            })

                        df_display = pd.DataFrame(display_data)
                        st.dataframe(
                            df_display,
                            hide_index=True,
                            use_container_width=True,
                            height=min(400, (len(suggestions) + 1) * 35 + 3)
                        )

                        # Détails expandables
                        with st.expander("📊 Détails des Suggestions"):
                            for i, sugg in enumerate(suggestions):
                                with st.container():
                                    st.markdown(f"""
                                    **#{i+1} - {_date_to_str(sugg.date)} | {sugg.periode} | {sugg.perimetre}**
                                    - **Ajustement:** {sugg.delta_hours:+.1f} h / {sugg.delta_chf:+,.0f} CHF
                                    - **Score de priorité:** {sugg.score:.3f}
                                    - **Motifs:** {', '.join(sugg.motifs)}
                                    - **Conflits:** {', '.join(sugg.conflits) if sugg.conflits else 'Aucun'}
                                    """)
                                    st.divider()

                        st.divider()

                        # Actions
                        col1, col2 = st.columns(2)
                        with col1:
                            if st.button(
                                f"✅ Appliquer Toutes les Suggestions ({category})",
                                type="primary",
                                key=f"apply_all_{category}",
                                use_container_width=True
                            ):
                                with st.spinner("Application des suggestions..."):
                                    result = apply_suggestions(suggestions, category)
                                    if result.get('success'):
                                        st.success(
                                            f"✅ {result['rules_created']} règle(s) créée(s) "
                                            f"dans Besoin Jour: "
                                            f"{result['totaux']['hours']:+,.1f} h / "
                                            f"{result['totaux']['chf']:+,.0f} CHF"
                                        )
                                        # Nettoyer l'ajustement proposé
                                        st.session_state.ajustement_propose = None
                                        st.session_state.generated_suggestions = None
                                        st.balloons()
                                        st.info(
                                            "🔄 Rendez-vous sur la page **Besoin Jour** "
                                            "pour voir les règles appliquées."
                                        )
                                    else:
                                        st.error(f"❌ {result.get('message', 'Erreur inconnue')}")

                        with col2:
                            if st.button(
                                f"🗑️ Rejeter Ces Suggestions ({category})",
                                type="secondary",
                                key=f"reject_{category}",
                                use_container_width=True
                            ):
                                del st.session_state.generated_suggestions[category]
                                st.success(f"Suggestions pour {category} rejetées.")
                                st.rerun()

    # Section 5: Historique des Applications (V2)
    with st.expander("📜 Historique des Applications (À venir - V2)"):
        st.info(
            "Cette section affichera l'historique des suggestions appliquées, "
            "avec possibilité d'annuler et snapshots avant/après."
        )
