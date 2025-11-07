# models/event.py
"""
Modèle de données pour les événements spéciaux impactant la planification
"""
from __future__ import annotations
from dataclasses import dataclass, asdict
from datetime import date, datetime
from typing import Dict, List, Optional
import json


@dataclass
class Event:
    """
    Représente un événement spécial qui impacte la planification
    """
    date: date
    name: str
    event_type: str  # 'critical', 'major', 'minor'
    description: str = ""
    penalty_factor: float = 0.5  # 0.0 (pas d'impact) à 1.0 (impact maximal)
    created_at: Optional[str] = None

    def __post_init__(self):
        """Validation et normalisation"""
        # Valider le type
        valid_types = ['critical', 'major', 'minor']
        if self.event_type not in valid_types:
            raise ValueError(f"event_type doit être dans {valid_types}")

        # Valider le penalty_factor
        if not 0.0 <= self.penalty_factor <= 1.0:
            raise ValueError("penalty_factor doit être entre 0.0 et 1.0")

        # Définir created_at si pas fourni
        if self.created_at is None:
            self.created_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        # Assigner penalty par défaut selon le type si non spécifié
        if self.penalty_factor == 0.5:  # Valeur par défaut
            self.penalty_factor = self._default_penalty_for_type(self.event_type)

    @staticmethod
    def _default_penalty_for_type(event_type: str) -> float:
        """Retourne la pénalité par défaut selon le type d'événement"""
        defaults = {
            'critical': 1.0,   # Blocage complet
            'major': 0.8,      # Forte dissuasion
            'minor': 0.3,      # Prudence légère
        }
        return defaults.get(event_type, 0.5)

    def to_dict(self) -> Dict:
        """Convertit en dictionnaire (pour stockage JSON)"""
        data = asdict(self)
        # Convertir date en string pour JSON
        data['date'] = self.date.isoformat()
        return data

    @classmethod
    def from_dict(cls, data: Dict) -> Event:
        """Crée un Event depuis un dictionnaire"""
        data_copy = data.copy()
        # Convertir string en date
        if isinstance(data_copy['date'], str):
            data_copy['date'] = date.fromisoformat(data_copy['date'])
        return cls(**data_copy)

    def get_label_fr(self) -> str:
        """Retourne le libellé en français du type"""
        labels = {
            'critical': '🔴 Critique',
            'major': '🟠 Majeur',
            'minor': '🟡 Mineur',
        }
        return labels.get(self.event_type, self.event_type)

    def get_color(self) -> str:
        """Retourne la couleur associée au type"""
        colors = {
            'critical': '#dc3545',  # Rouge
            'major': '#fd7e14',     # Orange
            'minor': '#ffc107',     # Jaune
        }
        return colors.get(self.event_type, '#6c757d')


class EventManager:
    """
    Gestionnaire centralisé des événements
    """

    @staticmethod
    def load_events_from_session() -> Dict[date, Event]:
        """Charge les événements depuis session_state"""
        import streamlit as st

        events_dict = st.session_state.get('calendar_events', {})

        # Convertir les clés string en date si nécessaire
        events = {}
        for key, value in events_dict.items():
            if isinstance(key, str):
                key = date.fromisoformat(key)
            if isinstance(value, dict):
                value = Event.from_dict(value)
            events[key] = value

        return events

    @staticmethod
    def save_events_to_session(events: Dict[date, Event]) -> None:
        """Sauvegarde les événements dans session_state"""
        import streamlit as st

        # Convertir en format sérialisable
        events_dict = {}
        for dt, event in events.items():
            key = dt.isoformat() if isinstance(dt, date) else dt
            events_dict[key] = event.to_dict() if isinstance(event, Event) else event

        st.session_state.calendar_events = events_dict

    @staticmethod
    def add_event(event: Event) -> None:
        """Ajoute un événement"""
        events = EventManager.load_events_from_session()
        events[event.date] = event
        EventManager.save_events_to_session(events)

    @staticmethod
    def remove_event(event_date: date) -> None:
        """Supprime un événement"""
        events = EventManager.load_events_from_session()
        if event_date in events:
            del events[event_date]
            EventManager.save_events_to_session(events)

    @staticmethod
    def get_event(event_date: date) -> Optional[Event]:
        """Récupère un événement pour une date donnée"""
        events = EventManager.load_events_from_session()
        return events.get(event_date)

    @staticmethod
    def get_events_for_year(year: int) -> Dict[date, Event]:
        """Retourne tous les événements d'une année"""
        events = EventManager.load_events_from_session()
        return {
            dt: evt for dt, evt in events.items()
            if dt.year == year
        }

    @staticmethod
    def get_penalty_for_date(event_date: date) -> float:
        """
        Retourne la pénalité pour une date donnée
        0.0 = pas d'événement, 1.0 = événement critique
        """
        event = EventManager.get_event(event_date)
        return event.penalty_factor if event else 0.0

    @staticmethod
    def import_from_json(json_path: str) -> None:
        """Importe des événements depuis un fichier JSON"""
        with open(json_path, 'r', encoding='utf-8') as f:
            data = json.load(f)

        events = {}
        for item in data:
            event = Event.from_dict(item)
            events[event.date] = event

        EventManager.save_events_to_session(events)

    @staticmethod
    def export_to_json(json_path: str, year: Optional[int] = None) -> None:
        """Exporte les événements vers un fichier JSON"""
        if year:
            events = EventManager.get_events_for_year(year)
        else:
            events = EventManager.load_events_from_session()

        data = [event.to_dict() for event in events.values()]

        with open(json_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)

    @staticmethod
    def create_default_events(year: int) -> None:
        """
        Crée des événements par défaut pour une année
        (exemples typiques pour Genève Aéroport)
        """
        default_events = [
            # Davos (mi-janvier)
            Event(date(year, 1, 16), "Davos - Jour 1", "major",
                  "Forum économique mondial - forte affluence VIP"),
            Event(date(year, 1, 17), "Davos - Jour 2", "major",
                  "Forum économique mondial - forte affluence VIP"),
            Event(date(year, 1, 18), "Davos - Jour 3", "major",
                  "Forum économique mondial - forte affluence VIP"),
            Event(date(year, 1, 19), "Davos - Jour 4", "major",
                  "Forum économique mondial - forte affluence VIP"),
            Event(date(year, 1, 20), "Davos - Jour 5", "major",
                  "Forum économique mondial - forte affluence VIP"),

            # Salon de l'Auto (mars)
            Event(date(year, 3, 5), "Salon de l'Auto - Ouverture", "major",
                  "Salon international de l'automobile - forte affluence"),
            Event(date(year, 3, 6), "Salon de l'Auto - Weekend", "major",
                  "Salon international de l'automobile - pic d'affluence"),
            Event(date(year, 3, 15), "Salon de l'Auto - Clôture", "major",
                  "Salon international de l'automobile - forte affluence"),

            # Fêtes de Genève (juillet/août)
            Event(date(year, 8, 1), "Fêtes de Genève - Début", "minor",
                  "Événement local - légère augmentation trafic"),
            Event(date(year, 8, 10), "Fêtes de Genève - Feu d'artifice", "minor",
                  "Événement local - légère augmentation trafic"),

            # Période de Noël
            Event(date(year, 12, 24), "Réveillon de Noël", "minor",
                  "Flux atypiques - familles et voyages"),
            Event(date(year, 12, 25), "Jour de Noël", "minor",
                  "Trafic réduit - jour férié"),
            Event(date(year, 12, 31), "Réveillon du Nouvel An", "minor",
                  "Flux atypiques - voyages de fin d'année"),
            Event(date(year, 1, 1), "Jour de l'An", "minor",
                  "Trafic réduit - jour férié"),
        ]

        for event in default_events:
            EventManager.add_event(event)
