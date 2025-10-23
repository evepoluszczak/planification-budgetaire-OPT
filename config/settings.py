"""
Configuration Streamlit
"""
import streamlit as st
from config.constants import GLOBAL_CSS, GVA_LOGO_URL


def configure_streamlit():
    """Configure la page Streamlit avec les paramètres de base"""
    st.set_page_config(
        page_title="Planificateur Budgétaire - OPT GA",
        page_icon="🛫",
        layout="wide"
    )

    # Appliquer le CSS global
    st.markdown(GLOBAL_CSS, unsafe_allow_html=True)


def render_gva_header():
    """Affiche le header GVA avec logo"""
    logo_h = 42
    st.markdown(
        f"""
        <div class="gva-header" style="--gva-logo-h:{logo_h}px;">
            <div class="gva-header-left">
                <img src='{GVA_LOGO_URL}' alt='Genève Aéroport' class="gva-logo"/>
                <div class="gva-title">Planificateur Budgétaire OPT</div>
            </div>
        </div>
        <div class="gva-accent-bar"></div>
        """,
        unsafe_allow_html=True
    )
