"""
Page Comparaison Historique - Comparaison PAX historique vs prévisions
TODO: Migrer le code depuis app.py.backup (lignes ~2931-3086)
"""
import streamlit as st


def render_comparaison_historique_page():
    """Affiche la page Comparaison Historique"""
    st.title("Comparaison Historique vs Prévisions Passagers")
    st.warning(
        "⚠️ Cette page est en cours de migration. "
        "Le code complet se trouve dans `app.py.backup` (lignes ~2931-3086). "
        "\n\nPour finaliser la migration, copiez le code de cette section depuis "
        "app.py.backup vers ce fichier."
    )

    st.markdown("### Fonctionnalités à migrer:")
    st.markdown("""
    - Sélection de dates historiques et prévisionnelles
    - Comparaison des volumes PAX
    - Estimation des heures AT basée sur la variation PAX
    - Graphiques comparatifs Altair
    - Calcul automatique de la date historique correspondante
    """)
