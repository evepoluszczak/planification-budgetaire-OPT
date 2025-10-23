"""
Page Budget Annuel - Génération et analyse du budget
TODO: Migrer le code depuis app.py.backup (lignes ~2139-2437)
"""
import streamlit as st


def render_budget_annuel_page():
    """Affiche la page Budget Annuel"""
    st.title("Budget Annuel Consolidé")
    st.warning(
        "⚠️ Cette page est en cours de migration. "
        "Le code complet se trouve dans `app.py.backup` (lignes ~2139-2437). "
        "\n\nPour finaliser la migration, copiez le code de cette section depuis "
        "app.py.backup vers ce fichier."
    )

    st.markdown("### Fonctionnalités à migrer:")
    st.markdown("""
    - Génération du budget annuel
    - Vue d'ensemble avec KPIs
    - Paramètres du calendrier (timeline des saisons)
    - Association des coûts par catégorie
    - Détails mensuels et journaliers
    """)
