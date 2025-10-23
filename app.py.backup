# app.py
import streamlit as st
import pandas as pd
import numpy as np
import datetime as dt
from datetime import timedelta
import io
import altair as alt
import re
import unicodedata
import json
from pathlib import Path
import concurrent.futures
import time

# =================== Fonctions de nettoyage des données ===================
def clean_dataframe(df):
    """Nettoie un DataFrame en remplaçant les valeurs infinies et NaN problématiques"""
    df = df.copy()
    # Remplacer les inf par de grandes valeurs finies
    df = df.replace([np.inf, -np.inf], [999999.0, -999999.0])
    # Remplacer les NaN par 0 dans les colonnes numériques
    numeric_cols = df.select_dtypes(include=[np.number]).columns
    df[numeric_cols] = df[numeric_cols].fillna(0)
    return df

def safe_metric_display(value, format_str="%,.0f"):
    """Affiche une métrique de manière sécurisée en gérant les valeurs infinies"""
    if pd.isna(value) or not np.isfinite(value):
        return "N/A"
    try:
        return format_str % value
    except:
        return str(value)


# =================== Branding & Configuration ===================
GVA_LOGO_URL = "https://upload.wikimedia.org/wikipedia/commons/thumb/1/1a/Logo_Gen%C3%A8ve_A%C3%A9roport.svg/512px-Logo_Gen%C3%A8ve_A%C3%A9roport.svg.png"

st.set_page_config(page_title="Planificateur Budgétaire - OPT GA", page_icon="🛫", layout="wide")

# =================== CSS Global (Modernisation UX/UI) ===================
# (CSS code remains the same as provided previously - Omitted for brevity)
st.markdown("""
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
/* Applique un style "carte" aux conteneurs principaux */
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
    color: white !important; /* Optional: Make checkmark white */
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
""", unsafe_allow_html=True)


def gva_header():
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

# =================== Pop-up Mode d'emploi ===================
@st.dialog("Mode d'emploi")
def show_help_dialog():
    # --- INDENTATION CORRIGÉE ICI ---
    st.caption("Guide d’utilisation du Planificateur Budgétaire OPT – Genève Aéroport")

    # --- 🎯 Objectif de l’outil ---
    with st.container():
        st.markdown(
            """
            <div class="objectif-container">
                <h3>Objectif de l’outil</h3>
                <div><b>✔ Construire</b> des grilles jour-type par catégorie pour estimer les heures et les coûts.</div>
                <div><b>✔ Générer</b> un Budget Annuel consolidé à partir de ces grilles et du calendrier des saisons.</div>
                <div><b>✔ Appliquer</b> des règles ponctuelles dans <i>Besoin Jour</i> pour ajuster certains jours/plages <b>sans modifier</b> les jours-types de base.</div>
                <div><b>✔ Exporter/Importer</b> un scénario complet pour le sauvegarder, le partager ou le reprendre plus tard.</div>
            </div>
            """,
            unsafe_allow_html=True
        )

    # --- Pré-requis ---
    with st.container(border=True):
        st.markdown("### Pré-requis")
        st.markdown(
            """
            1. Démarrer en choisissant la **base 2026** (ou en chargeant un scénario `.xlsx` existant).
            2. S'assurer que les **périmètres** par catégorie sont correctement définis.
            3. Vérifier que les **tarifs horaires** du personnel sont à jour dans la page *Configuration*.
            """
        )

    # --- Parcours Recommandé ---
    st.markdown("### Parcours Recommandé")
    st.markdown(
        """
        <div class="parcours-grid">
          <div class="parcours-card"><h4>1. Configuration</h4><p>Vérifiez les tarifs, saisons de référence et périmètres.</p></div>
          <div class="parcours-card"><h4>2. Planification</h4><p>Éditez ou créez les grilles pour chaque jour-type.</p></div>
          <div class="parcours-card"><h4>3. Budget Annuel</h4><p>Générez la projection annuelle et analysez les coûts.</p></div>
          <div class="parcours-card"><h4>4. Besoin Jour</h4><p>Appliquez des ajustements ponctuels si nécessaire.</p></div>
          <div class="parcours-card"><h4>5. Export</h4><p>Sauvegardez votre scénario via la barre latérale.</p></div>
        </div>
        """,
        unsafe_allow_html=True
    )

    st.divider()

    # --- Concepts Importants ---
    with st.container(border=True):
        st.markdown("### Concepts Importants")
        st.markdown(
            """
            - **Jour-type (JT)** : Modèle de planification (`Jour + Saison`). Grille binaire (0/1).
            - **Périmètre** : Poste ou zone opérationnelle (ex: *Check in 1*).
            - **Catégorie** : Regroupement de périmètres (AT, CSC, etc.).
            - **Règle *Besoin Jour*** : Modification **temporaire** (dates spécifiques), n'altère pas les JTs.
            - **Autosave** : Les règles *Besoin Jour* sont dans `rules_besoin_jour.json`.
            """
        )

    # --- Pages en détail ---
    st.markdown("### Pages en Détail")
    with st.expander("Configuration"):
        st.markdown("- **Personnel et Tarifs** : Mettez à jour les coûts horaires.\n- **Saisons de Référence** : Modèle pour les calendriers futurs.\n- **Périmètres** : Gérez les postes par catégorie.\n- **Attention** : Influence tous les calculs.")
    with st.expander("Planification"):
        st.markdown("- **Sélecteur** : Choisissez le JT à éditer.\n- **Gérer JTs** : Créez/Dupliquez des jours-types.\n- **Remplissage masse** : Accélérateur pour remplir les grilles.\n- **KPIs** : Total Heures, Pic Effectifs (temps réel pour le JT édité).")
    with st.expander("Budget Annuel"):
        st.markdown("3 Onglets :\n1. **Vue d'Ensemble & Génération** : Choisissez l'année et lancez le calcul.\n2. **Paramètres Calendrier** : Vérifiez/ajustez les saisons auto-calculées.\n3. **Association Coûts** : **Crucial !** Liez Catégorie <> Type Personnel.")
    with st.expander("Besoin Jour"):
        st.markdown("Pour gérer les exceptions :\n- **Périmètre Ajustement** : Définissez les dates cibles (filtres possibles).\n- **Gérer Règles (Onglet 2)** : Créez la règle (périmètres, plage horaire, valeur 0/1).\n- **Vue & Analyse (Onglet 1)** : Comparez grille base / après règles et l'impact annuel.")
    with st.expander("Exporter / Importer"):
        st.markdown("- **Exporter** (Sidebar) : Sauvegarde complète (`.xlsx`) avec règles Besoin Jour.\n- **Importer** (Accueil) : Charge un scénario et recalcule le budget.\n- **Règles Besoin Jour** : Fichier `json` séparé.")

    st.divider()

    # --- Checklist ---
    st.success("✅ Checklist Rapide")
    st.markdown("- [ ] **Configuration** : Tarifs et périmètres OK.\n- [ ] **Planification** : Jours-types nécessaires OK.\n- [ ] **Budget Annuel** : Mapping coûts OK & Budget généré.\n- [ ] **Besoin Jour** : Ajustements ponctuels OK (si besoin).\n- [ ] **Export** : Scénario sauvegardé.")

    col1, col2, col3 = st.columns([0.5, 0.3, 0.3])
    with col2:
        if st.button("Fermer", type="primary", use_container_width=False):
            st.session_state.show_help_dialog = False
            st.rerun()
    # --- FIN DE L'INDENTATION CORRIGÉE ---

# =================== Autosave JSON (règles) ===================
RULES_PLANNING_PATH = Path("rules_planning.json")
RULES_BESOIN_JOUR_PATH = Path("rules_besoin_jour.json")


PAX_DATA_FILE_PATH = Path(__file__).parent / "Forecast_pax.xlsx"
FACTU_AT_DIR = Path(__file__).parent / "facturation_at"  
FACTU_AT_GLOB = "Facturation Lot A *.xlsx"              



def _date_to_str(d):
    if isinstance(d, dt.date):
        return d.isoformat()
    return str(d)

def _str_to_date(x):
    if isinstance(x, dt.date):
        return x
    try:
        return dt.date.fromisoformat(str(x))
    except Exception:
        try:
            return pd.to_datetime(x).date()
        except Exception:
            return None

def save_rules_to_json(rules_list, path: Path):
    serializable = []
    for op in rules_list:
        op2 = dict(op)
        op2['start'] = _date_to_str(op2.get('start'))
        op2['end'] = _date_to_str(op2.get('end'))
        serializable.append(op2)
    try:
        path.write_text(json.dumps(serializable, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception as e:
        st.warning(f"Impossible d'enregistrer les règles ({path.name}) : {e}")

def load_rules_from_json(path: Path):
    if not path.exists():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        fixed = []
        for op in data:
            op2 = dict(op)
            op2['start'] = _str_to_date(op2.get('start'))
            op2['end'] = _str_to_date(op2.get('end'))
            if op2['start'] is None or op2['end'] is None:
                continue
            fixed.append(op2)
        return fixed
    except Exception as e:
        st.warning(f"Impossible de charger les règles ({path.name}) : {e}")
        return []

# =================== Fonctions Utilitaires (Helpers) ===================
# === Executor partagé pour tâches "longues" ===
if 'executor' not in st.session_state:
    st.session_state.executor = concurrent.futures.ThreadPoolExecutor(max_workers=1)

# Pour suivre la tâche PAX en cours (Future)
if 'pax_task' not in st.session_state:
    st.session_state.pax_task = None

def _strip_accents(s: str) -> str:
    return ''.join(c for c in unicodedata.normalize('NFKD', s) if not unicodedata.combining(c))

def canon(s: str) -> str:
    s = "" if s is None else str(s)
    s = re.sub(r"\s+", " ", s.strip())
    s = _strip_accents(s).lower()
    return s

JOURS_FR = ["Lundi", "Mardi", "Mercredi", "Jeudi", "Vendredi", "Samedi", "Dimanche"]

def split_jour_type(name: str):
    if not name: return (None, None)
    name = str(name).strip()
    for j in JOURS_FR:
        if name.startswith(j + " "):
            return j, name[len(j):].strip()
        if name == j:
            return j, ""
    return (None, None)

def find_closest_weekday(target_date: dt.date, target_weekday: int) -> dt.date:
    current_weekday = target_date.weekday()
    days_backward = (current_weekday - target_weekday + 7) % 7
    days_forward = (target_weekday - current_weekday + 7) % 7
    return target_date - timedelta(days=days_backward) if days_backward <= days_forward else target_date + timedelta(days=days_forward)

def sync_all_planning_grids_from_widgets():
    if "planning_data" not in st.session_state:
        return
    for category_key, day_types in st.session_state.planning_data.items():
        for jt_key, df in day_types.items():
            if isinstance(df, pd.DataFrame) and not df.empty:
                st.session_state.planning_data[category_key][jt_key] = df.fillna(0).astype(int).clip(0, 1)

def _sync_budget_annuel_state():
    if 'adjusted_saisons' in st.session_state:
        df = st.session_state.adjusted_saisons
        if isinstance(df, pd.DataFrame) and not df.empty:
            if 'Date Début' in df.columns:
                df['Date Début'] = pd.to_datetime(df['Date Début']).dt.date
            if 'Date Fin' in df.columns:
                df['Date Fin'] = pd.to_datetime(df['Date Fin']).dt.date
            st.session_state.adjusted_saisons = df

def export_full_state():
    sync_all_planning_grids_from_widgets()
    _sync_budget_annuel_state()

    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        # --- Existing sheets ---
        st.session_state.personnel.to_excel(writer, sheet_name='Personnel_Tarifs', index=False)
        st.session_state.saisons.to_excel(writer, sheet_name='Saisons', index=False)

        if 'adjusted_saisons' in st.session_state and isinstance(st.session_state.adjusted_saisons, pd.DataFrame) and not st.session_state.adjusted_saisons.empty:
            st.session_state.adjusted_saisons.to_excel(writer, sheet_name='Saisons_Ajustees', index=False)

        perimetres_list = [{'Categorie': cat, 'Perimetre': p} for cat, items in st.session_state.perimetres.items() for p in items]
        pd.DataFrame(perimetres_list).to_excel(writer, sheet_name='Perimetres', index=False)

        if 'cost_mapping' in st.session_state and st.session_state.cost_mapping:
            pd.DataFrame([{'Categorie': k, 'Type_Personnel': v} for k, v in st.session_state.cost_mapping.items()]).to_excel(writer, sheet_name='Cost_Mapping', index=False)

        for category, day_types_dict in st.session_state.planning_data.items():
            for day_type_name, grid_df in day_types_dict.items():
                sheet_name = f"JT_{category}_{day_type_name}"
                # Ensure index has a name before resetting
                if grid_df.index.name is None:
                    grid_df.index.name = "Perimetre"
                df_to_write = grid_df.reset_index()
                df_to_write.to_excel(writer, sheet_name=sheet_name, index=False)

        # --- NEW: Add Besoin Jour Rules sheet ---
        if 'besoin_jour_ops' in st.session_state and st.session_state.besoin_jour_ops:
            rules_export_list = []
            for op in st.session_state.besoin_jour_ops:
                # Create a copy and convert lists/dates for Excel
                op_export = op.copy()
                op_export['start'] = _date_to_str(op.get('start'))
                op_export['end'] = _date_to_str(op.get('end'))
                # Convert lists to comma-separated strings
                op_export['jours'] = ",".join(op.get('jours', []))
                op_export['saisons'] = ",".join(op.get('saisons', []))
                op_export['rows'] = ",".join(op.get('rows', []))
                rules_export_list.append(op_export)

            rules_df = pd.DataFrame(rules_export_list)
            # Define column order for consistency
            column_order = ['category', 'start', 'end', 'jours', 'saisons', 'rows', 'start_col', 'end_col', 'value']
            # Reindex to ensure all columns exist and are in order, fill missing with empty string or NaN
            rules_df = rules_df.reindex(columns=column_order, fill_value="")
            rules_df.to_excel(writer, sheet_name='Besoin_Jour_Regles', index=False)
        # --- End of NEW section ---

    return output.getvalue()

def load_data_from_excel(uploaded_file):
    try:
        xls = pd.ExcelFile(uploaded_file)

        # --- Existing loading logic ---
        st.session_state.personnel = pd.read_excel(xls, 'Personnel_Tarifs')
        saisons_df = pd.read_excel(xls, 'Saisons')
        saisons_df['Date Début'] = pd.to_datetime(saisons_df['Date Début']).dt.date
        saisons_df['Date Fin'] = pd.to_datetime(saisons_df['Date Fin']).dt.date
        st.session_state.saisons = saisons_df
        st.session_state.reference_year_saisons = saisons_df['Date Début'].iloc[0].year

        perimetres_df = pd.read_excel(xls, 'Perimetres')
        st.session_state.perimetres = perimetres_df.groupby('Categorie')['Perimetre'].apply(list).to_dict()

        st.session_state.planning_data = {cat: {} for cat in st.session_state.perimetres.keys()}
        jt_sheets = [s for s in xls.sheet_names if s.startswith('JT_')]
        for sheet_name in jt_sheets:
            try: # Add try-except for robustness against malformed sheet names
                parts = sheet_name.split('_')
                if len(parts) >= 3:
                    category, day_type_name = parts[1], "_".join(parts[2:])
                    df = pd.read_excel(xls, sheet_name)
                    # Check if 'Perimetre' column exists before setting index
                    if 'Perimetre' in df.columns:
                         df = df.set_index('Perimetre')
                         if category in st.session_state.planning_data:
                              # Ensure all expected columns (time slots) exist
                              time_slots = [f"{h:02d}:{m:02d}" for h in range(4, 24) for m in (0, 30)]
                              df = df.reindex(columns=time_slots, fill_value=0)
                              st.session_state.planning_data[category][day_type_name] = df.fillna(0).astype(int).clip(0, 1)
                    else:
                         st.warning(f"La feuille '{sheet_name}' n'a pas de colonne 'Perimetre'. Elle est ignorée.")
                else:
                     st.warning(f"Nom de feuille de planification invalide ignoré: '{sheet_name}'")
            except Exception as e_jt:
                 st.warning(f"Erreur lors de la lecture de la feuille '{sheet_name}': {e_jt}")


        if 'Cost_Mapping' in xls.sheet_names:
            cm = pd.read_excel(xls, 'Cost_Mapping')
            st.session_state.cost_mapping = {row['Categorie']: row['Type_Personnel'] for _, row in cm.iterrows()}
        else:
             st.session_state.cost_mapping = {} # Initialize if not present


        if 'Saisons_Ajustees' in xls.sheet_names:
            adj = pd.read_excel(xls, 'Saisons_Ajustees')
            adj['Date Début'] = pd.to_datetime(adj['Date Début']).dt.date
            adj['Date Fin'] = pd.to_datetime(adj['Date Fin']).dt.date
            st.session_state.adjusted_saisons = adj
            st.session_state.adjusted_saisons_year = adj['Date Début'].iloc[0].year
        else:
             # If no adjusted seasons, clear potential old state
             if 'adjusted_saisons' in st.session_state: del st.session_state['adjusted_saisons']
             if 'adjusted_saisons_year' in st.session_state: del st.session_state['adjusted_saisons_year']

        # --- NEW: Load Besoin Jour Rules from Excel ---
        if 'Besoin_Jour_Regles' in xls.sheet_names:
            rules_df = pd.read_excel(xls, 'Besoin_Jour_Regles')
            loaded_rules = []
            # Fill NaN values with empty strings before processing
            rules_df = rules_df.fillna("")
            for _, row in rules_df.iterrows():
                try:
                    op = row.to_dict()
                    # Convert dates back
                    op['start'] = _str_to_date(op.get('start'))
                    op['end'] = _str_to_date(op.get('end'))

                    # Convert comma-separated strings back to lists, handle empty strings
                    op['jours'] = [j.strip() for j in str(op.get('jours', '')).split(',') if j.strip()]
                    op['saisons'] = [s.strip() for s in str(op.get('saisons', '')).split(',') if s.strip()]
                    op['rows'] = [r.strip() for r in str(op.get('rows', '')).split(',') if r.strip()]

                    # Convert value to int, default to 0 if error
                    try:
                        op['value'] = int(op.get('value', 0))
                    except (ValueError, TypeError):
                        op['value'] = 0

                    # Basic validation (optional but recommended)
                    if op['start'] and op['end'] and op['start'] <= op['end'] and op['rows'] and op['start_col'] and op['end_col']:
                         loaded_rules.append(op)
                    else:
                         st.warning(f"Règle Besoin Jour ignorée car invalide ou incomplète : {op}")
                except Exception as e_rule:
                     st.warning(f"Erreur lors de la lecture d'une règle Besoin Jour: {e_rule} - Ligne: {row.to_dict()}")

            st.session_state.besoin_jour_ops = loaded_rules
            st.info(f"{len(loaded_rules)} règles Besoin Jour chargées depuis le fichier Excel.")
        else:
            # Fallback for older files: Load from JSON
            st.session_state.besoin_jour_ops = load_rules_from_json(RULES_BESOIN_JOUR_PATH)
            st.info("Aucune règle Besoin Jour trouvée dans le fichier Excel. Chargement depuis le fichier JSON local (si existant).")
        # --- End of NEW section ---

        # Auto-generate budget after loading everything
        try:
            year_to_generate = int(st.session_state.get('adjusted_saisons_year', st.session_state.saisons['Date Début'].iloc[0].year))
            generate_budget_state(year_to_generate)
            st.success(f"Budget pour l'année {year_to_generate} généré automatiquement après chargement.")
        except Exception as _e:
            st.warning(f"Le budget n'a pas pu être généré automatiquement après le chargement du fichier : {_e}")

        st.session_state.data_loaded = True
        return True, "Fichier chargé avec succès !"
    except Exception as e:
        # Clear potentially partially loaded state on error
        st.session_state.data_loaded = False
        st.session_state.pop('personnel', None)
        st.session_state.pop('saisons', None)
        st.session_state.pop('perimetres', None)
        st.session_state.pop('planning_data', None)
        st.session_state.pop('cost_mapping', None)
        st.session_state.pop('adjusted_saisons', None)
        st.session_state.pop('besoin_jour_ops', None)
        st.session_state.pop('budget_state', None)
        return False, f"Erreur critique lors de la lecture du fichier Excel : {e}"



def _season_timeline_df():
    # Ensure 'adjusted_saisons' exists and is a DataFrame
    if 'adjusted_saisons' not in st.session_state or not isinstance(st.session_state.adjusted_saisons, pd.DataFrame):
        return pd.DataFrame(columns=['Saison', 'Date Début', 'Date Fin', 'start', 'end', 'days'])

    df = st.session_state.adjusted_saisons.copy()

    # Convert columns to datetime if they are not already, handling potential errors
    try:
        df['Date Début'] = pd.to_datetime(df['Date Début'])
        df['Date Fin'] = pd.to_datetime(df['Date Fin'])
    except Exception as e:
        st.error(f"Erreur lors de la conversion des dates des saisons: {e}")
        return pd.DataFrame(columns=['Saison', 'Date Début', 'Date Fin', 'start', 'end', 'days'])

    df = df.sort_values('Date Début').reset_index(drop=True)
    df = df.assign(
        start=lambda d: d['Date Début'],
        end=lambda d: d['Date Fin'],
        days=lambda d: (d['Date Fin'] - d['Date Début']).dt.days + 1
    )
    return df


def _day_name_fr(series_dt):
    mapping = {0: "Lundi", 1: "Mardi", 2: "Mercredi", 3: "Jeudi", 4: "Vendredi", 5: "Samedi", 6: "Dimanche"}
    try:
        # Use French locale directly if available
        return series_dt.dt.day_name(locale='fr_FR.UTF-8').str.capitalize()
    except Exception:
        # Fallback to English names and mapping if locale fails
        try:
             return series_dt.dt.day_name().map({
                 'Monday': 'Lundi', 'Tuesday': 'Mardi', 'Wednesday': 'Mercredi',
                 'Thursday': 'Jeudi', 'Friday': 'Vendredi', 'Saturday': 'Samedi', 'Sunday': 'Dimanche'
             })
        except Exception:
             # Final fallback using weekday number
            return series_dt.dt.weekday.map(mapping)


def _get_grid(planning_dict: dict, name: str):
    if name in planning_dict:
        return name, planning_dict[name]
    cn = canon(name)
    for k in planning_dict.keys():
        if canon(k) == cn:
            return k, planning_dict[k]
    return None, None

def _ensure_grid(planning_dict: dict, name: str, perimetres: list, time_slots: list):
    k, df = _get_grid(planning_dict, name)
    if df is not None:
        # Ensure the DataFrame has the correct index and columns
        df = df.reindex(index=perimetres, columns=time_slots, fill_value=0)
        return k, df.fillna(0).astype(int).clip(0, 1) # Ensure correct type and values
    else:
        # Create a new DataFrame if it doesn't exist
        df = pd.DataFrame(0, index=perimetres, columns=time_slots).astype(int)
        planning_dict[name] = df
        return name, df


def _get_default_grid(planning_dict: dict):
    return _get_grid(planning_dict, "Default")


def _apply_bulk_range(category_key: str, jt_key_stored: str, rows: list, start_col: str, end_col: str, value: int):
    df = st.session_state.planning_data[category_key][jt_key_stored]
    if df.empty or start_col not in df.columns or end_col not in df.columns: return

    value = 1 if int(value) == 1 else 0
    cols = list(df.columns)
    i1, i2 = cols.index(start_col), cols.index(end_col)
    if i1 > i2: i1, i2 = i2, i1
    target_cols = cols[i1:i2 + 1]
    valid_rows = [r for r in rows if r in df.index]
    if not valid_rows: return

    df.loc[valid_rows, target_cols] = value
    st.session_state.planning_data[category_key][jt_key_stored] = df.fillna(0).astype(int).clip(0, 1)

def _apply_ops_to_grid(base_df: pd.DataFrame, date_: dt.date, jour: str, saison: str, category: str):
    if not isinstance(base_df, pd.DataFrame) or base_df.empty:
        return base_df

    g = base_df.copy()
    cols = list(g.columns)

    for op in st.session_state.besoin_jour_ops:
        if op.get('category') != category:
            continue

        try:
            op_start, op_end = _str_to_date(op['start']), _str_to_date(op['end'])
            if op_start is None or op_end is None or not (op_start <= date_ <= op_end):
                continue
        except Exception:
            continue # Ignore rule if dates are invalid

        if op['jours'] and (jour not in op['jours']):
            continue
        if op['saisons'] and (saison not in op['saisons']):
            continue

        if op['start_col'] in cols and op['end_col'] in cols:
            i1, i2 = cols.index(op['start_col']), cols.index(op['end_col'])
            if i1 > i2: i1, i2 = i2, i1
            target_cols = cols[i1:i2 + 1]
            rows = [r for r in op['rows'] if r in g.index] # Ensure rows exist in the grid
            if rows and target_cols:
                try:
                    g.loc[rows, target_cols] = int(op['value'])
                except ValueError:
                     st.warning(f"Invalid value in rule: {op['value']}") # Handle non-integer values if necessary
                     continue

    return g.fillna(0).astype(int).clip(0, 1)



def _finalize_pax_load(full_pax_data, overall_min_date, overall_max_date):
    if full_pax_data is None or full_pax_data.empty:
        st.session_state.pax_historical_status = "not_loaded"
        st.session_state.pax_forecast_status = "not_loaded"
        return

    st.session_state.pax_overall_min_date = overall_min_date
    st.session_state.pax_overall_max_date = overall_max_date

    today = dt.date.today()
    historical_data = full_pax_data[full_pax_data.index.date < today].copy()
    forecast_data   = full_pax_data[full_pax_data.index.date >= today].copy()

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



# --- FONCTION DE CHARGEMENT PAX GÉNÉRIQUE (CORRIGÉE) ---
@st.cache_data
def load_pax_data(file_path: Path, file_description: str):
    """
    Charge et transforme les données passagers (hist ou forecast) depuis un fichier local.
    [OPTIMISÉ avec vectorisation au lieu de df.apply]
    Retourne (DataFrame agrégé, date_min, date_max).
    """
    if not file_path.exists():
        st.warning(f"Fichier {file_description} non trouvé : {file_path}")
        return pd.DataFrame(), None, None

    try:
        # --- LECTURE DU FICHIER (CSV ou Excel) ---
        if file_path.suffix.lower() == '.csv':
            df = pd.read_csv(file_path, delimiter=";")
        elif file_path.suffix.lower() in ['.xlsx', '.xls']:
            try:
                # Tenter avec openpyxl par défaut
                df = pd.read_excel(file_path, engine='openpyxl') 
            except ImportError:
                 st.error("La lecture des fichiers Excel nécessite 'openpyxl'. Installez-le (`pip install openpyxl`)")
                 return pd.DataFrame(), None, None
            except Exception as e_read_excel:
                 st.error(f"Erreur lors de la lecture du fichier Excel ({file_path}): {e_read_excel}")
                 return pd.DataFrame(), None, None
        else:
             st.error(f"Format de fichier non supporté: {file_path.suffix}. Utilisez CSV ou Excel.")
             return pd.DataFrame(), None, None
        # --- FIN LECTURE ---

        # 1. DateTime (Correction: Utiliser directement Local Schedule Time)
        time_col_name = 'Local Schedule Time' # Nom de la colonne contenant date et heure
        try:
            # Essayer le format spécifique d'abord (plus rapide si ça correspond)
            df['DateTime'] = pd.to_datetime(
                df[time_col_name],
                format='%d.%m.%Y %H:%M', 
                errors='coerce' 
            )
            # Si beaucoup de NaT après format spécifique, tenter la conversion générique
            if df['DateTime'].isnull().sum() > len(df) / 2: 
                 st.warning(f"Format '%d.%m.%Y %H:%M' semble incorrect pour '{time_col_name}'. Tentative de conversion générique.")
                 df['DateTime'] = pd.to_datetime(df[time_col_name], errors='coerce')

        except KeyError as e:
            st.error(f"Erreur: Colonne '{time_col_name}' manquante dans le fichier Excel/CSV pour créer dt.")
            return pd.DataFrame(), None, None
        except ValueError: # Erreur si le format ne correspond pas du tout
             st.warning(f"Format '%d.%m.%Y %H:%M' invalide pour '{time_col_name}'. Tentative de conversion générique.")
             try:
                 # Conversion générique comme fallback
                  df['DateTime'] = pd.to_datetime(df[time_col_name], errors='coerce')
             except Exception as e_dt_generic:
                  st.error(f"Échec de la conversion générique de '{time_col_name}' : {e_dt_generic}")
                  return pd.DataFrame(), None, None
        except Exception as e_dt:
             st.error(f"Erreur inattendue lors de la conversion de '{time_col_name}' : {e_dt}")
             return pd.DataFrame(), None, None


        # 2. Nettoyage (Noms de colonnes à vérifier)
        pax_col = 'Expected Pax'
        schengen_col = 'Schengen Flight'
        arrdep_col = 'Arrival - Departure Code'
        
        required_cols_check = [pax_col, schengen_col, arrdep_col, time_col_name]
        try:
            df[pax_col] = pd.to_numeric(df[pax_col], errors='coerce').fillna(0)
            # Vérifier que les colonnes booléennes existent avant de les utiliser
            if not all(col in df.columns for col in [schengen_col, arrdep_col]):
                 missing = [col for col in [schengen_col, arrdep_col] if col not in df.columns]
                 st.error(f"Colonnes nécessaires manquantes pour le breakdown : {', '.join(missing)}")
                 return pd.DataFrame(), None, None
            df = df.dropna(subset=['DateTime']) 
            
        except KeyError as e:
             st.error(f"Erreur: Colonne manquante dans le fichier pour le nettoyage: {e}. Vérifiez '{pax_col}', '{schengen_col}', '{arrdep_col}'.")
             return pd.DataFrame(), None, None


        # 3. Dates Min/Max
        if df.empty:
            st.warning(f"Le fichier {file_description} est vide après nettoyage des dates/pax.")
            return pd.DataFrame(), None, None
        min_date = df['DateTime'].min().date()
        max_date = df['DateTime'].max().date()

        # --- OPTIMISATION : VECTORISATION ---
        # 4. Créer les colonnes de breakdown via masques booléens
        schengen_mask = df[schengen_col] == 'Y'
        arrival_mask = df[arrdep_col] == 'A'
        # On suppose que si ce n'est pas 'Y', c'est 'N' et si ce n'est pas 'A', c'est 'D'
        # Si d'autres valeurs sont possibles, il faudrait des masques plus spécifiques
        nonschengen_mask = ~schengen_mask 
        departure_mask = ~arrival_mask 

        pax_values = df[pax_col] # Récupérer la colonne une seule fois

        df['Pax_Schengen_A'] = np.where(schengen_mask & arrival_mask, pax_values, 0)
        df['Pax_Schengen_D'] = np.where(schengen_mask & departure_mask, pax_values, 0)
        df['Pax_NonSchengen_A'] = np.where(nonschengen_mask & arrival_mask, pax_values, 0)
        df['Pax_NonSchengen_D'] = np.where(nonschengen_mask & departure_mask, pax_values, 0)
        # --- FIN OPTIMISATION ---

        # 5. Agrégation (Inchangé, généralement rapide)
        pax_agg = df.set_index('DateTime').resample('30T').agg({
            'Pax_Schengen_A': 'sum', 'Pax_Schengen_D': 'sum',
            'Pax_NonSchengen_A': 'sum', 'Pax_NonSchengen_D': 'sum'
        })
        
        # 6. Retour
        return pax_agg, min_date, max_date
        
    except FileNotFoundError:
         st.error(f"Fichier {file_description} non trouvé à l'emplacement : {file_path}")
         return pd.DataFrame(), None, None
    except Exception as e:
        # Erreur plus générale
        st.error(f"Erreur inattendue lors du chargement/traitement du fichier {file_description} ({file_path}): {e}")
        import traceback
        st.error(traceback.format_exc()) # Affiche plus de détails pour le débogage
        return pd.DataFrame(), None, None


    return out

@st.cache_data
def load_facturation_at_month(year: int, month: int) -> pd.DataFrame:
    """
    Charge le fichier 'Facturation Lot A mm.yyyy.xlsx' pour le mois/année donnés.
    Détecte automatiquement la ligne contenant les entêtes ('Date ouvrable', 'Heures')
    en scannant les 5 premières lignes.
    """
    file_path = FACTU_AT_DIR / f"Facturation Lot A {month:02d}.{year}.xlsx"
    if not file_path.exists():
        st.info(f"Fichier facturation introuvable: {file_path.name}")
        return pd.DataFrame()

    try:
        df = None
        found_header = False

        # 🧠 On teste les 5 premières lignes pour trouver celle qui contient les bonnes colonnes
        for i in range(5):
            temp = pd.read_excel(file_path, engine="openpyxl", header=i, nrows=5)
            cols = [str(c).strip() for c in temp.columns]
            if "Date ouvrable" in cols and "Heures" in cols:
                df = pd.read_excel(file_path, engine="openpyxl", header=i)
                df.columns = cols  # nettoyage
                found_header = True
                break

        if not found_header:
            st.warning(
                f"Impossible de trouver les colonnes attendues ('Date ouvrable', 'Heures') dans {file_path.name}."
            )
            return pd.DataFrame()

        return df

    except Exception as e:
        st.warning(f"Erreur lors du chargement du fichier {file_path.name} : {e}")
        return pd.DataFrame()


# --- CHARGEMENT PAX NON BLOQUANT ---
# État initial
if 'pax_data_status' not in st.session_state:
    st.session_state.pax_data_status = "idle"   # idle | loading | loaded | failed
    st.session_state.pax_error = None

with st.sidebar:
    st.subheader("📦 Données PAX")
    # Bouton pour démarrer la tâche
    start = st.button(
        "Lancer le chargement PAX",
        disabled=(st.session_state.pax_data_status == "loading")
    )

    if start and st.session_state.pax_data_status != "loading":
        # Lancer la tâche dans un thread
        st.session_state.pax_error = None
        st.session_state.pax_data_status = "loading"
        st.session_state.pax_task = st.session_state.executor.submit(
            load_pax_data, PAX_DATA_FILE_PATH, "Passagers"
        )

    # Affichage de l'état + sondage
    if st.session_state.pax_data_status == "loading":
        st.status("Chargement PAX en cours… vous pouvez continuer la configuration en parallèle.")
        # Vérifie si le future est terminé
        if st.session_state.pax_task and st.session_state.pax_task.done():
            try:
                full_pax_data, overall_min_date, overall_max_date = st.session_state.pax_task.result()
                _finalize_pax_load(full_pax_data, overall_min_date, overall_max_date)
                st.session_state.pax_data_status = "loaded"
                st.toast("PAX chargés ✅", icon="✅")
            except Exception as e:
                st.session_state.pax_data_status = "failed"
                st.session_state.pax_error = str(e)
                st.toast("Échec chargement PAX ❌", icon="❌")

    elif st.session_state.pax_data_status == "loaded":
        st.success("Données PAX prêtes (hist. & forecast).")
        # Raccourcis d’info
        if 'pax_overall_min_date' in st.session_state and 'pax_overall_max_date' in st.session_state:
            st.caption(
                f"Période couverte : {st.session_state.pax_overall_min_date} → {st.session_state.pax_overall_max_date}"
            )

    elif st.session_state.pax_data_status == "failed":
        st.error(f"Erreur de chargement PAX : {st.session_state.pax_error or 'inconnue'}")
        if st.button("Réessayer"):
            st.session_state.pax_data_status = "idle"
            st.session_state.pax_task = None
            st.rerun()

    if st.session_state.pax_data_status in ("idle", "failed"):
        st.info("Cliquez sur le bouton ci-dessus pour charger les PAX pendant que vous réglez la configuration.")



# =================== Logique Budget ===================
def _ensure_adjusted_saisons_for_year(year: int):
    ref = st.session_state.get('saisons', pd.DataFrame())
    if ref.empty or 'Date Début' not in ref.columns or 'Date Fin' not in ref.columns:
        st.warning("Saisons de référence non définies ou invalides. Veuillez vérifier la configuration.")
        st.session_state.adjusted_saisons = pd.DataFrame(columns=['Saison', 'Date Début', 'Date Fin'])
        st.session_state.adjusted_saisons_year = year
        return

    # Check if recalculation is needed
    if 'adjusted_saisons' in st.session_state and \
       isinstance(st.session_state.adjusted_saisons, pd.DataFrame) and \
       not st.session_state.adjusted_saisons.empty and \
       st.session_state.get('adjusted_saisons_year') == year:
        return # Already calculated for this year

    adjusted_data = []
    has_error = False
    for _, row in ref.iterrows():
         try:
            start_ref_date = pd.to_datetime(row['Date Début']).date()
            end_ref_date = pd.to_datetime(row['Date Fin']).date()
            target_start = start_ref_date.replace(year=year)
            target_end = end_ref_date.replace(year=year)
            new_start_date = find_closest_weekday(target_start, start_ref_date.weekday())
            new_end_date = find_closest_weekday(target_end, end_ref_date.weekday())
            adjusted_data.append({'Saison': row['Saison'], 'Date Début': new_start_date, 'Date Fin': new_end_date})
         except Exception as e:
            st.error(f"Erreur lors de l'ajustement de la saison '{row.get('Saison', 'Inconnue')}': {e}")
            has_error = True
            break # Stop processing if an error occurs

    if has_error:
         st.session_state.adjusted_saisons = pd.DataFrame(columns=['Saison', 'Date Début', 'Date Fin'])
         st.session_state.adjusted_saisons_year = year
         return

    if adjusted_data:
        # Ensure the year starts on Jan 1st and ends on Dec 31st
        try:
            adjusted_data[0]['Date Début'] = dt.date(year, 1, 1)
            # Ensure end date doesn't go beyond Dec 31st
            adjusted_data[-1]['Date Fin'] = dt.date(year, 12, 31)

            # Adjust subsequent start dates to avoid overlaps or gaps
            for i in range(len(adjusted_data) - 1):
                # The next season starts the day after the current one ends
                adjusted_data[i+1]['Date Début'] = adjusted_data[i]['Date Fin'] + timedelta(days=1)
                # Ensure start date is not after end date within the same season
                if adjusted_data[i+1]['Date Début'] > adjusted_data[i+1]['Date Fin']:
                    # This implies an issue, maybe set end date same as start or handle as error
                    st.warning(f"Chevauchement ou date invalide détecté pour la saison {adjusted_data[i+1]['Saison']}. Ajustement forcé.")
                    adjusted_data[i+1]['Date Fin'] = adjusted_data[i+1]['Date Début'] # Minimal duration

        except IndexError:
             st.error("Erreur lors de l'ajustement des dates de début/fin d'année pour les saisons.")
             # Fallback to empty df
             st.session_state.adjusted_saisons = pd.DataFrame(columns=['Saison', 'Date Début', 'Date Fin'])
             st.session_state.adjusted_saisons_year = year
             return


    st.session_state.adjusted_saisons = pd.DataFrame(adjusted_data)
    st.session_state.adjusted_saisons_year = year



def generate_budget_state(year: int):
    sync_all_planning_grids_from_widgets()
    _sync_budget_annuel_state() # Ensures date types are correct
    _ensure_adjusted_saisons_for_year(year) # Ensures seasons for the target year are ready

    # Validate essential data
    if 'perimetres' not in st.session_state or not st.session_state.perimetres:
        st.error("Aucun périmètre défini. Veuillez vérifier la configuration.")
        return
    if 'personnel' not in st.session_state or st.session_state.personnel.empty:
        st.error("Aucun type de personnel défini. Veuillez vérifier la configuration.")
        return
    if 'adjusted_saisons' not in st.session_state or st.session_state.adjusted_saisons.empty:
         st.error(f"Le calendrier des saisons pour l'année {year} n'a pas pu être généré. Vérifiez les saisons de référence.")
         return


    try:
        days = pd.date_range(start=f"{year}-01-01", end=f"{year}-12-31", freq='D')
        calendar_df = pd.DataFrame({'Date': days})
        calendar_df['Jour'] = _day_name_fr(calendar_df['Date'])

        # Robust season assignment
        def assign_season(date_):
            d = date_.date() # Convert timestamp to date object
            for _, r in st.session_state.adjusted_saisons.iterrows():
                # Ensure comparison between date objects
                start_date = pd.to_datetime(r['Date Début']).date()
                end_date = pd.to_datetime(r['Date Fin']).date()
                if start_date <= d <= end_date:
                    return r['Saison']
            # Fallback if no season matches (should not happen if _ensure_adjusted_saisons is correct)
            st.warning(f"Date {d} n'appartient à aucune saison définie. Utilisation de 'Standard'.")
            return "Standard"

        calendar_df['Saison'] = calendar_df['Date'].apply(assign_season)
        calendar_df['Jour_Type_Global'] = calendar_df['Jour'] + " " + calendar_df['Saison']

        time_slots_default = [f"{h:02d}:{m:02d}" for h in range(4, 24) for m in (0, 30)]


        # Calculate hours and costs per category
        for category_key, perimetres_list in st.session_state.perimetres.items():
            planning_dict = st.session_state.planning_data.get(category_key, {})
            heures_col = f"Heures_{category_key}"
            cout_col = f"Coût_{category_key}"
            calendar_df[heures_col] = 0.0 # Initialize column

            if category_key == "AT":
                heures_list = []
                for jtg in calendar_df['Jour_Type_Global']:
                    # Use _ensure_grid to handle missing JTs gracefully
                    _, grid_df = _ensure_grid(planning_dict, jtg, perimetres_list, time_slots_default)
                    heures_list.append(grid_df.values.sum() * 0.5)
                calendar_df[heures_col] = heures_list
            else:
                 # Use default grid for other categories
                _, default_grid = _ensure_grid(planning_dict, "Default", perimetres_list, time_slots_default)
                daily_hours = default_grid.values.sum() * 0.5
                calendar_df[heures_col] = daily_hours

            # Calculate cost
            personnel_type = st.session_state.get('cost_mapping', {}).get(category_key)
            calendar_df[cout_col] = 0.0 # Initialize column
            if personnel_type:
                tarif_row = st.session_state.personnel[st.session_state.personnel['Type'] == personnel_type]
                if not tarif_row.empty:
                    try:
                        tarif = float(tarif_row['Coût Horaire'].iloc[0])
                        calendar_df[cout_col] = calendar_df[heures_col] * tarif
                    except (ValueError, TypeError):
                         st.warning(f"Tarif invalide pour le type de personnel '{personnel_type}'. Coût pour '{category_key}' mis à 0.")

        # Calculate totals
        heure_cols = [c for c in calendar_df.columns if c.startswith('Heures_') and c != 'Heures_Total_Jour']
        cout_cols = [c for c in calendar_df.columns if c.startswith('Coût_') and c != 'Coût_Total_Jour']
        calendar_df['Heures_Total_Jour'] = calendar_df[heure_cols].sum(axis=1)
        calendar_df['Coût_Total_Jour'] = calendar_df[cout_cols].sum(axis=1)

        # Create summary DataFrame
        summary = pd.DataFrame()
        if cout_cols:
             summary_data = calendar_df[cout_cols].sum()
             summary = pd.DataFrame({'Catégorie': summary_data.index, 'Coût': summary_data.values})
             summary['Catégorie'] = summary['Catégorie'].str.replace('Coût_', '', regex=False)


        # Update budget state
        st.session_state.budget_state = {
            'year': year,
            'calendar_df': calendar_df,
            'cout_cols': cout_cols, # Store list of cost columns used
            'summary': summary,
            'totals': {
                'heures_annuel': calendar_df['Heures_Total_Jour'].sum(),
                'cout_annuel': calendar_df['Coût_Total_Jour'].sum()
            },
            'selected_date': st.session_state.get('budget_state', {}).get('selected_date', dt.date(year, 1, 1))
        }
    except Exception as e:
         st.error(f"Une erreur s'est produite lors de la génération du budget : {e}")
         # Optionally reset state or handle specific errors
         st.session_state.budget_state = {} # Reset state on error

def _daily_pax_total(pax_df_30min: pd.DataFrame, date_: dt.date, flux: str = "Tous") -> float:
    if pax_df_30min is None or pax_df_30min.empty:
        return 0.0
    day = pax_df_30min[pax_df_30min.index.date == date_]
    if day.empty:
        return 0.0
    if flux == "Arrivée":
        total = (day.get("Pax_Schengen_A", 0).fillna(0) + day.get("Pax_NonSchengen_A", 0).fillna(0)).sum()
    elif flux == "Départ":
        total = (day.get("Pax_Schengen_D", 0).fillna(0) + day.get("Pax_NonSchengen_D", 0).fillna(0)).sum()
    else:
        total = (
            day.get("Pax_Schengen_A", 0).fillna(0) + day.get("Pax_Schengen_D", 0).fillna(0) +
            day.get("Pax_NonSchengen_A", 0).fillna(0) + day.get("Pax_NonSchengen_D", 0).fillna(0)
        ).sum()
    return float(total)


def _estimate_at_hours_from_pax_variation_core(historical_date: dt.date,
                                               forecast_date: dt.date,
                                               flux: str = "Tous") -> dict:
    if "df_factu_at" not in st.session_state:
        st.session_state.df_factu_at = load_facturation_at(FACTU_AT_DIR)
    df_at = st.session_state.df_factu_at
    h_hist = 0.0
    if (df_at is not None) and (not df_at.empty):
        row = df_at.loc[df_at["Date"] == historical_date]
        if not row.empty:
            h_hist = float(row["Heures_AT_realisees"].sum())

    hist_df = st.session_state.get("pax_historical_data", pd.DataFrame())
    fc_df   = st.session_state.get("pax_forecast_data", pd.DataFrame())
    pax_hist = _daily_pax_total(hist_df, historical_date, flux)
    pax_fc   = _daily_pax_total(fc_df,   forecast_date,   flux)

    facteur = (pax_fc / pax_hist) if pax_hist > 0 else None
    est = _round_half(h_hist * facteur) if (facteur is not None) else 0.0

    return {"heures_hist": h_hist, "pax_hist": pax_hist, "pax_fc": pax_fc,
            "facteur": facteur, "heures_estimees": est}

def estimate_at_hours_from_pax_variation(*args, **kwargs) -> dict:
    # Accepte:
    # - date_hist=..., date_fc=..., flux=...
    # - historical_date=..., forecast_date=..., flux=...
    # - positionnels (historical_date, forecast_date[, flux])
    if args:
        historical_date = args[0]
        forecast_date   = args[1] if len(args) > 1 else None
        flux            = args[2] if len(args) > 2 else kwargs.get("flux", "Tous")
    else:
        historical_date = kwargs.get("date_hist") or kwargs.get("historical_date")
        forecast_date   = kwargs.get("date_fc")   or kwargs.get("forecast_date")
        flux            = kwargs.get("flux", "Tous")

    if historical_date is None or forecast_date is None:
        raise TypeError("estimate_at_hours_from_pax_variation() requires two dates (historical & forecast).")

    return _estimate_at_hours_from_pax_variation_core(historical_date, forecast_date, flux)

def _to_float_hours(x) -> float:
    """Convertit une valeur de type 'Heures' en float, gère les virgules."""
    try:
        return float(str(x).replace(",", "."))
    except:
        return 0.0


def get_billed_hours_for_date(date_obj: dt.date) -> float:
    """
    Récupère la valeur de la colonne 'Heures' pour la ligne 'Date ouvrable' == 'Total dd.mm.yyyy'
    dans le fichier mensuel correspondant.
    Retourne 0.0 si non trouvé.
    """
    df = load_facturation_at_month(date_obj.year, date_obj.month)
    if df.empty:
        return 0.0

    if "Date ouvrable" not in df.columns or "Heures" not in df.columns:
        st.warning("Colonnes attendues manquantes ('Date ouvrable', 'Heures').")
        return 0.0

    date_str = date_obj.strftime("%d.%m.%Y")
    target_exact = f"Total {date_str}"

    s = df["Date ouvrable"].astype(str).str.strip()

    # 1) Correspondance exacte "Total dd.mm.yyyy"
    match = df[s == target_exact]

    # 2) Si besoin, tolère les espaces variables ("Total   dd.mm.yyyy")
    if match.empty:
        pattern = rf"^Total\s*{re.escape(date_str)}$"
        match = df[s.str.match(pattern, na=False)]

    # 3) Si Excel a stocké une vraie date, on tente conversion
    if match.empty:
        def normalize_total(v):
            try:
                d = pd.to_datetime(v, dayfirst=True, errors="raise")
                return f"Total {d.strftime('%d.%m.%Y')}"
            except:
                return str(v).strip()
        s2 = df["Date ouvrable"].apply(normalize_total)
        match = df[s2 == target_exact]

    if match.empty:
        return 0.0

    heures = match["Heures"].apply(_to_float_hours).sum()
    return float(heures)

def _round_half(x: float) -> float:
    """Arrondi au pas de 0.5h (30 minutes)."""
    return float(round(x * 2) / 2.0)


def estimate_at_hours_from_pax_variation(historical_date: dt.date, forecast_date: dt.date) -> dict:
    """
    Calcule :
    - heures_hist = heures facturées réelles (via get_billed_hours_for_date)
    - pax_hist / pax_fc = volumes PAX historiques et prévisionnels
    - heures_estimees = heures_hist * (pax_fc / pax_hist)
    Renvoie un dictionnaire pour affichage dans Streamlit.
    """
    heures_hist = get_billed_hours_for_date(historical_date)

    hist_df = st.session_state.get("pax_historical_data", pd.DataFrame())
    fc_df = st.session_state.get("pax_forecast_data", pd.DataFrame())

    pax_hist = _daily_pax_total(hist_df, historical_date)
    pax_fc = _daily_pax_total(fc_df, forecast_date)

    facteur = (pax_fc / pax_hist) if pax_hist > 0 else None
    heures_estimees = _round_half(heures_hist * facteur) if facteur is not None else 0.0

    return {
        "heures_hist": heures_hist,
        "pax_hist": pax_hist,
        "pax_fc": pax_fc,
        "facteur": facteur,
        "heures_estimees": heures_estimees
    }


# =================== Initialisation des données (Base 2026) ===================
def initialize_session_state_2026():
    # Check if data is already loaded to prevent re-initialization
    # Note: The original code had a 'return' here which might prevent updates if called again.
    # Consider if this check is needed or if re-initialization should always happen.
    # if 'data_loaded' in st.session_state and st.session_state.data_loaded:
    #    return # Skip if already initialized

    st.session_state.personnel = pd.DataFrame([
        {'Type': 'AT', 'Coût Horaire': 45.50}, {'Type': 'ATR', 'Coût Horaire': 54.00},
        {'Type': 'CSC', 'Coût Horaire': 42.00}, {'Type': 'EES', 'Coût Horaire': 43.00},
        {'Type': 'AT Resp', 'Coût Horaire': 54.00}, {'Type': 'Sect FR', 'Coût Horaire': 41.00},
    ])

    st.session_state.saisons = pd.DataFrame([
        {'Saison': 'Hiver', 'Date Début': dt.date(2026, 1, 1), 'Date Fin': dt.date(2026, 3, 28)},
        {'Saison': 'Standard', 'Date Début': dt.date(2026, 3, 29), 'Date Fin': dt.date(2026, 6, 27)},
        {'Saison': 'Été', 'Date Début': dt.date(2026, 6, 28), 'Date Fin': dt.date(2026, 8, 29)},
        {'Saison': 'Standard', 'Date Début': dt.date(2026, 8, 30), 'Date Fin': dt.date(2026, 10, 24)},
        {'Saison': 'Hiver', 'Date Début': dt.date(2026, 10, 25), 'Date Fin': dt.date(2026, 12, 31)},
    ])
    st.session_state.reference_year_saisons = 2026

    st.session_state.perimetres = {
        "AT": ['Check in 1', 'Check in 2', 'Check in 3', 'Guichet info', 'Transit', 'Aile Est Départ', 'Aile Est Départ ABC', 'Aile Est Arrivée', 'Aile Est Arrivée ABC', 'Aile Est Arrivée Transf.', 'Aile Est Arrivée Dispatch.', "Sect. France", "Visitor's Center", 'Hall bagage (+ Transfert)', 'Accueil famille CSC', 'Priority Lane'],
        "CSC": ['CSC 1 Dispatch E-gate', 'CSC 2 Assistant E-gate', 'CSC 3 Dispatch PL / M 1-8', 'CSC 4 Dispatch M 9-16', 'CSC 5 Dispatch M Boosted', 'CSC 6 SR1 M Boosted', 'CSC 7 SR1 M Boosted', 'CSC 8 SR1 M Boosted', 'CSC 9 SR1 M Boosted'],
        "EES": ['EES 1', 'EES 2', 'EES 3', 'EES 4', 'EES 5', 'EES 6', 'EES 7', 'EES 8'],
        "Sect. FR": ['Entrée Secteur France', 'Sortie Secteur France'],
        "AT Resp.": ['AT Resp. Aile Est', 'AT Resp. CSC', 'Coordinateur']
    }

    st.session_state.planning_data = {}
    time_slots = [f"{h:02d}:{m:02d}" for h in range(4, 24) for m in (0, 30)]

    def parse_grid_from_markers(data_dict, perimetres_list):
        # Ensure perimetres_list is used for the index
        grid = pd.DataFrame(0, index=perimetres_list, columns=time_slots, dtype=int)
        for perimetre, markers in data_dict.items():
            if perimetre in grid.index:
                 # Ensure markers list has the correct length, padding with NaN if needed
                 # Using 0 instead of NaN for padding aligns better with integer type
                 full_markers = (markers + [0] * len(time_slots))[:len(time_slots)]
                 # Convert markers to 0 or 1, treating non-1 values as 0
                 # Use np.isnan to handle actual NaN values if they exist in the input data
                 grid.loc[perimetre] = [1 if (not pd.isna(m) and str(m).strip() == '1') else 0 for m in full_markers]
        # Fill any remaining NaNs (if any somehow occurred) with 0 and ensure type
        return grid.fillna(0).astype(int).clip(0, 1)


    # Initialize planning data for each category
    for cat, perims in st.session_state.perimetres.items():
        st.session_state.planning_data[cat] = {} # Ensure dict exists

        # Apply specific initial data if available
        if cat == 'CSC':
            # Use actual length of time_slots for padding
            csc_data = {p:[1]*34 + [0]*(len(time_slots)-34) for p in perims} # 34 is 17 hours * 2 slots/hour
            st.session_state.planning_data[cat]['Default'] = parse_grid_from_markers(csc_data, perims)
        elif cat == 'EES':
             # 4 empty slots (2 hours) then 32 '1's (16 hours), pad rest with 0
             ees_data = {p:([0]*4 + [1]*32 + [0]*(len(time_slots)-36))[:len(time_slots)] for p in perims}
             st.session_state.planning_data[cat]['Default'] = parse_grid_from_markers(ees_data, perims)
        elif cat == 'Sect. FR':
            # 41 slots (20.5 hours), pad rest with 0
            sect_fr_data = {p: ([1]*41 + [0]*(len(time_slots)-41))[:len(time_slots)] for p in perims}
            st.session_state.planning_data[cat]['Default'] = parse_grid_from_markers(sect_fr_data, perims)
        elif cat == 'AT Resp.':
            at_resp_data = {
                 'AT Resp. Aile Est': [0]*4 + [1]*28 + [0]*(len(time_slots)-32), # 4 empty (2h), 28 ones (14h)
                 'AT Resp. CSC': [1]*32 + [0]*(len(time_slots)-32), # 32 ones (16h)
                 'Coordinateur': [1]*3 + [0]*(len(time_slots)-3) # 3 ones (1.5h)
             }
             # Ensure all perimeters for AT Resp are included, padding unspecified ones with 0s
            full_at_resp_data = {p: at_resp_data.get(p, [0]*len(time_slots)) for p in perims}
            st.session_state.planning_data[cat]['Default'] = parse_grid_from_markers(full_at_resp_data, perims)

        elif cat == 'AT':
            # Provided data for AT - Needs careful mapping and padding
            at_day_type_data = {
                "Lundi Standard": {
                    "Aile Est Arrivée": [np.nan]*5 + [1]*34, "Aile Est Arrivée ABC": [np.nan]*5 + [1]*34,
                    "Aile Est Arrivée Transf.": [np.nan]*9 + [1]*24 + [np.nan]*6, "Aile Est Arrivée dispatch": [np.nan]*3 + [1]*26 + [np.nan]*10,
                    "Aile Est Départ": [1]*29 + [np.nan]*10, "Aile Est Départ ABC": [np.nan]*1 + [1]*32 + [np.nan]*6,
                    "Check in 1": [np.nan]*1 + [1]*28 + [np.nan]*10, "Check in 2": [np.nan]*9 + [1]*20 + [np.nan]*10,
                    "Guichet info": [np.nan]*9 + [1]*18 + [np.nan]*12, "Hall bagage (+ Transfert)": [np.nan]*9 + [1]*28 + [np.nan]*2,
                    "Priority Lane": [np.nan]*1 + [1]*28 + [np.nan]*10, "Transit": [np.nan]*1 + [1]*30 + [np.nan]*8,
                    "Visitor's Center": [np.nan]*5 + [1]*4 + [np.nan]*20 + [1]*10,
                },
                "Lundi Été": {
                    "Accueil famille AE": [np.nan]*10 + [1]*20 + [np.nan]*10, "Accueil famille CSC": [1]*28 + [np.nan]*12,
                    "Aile Est Arrivée": [np.nan]*6 + [1]*34, "Aile Est Arrivée ABC": [np.nan]*6 + [1]*34,
                    "Aile Est Arrivée Transf.": [np.nan]*10 + [1]*20 + [np.nan]*10, "Aile Est Arrivée dispatch": [np.nan]*4 + [1]*26 + [np.nan]*10,
                    "Aile Est Départ": [np.nan]*2 + [1]*34 + [np.nan]*4, "Aile Est Départ ABC": [np.nan]*2 + [1]*34 + [np.nan]*4,
                    "Check in 1": [1]*30 + [np.nan]*10, "Check in 2": [np.nan]*2 + [1]*30 + [np.nan]*8,
                    "Guichet info": [np.nan]*10 + [1]*20 + [np.nan]*10, "Hall bagage (+ Transfert)": [np.nan]*14 + [1]*24 + [np.nan]*2,
                    "Priority Lane": [1]*32 + [np.nan]*8, "Sect. France": [np.nan]*28 + [1]*4 + [np.nan]*8,
                    "Transit": [np.nan]*2 + [1]*34 + [np.nan]*4, "Visitor's Center": [np.nan]*6 + [1]*4 + [np.nan]*20 + [1]*10,
                },
                "Lundi Hiver": {
                    "Accueil famille CSC": [1]*31 + [np.nan]*8, "Accès Sect. France": [np.nan]*9 + [1]*20 + [np.nan]*10,
                    "Aile Est Arrivée": [np.nan]*5 + [1]*34, "Aile Est Arrivée ABC": [np.nan]*5 + [1]*34,
                    "Aile Est Arrivée Transf.": [np.nan]*9 + [1]*29 + [np.nan]*1, "Aile Est Arrivée dispatch": [np.nan]*3 + [1]*26 + [np.nan]*10,
                    "Aile Est Départ": [1]*35 + [np.nan]*4, "Aile Est Départ ABC": [np.nan]*1 + [1]*34 + [np.nan]*4,
                    "Check in 1": [np.nan]*1 + [1]*26 + [np.nan]*12, "Check in 2": [np.nan]*5 + [1]*28 + [np.nan]*6,
                    "Guichet info": [np.nan]*9 + [1]*18 + [np.nan]*12, "Hall bagage (+ Transfert)": [np.nan]*9 + [1]*29 + [np.nan]*1,
                    "Priority Lane": [1]*29 + [np.nan]*10, "Transit": [np.nan]*1 + [1]*30 + [np.nan]*8,
                    "Visitor's Center": [np.nan]*5 + [1]*4 + [np.nan]*20 + [1]*10,
                },
                "Mardi Standard": {
                    "Aile Est Arrivée": [np.nan]*5 + [1]*34, "Aile Est Arrivée ABC": [np.nan]*5 + [1]*34,
                    "Aile Est Arrivée Transf.": [np.nan]*9 + [1]*22 + [np.nan]*8, "Aile Est Arrivée dispatch": [np.nan]*3 + [1]*26 + [np.nan]*10,
                    "Aile Est Départ": [1]*35 + [np.nan]*4, "Aile Est Départ ABC": [np.nan]*1 + [1]*32 + [np.nan]*6,
                    "Check in 1": [np.nan]*1 + [1]*24 + [np.nan]*14, "Guichet info": [np.nan]*9 + [1]*16 + [np.nan]*14,
                    "Hall bagage (+ Transfert)": [np.nan]*13 + [1]*24 + [np.nan]*2, "Priority Lane": [np.nan]*1 + [1]*30 + [np.nan]*8,
                    "Transit": [np.nan]*1 + [1]*30 + [np.nan]*8, "Visitor's Center": [np.nan]*5 + [1]*4 + [np.nan]*20 + [1]*10,
                },
                 "Mardi Été": {
                    "Accueil famille CSC": [1]*28 + [np.nan]*12, "Aile Est Arrivée": [np.nan]*6 + [1]*34,
                    "Aile Est Arrivée ABC": [np.nan]*6 + [1]*34, "Aile Est Arrivée Transf.": [np.nan]*10 + [1]*20 + [np.nan]*10,
                    "Aile Est Arrivée dispatch": [np.nan]*4 + [1]*26 + [np.nan]*10, "Aile Est Départ": [np.nan]*2 + [1]*34 + [np.nan]*4,
                    "Aile Est Départ ABC": [np.nan]*2 + [1]*34 + [np.nan]*4, "Check in 1": [1]*30 + [np.nan]*10,
                    "Guichet info": [np.nan]*10 + [1]*20 + [np.nan]*10, "Hall bagage (+ Transfert)": [np.nan]*10 + [1]*28 + [np.nan]*2,
                    "Priority Lane": [1]*32 + [np.nan]*8, "Transit": [np.nan]*2 + [1]*32 + [np.nan]*6,
                    "Visitor's Center": [np.nan]*6 + [1]*4 + [np.nan]*20 + [1]*10,
                },
                "Mardi Hiver": {
                    "Accès Sect. France": [np.nan]*9 + [1]*20 + [np.nan]*10, "Aile Est Arrivée": [np.nan]*5 + [1]*34,
                    "Aile Est Arrivée ABC": [np.nan]*5 + [1]*34, "Aile Est Arrivée Transf.": [np.nan]*9 + [1]*29 + [np.nan]*1,
                    "Aile Est Arrivée dispatch": [np.nan]*3 + [1]*26 + [np.nan]*10, "Aile Est Départ": [1]*35 + [np.nan]*4,
                    "Aile Est Départ ABC": [np.nan]*1 + [1]*34 + [np.nan]*4, "Check in 1": [np.nan]*1 + [1]*26 + [np.nan]*12,
                    "Check in 2": [np.nan]*5 + [1]*28 + [np.nan]*6, "Guichet info": [np.nan]*9 + [1]*18 + [np.nan]*12,
                    "Hall bagage (+ Transfert)": [np.nan]*9 + [1]*29 + [np.nan]*1, "Priority Lane": [1]*29 + [np.nan]*10,
                    "Transit": [np.nan]*1 + [1]*30 + [np.nan]*8, "Visitor's Center": [np.nan]*5 + [1]*4 + [np.nan]*20 + [1]*10,
                },
                "Mercredi Standard": {
                    "Aile Est Arrivée": [np.nan]*5 + [1]*34, "Aile Est Arrivée ABC": [np.nan]*5 + [1]*34,
                    "Aile Est Arrivée Transf.": [np.nan]*9 + [1]*22 + [np.nan]*8, "Aile Est Arrivée dispatch": [np.nan]*3 + [1]*26 + [np.nan]*10,
                    "Aile Est Départ": [1]*35 + [np.nan]*4, "Aile Est Départ ABC": [np.nan]*1 + [1]*32 + [np.nan]*6,
                    "Check in 1": [np.nan]*1 + [1]*24 + [np.nan]*14, "Guichet info": [np.nan]*9 + [1]*16 + [np.nan]*14,
                    "Hall bagage (+ Transfert)": [np.nan]*13 + [1]*24 + [np.nan]*2, "Priority Lane": [np.nan]*1 + [1]*30 + [np.nan]*8,
                    "Transit": [np.nan]*1 + [1]*30 + [np.nan]*8, "Visitor's Center": [np.nan]*5 + [1]*4 + [np.nan]*20 + [1]*10,
                },
                "Mercredi Été": {
                    "Accueil famille CSC": [1]*28 + [np.nan]*12, "Aile Est Arrivée": [np.nan]*6 + [1]*34,
                    "Aile Est Arrivée ABC": [np.nan]*6 + [1]*34, "Aile Est Arrivée Transf.": [np.nan]*10 + [1]*20 + [np.nan]*10,
                    "Aile Est Arrivée dispatch": [np.nan]*4 + [1]*26 + [np.nan]*10, "Aile Est Départ": [np.nan]*2 + [1]*34 + [np.nan]*4,
                    "Aile Est Départ ABC": [np.nan]*2 + [1]*34 + [np.nan]*4, "Check in 1": [1]*30 + [np.nan]*10,
                    "Guichet info": [np.nan]*10 + [1]*20 + [np.nan]*10, "Hall bagage (+ Transfert)": [np.nan]*10 + [1]*28 + [np.nan]*2,
                    "Priority Lane": [1]*32 + [np.nan]*8, "Transit": [np.nan]*2 + [1]*32 + [np.nan]*6,
                    "Visitor's Center": [np.nan]*6 + [1]*4 + [np.nan]*20 + [1]*10,
                },
                "Mercredi Hiver": {
                    "Accès Sect. France": [np.nan]*9 + [1]*20 + [np.nan]*10, "Aile Est Arrivée": [np.nan]*5 + [1]*34,
                    "Aile Est Arrivée ABC": [np.nan]*5 + [1]*34, "Aile Est Arrivée Transf.": [np.nan]*9 + [1]*29 + [np.nan]*1,
                    "Aile Est Arrivée dispatch": [np.nan]*3 + [1]*26 + [np.nan]*10, "Aile Est Départ": [1]*35 + [np.nan]*4,
                    "Aile Est Départ ABC": [np.nan]*1 + [1]*34 + [np.nan]*4, "Check in 1": [np.nan]*1 + [1]*26 + [np.nan]*12,
                    "Check in 2": [np.nan]*5 + [1]*28 + [np.nan]*6, "Guichet info": [np.nan]*9 + [1]*18 + [np.nan]*12,
                    "Hall bagage (+ Transfert)": [np.nan]*9 + [1]*29 + [np.nan]*1, "Priority Lane": [1]*29 + [np.nan]*10,
                    "Transit": [np.nan]*1 + [1]*30 + [np.nan]*8, "Visitor's Center": [np.nan]*5 + [1]*4 + [np.nan]*20 + [1]*10,
                },
                "Jeudi Standard": {
                    "Aile Est Arrivée": [np.nan]*5 + [1]*34, "Aile Est Arrivée ABC": [np.nan]*5 + [1]*34,
                    "Aile Est Arrivée Transf.": [np.nan]*9 + [1]*22 + [np.nan]*8, "Aile Est Arrivée dispatch": [np.nan]*3 + [1]*26 + [np.nan]*10,
                    "Aile Est Départ": [1]*35 + [np.nan]*4, "Aile Est Départ ABC": [np.nan]*1 + [1]*32 + [np.nan]*6,
                    "Check in 1": [np.nan]*1 + [1]*24 + [np.nan]*14, "Guichet info": [np.nan]*9 + [1]*16 + [np.nan]*14,
                    "Hall bagage (+ Transfert)": [np.nan]*13 + [1]*24 + [np.nan]*2, "Priority Lane": [np.nan]*1 + [1]*30 + [np.nan]*8,
                    "Transit": [np.nan]*1 + [1]*30 + [np.nan]*8, "Visitor's Center": [np.nan]*5 + [1]*4 + [np.nan]*20 + [1]*10,
                },
                "Jeudi Été": {
                    "Accueil famille CSC": [1]*28 + [np.nan]*12, "Aile Est Arrivée": [np.nan]*6 + [1]*34,
                    "Aile Est Arrivée ABC": [np.nan]*6 + [1]*34, "Aile Est Arrivée Transf.": [np.nan]*10 + [1]*20 + [np.nan]*10,
                    "Aile Est Arrivée dispatch": [np.nan]*4 + [1]*26 + [np.nan]*10, "Aile Est Départ": [np.nan]*2 + [1]*34 + [np.nan]*4,
                    "Aile Est Départ ABC": [np.nan]*2 + [1]*34 + [np.nan]*4, "Check in 1": [1]*30 + [np.nan]*10,
                    "Guichet info": [np.nan]*10 + [1]*20 + [np.nan]*10, "Hall bagage (+ Transfert)": [np.nan]*10 + [1]*28 + [np.nan]*2,
                    "Priority Lane": [1]*32 + [np.nan]*8, "Transit": [np.nan]*2 + [1]*32 + [np.nan]*6,
                    "Visitor's Center": [np.nan]*6 + [1]*4 + [np.nan]*20 + [1]*10,
                },
                "Jeudi Hiver": {
                    "Accès Sect. France": [np.nan]*9 + [1]*20 + [np.nan]*10, "Aile Est Arrivée": [np.nan]*5 + [1]*34,
                    "Aile Est Arrivée ABC": [np.nan]*5 + [1]*34, "Aile Est Arrivée Transf.": [np.nan]*9 + [1]*29 + [np.nan]*1,
                    "Aile Est Arrivée dispatch": [np.nan]*3 + [1]*26 + [np.nan]*10, "Aile Est Départ": [1]*35 + [np.nan]*4,
                    "Aile Est Départ ABC": [np.nan]*1 + [1]*34 + [np.nan]*4, "Check in 1": [np.nan]*1 + [1]*26 + [np.nan]*12,
                    "Check in 2": [np.nan]*5 + [1]*28 + [np.nan]*6, "Guichet info": [np.nan]*9 + [1]*18 + [np.nan]*12,
                    "Hall bagage (+ Transfert)": [np.nan]*9 + [1]*29 + [np.nan]*1, "Priority Lane": [1]*29 + [np.nan]*10,
                    "Transit": [np.nan]*1 + [1]*30 + [np.nan]*8, "Visitor's Center": [np.nan]*5 + [1]*4 + [np.nan]*20 + [1]*10,
                },
                "Vendredi Standard": {
                    "Aile Est Arrivée": [np.nan]*5 + [1]*34, "Aile Est Arrivée ABC": [np.nan]*5 + [1]*34,
                    "Aile Est Arrivée Transf.": [np.nan]*9 + [1]*24 + [np.nan]*6, "Aile Est Arrivée dispatch": [np.nan]*3 + [1]*26 + [np.nan]*10,
                    "Aile Est Départ": [1]*29 + [np.nan]*10, "Aile Est Départ ABC": [np.nan]*1 + [1]*32 + [np.nan]*6,
                    "Check in 1": [np.nan]*1 + [1]*28 + [np.nan]*10, "Guichet info": [np.nan]*9 + [1]*18 + [np.nan]*12,
                    "Hall bagage (+ Transfert)": [np.nan]*9 + [1]*28 + [np.nan]*2, "Priority Lane": [np.nan]*1 + [1]*28 + [np.nan]*10,
                    "Transit": [np.nan]*1 + [1]*30 + [np.nan]*8, "Visitor's Center": [np.nan]*5 + [1]*4 + [np.nan]*20 + [1]*10,
                },
                "Vendredi Été": {
                    "Accueil famille AE": [np.nan]*10 + [1]*20 + [np.nan]*10, "Accueil famille CSC": [1]*28 + [np.nan]*12,
                    "Aile Est Arrivée": [np.nan]*6 + [1]*34, "Aile Est Arrivée ABC": [np.nan]*6 + [1]*34,
                    "Aile Est Arrivée Transf.": [np.nan]*10 + [1]*20 + [np.nan]*10, "Aile Est Arrivée dispatch": [np.nan]*4 + [1]*26 + [np.nan]*10,
                    "Aile Est Départ": [np.nan]*1 + [1]*35 + [np.nan]*4, "Aile Est Départ ABC": [np.nan]*1 + [1]*35 + [np.nan]*4,
                    "Check in 1": [1]*28 + [np.nan]*12, "Check in 2": [1]*32 + [np.nan]*8,
                    "Guichet info": [np.nan]*10 + [1]*18 + [np.nan]*12, "Hall bagage (+ Transfert)": [np.nan]*14 + [1]*24 + [np.nan]*2,
                    "Priority Lane": [np.nan]*10 + [1]*22 + [np.nan]*8, "Transit": [np.nan]*1 + [1]*35 + [np.nan]*4,
                    "Visitor's Center": [np.nan]*6 + [1]*4 + [np.nan]*20 + [1]*10,
                },
                "Vendredi Hiver": {
                    "Accueil famille CSC": [1]*31 + [np.nan]*8, "Accès Sect. France": [np.nan]*9 + [1]*20 + [np.nan]*10,
                    "Aile Est Arrivée": [np.nan]*5 + [1]*34, "Aile Est Arrivée ABC": [np.nan]*5 + [1]*34,
                    "Aile Est Arrivée Transf.": [np.nan]*9 + [1]*29 + [np.nan]*1, "Aile Est Arrivée dispatch": [np.nan]*3 + [1]*26 + [np.nan]*10,
                    "Aile Est Départ": [1]*35 + [np.nan]*4, "Aile Est Départ ABC": [np.nan]*1 + [1]*34 + [np.nan]*4,
                    "Check in 1": [np.nan]*1 + [1]*26 + [np.nan]*12, "Check in 2": [np.nan]*5 + [1]*28 + [np.nan]*6,
                    "Guichet info": [np.nan]*9 + [1]*18 + [np.nan]*12, "Hall bagage (+ Transfert)": [np.nan]*9 + [1]*29 + [np.nan]*1,
                    "Priority Lane": [1]*29 + [np.nan]*10, "Transit": [np.nan]*1 + [1]*30 + [np.nan]*8,
                    "Visitor's Center": [np.nan]*5 + [1]*4 + [np.nan]*20 + [1]*10,
                },
                "Samedi Standard": {
                    "Aile Est Arrivée": [np.nan]*5 + [1]*34, "Aile Est Arrivée ABC": [np.nan]*5 + [1]*34,
                    "Aile Est Arrivée Transf.": [np.nan]*9 + [1]*24 + [np.nan]*6, "Aile Est Arrivée dispatch": [np.nan]*3 + [1]*26 + [np.nan]*10,
                    "Aile Est Départ": [1]*29 + [np.nan]*10, "Aile Est Départ ABC": [np.nan]*1 + [1]*32 + [np.nan]*6,
                    "Check in 1": [np.nan]*1 + [1]*28 + [np.nan]*10, "Guichet info": [np.nan]*9 + [1]*18 + [np.nan]*12,
                    "Hall bagage (+ Transfert)": [np.nan]*9 + [1]*28 + [np.nan]*2, "Priority Lane": [np.nan]*1 + [1]*28 + [np.nan]*10,
                    "Transit": [np.nan]*1 + [1]*30 + [np.nan]*8, "Visitor's Center": [np.nan]*5 + [1]*4 + [np.nan]*20 + [1]*10,
                },
                "Samedi Été": {
                    "Accueil famille AE": [np.nan]*10 + [1]*20 + [np.nan]*10, "Accueil famille CSC": [1]*28 + [np.nan]*12,
                    "Aile Est Arrivée": [np.nan]*6 + [1]*34, "Aile Est Arrivée ABC": [np.nan]*6 + [1]*34,
                    "Aile Est Arrivée Transf.": [np.nan]*10 + [1]*20 + [np.nan]*10, "Aile Est Arrivée dispatch": [np.nan]*4 + [1]*26 + [np.nan]*10,
                    "Aile Est Départ": [np.nan]*1 + [1]*35 + [np.nan]*4, "Aile Est Départ ABC": [np.nan]*1 + [1]*35 + [np.nan]*4,
                    "Check in 1": [1]*28 + [np.nan]*12, "Check in 2": [np.nan]*4 + [1]*28 + [np.nan]*8,
                    "Guichet info": [np.nan]*10 + [1]*18 + [np.nan]*12, "Hall bagage (+ Transfert)": [np.nan]*14 + [1]*24 + [np.nan]*2,
                    "Priority Lane": [1]*28 + [np.nan]*12, "Transit": [np.nan]*1 + [1]*35 + [np.nan]*4,
                    "Visitor's Center": [np.nan]*6 + [1]*4 + [np.nan]*20 + [1]*10,
                },
                "Samedi Hiver": {
                    "Accueil famille CSC": [1]*31 + [np.nan]*8, "Accès Sect. France": [np.nan]*7 + [1]*22 + [np.nan]*10,
                    "Aile Est Arrivée": [np.nan]*5 + [1]*34, "Aile Est Arrivée ABC": [np.nan]*5 + [1]*34,
                    "Aile Est Arrivée Transf.": [np.nan]*7 + [1]*31 + [np.nan]*1, "Aile Est Arrivée dispatch": [np.nan]*3 + [1]*26 + [np.nan]*10,
                    "Aile Est Départ": [np.nan]*1 + [1]*32 + [np.nan]*6, "Aile Est Départ ABC": [np.nan]*1 + [1]*34 + [np.nan]*4,
                    "Check in 1": [np.nan]*1 + [1]*32 + [np.nan]*6, "Check in 2": [np.nan]*1 + [1]*32 + [np.nan]*6,
                    "Check in 3": [1]*29 + [np.nan]*10, "Guichet info": [np.nan]*5 + [1]*24 + [np.nan]*10,
                    "Hall bagage (+ Transfert)": [np.nan]*9 + [1]*22 + [np.nan]*4 + [1]*3 + [np.nan]*1, "Priority Lane": [1]*29 + [np.nan]*10,
                    "T2 Arrivée": [np.nan]*7 + [1]*22 + [np.nan]*10, "T2 Départ": [np.nan]*5 + [1]*24 + [np.nan]*10,
                    "T2 Portier": [np.nan]*5 + [1]*24 + [np.nan]*10, "T2 Renfort": [np.nan]*7 + [1]*12 + [np.nan]*20,
                    "Transit": [np.nan]*5 + [1]*24 + [np.nan]*10, "Visitor's Center": [np.nan]*5 + [1]*4 + [np.nan]*20 + [1]*10,
                },
                "Dimanche Standard": {
                    "Aile Est Arrivée": [np.nan]*5 + [1]*34, "Aile Est Arrivée ABC": [np.nan]*5 + [1]*34,
                    "Aile Est Arrivée Transf.": [np.nan]*9 + [1]*24 + [np.nan]*6, "Aile Est Arrivée dispatch": [np.nan]*3 + [1]*26 + [np.nan]*10,
                    "Aile Est Départ": [1]*29 + [np.nan]*10, "Aile Est Départ ABC": [np.nan]*1 + [1]*32 + [np.nan]*6,
                    "Check in 1": [np.nan]*1 + [1]*28 + [np.nan]*10, "Guichet info": [np.nan]*9 + [1]*18 + [np.nan]*12,
                    "Hall bagage (+ Transfert)": [np.nan]*9 + [1]*28 + [np.nan]*2, "Priority Lane": [np.nan]*1 + [1]*28 + [np.nan]*10,
                    "Transit": [np.nan]*1 + [1]*30 + [np.nan]*8, "Visitor's Center": [np.nan]*5 + [1]*4 + [np.nan]*20 + [1]*10,
                },
                "Dimanche Été": {
                    "Accueil famille AE": [np.nan]*10 + [1]*20 + [np.nan]*10, "Accueil famille CSC": [1]*28 + [np.nan]*12,
                    "Aile Est Arrivée": [np.nan]*6 + [1]*34, "Aile Est Arrivée ABC": [np.nan]*6 + [1]*34,
                    "Aile Est Arrivée Transf.": [np.nan]*10 + [1]*20 + [np.nan]*10, "Aile Est Arrivée dispatch": [np.nan]*4 + [1]*26 + [np.nan]*10,
                    "Aile Est Départ": [np.nan]*1 + [1]*35 + [np.nan]*4, "Aile Est Départ ABC": [np.nan]*1 + [1]*35 + [np.nan]*4,
                    "Check in 1": [1]*28 + [np.nan]*12, "Check in 2": [np.nan]*4 + [1]*24 + [np.nan]*12,
                    "Guichet info": [np.nan]*10 + [1]*18 + [np.nan]*12, "Hall bagage (+ Transfert)": [np.nan]*10 + [1]*28 + [np.nan]*2,
                    "Priority Lane": [1]*32 + [np.nan]*8, "Transit": [np.nan]*1 + [1]*35 + [np.nan]*4,
                    "Visitor's Center": [np.nan]*6 + [1]*4 + [np.nan]*20 + [1]*10,
                },
                "Dimanche Hiver": {
                    "Accueil famille CSC": [1]*31 + [np.nan]*8, "Accès Sect. France": [np.nan]*7 + [1]*22 + [np.nan]*10,
                    "Aile Est Arrivée": [np.nan]*5 + [1]*34, "Aile Est Arrivée ABC": [np.nan]*5 + [1]*34,
                    "Aile Est Arrivée Transf.": [np.nan]*7 + [1]*31 + [np.nan]*1, "Aile Est Arrivée dispatch": [np.nan]*3 + [1]*26 + [np.nan]*10,
                    "Aile Est Départ": [np.nan]*1 + [1]*34 + [np.nan]*4, "Aile Est Départ ABC": [np.nan]*1 + [1]*34 + [np.nan]*4,
                    "Check in 1": [np.nan]*1 + [1]*30 + [np.nan]*8, "Check in 2": [np.nan]*1 + [1]*30 + [np.nan]*8,
                    "Check in 3": [1]*29 + [np.nan]*10, "Guichet info": [np.nan]*5 + [1]*24 + [np.nan]*10,
                    "Hall bagage (+ Transfert)": [np.nan]*7 + [1]*31 + [np.nan]*1, "Priority Lane": [1]*29 + [np.nan]*10,
                    "T2 Arrivée": [np.nan]*7 + [1]*22 + [np.nan]*10, "T2 Départ": [np.nan]*7 + [1]*22 + [np.nan]*10,
                    "T2 Portier": [np.nan]*7 + [1]*22 + [np.nan]*10, "T2 Renfort": [np.nan]*7 + [1]*12 + [np.nan]*20,
                    "Transit": [np.nan]*5 + [1]*24 + [np.nan]*10, "Visitor's Center": [np.nan]*5 + [1]*4 + [np.nan]*20 + [1]*10,
                },
            }
            # --- INDENTATION CORRIGÉE ICI ---
            for name, data_dict in at_day_type_data.items():
                # Ensure all perimeters for AT are included for each day type
                full_data_dict = {p: data_dict.get(p, [np.nan]*len(time_slots)) for p in perims} # Use NaN for missing in raw data
                st.session_state.planning_data[cat][name] = parse_grid_from_markers(full_data_dict, perims)
            # --- FIN DE L'INDENTATION CORRIGÉE ---

            # Ensure AT has a 'Default' grid if no other grids were defined (fallback)
            if not st.session_state.planning_data[cat]:
                 st.session_state.planning_data[cat]['Default'] = pd.DataFrame(0, index=perims, columns=time_slots).astype(int)
        else:
             # For any other category not explicitly defined, create a default empty grid
             st.session_state.planning_data[cat]['Default'] = pd.DataFrame(0, index=perims, columns=time_slots).astype(int)


    # Initialize cost mapping (attempt basic mapping)
    st.session_state.cost_mapping = {}
    personnel_types = st.session_state.personnel['Type'].tolist()
    for cat in st.session_state.perimetres.keys():
        # Simple matching logic (can be improved)
        match = cat.replace('.', '') # Remove dots for better matching
        if match in personnel_types:
            st.session_state.cost_mapping[cat] = match
        elif cat == 'Sect. FR' and 'Sect FR' in personnel_types:
             st.session_state.cost_mapping[cat] = 'Sect FR'
        elif not personnel_types:
             pass # No personnel defined yet
        else:
             st.session_state.cost_mapping[cat] = personnel_types[0] # Default to first type if no match


    # Load Besoin Jour rules
    st.session_state.besoin_jour_ops = load_rules_from_json(RULES_BESOIN_JOUR_PATH)

    st.session_state.data_loaded = True

    # Attempt to generate the budget for the reference year
    try:
        generate_budget_state(st.session_state.reference_year_saisons)
    except Exception as e:
        st.warning(f"Budget initial ({st.session_state.reference_year_saisons}) n'a pas pu être généré automatiquement : {e}")

    st.rerun() # Rerun to reflect the loaded state


# =================== Planning UI ===================

def _render_grid_for_edit(category_key: str, jt_key_requested: str, title_suffix: str = ""):
    perimetres = st.session_state.perimetres.get(category_key, [])
    if not perimetres:
        st.warning(f"Aucun périmètre défini pour la catégorie '{category_key}'.")
        return

    planning_dict = st.session_state.planning_data.setdefault(category_key, {})
    time_slots = [f"{h:02d}:{m:02d}" for h in range(4, 24) for m in (0, 30)]

    # Use _ensure_grid which handles creation and index/column alignment
    stored_key, grid_src = _ensure_grid(planning_dict, jt_key_requested, perimetres, time_slots)

    st.subheader(f"Grille {category_key} — {stored_key} {title_suffix}")

    # Add index name for clarity in editor if it's missing
    if grid_src.index.name is None:
        grid_src.index.name = "Perimetre"

    # Reset index to make 'Perimetre' a regular column for the editor
    # Pass a copy to avoid potential modifications to the original session state DataFrame index
    grid_to_edit = grid_src.reset_index().copy()

    # FIX: Ajout d'un préfixe unique pour les clés pour éviter les collisions
    page_key_prefix = "bj_" if title_suffix == "(Standard)" else "plan_"
    editor_key = f"grid_editor_{page_key_prefix}_{category_key}_{stored_key}"


    num_rows = len(grid_to_edit)
    # Define height constraints
    min_height = 200
    max_height = 700 # Increased max height
    row_height_approx = 35 # Approximate height per row
    calculated_height = (num_rows + 1) * row_height_approx + 3 # +1 for header, +3 for padding
    dynamic_height = min(max(calculated_height, min_height), max_height)

    # Configure columns for the editor
    column_config = {
        # Ensure 'Perimetre' is correctly referenced (it's the first column after reset_index)
        grid_to_edit.columns[0]: st.column_config.TextColumn(
            "Périmètre",
            disabled=True,
            help="Le nom du périmètre (non modifiable ici).",
            width="medium" # Adjust width if needed
        )
    }
    # Add checkbox config for time slots
    for ts in time_slots:
        column_config[ts] = st.column_config.CheckboxColumn(ts, default=False)

    edited_df_from_widget = st.data_editor(
        grid_to_edit, # Pass the DataFrame with 'Perimetre' as a column
        height=dynamic_height,
        use_container_width=True,
        key=editor_key, # Utilise la clé unique
        num_rows="fixed", # Prevent adding/deleting rows directly in grid editor
        column_config=column_config,
        hide_index=True, # Hide the default numerical index (0, 1, 2...)
    )

    # Ajout d'un bouton de sauvegarde manuelle
    c1_save, c2_save = st.columns([0.3, 0.7])
    with c1_save:
        if st.button("Enregistrer les modifications 💾", key=f"save_btn_{editor_key}", type="primary", use_container_width=True):
            try:
                edited_df_from_editor = edited_df_from_widget
                original_df = st.session_state.planning_data[category_key][stored_key]
                index_col_name = edited_df_from_editor.columns[0]
                new_df = edited_df_from_editor.set_index(index_col_name)
                new_df.index.name = original_df.index.name
                new_df = new_df.reindex(columns=time_slots, fill_value=0)
                new_df = new_df.fillna(0).astype(int).clip(0, 1)
                st.session_state.planning_data[category_key][stored_key] = new_df
                st.rerun()
            except Exception as e:
                st.error(f"Erreur lors de la sauvegarde : {e}")
        with c2_save:
            st.error("Pensez à enregistrer si vous effectuez des changements directement dans la grille.")


    # --- Bulk Edit Section ---
    with st.expander("🛠️ Remplir une plage horaire en masse"):
        # Read the potentially updated grid state from session_state for bulk operations
        df_bulk = st.session_state.planning_data[category_key][stored_key]
        all_rows = list(df_bulk.index)
        all_cols = list(df_bulk.columns)

        if not all_rows or not all_cols:
            st.info("La grille est vide ou n'a pas de créneaux horaires.")
        else:
            col_r, col_s, col_v, col_btn = st.columns([0.38, 0.42, 0.08, 0.12])
            with col_r:
                rows_sel = st.multiselect("Périmètre(s)", options=all_rows, default=[], key=f"bulk_rows_{page_key_prefix}_{category_key}_{stored_key}")
            with col_s:
                start_col, end_col = st.select_slider("Plage horaire", options=all_cols, value=(all_cols[0], all_cols[-1]), key=f"bulk_range_{page_key_prefix}_{category_key}_{stored_key}")
            with col_v:
                val_set = st.radio("Valeur", [1, 0], index=0, key=f"bulk_val_{page_key_prefix}_{category_key}_{stored_key}", label_visibility="collapsed")
            with col_btn:
                st.markdown('<div style="height: 28px;"></div>', unsafe_allow_html=True) # Spacer for alignment
                if st.button("✅", key=f"bulk_apply_{page_key_prefix}_{category_key}_{stored_key}", use_container_width=True):
                    if not rows_sel:
                        st.warning("Veuillez sélectionner au moins un périmètre.")
                    else:
                        _apply_bulk_range(category_key, stored_key, rows_sel, start_col, end_col, val_set)
                        st.success("Plage mise à jour.")
                        st.rerun() # Rerun needed to show bulk changes in the editor above

    # --- Analysis/KPI Section ---
    grid_now = st.session_state.planning_data[category_key][stored_key]
    total_par_creneau = grid_now.sum(axis=0)
    total_heures = grid_now.values.sum() * 0.5
    pic_effectifs = int(total_par_creneau.max()) if not total_par_creneau.empty else 0

    st.bar_chart(total_par_creneau, height=230)
    st.markdown(
        f"""
        <div class="kpi-cards">
            <div class="kpi-card kpi-blue">
                <div class="label">Total Heures Planifiées (JT)</div>
                <div class="value">{total_heures:.1f} h</div>
            </div>
            <div class="kpi-card kpi-green">
                <div class="label">Pic Effectifs Requis (JT)</div>
                <div class="value">{pic_effectifs} agents</div>
            </div>
        </div>
        """, unsafe_allow_html=True
    )

def planning_editor_ui(category_name, category_key):
    # Ensure perimetres exist for the category
    perimetres = st.session_state.perimetres.get(category_key, [])
    if not perimetres:
        st.error(f"Aucun périmètre n'est défini pour la catégorie '{category_name}'. Veuillez les ajouter dans la page 'Configuration'.")
        return # Stop execution for this UI component if no perimetres

    planning_dict = st.session_state.planning_data.setdefault(category_key, {})
    time_slots = [f"{h:02d}:{m:02d}" for h in range(4, 24) for m in (0, 30)]


    # Ensure a 'Default' grid exists if the dictionary is empty
    if not planning_dict:
        planning_dict['Default'] = pd.DataFrame(0, index=perimetres, columns=time_slots).astype(int)

    # Sort existing day types for the selectbox
    jours_ordre = ["Lundi", "Mardi", "Mercredi", "Jeudi", "Vendredi", "Samedi", "Dimanche", "Default"] # Add Default
    saisons_ordre = ["Standard", "Été", "Ete", "Hiver"]
    def tri_jour_type(name: str):
        name_lower = str(name).lower()
        if name_lower == "default":
             return (len(jours_ordre), 0) # Place Default last or first? Last seems reasonable.
        for i, jour in enumerate(jours_ordre):
            if name_lower.startswith(jour.lower()):
                for j, saison in enumerate(saisons_ordre):
                    # Check if season name is part of the string
                    if saison.lower() in name_lower:
                        return (i, j)
                return (i, len(saisons_ordre)) # If day matches but no known season
        return (len(jours_ordre), len(saisons_ordre)) # Fallback if no match

    jours_existants = sorted(list(planning_dict.keys()), key=tri_jour_type)

    selected_jour_type = st.selectbox(
        f"Sélectionner un jour-type pour **{category_name}** :",
        jours_existants,
        key=f"active_jt_{category_key}"
    )

    with st.expander("🛈"):
        st.info(f"Modifiez ici la grille horaire pour le jour-type **{selected_jour_type}** de la catégorie **{category_name}**. Cochez les cases pour indiquer la présence d'un agent. **N'oubliez pas d'enregistrer vos modifications avec le bouton 💾 sous la grille.**")
        st.info("Vous pouvez également **modifier une plage horaire en masse** directement sous la grille")

    # Expander for creating/duplicating day types
    with st.expander("Gérer les jours-types (créer/dupliquer)"):
        with st.form(key=f"form_create_jt_{category_key}"):
            st.write("**Créer ou Dupliquer un Jour-Type**")
            new_name = st.text_input("Nom du nouveau jour-type (ex: 'Lundi Événement')", key=f"new_name_{category_key}")
            source_options = ["(Partir de zéro)"] + jours_existants
            source = st.selectbox("Basé sur (laisse vide pour créer de zéro) :", source_options, index=0, key=f"source_{category_key}")

            if st.form_submit_button("Créer / Dupliquer"):
                existants_canon = {canon(k) for k in planning_dict.keys()}
                if new_name and canon(new_name) not in existants_canon:
                    if source != "(Partir de zéro)":
                        # Ensure source grid exists before copying
                        if source in planning_dict:
                             # Use _ensure_grid to make sure the source is aligned
                             _, source_grid = _ensure_grid(planning_dict, source, perimetres, time_slots)
                             new_grid = source_grid.copy()
                        else:
                             st.error(f"Le jour-type source '{source}' n'existe pas.")
                             new_grid = None # Prevent creation
                    else: # Partir de zéro
                        new_grid = pd.DataFrame(0, index=perimetres, columns=time_slots).astype(int)

                    if new_grid is not None:
                        planning_dict[new_name] = new_grid
                        st.success(f"Jour-type '{new_name}' créé.")
                        # Update jours_existants immediately for potential selection
                        jours_existants.append(new_name)
                        jours_existants.sort(key=tri_jour_type)
                        # Optionally set the new JT as selected, or just rerun
                        st.session_state[f"active_jt_{category_key}"] = new_name # Select the newly created JT
                        st.rerun()
                elif not new_name:
                     st.error("Veuillez entrer un nom pour le nouveau jour-type.")
                else: # Name already exists
                    st.error(f"Un jour-type nommé '{new_name}' (ou similaire) existe déjà.")

    # Render the editor for the selected day type
    if selected_jour_type:
        # Use container for visual grouping, maybe border=True if desired
        with st.container():#border=True
            _render_grid_for_edit(category_key, selected_jour_type)


# =================== EXÉCUTION PRINCIPALE DE L'APPLICATION ===================
gva_header()

# Initialize session state keys if they don't exist
if 'data_loaded' not in st.session_state:
    st.session_state.data_loaded = False
if 'besoin_jour_ops' not in st.session_state:
    # Try loading from JSON, default to empty list if fails
    st.session_state.besoin_jour_ops = load_rules_from_json(RULES_BESOIN_JOUR_PATH)
if 'budget_state' not in st.session_state:
     st.session_state.budget_state = {} # Initialize budget state
if 'show_help_dialog' not in st.session_state: st.session_state.show_help_dialog = False

if st.session_state.show_help_dialog:
    show_help_dialog()
    st.session_state.show_help_dialog = False


# Welcome screen or main app logic
if not st.session_state.data_loaded:
    #st.title("Bienvenue sur le Planificateur Budgétaire")

    if st.button("Ouvrir le Mode d'emploi"):
        # on force l'ouverture de la page d’aide
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
                    # No need to rerun here, initialize sets data_loaded=True, loop will continue
                except Exception as e:
                     st.error(f"Erreur lors de l'initialisation des données 2026: {e}")

    with col2:
        with st.container(border=True):
            st.subheader("Charger un scénario existant")
            st.markdown("Chargez un fichier `.xlsx` que vous avez précédemment sauvegardé.")
            uploaded_file = st.file_uploader("Choisissez un fichier Excel", type="xlsx", label_visibility="collapsed")
            if uploaded_file is not None:
                success, message = load_data_from_excel(uploaded_file)
                if success:
                    st.success(message)
                    # Data is loaded, state is set, Streamlit will rerun automatically
                    st.rerun() # Explicit rerun might still be needed depending on load_data logic
                else:
                    st.error(message)



else:
    # Main application interface if data is loaded

    # --- MODIFICATION : CHARGEMENT AUTO ET DIVISION DES PAX ---
    if 'pax_data_status' not in st.session_state:
        # Charger le fichier unique
        full_pax_data, overall_min_date, overall_max_date = load_pax_data(PAX_DATA_FILE_PATH, "Passagers")
        
        st.session_state.pax_data_status = "attempted" # Marquer que le chargement a été tenté
        
        if not full_pax_data.empty:
            st.session_state.pax_overall_min_date = overall_min_date
            st.session_state.pax_overall_max_date = overall_max_date
            
            # Obtenir la date du jour
            today = dt.date.today()
            
            # Diviser les données
            historical_data = full_pax_data[full_pax_data.index.date < today].copy()
            forecast_data = full_pax_data[full_pax_data.index.date >= today].copy()
            
            # Stocker les données historiques et leurs dates
            if not historical_data.empty:
                st.session_state.pax_historical_data = historical_data
                st.session_state.pax_historical_min_date = historical_data.index.min().date()
                st.session_state.pax_historical_max_date = historical_data.index.max().date()
                st.session_state.pax_historical_status = "loaded"
            else:
                st.session_state.pax_historical_status = "no_data_found"
                
            # Stocker les données prévisionnelles et leurs dates
            if not forecast_data.empty:
                st.session_state.pax_forecast_data = forecast_data
                st.session_state.pax_forecast_min_date = forecast_data.index.min().date()
                st.session_state.pax_forecast_max_date = forecast_data.index.max().date()
                st.session_state.pax_forecast_status = "loaded"
            else:
                 st.session_state.pax_forecast_status = "no_data_found"

        else:
            # Le fichier n'a pas pu être chargé ou était vide
            st.session_state.pax_historical_status = "not_loaded"
            st.session_state.pax_forecast_status = "not_loaded"
    # --- FIN DU CHARGEMENT AUTO ---

    if "show_help_dialog" not in st.session_state:
        st.session_state["show_help_dialog"] = False

    with st.sidebar:
        st.title("Navigation")

        # Menu principal (ajout de "Comparaison Historique")
        page = st.radio(
            "Navigation",
            ["Configuration", "Planification", "Budget Annuel", "Besoin Jour",
             "Comparaison Historique", # <--- AJOUTÉ
             "Simulateur Objectif"],
            label_visibility="hidden"
        )

        # Bouton Mode d'emploi
        if st.button("❔ Mode d'emploi", use_container_width=True, help="Ouvrir le guide d’utilisation"):
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
                    if "export_bytes" in st.session_state: del st.session_state["export_bytes"]
                    if "export_filename" in st.session_state: del st.session_state["export_filename"]

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


    # =================== DÉFINITION DES PAGES ===================

    def _nop_callback(*args, **kwargs):
        pass

    # --- Logique d'affichage des pages ---
    if page == "Configuration":
        # ... (Code de la page Configuration - inchangé, omis pour brièveté) ...
        st.title("Configuration Générale")
        st.markdown("Modifiez ici les paramètres de base qui alimentent tous les calculs de planification.")

        # -- Bloc 1 : Personnel et Tarifs --
        with st.expander("1 - Personnel et Tarifs Horaires", expanded=True):
            st.info("🛈 Définissez ici les différents types de personnel et leur coût horaire. Ces tarifs seront utilisés pour calculer le coût du budget annuel.")           
            if 'personnel' not in st.session_state or not isinstance(st.session_state.personnel, pd.DataFrame):
                 st.warning("Données personnel non initialisées.")
            else:
                editor_personnel_key="editor_personnel_config"
                personnel_before_edit = st.session_state.personnel.copy()
                edited_personnel = st.data_editor(
                     personnel_before_edit,
                     num_rows="dynamic",
                     key=editor_personnel_key,
                     use_container_width=True,
                     column_config={
                         "Type": st.column_config.TextColumn("Type", required=True),
                         "Coût Horaire": st.column_config.NumberColumn("Coût Horaire (CHF)", format="%.2f", required=True, min_value=0.0)
                     },
                     hide_index=True
                 )
                if not edited_personnel.equals(personnel_before_edit):
                    st.session_state.personnel = edited_personnel.copy()
                    st.rerun()

        # -- Bloc 2 : Périmètres --
        with st.expander("2 - Gestion des Périmètres par Catégorie", expanded=False):
            st.info("🛈 Listez ici tous les postes ou zones opérationnelles ('Périmètres') et regroupez-les par 'Catégorie' **- utiliser les types de personnel définis en 1.** C'est essentiel pour organiser la planification.")           
            if 'perimetres' not in st.session_state or not st.session_state.perimetres:
                 st.warning("Données périmètres non initialisées.")
            else:
                 all_categories = sorted(list(st.session_state.perimetres.keys()))
                 categories_options = ["Toutes"] + all_categories

                 selected_category_filter = st.selectbox(
                     "Filtrer Catégorie (pour affichage/édition):",
                     categories_options,
                     key="perimetre_filter_select"
                 )

                 # --- Créer DataFrame AVANT éditeur pour référence et affichage ---
                 perimetres_list_before = [{'Categorie': c, 'Perimetre': p} for c, items in st.session_state.perimetres.items() for p in items]
                 perimetres_df_full_before = pd.DataFrame(perimetres_list_before)

                 if selected_category_filter != "Toutes":
                     df_to_display = perimetres_df_full_before[perimetres_df_full_before['Categorie'] == selected_category_filter].copy()
                 else:
                     df_to_display = perimetres_df_full_before.copy()

                 st.markdown("Ajoutez, modifiez ou supprimez des périmètres:")
                 editor_perimetres_key = "editor_perimetres_widget"

                 # --- Afficher l'éditeur et CAPTURER le résultat ---
                 edited_part = st.data_editor(
                     df_to_display, # Le DataFrame (potentiellement filtré) à éditer
                     num_rows="dynamic",
                     use_container_width=True,
                     key=editor_perimetres_key,
                     column_config={
                         "Categorie": st.column_config.TextColumn(
                             "Catégorie", help="Entrez un nom existant ou nouveau.", required=True
                         ),
                         "Perimetre": st.column_config.TextColumn("Périmètre", required=True)
                     },
                     hide_index=True,
                    
                 )

                 # --- Logique de mise à jour APRES l'éditeur ---
                 if not edited_part.equals(df_to_display):
                    try:
                        # Nettoyer les données éditées
                        edited_part_cleaned = edited_part.dropna(subset=['Perimetre', 'Categorie'])
                        edited_part_cleaned['Categorie'] = edited_part_cleaned['Categorie'].astype(str).str.strip()
                        edited_part_cleaned['Perimetre'] = edited_part_cleaned['Perimetre'].astype(str).str.strip()
                        edited_part_cleaned = edited_part_cleaned[edited_part_cleaned['Perimetre'] != '']
                        edited_part_cleaned = edited_part_cleaned[edited_part_cleaned['Categorie'] != '']
                        edited_part_cleaned = edited_part_cleaned.drop_duplicates(subset=['Categorie', 'Perimetre'])

                        # Reconstruire le DataFrame complet
                        if selected_category_filter != "Toutes":
                            other_categories_df = perimetres_df_full_before[perimetres_df_full_before['Categorie'] != selected_category_filter]
                            reconstructed_df = pd.concat([other_categories_df, edited_part_cleaned], ignore_index=True)
                        else:
                            reconstructed_df = edited_part_cleaned

                        # Reconstruire le dictionnaire final
                        final_categories = sorted(reconstructed_df['Categorie'].unique().tolist())
                        new_perimetres_dict = {cat: [] for cat in final_categories} 

                        if not reconstructed_df.empty:
                            grouped = reconstructed_df.groupby('Categorie')['Perimetre'].apply(list)
                            for cat, items in grouped.items():
                                new_perimetres_dict[cat] = sorted(items) 

                        # Comparer et mettre à jour
                        current_perimetres_sorted = {k: sorted(v) for k, v in st.session_state.get('perimetres', {}).items()}
                        new_perimetres_sorted = {k: sorted(v) for k, v in new_perimetres_dict.items()}

                        if current_perimetres_sorted != new_perimetres_sorted:
                            st.session_state.perimetres = new_perimetres_dict 
                            for cat in new_perimetres_dict:
                                st.session_state.planning_data.setdefault(cat, {})
                            st.rerun() 

                    except Exception as e:
                        st.error(f"Erreur lors de la mise à jour des périmètres après édition: {e}")


       # -- Bloc 3 : Saisons de Référence --
        with st.expander("3 - Saisons de Référence", expanded=False):
             st.info("🛈 Définissez les dates des saisons pour une année de référence (ex: 2026). Ces dates serviront de modèle pour calculer automatiquement les calendriers des années futures.")           
             if 'saisons' not in st.session_state or not isinstance(st.session_state.saisons, pd.DataFrame):
                 st.warning("Données saisons non initialisées.")
             else:
                st.markdown(f"Année de référence: **{st.session_state.get('reference_year_saisons', 'N/A')}**")
                try:
                    df_saisons_before_edit = st.session_state.saisons.copy()
                    df_saisons_to_edit = df_saisons_before_edit.copy()
                    df_saisons_to_edit['Date Début'] = pd.to_datetime(df_saisons_to_edit['Date Début'], errors='coerce').dt.date
                    df_saisons_to_edit['Date Fin'] = pd.to_datetime(df_saisons_to_edit['Date Fin'], errors='coerce').dt.date
                    df_saisons_to_edit.dropna(subset=['Date Début', 'Date Fin'], inplace=True)

                    editor_saisons_key = "editor_saisons_config"
                    edited_saisons = st.data_editor(
                        df_saisons_to_edit,
                        column_config={
                            "Saison": st.column_config.TextColumn("Saison", required=True),
                            "Date Début": st.column_config.DateColumn("Début", format="DD/MM/YYYY", required=True),
                            "Date Fin": st.column_config.DateColumn("Fin", format="DD/MM/YYYY", required=True)
                        },
                        num_rows="dynamic",
                        key=editor_saisons_key,
                        use_container_width=True,
                        hide_index=True
                    )
                    if not edited_saisons.equals(df_saisons_to_edit):
                         edited_saisons['Date Début'] = pd.to_datetime(edited_saisons['Date Début']).dt.date
                         edited_saisons['Date Fin'] = pd.to_datetime(edited_saisons['Date Fin']).dt.date
                         st.session_state.saisons = edited_saisons.copy()
                         if not edited_saisons.empty:
                              st.session_state.reference_year_saisons = edited_saisons['Date Début'].iloc[0].year
                         st.rerun()

                except Exception as e:
                     st.error(f"Err saisons: {e}")


    elif page == "Planification":
        # ... (Code de la page Planification - inchangé, omis pour brièveté) ...
        st.title("Planification des Jours-Types")
        st.markdown("Définissez les grilles de présence pour chaque jour-type. C'est le cœur de la planification.")
        if 'perimetres' not in st.session_state or not st.session_state.perimetres:
             st.error("Les périmètres ne sont pas définis. Allez à la page 'Configuration'.")
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
                 st.warning("Aucune catégorie de périmètre n'est définie.")

    elif page == "Budget Annuel":
        # ... (Code de la page Budget Annuel - inchangé, omis pour brièveté) ...
        st.title("Budget Annuel Consolidé")
        st.markdown("Générez une projection annuelle complète basée sur vos planifications et paramètres.")
        year = st.number_input(
            "Année du budget :",
            value=st.session_state.get('adjusted_saisons_year', dt.date.today().year + 1),
            min_value=2024, max_value=2050, key="budget_year_selector"
        )
        tabs_budget = st.tabs(["Vue d'Ensemble & Génération", "Paramètres du Calendrier", "Association des Coûts"])
        with tabs_budget[0]: 
            st.markdown('<div class="ga-card">', unsafe_allow_html=True)
            st.subheader("Génération du Budget")
            st.markdown(f"Calculez le budget pour l’année **{year}** à partir des JTs et du calendrier.", help="Vérifiez d’abord le personnel et l’association des coûts.")
            if 'personnel' in st.session_state and not st.session_state.personnel.empty:
                cols_act = st.columns([1,1.2])
                with cols_act[0]:
                    if st.button("Lancer la génération", type="primary", use_container_width=True, key="generate_budget_button"):
                        with st.spinner("Consolidation en cours…"):
                            generate_budget_state(year)
                        if 'budget_state' in st.session_state and st.session_state.budget_state.get('year') == year:
                            st.success("Budget annuel généré avec succès !")
                        else:
                            st.error("La génération a échoué. Consultez les messages précédents.")
                with cols_act[1]:
                    st.info("Regénérez après tout changement de **saisons**, **tarifs** ou **mapping des coûts**.")
            else:
                st.warning("Définissez d’abord les **types de personnel** dans la page *Configuration*.")
            st.markdown('</div>', unsafe_allow_html=True)

            bs = st.session_state.get('budget_state', {})
            if bs and bs.get('year') == year:
                with st.container(border=True):
                    st.subheader("Synthèse Annuelle")
                    totals = bs.get('totals', {})
                    total_heures_annuel = totals.get('heures_annuel', 0.0)
                    total_cout_annuel = totals.get('cout_annuel', 0.0)
                    st.markdown(f"""<div class="kpi-cards"> <div class="kpi-card kpi-blue"> <div class="label">Volume Heures Annuel TOTAL</div> <div class="value">{total_heures_annuel:,.0f} h</div> </div> <div class="kpi-card kpi-amber"> <div class="label">Coût Annuel TOTAL</div> <div class="value">{total_cout_annuel:,.0f} CHF</div> </div> </div>""", unsafe_allow_html=True)
                    st.markdown("---")
                    st.subheader("Répartition du Coût par Catégorie")
                    summary = bs.get('summary', pd.DataFrame())
                    if not summary.empty:
                        col1, col2 = st.columns([0.4, 0.6])
                        with col1:
                            st.dataframe(summary.set_index('Catégorie').style.format({'Coût': '{:,.0f} CHF'}), use_container_width=True)
                        with col2:
                            try:
                                chart = alt.Chart(summary).mark_bar().encode(x=alt.X('Catégorie:N', sort='-y', title=None), y=alt.Y('Coût:Q', title="Coût (CHF)"), tooltip=['Catégorie', alt.Tooltip('Coût:Q', format=',.0f')]).properties(height=250)
                                st.altair_chart(chart, use_container_width=True)
                            except Exception as e:
                                st.warning(f"Impossible d'afficher le graphique : {e}")
                                st.bar_chart(summary.set_index('Catégorie'))
                    else:
                        st.info("Aucun coût calculé (vérifiez l'association des coûts et les tarifs).")
                # --- NOUVEAU BLOC : DÉTAIL MENSUEL ET JOURNALIER ---
                with st.container(border=True):
                    st.subheader("Budget Détaillé par Période")
                    calendar_df = bs.get('calendar_df', pd.DataFrame())

                    if not calendar_df.empty:
                        try:
                            # --- PRÉPARATION DES DONNÉES MENSUELLES ---
                            calendar_df['Date'] = pd.to_datetime(calendar_df['Date'])
                            calendar_df['Mois_Str'] = calendar_df['Date'].dt.strftime('%m.%Y')
                            calendar_df['Month_Obj'] = calendar_df['Date'].dt.to_period('M') # Pour trier
                            calendar_df = calendar_df.sort_values('Date')

                            cost_cols = [c for c in calendar_df.columns if c.startswith('Coût_') and c != 'Coût_Total_Jour']
                            hour_cols = [c for c in calendar_df.columns if c.startswith('Heures_') and c != 'Heures_Total_Jour']
                            cols_to_group = ['Mois_Str', 'Month_Obj'] + cost_cols + hour_cols

                            # Grouper par mois et sommer (garder l'ordre avec Month_Obj puis le retirer)
                            monthly_summary = calendar_df[cols_to_group].groupby(['Month_Obj', 'Mois_Str'], sort=True).sum(numeric_only=True).reset_index()
                            monthly_summary = monthly_summary.drop(columns=['Month_Obj']) # On n'a plus besoin de l'objet Period
                            # ✅ CORRECTION : Nettoyer les NaN dès le groupby pour éviter propagation
                            monthly_summary = monthly_summary.fillna(0)

                            # --- Tableaux Mensuels ---
                            tab_monthly_cost, tab_monthly_hour = st.tabs(["📊 Détail Mensuel (CHF)", "🕒 Détail Mensuel (Heures)"])

                            with tab_monthly_cost:
                                df_costs = monthly_summary[['Mois_Str'] + cost_cols].copy()
                                category_cost_cols = [c.replace('Coût_', '') for c in cost_cols]
                                df_costs.columns = ['Mois'] + category_cost_cols
                                if category_cost_cols:
                                    df_costs[category_cost_cols] = df_costs[category_cost_cols].apply(pd.to_numeric, errors='coerce').fillna(0.0).astype(float)
                                df_costs['Total'] = df_costs[category_cost_cols].sum(axis=1)

                                col_config_costs = {"Mois": st.column_config.TextColumn("Mois")}
                                for cat in category_cost_cols:
                                    col_config_costs[cat] = st.column_config.NumberColumn(f"{cat}", format="%,.0f CHF")
                                col_config_costs["Total"] = st.column_config.NumberColumn("Total", format="%,.0f CHF")

                                # ✅ CORRECTION : Éliminer tous les NaN avant affichage
                                df_costs = df_costs.fillna(0)
                                st.dataframe(df_costs, column_config=col_config_costs, hide_index=True, use_container_width=True) # Pas de height

                            with tab_monthly_hour:
                                df_hours = monthly_summary[['Mois_Str'] + hour_cols].copy()
                                category_hour_cols = [c.replace('Heures_', '') for c in hour_cols]
                                df_hours.columns = ['Mois'] + category_hour_cols
                                if category_hour_cols:
                                    df_hours[category_hour_cols] = df_hours[category_hour_cols].apply(pd.to_numeric, errors='coerce').fillna(0.0).astype(float)
                                df_hours['Total'] = df_hours[category_hour_cols].sum(axis=1)

                                col_config_hours = {"Mois": st.column_config.TextColumn("Mois")}
                                for cat in category_hour_cols:
                                    col_config_hours[cat] = st.column_config.NumberColumn(f"{cat}", format="%.1f h")
                                col_config_hours["Total"] = st.column_config.NumberColumn("Total", format="%.1f h")

                                st.dataframe(df_hours, column_config=col_config_hours, hide_index=True, use_container_width=True) # Pas de height

                            # --- SECTION DÉTAIL JOURNALIER PAR MOIS SÉLECTIONNÉ ---
                            st.divider()
                            st.markdown("##### 🗓️ Explorer le Détail Journalier")
                            available_months = monthly_summary['Mois_Str'].unique().tolist()
                            selected_month = st.selectbox("Sélectionner un mois pour voir les jours :", available_months, key="budget_detail_month_select")

                            if selected_month:
                                df_daily_detail = calendar_df[calendar_df['Mois_Str'] == selected_month].copy()
                                df_daily_detail['Jour_Semaine'] = _day_name_fr(df_daily_detail['Date']) # Récupérer le nom du jour

                                tab_daily_cost, tab_daily_hour = st.tabs([f" Détail Jours {selected_month} (CHF)", f" Détail Jours {selected_month} (Heures)"])

                                with tab_daily_cost:
                                    cols_to_show_cost = ['Date', 'Jour_Semaine'] + cost_cols + ['Coût_Total_Jour']
                                    df_daily_costs_view = df_daily_detail[cols_to_show_cost].copy()
                                    cost_view_cols_rename = {c: c.replace('Coût_', '') for c in cost_cols}
                                    cost_view_cols_rename['Coût_Total_Jour'] = 'Total'
                                    cost_view_cols_rename['Jour_Semaine'] = 'Jour'
                                    df_daily_costs_view = df_daily_costs_view.rename(columns=cost_view_cols_rename)

                                    # Coercion + fillna pour les coûts journaliers
                                    numeric_cost_cols_daily = list(cost_view_cols_rename.values())
                                    if 'Date' in numeric_cost_cols_daily: numeric_cost_cols_daily.remove('Date') # Ne pas convertir Date
                                    if 'Jour' in numeric_cost_cols_daily: numeric_cost_cols_daily.remove('Jour') # Ne pas convertir Jour
                                    if numeric_cost_cols_daily:
                                        df_daily_costs_view[numeric_cost_cols_daily] = df_daily_costs_view[numeric_cost_cols_daily].apply(pd.to_numeric, errors='coerce').fillna(0.0).astype(float)


                                    daily_cost_config = {
                                        "Date": st.column_config.DateColumn("Date", format="DD/MM/YYYY"),
                                        "Jour": st.column_config.TextColumn("Jour")
                                    }
                                    for cat_col in cost_view_cols_rename.values():
                                        if cat_col not in ["Date", "Jour"]:
                                            daily_cost_config[cat_col] = st.column_config.NumberColumn(f"{cat_col} (CHF)", format="%,.0f")

                                    st.dataframe(df_daily_costs_view, column_config=daily_cost_config, hide_index=True, use_container_width=True) # Pas de height

                                with tab_daily_hour:
                                    cols_to_show_hour = ['Date', 'Jour_Semaine'] + hour_cols + ['Heures_Total_Jour']
                                    df_daily_hours_view = df_daily_detail[cols_to_show_hour].copy()
                                    hour_view_cols_rename = {c: c.replace('Heures_', '') for c in hour_cols}
                                    hour_view_cols_rename['Heures_Total_Jour'] = 'Total'
                                    hour_view_cols_rename['Jour_Semaine'] = 'Jour'
                                    df_daily_hours_view = df_daily_hours_view.rename(columns=hour_view_cols_rename)

                                    # Coercion + fillna pour les heures journalières
                                    numeric_hour_cols_daily = list(hour_view_cols_rename.values())
                                    if 'Date' in numeric_hour_cols_daily: numeric_hour_cols_daily.remove('Date') # Ne pas convertir Date
                                    if 'Jour' in numeric_hour_cols_daily: numeric_hour_cols_daily.remove('Jour') # Ne pas convertir Jour
                                    if numeric_hour_cols_daily:
                                        df_daily_hours_view[numeric_hour_cols_daily] = df_daily_hours_view[numeric_hour_cols_daily].apply(pd.to_numeric, errors='coerce').fillna(0.0).astype(float)


                                    daily_hour_config = {
                                        "Date": st.column_config.DateColumn("Date", format="DD/MM/YYYY"),
                                        "Jour": st.column_config.TextColumn("Jour")
                                    }
                                    for cat_col in hour_view_cols_rename.values():
                                        if cat_col not in ["Date", "Jour"]:
                                             daily_hour_config[cat_col] = st.column_config.NumberColumn(f"{cat_col} (h)", format="%.1f")

                                    st.dataframe(df_daily_hours_view, column_config=daily_hour_config, hide_index=True, use_container_width=True) # Pas de height

                        except Exception as e:
                            st.error(f"Erreur lors de la préparation du détail mensuel/journalier : {e}")
                            import traceback
                            st.error(traceback.format_exc()) # Pour le débogage

                    else:
                        st.info("Le détail mensuel/journalier n'est pas disponible (budget non généré ou vide).")

        with tabs_budget[1]: # Calendar Parameters
            with st.container(border=True):
                st.subheader(f"Calendrier des Saisons pour {year}")
                st.markdown("Les dates sont calculées automatiquement. Ajustez si nécessaire.")

                # Ensure seasons for the selected year are calculated/updated
                _ensure_adjusted_saisons_for_year(year)

                if 'adjusted_saisons' not in st.session_state or st.session_state.adjusted_saisons.empty:
                     st.warning(f"Impossible de déterminer le calendrier des saisons pour {year}.")
                else:
                    col_edit, col_viz = st.columns([0.4, 0.6])
                    with col_edit:
                         # Make a copy for editing to compare changes
                         current_adjusted_saisons = st.session_state.adjusted_saisons.copy()
                         edited_adjusted_saisons = st.data_editor(
                             current_adjusted_saisons,
                             column_config={
                                 "Saison": st.column_config.TextColumn("Nom Saison", required=True),
                                 "Date Début": st.column_config.DateColumn("Date Début", format="DD/MM/YYYY", required=True),
                                 "Date Fin": st.column_config.DateColumn("Date Fin", format="DD/MM/YYYY", required=True)
                             },
                             num_rows="dynamic", # Allow adding/deleting seasons for the year
                             key="editor_adjusted_saisons",
                             use_container_width=True,
                             hide_index=True
                         )
                         # Update state only if changes were made
                         if not edited_adjusted_saisons.equals(current_adjusted_saisons):
                              # Basic validation: Check for overlaps or gaps? (More complex)
                              st.session_state.adjusted_saisons = edited_adjusted_saisons
                              st.info("Calendrier ajusté. Regénérez le budget pour appliquer les changements.")
                              # Rerun to update the timeline visualization
                              st.rerun()

                    with col_viz:
                         try:
                             timeline_df = _season_timeline_df() # Uses the current state
                             if not timeline_df.empty:
                                 # Color mapping logic
                                 base_map = {"Hiver": "#0076aa", "Standard": "#C2C3CB", "Été": "#68813B", "Ete": "#68813B"}
                                 fallback_palette = ["#C0A192", "#E5D8D1", "#E0E1D4"]
                                 seasons = list(pd.unique(timeline_df["Saison"]))
                                 colors, fp_idx = [], 0
                                 for s in seasons:
                                     colors.append(base_map.get(s, fallback_palette[fp_idx % len(fallback_palette)]))
                                     if s not in base_map: fp_idx += 1

                                 # Altair chart
                                 timeline = alt.Chart(timeline_df).mark_bar(cornerRadius=3, height=50).encode(
                                     x=alt.X("start:T", title="", axis=alt.Axis(format="%b")),
                                     x2="end:T",
                                     y=alt.Y("Saison:N", sort=None, title=None, axis=alt.Axis(labels=True, ticks=False, domain=False)),
                                     tooltip=["Saison", "start:T", "end:T", alt.Tooltip("days", title="Durée (j)")],
                                     color=alt.Color("Saison:N", legend=alt.Legend(title="Saison"), scale=alt.Scale(domain=seasons, range=colors)),
                                     order=alt.Order("start:T") # Ensure correct order
                                 ).properties(
                                      # Adjust height based on number of seasons
                                      height=max(100, len(seasons) * 75)
                                      )
                                 st.altair_chart(timeline, use_container_width=True)
                             else:
                                  st.info("Aucune donnée de saison à visualiser.")
                         except Exception as e:
                             st.warning(f"Impossible d'afficher la frise chronologique: {e}")


        with tabs_budget[2]: # Cost Association
            with st.container(border=True):
                st.subheader("Association Personnel-Coût par Catégorie")
                st.markdown("Associez chaque catégorie à un type de personnel pour le calcul des coûts.")

                if 'personnel' not in st.session_state or st.session_state.personnel.empty:
                    st.warning("Définissez d'abord les types de personnel dans 'Configuration'.")
                elif 'perimetres' not in st.session_state or not st.session_state.perimetres:
                     st.warning("Définissez d'abord les catégories/périmètres dans 'Configuration'.")

                else:
                    personnel_list = st.session_state.personnel['Type'].tolist()
                    cost_mapping = st.session_state.get('cost_mapping', {})
                    # Ensure cost_mapping exists for all categories
                    for cat in st.session_state.perimetres.keys():
                         if cat not in cost_mapping:
                              cost_mapping[cat] = personnel_list[0] if personnel_list else None


                    cols = st.columns(3)
                    sorted_categories = sorted(list(st.session_state.perimetres.keys()))
                    changed = False
                    for i, key in enumerate(sorted_categories):
                        with cols[i % 3]:
                             current_personnel = cost_mapping.get(key)
                             try:
                                 # Set index based on current mapping, fallback to 0
                                 default_idx = personnel_list.index(current_personnel) if current_personnel in personnel_list else 0
                             except ValueError:
                                 default_idx = 0 # Fallback if personnel list is empty or type not found

                             new_personnel = st.selectbox(
                                 f"**{key}** :",
                                 personnel_list,
                                 index=default_idx,
                                 key=f"map_{key}"
                             )
                             # Update mapping if selection changed
                             if new_personnel != current_personnel:
                                 cost_mapping[key] = new_personnel
                                 changed = True

                    # Update session state if any mapping changed
                    if changed:
                         st.session_state.cost_mapping = cost_mapping
                         st.info("Association mise à jour. Regénérez le budget pour appliquer.")
                         st.rerun() # Rerun to confirm selection visually


    elif page == "Besoin Jour":
        st.title("Ajustement du Besoin Journalier")
        st.markdown("Appliquez des modifications temporaires (ex: événements) sans altérer vos jours-types de base.")

        bs = st.session_state.get('budget_state', {})
        if not bs or 'year' not in bs or 'calendar_df' not in bs or bs['calendar_df'].empty:
            st.warning("⚠️ Aucun budget annuel valide en mémoire. Veuillez d'abord en générer un via la page **Budget Annuel**.")
            st.stop() 

        year = bs['year']

        def assign_season(d: dt.date) -> str:
            if 'adjusted_saisons' not in st.session_state or st.session_state.adjusted_saisons.empty: return "Standard"
            try:
                for _, r in st.session_state.adjusted_saisons.iterrows():
                    start_date = pd.to_datetime(r['Date Début']).date()
                    end_date = pd.to_datetime(r['Date Fin']).date()
                    if start_date <= d <= end_date: return r['Saison']
                return "Standard"
            except Exception as e: st.error(f"Erreur dans assign_season : {e}"); return "Standard" 
        
        with st.container(border=True):
            st.subheader("Impact Annuel Recalculé")
            with st.spinner("Recalcul du budget annuel avec tous les ajustements..."):
                try:
                    calendar_dyn = bs['calendar_df'].copy()  
                    heures_vals_at_recalc = []
                    costs_vals_at_recalc = []
                    tarif_at = 0.0
                    personnel_type_at = st.session_state.get('cost_mapping', {}).get("AT")
                    if personnel_type_at:
                        personnel_df = st.session_state.get('personnel', pd.DataFrame())
                        if not personnel_df.empty:
                            row_tarif = personnel_df[personnel_df['Type'] == personnel_type_at]
                            if not row_tarif.empty: tarif_at = float(row_tarif['Coût Horaire'].iloc[0])
                    perimetres_AT = st.session_state.perimetres.get("AT", [])
                    time_slots_default = [f"{h:02d}:{m:02d}" for h in range(4, 24) for m in (0, 30)]
                    planning_dict_at = st.session_state.planning_data.get("AT", {})
                    for _, r in calendar_dyn.iterrows():
                        jour, saison, date_ = r['Jour'], r['Saison'], r['Date'].date()
                        jtg = r['Jour_Type_Global']
                        _, base_df_at = _ensure_grid(planning_dict_at, jtg, perimetres_AT, time_slots_default)
                        eff_df_at = _apply_ops_to_grid(base_df_at, date_, jour, saison, category="AT")
                        day_hours = eff_df_at.values.sum() * 0.5
                        heures_vals_at_recalc.append(day_hours)
                        costs_vals_at_recalc.append(day_hours * tarif_at)
                    calendar_dyn["Heures_AT"] = heures_vals_at_recalc
                    calendar_dyn["Coût_AT"] = costs_vals_at_recalc
                    heure_cols_categories = [c for c in calendar_dyn.columns if c.startswith('Heures_') and c != 'Heures_Total_Jour']
                    cout_cols_categories = [c for c in calendar_dyn.columns if c.startswith('Coût_') and c != 'Coût_Total_Jour']
                    calendar_dyn['Heures_Total_Jour'] = calendar_dyn[heure_cols_categories].sum(axis=1) if heure_cols_categories else 0.0
                    calendar_dyn['Coût_Total_Jour'] = calendar_dyn[cout_cols_categories].sum(axis=1) if cout_cols_categories else 0.0
                    cur_hours_recalc = calendar_dyn['Heures_Total_Jour'].sum()
                    cur_cost_recalc = calendar_dyn['Coût_Total_Jour'].sum()
                    base_totals = bs.get('totals', {})
                    base_hours = float(base_totals.get('heures_annuel', 0.0))
                    base_cost = float(base_totals.get('cout_annuel', 0.0))
                    def _delta_str(cur, base, unit):
                        if base == 0: pct_str = "N/A" if cur == 0 else "+Inf%"; diff = cur
                        else: diff = cur - base; pct = (diff / base) * 100.0; pct_str = f"{pct:+.1f}%"
                        sign = "+" if diff >= 0 else ""
                        return f"{sign}{diff:,.0f} {unit} ({pct_str})"
                    st.markdown(f"""<div class="kpi-cards"><div class="kpi-card kpi-blue"><div class="label">Nouveau Total Heures Annuel</div><div class="value">{cur_hours_recalc:,.0f} h</div><div class="delta">{_delta_str(cur_hours_recalc, base_hours, "h")} vs Budget</div></div><div class="kpi-card kpi-amber"><div class="label">Nouveau Coût Annuel</div><div class="value">{cur_cost_recalc:,.0f} CHF</div><div class="delta">{_delta_str(cur_cost_recalc, base_cost, "CHF")} vs Budget</div></div></div>""", unsafe_allow_html=True)
                except Exception as e: st.error(f"Erreur lors du recalcul de l'impact annuel: {e}")

        with st.container(border=True):
            st.subheader("Périmètre de l'Ajustement")
            mode = st.radio("Portée", ["Date unique", "Plage de dates"], index=1, horizontal=True, key="bj_mode_select") 
            min_d = dt.date(year, 1, 1); max_d = dt.date(year, 12, 31)
            default_start = bs.get('selected_date', min_d)
            if not (min_d <= default_start <= max_d): default_start = min_d
            default_end = min(default_start + timedelta(days=6), max_d) 
            date_range_selected = [] 
            if mode == "Date unique":
                picked_date = st.date_input("Date cible", value=default_start, min_value=min_d, max_value=max_d, key="bj_single_date")
                date_range_selected = [picked_date] if picked_date else []
            else:  
                date_range_output = st.date_input("Plage de dates cible", value=(default_start, default_end), min_value=min_d, max_value=max_d, key="bj_date_range")
                if isinstance(date_range_output, (tuple, list)) and len(date_range_output) == 2:
                    start_d, end_d = date_range_output
                    if start_d and end_d:
                        if start_d > end_d: start_d, end_d = end_d, start_d 
                        date_range_selected = pd.date_range(start=start_d, end=end_d, freq='D').date.tolist()
                    else: date_range_selected = [] 
                else:
                    st.warning("Sélection de plage invalide. Réinitialisation à la plage par défaut.")
                    start_d, end_d = default_start, default_end
                    date_range_selected = pd.date_range(start=start_d, end=end_d, freq='D').date.tolist()
            
            date_range_final = []; jt_set = []
            if date_range_selected:
                try:
                    temp_df = pd.DataFrame({'Date': pd.to_datetime(date_range_selected)})
                    temp_df['Jour'] = _day_name_fr(temp_df['Date'])
                    temp_df['Saison'] = temp_df['Date'].apply(lambda dt: assign_season(dt.date()))
                    WEEK_ORDER = ["Lundi", "Mardi", "Mercredi", "Jeudi", "Vendredi", "Samedi", "Dimanche"]
                    jours_present = temp_df['Jour'].unique().tolist()
                    jours_in_range = [j for j in WEEK_ORDER if j in jours_present]
                    saisons_in_range = sorted(temp_df['Saison'].unique().tolist())
                    col_f1, col_f2 = st.columns(2)
                    with col_f1: jours_filter = st.multiselect("Filtrer par Jours (optionnel)", options=jours_in_range, default=[], key="bj_jours_filter")
                    with col_f2: saisons_filter = st.multiselect("Filtrer par Saisons (optionnel)", options=saisons_in_range, default=[], key="bj_saisons_filter")
                    filtered_dates_df = temp_df[temp_df['Jour'].isin(jours_filter if jours_filter else jours_in_range) & temp_df['Saison'].isin(saisons_filter if saisons_filter else saisons_in_range)]
                    date_range_final = filtered_dates_df['Date'].dt.date.tolist()
                    jt_set = sorted(filtered_dates_df.apply(lambda row: f"{row['Jour']} {row['Saison']}", axis=1).unique().tolist())
                    st.caption(f"{len(date_range_final)} jour(s) sélectionné(s) correspondant aux filtres. Jour-types (AT) impactés: {', '.join(jt_set) if jt_set else 'Aucun'}")
                except Exception as e: st.error(f"Erreur lors de l'application des filtres de date/saison: {e}"); date_range_final = []; jt_set = []
            else: st.warning("Veuillez sélectionner une date ou une plage valide.")

        tabs_besoin = st.tabs(["Vue & Analyse (Après Règles)", "Gérer les Règles d'Ajustement (AT)"])
        with tabs_besoin[0]: 
            if not date_range_final: st.info("Sélectionnez une date ou une plage valide et appliquez des filtres pour voir l'aperçu et l'impact.")
            else:
                with st.container(border=True):
                    st.subheader("Aperçu de la Grille AT (lecture seule)")
                    preview_date = date_range_final[0] 
                    if len(date_range_final) > 1: preview_date = st.selectbox("Choisir une date pour l'aperçu", options=date_range_final, format_func=lambda d: f"{_day_name_fr(pd.Series([pd.to_datetime(d)])).iloc[0]} {d.strftime('%d.%m.%Y')}", key="bj_preview_date_selector")
                    preview_jour = _day_name_fr(pd.Series(pd.to_datetime([preview_date]))).iloc[0]
                    preview_saison = assign_season(preview_date) 
                    preview_jt = f"{preview_jour} {preview_saison}"
                    perimetres_AT = st.session_state.perimetres.get("AT", [])
                    time_slots_default = [f"{h:02d}:{m:02d}" for h in range(4, 24) for m in (0, 30)]
                    planning_dict_at = st.session_state.planning_data.get("AT", {})
                    _, base_df = _ensure_grid(planning_dict_at, preview_jt, perimetres_AT, time_slots_default)
                    eff_df = _apply_ops_to_grid(base_df, preview_date, preview_jour, preview_saison, category="AT")
                    view_choice = st.radio("Afficher grille:", ("Après règles (effective)", "Base (avant règles)"), horizontal=True, key="bj_grid_view_toggle")
                    grid_to_show = eff_df if view_choice.startswith("Après") else base_df
                    def highlight_zero_rows(row): is_zero = (row == 0).all(); return ['background-color: #f0f0f0'] * len(row) if is_zero else [''] * len(row)
                    styled_grid = grid_to_show.style.apply(highlight_zero_rows, axis=1)
                    st.dataframe(styled_grid, use_container_width=True, height=(len(grid_to_show.index) + 1) * 35 + 3)
                    day_total_hours = grid_to_show.values.sum() * 0.5
                    tarif_at_day = 0.0
                    personnel_type_at_day = st.session_state.get('cost_mapping', {}).get("AT")
                    if personnel_type_at_day:
                        personnel_df_day = st.session_state.get('personnel', pd.DataFrame())
                        if not personnel_df_day.empty:
                            row_tarif_day = personnel_df_day[personnel_df_day['Type'] == personnel_type_at_day]
                            if not row_tarif_day.empty:
                                try: tarif_at_day = float(row_tarif_day['Coût Horaire'].iloc[0])
                                except (ValueError, TypeError): tarif_at_day = 0.0 
                    day_total_cost = day_total_hours * tarif_at_day
                    st.caption(f"**Total pour le {preview_date.strftime('%d.%m.%Y')} ({view_choice}):** {day_total_hours:,.1f} h / {day_total_cost:,.0f} CHF")

                    # --- BLOC PAX CORRIGÉ ---
                    st.divider()
                    st.subheader(f"Prévisions Passagers - {preview_date.strftime('%d.%m.%Y')}")
                    
                    if 'pax_forecast_data' in st.session_state and not st.session_state.pax_forecast_data.empty: # Utilise forecast_data
                        pax_agg_full = st.session_state.pax_forecast_data 
                        
                        pax_filter = st.radio("Filtrer le flux de passagers :", ('Tous', 'Arrivée', 'Départ'), horizontal=True, key="pax_flow_filter")
                        
                        df_day_raw = pax_agg_full[pax_agg_full.index.date == preview_date].copy()
                        
                        if not df_day_raw.empty:
                            df_day = pd.DataFrame(index=df_day_raw.index)
                            if pax_filter == 'Tous':
                                df_day['Pax Schengen'] = df_day_raw['Pax_Schengen_A'] + df_day_raw['Pax_Schengen_D']
                                df_day['Pax Non-Schengen'] = df_day_raw['Pax_NonSchengen_A'] + df_day_raw['Pax_NonSchengen_D']
                            elif pax_filter == 'Arrivée':
                                df_day['Pax Schengen'] = df_day_raw['Pax_Schengen_A']
                                df_day['Pax Non-Schengen'] = df_day_raw['Pax_NonSchengen_A']
                            elif pax_filter == 'Départ':
                                df_day['Pax Schengen'] = df_day_raw['Pax_Schengen_D']
                                df_day['Pax Non-Schengen'] = df_day_raw['Pax_NonSchengen_D']
                            
                            df_day['Pax Total'] = df_day['Pax Schengen'] + df_day['Pax Non-Schengen'] # Correction KeyError

                            total_pax_jour = df_day['Pax Total'].sum()
                            total_schengen = df_day['Pax Schengen'].sum()
                            total_non_schengen = df_day['Pax Non-Schengen'].sum()
                            
                            st.markdown(f"""<div class="kpi-cards"><div class="kpi-card kpi-blue"><div class="label">Total Passagers ({pax_filter})</div><div class="value">{total_pax_jour:,.0f}</div></div><div class="kpi-card kpi-green"><div class="label">Total Schengen ({pax_filter})</div><div class="value">{total_schengen:,.0f}</div></div><div class="kpi-card kpi-amber"><div class="label">Total Non-Schengen ({pax_filter})</div><div class="value">{total_non_schengen:,.0f}</div></div></div>""", unsafe_allow_html=True)
                            st.markdown("---")
                            
                            if total_pax_jour > 0: # Correction bug affichage heures
                                df_day['Heure'] = df_day.index.strftime('%H:%M')
                                df_chart_to_melt = df_day[['Heure', 'Pax Schengen', 'Pax Non-Schengen']]
                                df_chart_long = df_chart_to_melt.melt('Heure', var_name='Zone', value_name='Passagers')

                                chart = alt.Chart(df_chart_long).mark_bar().encode( # Correction bug affichage barres
                                    x=alt.X('Heure:O', sort=None, title='Heure'), 
                                    y=alt.Y('Passagers:Q', title=f'Nombre de Passagers ({pax_filter})'),
                                    color=alt.Color('Zone:N', title='Zone'),
                                    xOffset=alt.XOffset('Zone:N', title='Zone'), 
                                    tooltip=['Heure', 'Zone', 'Passagers']
                                ).properties().interactive()
                                
                                st.altair_chart(chart, use_container_width=True)
                            else: st.info(f"Aucune prévision passager ({pax_filter}) trouvée pour le {preview_date.strftime('%d.%m.%Y')}.")
                        else: st.info(f"Aucune prévision passager trouvée dans le fichier pour le {preview_date.strftime('%d.%m.%Y')}.")
                    else: st.info(f"Données prévisionnelles non chargées ou non trouvées dans '{PAX_DATA_FILE_PATH.name}'.")
                    # --- FIN DU BLOC PAX ---

        with tabs_besoin[1]: # Manage Rules Tab
            with st.container(border=True):
                st.subheader("Définir une Nouvelle Règle (AT)")
                if not date_range_final:
                    st.warning("Veuillez d'abord sélectionner une plage de dates et des filtres valides.")
                elif not jt_set:
                    st.info("La sélection de dates/filtres actuelle n'impacte aucun jour-type AT connu.")
                else:
                    # Get perimeters for AT category
                    perimetres_AT = st.session_state.perimetres.get("AT", [])
                    if not perimetres_AT:
                        st.error("Aucun périmètre défini pour AT dans la Configuration.")
                    else:
                        time_slots_default = [f"{h:02d}:{m:02d}" for h in range(4, 24) for m in (0, 30)]

                        # Form for adding a rule
                        with st.form(key="add_rule_form"):
                            st.caption(f"Cette règle s'appliquera aux {len(date_range_final)} jours sélectionnés via les filtres actifs.")
                            c1, c2, c3 = st.columns([0.5, 0.3, 0.2])
                            with c1:
                                rows_sel = st.multiselect("Périmètre(s) AT à modifier", options=perimetres_AT, key="rule_rows_sel")
                            with c2:
                                start_col, end_col = st.select_slider("Plage horaire à modifier", options=time_slots_default, value=(time_slots_default[0], time_slots_default[-1]), key="rule_range_cols")
                            with c3:
                                val_set = st.radio("Valeur", [1, 0], index=0, key="rule_value", horizontal=True)

                            submitted = st.form_submit_button("Ajouter la Règle")
                            if submitted:
                                if not rows_sel:
                                    st.error("Sélectionnez au moins un périmètre.")
                                elif not date_range_final:
                                    st.error("La plage de dates filtrée est vide. Ajustez les dates ou les filtres.")
                                else:
                                    # Create the rule dictionary using the *filtered* date range info
                                    new_rule = {
                                        'category': 'AT',
                                        'start': min(date_range_final), # Use min/max of the actual dates affected
                                        'end': max(date_range_final),
                                        'jours': jours_filter.copy(), # Store the filters used to define the scope
                                        'saisons': saisons_filter.copy(),
                                        'rows': rows_sel,
                                        'start_col': start_col,
                                        'end_col': end_col,
                                        'value': int(val_set)
                                    }
                                    st.session_state.besoin_jour_ops.append(new_rule)
                                    save_rules_to_json(st.session_state.besoin_jour_ops, RULES_BESOIN_JOUR_PATH)
                                    st.success(f"Règle ajoutée. Elle affectera les jours correspondants aux filtres dans la plage {min(date_range_final)} - {max(date_range_final)}.")
                                    st.rerun() # Rerun to update the list of rules below

            with st.container(border=True):
                st.subheader("Règles Enregistrées (AT)")
                # Get rules and their original indices BEFORE filtering
                all_ops_with_indices = list(enumerate(st.session_state.besoin_jour_ops))
                ops_at_with_indices = [(i, op) for i, op in all_ops_with_indices if op.get('category') == 'AT']


                if not ops_at_with_indices:
                    st.info("Aucune règle d'ajustement définie pour la catégorie AT.")
                else:
                    if st.button("Supprimer Toutes les Règles AT", type="secondary", key="delete_all_at_rules"):
                        # Rebuild the list excluding 'AT' rules
                        st.session_state.besoin_jour_ops = [op for op in st.session_state.besoin_jour_ops if op.get('category') != 'AT']
                        save_rules_to_json(st.session_state.besoin_jour_ops, RULES_BESOIN_JOUR_PATH)
                        st.success("Toutes les règles AT ont été supprimées.")
                        st.rerun()
                    st.divider()

                    # Display rules individually using their original index for keys and deletion
                    indices_to_delete = [] # Store indices to delete after iteration
                    for original_index, op in ops_at_with_indices:
                        col1, col2 = st.columns([0.9, 0.1]) # Adjusted column ratio slightly
                        with col1:
                            # Display rule details
                            jours_str = ", ".join(op.get('jours', [])) or 'Tous'
                            saisons_str = ", ".join(op.get('saisons', [])) or 'Toutes'
                            rows_str = ", ".join(op.get('rows', []))
                            start_str = _date_to_str(op.get('start', 'N/A'))
                            end_str = _date_to_str(op.get('end', 'N/A'))
                            rule_color = '#28a745' if op.get('value', 0) == 1 else '#dc3545' # Green for 1, Red for 0
                            st.markdown(f"""
                            <div class="rule-card" style="--rule-color:{rule_color};">
                                <p><strong>Période:</strong> {start_str} au {end_str}</p>
                                <p><strong>Filtres:</strong> Jours: [{jours_str}] / Saisons: [{saisons_str}]</p>
                                <p><strong>Action:</strong> Mettre à <strong>{op.get('value', 'N/A')}</strong> de {op.get('start_col', 'N/A')} à {op.get('end_col', 'N/A')} pour : <i>{rows_str}</i></p>
                            </div>
                            """, unsafe_allow_html=True)
                        with col2:
                            # Delete button linked to the original index
                            if st.button("❌", key=f"del_rule_{original_index}", help=f"Supprimer cette règle", use_container_width=True):
                                indices_to_delete.append(original_index) # Mark for deletion

                    # Process deletions after the loop
                    if indices_to_delete:
                        # Sort indices in reverse order to avoid shifting issues during pop
                        indices_to_delete.sort(reverse=True)
                        deleted_count = 0
                        try:
                            original_list_len = len(st.session_state.besoin_jour_ops)
                            for index_to_del in indices_to_delete:
                                # Double check index validity before popping
                                if 0 <= index_to_del < len(st.session_state.besoin_jour_ops):
                                    # Verify it's still an AT rule before deleting (safety check)
                                    if st.session_state.besoin_jour_ops[index_to_del].get('category') == 'AT':
                                            st.session_state.besoin_jour_ops.pop(index_to_del)
                                            deleted_count += 1
                                    else:
                                            st.warning(f"Tentative de suppression d'une règle non-AT à l'index {index_to_del}. Ignoré.")
                                else:
                                    st.error(f"Erreur: Index {index_to_del} hors limites lors de la suppression.")
                            if deleted_count > 0:
                                save_rules_to_json(st.session_state.besoin_jour_ops, RULES_BESOIN_JOUR_PATH)
                                st.success(f"{deleted_count} règle(s) supprimée(s).")
                                st.rerun()
                        except Exception as e:
                            st.error(f"Erreur inattendue lors de la suppression des règles: {e}")


        ### --- Display editors for other categories (unaffected by rules) ---
        st.divider()
        st.subheader("Planification Standard des Autres Catégories")
        other_categories = [cat for cat in st.session_state.get('perimetres', {}).keys() if cat != 'AT']
        if other_categories:
            # Sort tabs alphabetically
            sorted_other_categories = sorted(other_categories)
            other_tabs = st.tabs(sorted_other_categories)
            for i, cat_key in enumerate(sorted_other_categories):
                with other_tabs[i]:
                    with st.container(): # Using container for potential future bordering
                        _render_grid_for_edit(cat_key, "Default", title_suffix="(Standard)")
        else:
            st.info("Aucune autre catégorie de planification n'est définie dans la Configuration.")  


    elif page == "Simulateur Objectif":
        st.title("Simulateur d'Objectif de Coût")
        st.markdown("Simulez l'impact en heures d'un ajustement de coût global (augmentation/réduction) en le répartissant sur les catégories.")

        # --- Pré-requis : Doit avoir un budget généré ---
        bs = st.session_state.get('budget_state', {})
        if not bs or 'year' not in bs or 'calendar_df' not in bs or bs['calendar_df'].empty:
            st.warning("⚠️ Aucun budget annuel valide en mémoire. Veuillez d'abord en générer un via la page **Budget Annuel**.")
            st.stop()
        
        # --- Logique du Simulateur ---
        with st.container(border=True):
            st.subheader("Simulation d'Objectif de Coût Annuel")
            st.markdown("Répartissez un objectif de coût global (augmentation/réduction) entre les catégories pour voir l'impact en heures. *Cet outil est un simulateur et n'applique pas de règles.*")

            # 1. Get Base Data
            base_cost_total = bs.get('totals', {}).get('cout_annuel', 0.0)
            cost_mapping = st.session_state.get('cost_mapping', {})
            personnel_df = st.session_state.get('personnel', pd.DataFrame())
            all_categories = sorted(list(st.session_state.get('perimetres', {}).keys()))

            st.metric("Budget Annuel de Base (avant règles)", f"{base_cost_total:,.0f} CHF")
            
            # 2. Build Hourly Rate Mapping
            category_hourly_rates = {}
            missing_rates = []
            if personnel_df.empty:
                st.error("Définissez les tarifs du personnel dans la 'Configuration'.")
            else:
                for cat in all_categories:
                    personnel_type = cost_mapping.get(cat)
                    if personnel_type:
                        rate_row = personnel_df[personnel_df['Type'] == personnel_type]
                        if not rate_row.empty:
                            try:
                                rate = float(rate_row['Coût Horaire'].iloc[0])
                                if rate > 0:
                                    category_hourly_rates[cat] = rate
                                else:
                                    category_hourly_rates[cat] = 0.0
                                    missing_rates.append(f"'{cat}' (tarif à 0)")
                            except Exception:
                                category_hourly_rates[cat] = 0.0
                                missing_rates.append(f"'{cat}' (tarif invalide)")
                        else:
                            category_hourly_rates[cat] = 0.0
                            missing_rates.append(f"'{cat}' (type '{personnel_type}' non trouvé)")
                    else:
                        category_hourly_rates[cat] = 0.0
                        missing_rates.append(f"'{cat}' (pas de mapping)")
            
            if missing_rates:
                st.warning(f"Calcul impossible pour : {', '.join(missing_rates)}. Vérifiez 'Configuration' et 'Association des Coûts'.")

            st.divider()

            # 3. User Inputs
            target_adjustment = st.number_input(
                "Objectif d'ajustement (en CHF, négatif pour réduire)", 
                value=0.0, 
                step=1000.0, 
                format="%.0f",
                key="sim_target_adjustment" # La clé est unique car sur une nouvelle page
            )
            
            st.markdown("**Répartition de l'ajustement (%) :**")
            
            # Use st.columns for layout
            num_categories = len(all_categories)
            cols_per_row = 5 # Adjust as needed
            num_rows = (num_categories + cols_per_row - 1) // cols_per_row
            
            distrib_pct = {}
            total_pct = 0.0
            
            cat_iter = iter(all_categories)
            for _ in range(num_rows):
                cols = st.columns(cols_per_row)
                for i in range(cols_per_row):
                    try:
                        cat = next(cat_iter)
                        with cols[i]:
                            # Initialize pct to 0 if not in state
                            if f'distrib_pct_{cat}' not in st.session_state:
                                st.session_state[f'distrib_pct_{cat}'] = 0.0
                            
                            pct = st.number_input(
                                f"% {cat}", 
                                min_value=0.0, 
                                max_value=100.0, 
                                value=st.session_state[f'distrib_pct_{cat}'], 
                                step=1.0, 
                                key=f'distrib_pct_{cat}', # La clé est unique
                                format="%.1f"
                            )
                            distrib_pct[cat] = pct
                            total_pct += pct
                    except StopIteration:
                        pass # No more categories for this row
            
            # Display total percentage
            if abs(total_pct - 100.0) > 0.1:
                st.warning(f"Le total des pourcentages est de **{total_pct:.1f}%**. Il devrait être de 100%.")
            else:
                st.success(f"Total des pourcentages : {total_pct:.1f}%.")

            st.divider()

            # 4. Calculation and Display
            if target_adjustment != 0:
                if abs(total_pct) < 0.1:
                     st.error("Veuillez définir une répartition (pourcentage) pour au moins une catégorie.")
                else:
                    results = []
                    for cat in all_categories:
                        # Normaliser la répartition si le total n'est pas 100%
                        pct_of_target = (distrib_pct.get(cat, 0.0) / total_pct) if total_pct > 0 else 0.0
                        
                        cost_adjustment_cat_raw = target_adjustment * pct_of_target
                        cost_adjustment_cat = np.ceil(cost_adjustment_cat_raw)
                        
                        hourly_rate = category_hourly_rates.get(cat, 0.0)
                        
                        hour_adjustment_cat = 0.0
                        if hourly_rate > 0:
                            hour_adjustment_cat_raw = cost_adjustment_cat_raw / hourly_rate # Utilise le coût non arrondi pour un calcul d'heures plus précis...
                            hour_adjustment_cat = np.ceil(hour_adjustment_cat_raw) # ...puis arrondit le résultat
                        elif cost_adjustment_cat != 0:
                            hour_adjustment_cat = 999999.0  # Valeur très grande indiquant l'impossibilité
                        
                        results.append({
                            'Catégorie': cat,
                            'Part Répartition (%)': distrib_pct.get(cat, 0.0), # Afficher le % saisi par l'utilisateur
                            'Ajustement Coût (CHF)': cost_adjustment_cat,
                            'Tarif Horaire (CHF)': hourly_rate,
                            'Ajustement Heures (h)': hour_adjustment_cat
                        })
                    
                    results_df = pd.DataFrame(results)
                    # Filter out rows with 0% distribution
                    results_df = results_df[results_df['Part Répartition (%)'] > 0].copy()

                    st.subheader("Résultat de la Simulation")
                    # Afficher un avertissement si le total n'est pas 100%
                    if abs(total_pct - 100.0) > 0.1:
                        st.info(f"Note : Les montants ont été ajustés proportionnellement car le total de la répartition est de {total_pct:.1f}%.")

                    st.dataframe(
                        results_df,
                        column_config={
                            'Part Répartition (%)': st.column_config.NumberColumn(format="%.1f%%"),
                            'Ajustement Coût (CHF)': st.column_config.NumberColumn(format="%,.0f CHF"),
                            'Tarif Horaire (CHF)': st.column_config.NumberColumn(format="%.2f CHF"),
                            'Ajustement Heures (h)': st.column_config.NumberColumn(format="%,.0f h"),
                         
                        },
                        hide_index=True, 
                        use_container_width=True
                    )
            else:
                st.info("Saisissez un objectif d'ajustement non nul pour lancer la simulation.")
            


    elif page == "Comparaison Historique":
        st.title("Comparaison Historique vs Prévisions Passagers")
        st.markdown("Comparez les volumes de passagers entre une date passée et une date future.")

        # --- MODIFICATION : VÉRIFIER LES STATUTS SÉPARÉS ---
        hist_loaded = st.session_state.get('pax_historical_status') == "loaded"
        fc_loaded = st.session_state.get('pax_forecast_status') == "loaded" # Vérifie le statut forecast

        if not hist_loaded or not fc_loaded:
            messages = []
            if not hist_loaded: messages.append("historiques")
            if not fc_loaded: messages.append("prévisionnelles")
            st.warning(f"Données passagers {' et '.join(messages)} non disponibles. Vérifiez le fichier '{PAX_DATA_FILE_PATH.name}'.")
            st.stop()
        # --- FIN MODIFICATION ---

        # Récupérer les données et les plages de dates spécifiques
        hist_data = st.session_state.pax_historical_data
        hist_min = st.session_state.pax_historical_min_date
        hist_max = st.session_state.pax_historical_max_date
        
        fc_data = st.session_state.pax_forecast_data # Utilise forecast_data
        fc_min = st.session_state.pax_forecast_min_date
        fc_max = st.session_state.pax_forecast_max_date

        # --- Calcul de la date historique par défaut ---
        default_forecast_date = fc_min # Date prévisionnelle par défaut
        default_historical_date = hist_max # Fallback par défaut

        try:
            # Date cible approximative (même jour/mois, année N-1)
            target_hist_date_approx = default_forecast_date.replace(year=default_forecast_date.year - 1)
            
            # Jour de la semaine de la date prévisionnelle (0=Lundi, ..., 6=Dimanche)
            target_weekday = default_forecast_date.weekday()
            
            # Trouver la date N-1 la plus proche ayant le même jour de la semaine
            calculated_hist_date = find_closest_weekday(target_hist_date_approx, target_weekday)
            
            # Vérifier si cette date est DANS la plage historique disponible
            if hist_min <= calculated_hist_date <= hist_max:
                default_historical_date = calculated_hist_date
            else:
                # Si hors plage, on garde hist_max mais on prévient l'utilisateur
                st.caption(f"Note: La date historique correspondante ({calculated_hist_date.strftime('%d.%m.%Y')}) est hors plage disponible ({hist_min.strftime('%d.%m.%Y')} - {hist_max.strftime('%d.%m.%Y')}). Utilisation de la date la plus récente ({hist_max.strftime('%d.%m.%Y')}).")
                default_historical_date = hist_max # Utilise le fallback défini plus haut

        except Exception as e:
            # En cas d'erreur de calcul (ex: date invalide, très peu probable ici)
            st.warning(f"Erreur lors du calcul de la date historique par défaut: {e}. Utilisation de {hist_max.strftime('%d.%m.%Y')}.")
            default_historical_date = hist_max # Assure qu'on a une valeur valide

        # Sélecteurs de date (les min/max sont maintenant corrects)
        col1, col2 = st.columns(2)
        with col1:
            historical_date = st.date_input("Choisir la date historique de référence", value=default_historical_date, min_value=hist_min, max_value=hist_max, key="hist_date_compare")
        with col2:
             forecast_date = st.date_input("Choisir la date prévisionnelle à comparer", value=default_forecast_date, min_value=fc_min, max_value=fc_max, key="fc_date_compare")
            
        pax_filter_compare = st.radio("Filtrer le flux :", ('Tous', 'Arrivée', 'Départ'), horizontal=True, key="pax_flow_filter_compare")

        if historical_date and forecast_date:
            
            def get_filtered_daily_pax(data, selected_date, pax_filter):
                df_day_raw = data[data.index.date == selected_date].copy()
                if df_day_raw.empty: return pd.DataFrame(columns=['Pax Schengen', 'Pax Non-Schengen', 'Pax Total'])
                df_day = pd.DataFrame(index=df_day_raw.index)
                if pax_filter == 'Tous':
                    df_day['Pax Schengen'] = df_day_raw['Pax_Schengen_A'] + df_day_raw['Pax_Schengen_D']
                    df_day['Pax Non-Schengen'] = df_day_raw['Pax_NonSchengen_A'] + df_day_raw['Pax_NonSchengen_D']
                elif pax_filter == 'Arrivée':
                    df_day['Pax Schengen'] = df_day_raw['Pax_Schengen_A']
                    df_day['Pax Non-Schengen'] = df_day_raw['Pax_NonSchengen_A']
                elif pax_filter == 'Départ':
                    df_day['Pax Schengen'] = df_day_raw['Pax_Schengen_D']
                    df_day['Pax Non-Schengen'] = df_day_raw['Pax_NonSchengen_D']
                df_day['Pax Total'] = df_day['Pax Schengen'] + df_day['Pax Non-Schengen']
                return df_day

            hist_day_pax = get_filtered_daily_pax(hist_data, historical_date, pax_filter_compare)
            fc_day_pax = get_filtered_daily_pax(fc_data, forecast_date, pax_filter_compare)

            hist_total = hist_day_pax['Pax Total'].sum()
            fc_total = fc_day_pax['Pax Total'].sum()
            delta_total = fc_total - hist_total
            delta_pct = (delta_total / hist_total * 100) if hist_total != 0 else 0.0

            st.markdown("---")
            st.subheader(f"Comparaison Passagers ({pax_filter_compare})")

            col_kpi1, col_kpi2, col_kpi3 = st.columns(3)
            with col_kpi1: st.metric(f"Historique ({historical_date.strftime('%d.%m')})", f"{hist_total:,.0f}")
            with col_kpi2: st.metric(f"Prévisions ({forecast_date.strftime('%d.%m')})", f"{fc_total:,.0f}")
            with col_kpi3:
                 delta_sign = "+" if delta_total >= 0 else ""; delta_pct_str = f"{delta_pct:+.1f}%" if abs(delta_pct) < 1e10 else "N/A"
                 st.metric("Delta vs Historique", f"{delta_sign}{delta_total:,.0f}", f"{delta_pct_str}")

            # --- AT à partir des fichiers "Facturation Lot A mm.yyyy.xlsx" ---
            st.markdown("---")
            st.subheader("AT – Heures facturées (historique) & estimation (variation PAX)")

            try:
                # Utilise la fonction fournie précédemment (basée sur 'Total dd.mm.yyyy' du fichier mensuel)
                res = estimate_at_hours_from_pax_variation(
                    historical_date,  # date historique sélectionnée dans cette page
                    forecast_date     # date prévisionnelle sélectionnée dans cette page
                )

                c1, c2, c3, c4 = st.columns(4)
                with c1:
                    st.metric("AT facturé (jour hist.)", f"{res['heures_hist']:.1f} h")
                with c2:
                    fact_txt = "N/A" if res["facteur"] is None else f"{res['facteur']:.2f}×"
                    st.metric("Facteur PAX (fc/hist)", fact_txt)
                with c3:
                    st.metric("AT estimé (jour fc)", f"{res['heures_estimees']:.1f} h")
                with c4:
                    st.caption(f"PAX hist: {res['pax_hist']:.0f} | PAX fc: {res['pax_fc']:.0f}")

                st.info("Règle : AT_est = AT_hist × (PAX_forecast / PAX_hist). Arrondi au pas de 0,5 h.")
            except Exception as e:
                st.warning(f"Calcul AT indisponible : {e}")


            hist_day_pax['Type'] = 'Historique'; fc_day_pax['Type'] = 'Prévisions'
            
            combined_pax = pd.concat([hist_day_pax[['Pax Schengen', 'Pax Non-Schengen', 'Type']], fc_day_pax[['Pax Schengen', 'Pax Non-Schengen', 'Type']]], sort=True).fillna(0)
            combined_pax['Heure'] = combined_pax.index.strftime('%H:%M')
            
            pax_long = combined_pax.melt(id_vars=['Heure', 'Type'], value_vars=['Pax Schengen', 'Pax Non-Schengen'], var_name='Zone', value_name='Passagers')

            # Créer le graphique Altair comparatif groupé par Heure et Type
            chart_compare = alt.Chart(pax_long).mark_bar().encode(
                # L'axe X principal est l'Heure
                x=alt.X('Heure:O', sort=None, title='Heure'),
                
                # L'axe Y est le nombre de passagers
                y=alt.Y('Passagers:Q', title=f'Passagers ({pax_filter_compare})'),
                
                # La couleur distingue Schengen / Non-Schengen
                color=alt.Color('Zone:N', title='Zone'),
                
                # xOffset groupe Historique / Prévisions côte à côte pour chaque Heure
                xOffset=alt.XOffset('Type:N', title='Type'), 
                
                # Tooltip pour les détails
                tooltip=['Heure', 'Type', 'Zone', 'Passagers']
            ).properties(
                # Ajuster la largeur si les barres sont trop serrées
                # width=alt.Step(20) 
            ).interactive()

            st.altair_chart(chart_compare, use_container_width=True)

        
        else: st.info("Veuillez sélectionner une date historique et une date prévisionnelle.")


    elif page == "Simulateur Objectif":
        st.title("Simulateur d'Objectif de Coût")
        st.markdown("Simulez l'impact en heures d'un ajustement de coût global (augmentation/réduction) en le répartissant sur les catégories.")
        bs = st.session_state.get('budget_state', {})
        if not bs or 'year' not in bs or 'calendar_df' not in bs or bs['calendar_df'].empty:
            st.warning("⚠️ Aucun budget annuel valide en mémoire. Veuillez d'abord en générer un via la page **Budget Annuel**.")
            st.stop()
        with st.container(border=True):
            st.subheader("Simulation d'Objectif de Coût Annuel")
            st.markdown("Répartissez un objectif de coût global (augmentation/réduction) entre les catégories pour voir l'impact en heures. *Cet outil est un simulateur et n'applique pas de règles.*")
            base_cost_total = bs.get('totals', {}).get('cout_annuel', 0.0)
            cost_mapping = st.session_state.get('cost_mapping', {})
            personnel_df = st.session_state.get('personnel', pd.DataFrame())
            all_categories = sorted(list(st.session_state.get('perimetres', {}).keys()))
            st.metric("Budget Annuel de Base (avant règles)", f"{base_cost_total:,.0f} CHF")
            category_hourly_rates = {}; missing_rates = []
            if personnel_df.empty: st.error("Définissez les tarifs du personnel dans la 'Configuration'.")
            else:
                for cat in all_categories:
                    personnel_type = cost_mapping.get(cat)
                    if personnel_type:
                        rate_row = personnel_df[personnel_df['Type'] == personnel_type]
                        if not rate_row.empty:
                            try:
                                rate = float(rate_row['Coût Horaire'].iloc[0])
                                if rate > 0: category_hourly_rates[cat] = rate
                                else: category_hourly_rates[cat] = 0.0; missing_rates.append(f"'{cat}' (tarif à 0)")
                            except Exception: category_hourly_rates[cat] = 0.0; missing_rates.append(f"'{cat}' (tarif invalide)")
                        else: category_hourly_rates[cat] = 0.0; missing_rates.append(f"'{cat}' (type '{personnel_type}' non trouvé)")
                    else: category_hourly_rates[cat] = 0.0; missing_rates.append(f"'{cat}' (pas de mapping)")
            if missing_rates: st.warning(f"Calcul impossible pour : {', '.join(missing_rates)}. Vérifiez 'Configuration' et 'Association des Coûts'.")
            st.divider()
            target_adjustment = st.number_input("Objectif d'ajustement (en CHF, négatif pour réduire)", value=0.0, step=1000.0, format="%.0f", key="sim_target_adjustment")
            st.markdown("**Répartition de l'ajustement (%) :**")
            num_categories = len(all_categories); cols_per_row = 5; num_rows = (num_categories + cols_per_row - 1) // cols_per_row
            distrib_pct = {}; total_pct = 0.0
            cat_iter = iter(all_categories)
            for _ in range(num_rows):
                cols = st.columns(cols_per_row)
                for i in range(cols_per_row):
                    try:
                        cat = next(cat_iter)
                        with cols[i]:
                            if f'distrib_pct_{cat}' not in st.session_state: st.session_state[f'distrib_pct_{cat}'] = 0.0
                            pct = st.number_input(f"% {cat}", min_value=0.0, max_value=100.0, value=st.session_state[f'distrib_pct_{cat}'], step=1.0, key=f'distrib_pct_{cat}', format="%.1f")
                            distrib_pct[cat] = pct; total_pct += pct
                    except StopIteration: pass 
            if abs(total_pct - 100.0) > 0.1: st.warning(f"Le total des pourcentages est de **{total_pct:.1f}%**. Il devrait être de 100%.")
            else: st.success(f"Total des pourcentages : {total_pct:.1f}%.")
            st.divider()
            if target_adjustment != 0:
                if abs(total_pct) < 0.1: st.error("Veuillez définir une répartition (pourcentage) pour au moins une catégorie.")
                else:
                    results = []
                    for cat in all_categories:
                        pct_of_target = (distrib_pct.get(cat, 0.0) / total_pct) if total_pct > 0 else 0.0
                        cost_adjustment_cat_raw = target_adjustment * pct_of_target
                        cost_adjustment_cat = np.ceil(cost_adjustment_cat_raw)
                        hourly_rate = category_hourly_rates.get(cat, 0.0)
                        hour_adjustment_cat = 0.0
                        if hourly_rate > 0: hour_adjustment_cat_raw = cost_adjustment_cat_raw / hourly_rate; hour_adjustment_cat = np.ceil(hour_adjustment_cat_raw) 
                        elif cost_adjustment_cat != 0: hour_adjustment_cat = 999999.0  # Très grande valeur
                        results.append({'Catégorie': cat, 'Part Répartition (%)': distrib_pct.get(cat, 0.0), 'Ajustement Coût (CHF)': cost_adjustment_cat, 'Tarif Horaire (CHF)': hourly_rate, 'Ajustement Heures (h)': hour_adjustment_cat})
                    results_df = pd.DataFrame(results)
                    results_df = results_df[results_df['Part Répartition (%)'] > 0].copy()
                    st.subheader("Résultat de la Simulation")
                    if abs(total_pct - 100.0) > 0.1: st.info(f"Note : Les montants ont été ajustés proportionnellement car le total de la répartition est de {total_pct:.1f}%.")
                    st.dataframe(results_df, column_config={'Part Répartition (%)': st.column_config.NumberColumn(format="%.1f%%"), 'Ajustement Coût (CHF)': st.column_config.NumberColumn(format="%,.0f CHF"), 'Tarif Horaire (CHF)': st.column_config.NumberColumn(format="%.2f CHF"), 'Ajustement Heures (h)': st.column_config.NumberColumn(format="%,.0f h"),}, hide_index=True, use_container_width=True)
            else: st.info("Saisissez un objectif d'ajustement non nul pour lancer la simulation.")
