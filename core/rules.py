"""
Gestion des règles de planification et d'ajustement
"""
import json
from pathlib import Path
import streamlit as st
from utils.date_utils import _date_to_str, _str_to_date


def save_rules_to_json(rules_list, path: Path):
    """Sauvegarde une liste de règles dans un fichier JSON"""
    serializable = []
    for op in rules_list:
        op2 = dict(op)
        op2['start'] = _date_to_str(op2.get('start'))
        op2['end'] = _date_to_str(op2.get('end'))
        serializable.append(op2)
    try:
        path.write_text(
            json.dumps(serializable, ensure_ascii=False, indent=2),
            encoding="utf-8"
        )
    except Exception as e:
        st.warning(f"Impossible d'enregistrer les règles ({path.name}) : {e}")


def load_rules_from_json(path: Path):
    """Charge les règles depuis un fichier JSON"""
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
