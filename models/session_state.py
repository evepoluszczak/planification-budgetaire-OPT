"""
Initialisation de l'état de session (données de base 2026)
"""
import datetime as dt
import numpy as np
import pandas as pd
import streamlit as st
from config.constants import TIME_SLOTS, RULES_BESOIN_JOUR_PATH
from core.rules import load_rules_from_json
from core.budget import generate_budget_state
from models.planif_AT_base import DATA as AT_DATA


def initialize_session_state_2026():
    """Initialise l'état de session avec les données de base 2026"""

    # Personnel et tarifs
    st.session_state.personnel = pd.DataFrame([
        {'Type': 'AT', 'Coût Horaire': 45.50},
        {'Type': 'ATR', 'Coût Horaire': 54.00},
        {'Type': 'ATF', 'Coût Horaire': 54.00},
        {'Type': 'CSC', 'Coût Horaire': 42.00},
        {'Type': 'EES', 'Coût Horaire': 43.00},
        {'Type': 'AT Resp', 'Coût Horaire': 54.00},
        {'Type': 'Sect FR', 'Coût Horaire': 41.00},
    ])

    # Saisons de référence
    st.session_state.saisons = pd.DataFrame([
        {'Saison': 'Hiver', 'Date Début': dt.date(2026, 1, 1), 'Date Fin': dt.date(2026, 3, 28)},
        {'Saison': 'Standard', 'Date Début': dt.date(2026, 3, 29), 'Date Fin': dt.date(2026, 6, 27)},
        {'Saison': 'Été', 'Date Début': dt.date(2026, 6, 28), 'Date Fin': dt.date(2026, 8, 29)},
        {'Saison': 'Standard', 'Date Début': dt.date(2026, 8, 30), 'Date Fin': dt.date(2026, 10, 24)},
        {'Saison': 'Hiver', 'Date Début': dt.date(2026, 10, 25), 'Date Fin': dt.date(2026, 12, 31)},
    ])
    st.session_state.reference_year_saisons = 2026

    # Périmètres par catégorie
    st.session_state.perimetres = {
        "AT": [
            'Check in 1', 'Check in 2', 'Check in 3', 'Guichet info', 'Transit',
            'Aile Est Départ', 'Aile Est Départ ABC', 'Aile Est Arrivée',
            'Aile Est Arrivée ABC', 'Aile Est Arrivée Transf.',
            'Aile Est Arrivée dispatch', "Sect. France", "Visitor's Center",
            'Hall bagage (+ Transfert)', 'Accueil famille CSC', 'Accueil famille AE',
            'Accès Sect. France', 'Priority Lane', 'T2 Arrivée', 'T2 Départ',
            'T2 Portier', 'T2 Renfort'
        ],
        "CSC": [
            'CSC 1 Dispatch E-gate', 'CSC 2 Assistant E-gate',
            'CSC 3 Dispatch PL / M 1-8', 'CSC 4 Dispatch M 9-16',
            'CSC 5 Dispatch M Boosted', 'CSC 6 SR1 M Boosted',
            'CSC 7 SR1 M Boosted', 'CSC 8 SR1 M Boosted', 'CSC 9 SR1 M Boosted'
        ],
        "EES": ['EES 1', 'EES 2', 'EES 3', 'EES 4', 'EES 5', 'EES 6', 'EES 7', 'EES 8'],
        "Sect. FR": ['Entrée Secteur France', 'Sortie Secteur France'],
        "AT Resp.": ['AT Resp. Aile Est', 'AT Resp. CSC', 'Coordinateur']
    }

    # Initialiser les données de planification
    st.session_state.planning_data = {}

    def parse_grid_from_markers(data_dict, perimetres_list):
        """Parse une grille à partir de markers (0/1/NaN)"""
        grid = pd.DataFrame(0, index=perimetres_list, columns=TIME_SLOTS, dtype=int)
        for perimetre, markers in data_dict.items():
            if perimetre in grid.index:
                full_markers = (markers + [0] * len(TIME_SLOTS))[:len(TIME_SLOTS)]
                grid.loc[perimetre] = [
                    1 if (not pd.isna(m) and str(m).strip() == '1') else 0
                    for m in full_markers
                ]
        return grid.fillna(0).astype(int).clip(0, 1)

    # Initialiser chaque catégorie avec des grilles par défaut
    for cat, perims in st.session_state.perimetres.items():
        st.session_state.planning_data[cat] = {}

        if cat == 'AT':
            # Charger les données AT depuis planif_AT_base.py
            for jour_saison, day_data in AT_DATA.items():
                st.session_state.planning_data[cat][jour_saison] = parse_grid_from_markers(day_data, perims)
            # Ajouter aussi une grille "Default" (copie de Lundi Standard)
        elif cat == 'CSC':
            # Distributions spécifiques par périmètre CSC
            csc_data = {}
            for p in perims:
                if p in ['CSC 1 Dispatch E-gate', 'CSC 2 Assistant E-gate',
                        'CSC 6 SR1 M Boosted', 'CSC 7 SR1 M Boosted',
                        'CSC 8 SR1 M Boosted', 'CSC 9 SR1 M Boosted']:
                    csc_data[p] = [1]*34 + [0]*(len(TIME_SLOTS)-34)
                elif p == 'CSC 3 Dispatch PL / M 1-8':
                    csc_data[p] = [1]*32 + [0]*(len(TIME_SLOTS)-32)
                elif p == 'CSC 4 Dispatch M 9-16':
                    csc_data[p] = [1]*30 + [0]*(len(TIME_SLOTS)-30)
                elif p == 'CSC 5 Dispatch M Boosted':
                    csc_data[p] = [1]*28 + [0]*(len(TIME_SLOTS)-28)
                else:
                    # Pour tout autre périmètre CSC non spécifié
                    csc_data[p] = [1]*34 + [0]*(len(TIME_SLOTS)-34)
            st.session_state.planning_data[cat]['Default'] = parse_grid_from_markers(csc_data, perims)
        elif cat == 'EES':
            # Distributions spécifiques par périmètre EES
            ees_data = {}
            for p in perims:
                if p in ['EES 1', 'EES 2', 'EES 3']:
                    ees_data[p] = ([0]*4 + [1]*32 + [0]*(len(TIME_SLOTS)-36))[:len(TIME_SLOTS)]
                elif p in ['EES 4', 'EES 5', 'EES 6', 'EES 7']:
                    ees_data[p] = ([0]*4 + [1]*36 + [0]*(len(TIME_SLOTS)-40))[:len(TIME_SLOTS)]
                else:
                    # Pour tout autre périmètre EES (EES 8 par exemple)
                    ees_data[p] = ([0]*4 + [1]*32 + [0]*(len(TIME_SLOTS)-36))[:len(TIME_SLOTS)]
            st.session_state.planning_data[cat]['Default'] = parse_grid_from_markers(ees_data, perims)
        elif cat == 'Sect. FR':
            sect_fr_data = {p: ([1]*41 + [0]*(len(TIME_SLOTS)-41))[:len(TIME_SLOTS)] for p in perims}
            st.session_state.planning_data[cat]['Default'] = parse_grid_from_markers(sect_fr_data, perims)
        elif cat == 'AT Resp.':
            at_resp_data = {
                'AT Resp. Aile Est': [0]*4 + [1]*28 + [0]*(len(TIME_SLOTS)-32),
                'AT Resp. CSC': [1]*32 + [0]*(len(TIME_SLOTS)-32),
                'Coordinateur': [1]*3 + [0]*(len(TIME_SLOTS)-3)
            }
            full_at_resp_data = {p: at_resp_data.get(p, [0]*len(TIME_SLOTS)) for p in perims}
            st.session_state.planning_data[cat]['Default'] = parse_grid_from_markers(full_at_resp_data, perims)
        else:
            # Pour toute autre catégorie, grille vide par défaut
            st.session_state.planning_data[cat]['Default'] = pd.DataFrame(
                0, index=perims, columns=TIME_SLOTS
            ).astype(int)

    # Initialiser le mapping des coûts
    st.session_state.cost_mapping = {}
    personnel_types = st.session_state.personnel['Type'].tolist()
    for cat in st.session_state.perimetres.keys():
        match = cat.replace('.', '')
        if match in personnel_types:
            st.session_state.cost_mapping[cat] = match
        elif cat == 'Sect. FR' and 'Sect FR' in personnel_types:
            st.session_state.cost_mapping[cat] = 'Sect FR'
        elif personnel_types:
            st.session_state.cost_mapping[cat] = personnel_types[0]

    # Charger les règles Besoin Jour
    st.session_state.besoin_jour_ops = load_rules_from_json(RULES_BESOIN_JOUR_PATH)

    # Initialiser la table Formation / Doublure AT
    if 'budget_formation_at' not in st.session_state:
        st.session_state.budget_formation_at = pd.DataFrame([
            {'Dénomination': 'Formation (théorique) AT S26', 'Effectif (pers.)': 20, 'Heures': 17.0, 'Nbre de shifts': 1},
            {'Dénomination': 'Formation (pratique) AT S26', 'Effectif (pers.)': 20, 'Heures': 6.5, 'Nbre de shifts': 3},
            {'Dénomination': 'Formation (théorique) AT CHT W26', 'Effectif (pers.)': 20, 'Heures': 17.0, 'Nbre de shifts': 1},
            {'Dénomination': 'Formation (pratique) AT CHT W26', 'Effectif (pers.)': 20, 'Heures': 6.5, 'Nbre de shifts': 3},
            {'Dénomination': "Formation Visitor's Center", 'Effectif (pers.)': 20, 'Heures': 4.0, 'Nbre de shifts': 1},
            {'Dénomination': 'Refresher AT CDI', 'Effectif (pers.)': 0, 'Heures': 0.0, 'Nbre de shifts': 0},
            {'Dénomination': 'Cours FEU', 'Effectif (pers.)': 40, 'Heures': 3.0, 'Nbre de shifts': 1},
            {'Dénomination': 'Cours DEFI', 'Effectif (pers.)': 40, 'Heures': 2.0, 'Nbre de shifts': 1}
        ])

    # Initialiser la table Shift AT Formateurs planifiés
    if 'budget_formateurs_at' not in st.session_state:
        st.session_state.budget_formateurs_at = pd.DataFrame([
            {'Dénomination': 'Formation (théorique) AT S26', 'Effectif (pers.)': 2, 'Heures': 17.0, 'Nbre de shifts': 1},
            {'Dénomination': 'Doublure formation (pratique) AT S26', 'Effectif (pers.)': 20, 'Heures': 6.5, 'Nbre de shifts': 4},
            {'Dénomination': 'Formation (théorique) AT CHT W26', 'Effectif (pers.)': 2, 'Heures': 17.0, 'Nbre de shifts': 1},
            {'Dénomination': 'Doublure formation (pratique) AT CHT W26', 'Effectif (pers.)': 20, 'Heures': 6.5, 'Nbre de shifts': 4},
            {'Dénomination': "Doublure Visitor's Center", 'Effectif (pers.)': 20, 'Heures': 4.0, 'Nbre de shifts': 1}
        ])

    st.session_state.data_loaded = True

    # Générer le budget initial
    try:
        generate_budget_state(st.session_state.reference_year_saisons)
    except Exception as e:
        st.warning(f"Budget initial non généré automatiquement : {e}")

    st.rerun()
