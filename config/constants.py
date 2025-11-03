"""
Constantes et configuration de l'application
"""
from pathlib import Path

# =================== Branding & URLs ===================
GVA_LOGO_URL = "https://upload.wikimedia.org/wikipedia/commons/thumb/1/1a/Logo_Gen%C3%A8ve_A%C3%A9roport.svg/512px-Logo_Gen%C3%A8ve_A%C3%A9roport.svg.png"

# =================== Fichiers et Chemins ===================
BASE_DIR = Path(__file__).parent.parent
RULES_PLANNING_PATH = BASE_DIR / "rules_planning.json"
RULES_BESOIN_JOUR_PATH = BASE_DIR / "rules_besoin_jour.json"
INPUT_FILES_DIR = BASE_DIR / "input_files"
PAX_DATA_FILE_PATH = INPUT_FILES_DIR / "Forecast_pax.xlsx"  # Kept for compatibility
PAX_FORECAST_FILE_PATH = INPUT_FILES_DIR / "Forecast_pax.xlsx"
PAX_HISTORICAL_FILE_PATH = INPUT_FILES_DIR / "Historic_pax.xlsx"
FACTU_AT_DIR = BASE_DIR / "input_files"/"facturation"
FACTU_AT_GLOB = "Facturation Lot A *.xlsx"

# =================== Jours et Saisons ===================
JOURS_FR = ["Lundi", "Mardi", "Mercredi", "Jeudi", "Vendredi", "Samedi", "Dimanche"]

# Ordre de tri des saisons
SAISONS_ORDRE = ["Standard", "Été", "Ete", "Hiver"]

# Créneaux horaires par défaut (de 04:00 à 23:30, pas de 30 minutes)
TIME_SLOTS = [f"{h:02d}:{m:02d}" for h in range(4, 25) for m in (0, 30)]

# =================== CSS Global ===================
GLOBAL_CSS = """
<style>
/* --- Base & Typographie --- */
body {
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif;
}

/* --- En-tête --- */
.gva-header { display: flex; justify-content: space-between; align-items: center; }
.gva-header-left { display: flex; align-items: center; gap: 18px; }
.gva-logo { height: var(--gva-logo-h, 42px); }
.gva-title { font-size: calc(var(--gva-logo-h, 42px) * 0.9); font-weight: 700; color: #333; }
.gva-accent-bar { height: 4px; background: #0076aa; border-radius: 2px; margin-bottom: 2rem; }

/* --- Conteneurs stylisés (Cartes) --- */
div[data-testid="stVerticalBlock"] > [data-testid="stVerticalBlock"] > [data-testid="stVerticalBlock"] > [data-testid="stVerticalBlock"]:not([data-testid="stFullScreenFrame"]) {
    border: 1px solid rgba(0,0,0,0.08);
    border-radius: 14px;
    padding: 1.5rem 1.5rem 1.5rem;
    box-shadow: 0 4px 6px rgba(0,0,0,0.04);
    margin-bottom: 1.5rem;
}

/* --- KPI Cards avec Hover Effect --- */
.kpi-cards {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(260px, 1fr));
    gap: 14px;
    margin: 6px 0 18px;
}
.kpi-card {
    border-radius: 14px;
    padding: 16px 18px;
    background: var(--kpi-bg, #edf6ff);
    border: 1px solid rgba(0, 0, 0, 0.06);
    box-shadow: 0 4px 6px rgba(0,0,0,0.04);
    transition: all 0.3s ease-in-out;
}
.kpi-card:hover {
    transform: translateY(-5px) scale(1.02);
    box-shadow: 0 10px 20px rgba(0,0,0,0.08);
    cursor: default;
}
.kpi-card .value { font-size: 26px; font-weight: 700; margin: 4px 0 8px; }
.kpi-card .delta { font-size: 14px; opacity: 0.9; }
.kpi-card .label { font-size: 13px; text-transform: uppercase; letter-spacing: .4px; opacity: .8; }
.kpi-blue { --kpi-bg: #eaf3ff; }
.kpi-amber { --kpi-bg: #fff7e6; }
.kpi-green { --kpi-bg: #e9f9f0; }
.kpi-red { --kpi-bg: #fff0f0; }

/* --- Carte pour les règles d'ajustement --- */
.rule-card {
    border: 1px solid #ddd;
    border-left: 5px solid var(--rule-color, #0076aa);
    border-radius: 8px;
    padding: 12px 15px;
    margin-bottom: 10px;
    background-color: #fafafa;
}
.rule-card p {
    margin: 0 0 5px 0;
    font-size: 14px;
    color: #333;
}
.rule-card p strong {
    color: #000;
}

/* --- Style checked checkboxes in st.data_editor --- */
div[data-testid="stDataFrame"] .dvn-stack .glide-data-grid .boolean-cell.true {
    background-color: #0076aa !important;
}

div[data-testid="stDataFrame"] .dvn-stack .glide-data-grid .boolean-cell.true svg {
    color: white !important;
}

/* ----- Styles pour la modale Mode d'emploi ----- */
div[role="dialog"]{
  width: 90vw !important;
  max-width: 1400px !important;
  padding: 0 !important;
}
div[role="dialog"] > div{
  width: 100% !important;
  max-width: 100% !important;
}
div[role="dialog"] .stDialog{
  max-height: 80vh;
  overflow: auto;
  padding: 1rem 1.25rem 1.25rem;
}
div[role="dialog"] [data-testid="stVerticalBlock"]{
  padding-top: .25rem !important;
  padding-bottom: .25rem !important;
}
.objectif-container {
  background: linear-gradient(135deg, #e6f0ff 0%, #ffffff 90%);
  border: 1px solid #b3d1ff;
  border-radius: 10px;
  padding: 1.25rem 1.5rem;
  margin-bottom: 1.5rem;
  box-shadow: 0 2px 6px rgba(0, 75, 155, 0.1);
  transition: transform 0.2s ease, box-shadow 0.2s ease;
}
.objectif-container:hover {
  transform: scale(1.01);
  box-shadow: 0 4px 12px rgba(0, 75, 155, 0.15);
}
.objectif-container h3 {
  color: #004b9b; margin-top: 0; margin-bottom: .75rem;
}
.objectif-container div {
  margin-bottom: 0.4rem; font-size: 0.95rem;
}
.parcours-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
  gap: 14px; margin-bottom: 1.5rem;
}
.parcours-card {
  background: #f5f9ff; border: 1px solid #d9e7ff;
  border-radius: 10px; padding: 1.2rem 1.2rem;
  display: flex; flex-direction: column; justify-content: space-between;
  min-height: 135px; box-shadow: 0 1px 3px rgba(0, 75, 155, 0.06);
  transition: transform 0.15s ease, box-shadow 0.15s ease;
}
.parcours-card:hover {
  transform: translateY(-2px); box-shadow: 0 4px 10px rgba(0, 75, 155, 0.08);
}
.parcours-card h4 {
  color: #0b5fb0; margin: 0 0 .35rem 0; font-weight: 600; font-size: 1rem;
}
.parcours-card p {
  margin: 0; line-height: 1.35; font-size: 0.95rem;
}
.st-expander > details > summary {
  font-weight: 600;
}
</style>
"""
