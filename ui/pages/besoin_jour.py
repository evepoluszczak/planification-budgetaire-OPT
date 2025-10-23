"""
Page Besoin Jour - Ajustements ponctuels
TODO: Migrer le code depuis app.py.backup (lignes ~2439-2764)
"""
import streamlit as st


def render_besoin_jour_page():
    """Affiche la page Besoin Jour"""
    st.title("Ajustement du Besoin Journalier")
    st.warning(
        "⚠️ Cette page est en cours de migration. "
        "Le code complet se trouve dans `app.py.backup` (lignes ~2439-2764). "
        "\n\nPour finaliser la migration, copiez le code de cette section depuis "
        "app.py.backup vers ce fichier."
    )

    st.markdown("### Fonctionnalités à migrer:")
    st.markdown("""
    - Impact annuel recalculé avec règles
    - Périmètre de l'ajustement (dates, filtres)
    - Vue & Analyse (aperçu grilles AT)
    - Gestion des règles d'ajustement
    - Données PAX prévisionnelles
    """)
