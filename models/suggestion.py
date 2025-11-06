"""
Structures de données pour le système de suggestions d'ajustement des heures
"""
from dataclasses import dataclass, field, asdict
from datetime import date, datetime
from typing import List, Dict, Optional, Any
import json


@dataclass
class Suggestion:
    """
    Suggestion d'ajustement d'heures sur une période donnée

    Attributes:
        date: Date de la suggestion
        periode: Période horaire (ex: "18:00-22:00")
        perimetre: Périmètre concerné (ex: "Départs Non-Schengen")
        categorie: Catégorie de personnel (ex: "AT")
        delta_hours: Variation d'heures (négatif=retrait, positif=ajout)
        delta_chf: Impact financier correspondant
        score: Score de priorité (0-1, plus élevé = meilleur)
        motifs: Liste des raisons justifiant cette suggestion
        conflits: Liste des conflits ou avertissements potentiels
        slot_indices: Indices des time slots concernés (optionnel)
    """
    date: date
    periode: str
    perimetre: str
    categorie: str
    delta_hours: float
    delta_chf: float
    score: float
    motifs: List[str] = field(default_factory=list)
    conflits: List[str] = field(default_factory=list)
    slot_indices: Optional[List[int]] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convertit en dictionnaire (avec dates en string)"""
        d = asdict(self)
        d['date'] = self.date.isoformat() if self.date else None
        return d

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'Suggestion':
        """Crée une Suggestion depuis un dictionnaire"""
        data_copy = data.copy()
        if 'date' in data_copy and isinstance(data_copy['date'], str):
            data_copy['date'] = datetime.fromisoformat(data_copy['date']).date()
        return cls(**data_copy)

    def format_display(self) -> str:
        """Formatte pour affichage utilisateur"""
        sign = "+" if self.delta_hours > 0 else ""
        return (
            f"{self.date.strftime('%d/%m')} {self.periode} - {self.perimetre} : "
            f"{sign}{self.delta_hours:.1f}h ({sign}{self.delta_chf:.0f} CHF) "
            f"[Score: {self.score:.2f}]"
        )


@dataclass
class SuggestionConfig:
    """
    Configuration pour la génération de suggestions

    Attributes:
        min_block_hours: Taille minimale d'une suggestion en heures
        min_agents_per_slot: Nombre minimum d'agents par slot (plancher)
        max_agents_per_slot: Nombre maximum d'agents par slot (plafond, optionnel)
        penalty_events: Pénalité pour les événements spéciaux (0-1)
        weights: Pondérations pour le scoring
        locked_categories: Catégories verrouillées (non modifiables)
        locked_perimetres: Périmètres verrouillés
        locked_dates: Dates verrouillées (format ISO string)
        respect_strict_delta: Si True, priorise heures sur CHF
    """
    min_block_hours: float = 1.0
    min_agents_per_slot: int = 1
    max_agents_per_slot: Optional[int] = None
    penalty_events: float = 0.5
    weights: Dict[str, float] = field(default_factory=lambda: {
        'pax_intensity': 0.40,
        'ratio_efficiency': 0.35,
        'variance_stability': 0.25
    })
    locked_categories: List[str] = field(default_factory=list)
    locked_perimetres: List[str] = field(default_factory=list)
    locked_dates: List[str] = field(default_factory=list)
    respect_strict_delta: bool = True

    def is_locked(self, category: str = None, perimetre: str = None,
                  date_val: date = None) -> bool:
        """Vérifie si une combinaison est verrouillée"""
        if category and category in self.locked_categories:
            return True
        if perimetre and perimetre in self.locked_perimetres:
            return True
        if date_val:
            date_str = date_val.isoformat()
            if date_str in self.locked_dates:
                return True
        return False

    def to_dict(self) -> Dict[str, Any]:
        """Convertit en dictionnaire"""
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'SuggestionConfig':
        """Crée une config depuis un dictionnaire"""
        return cls(**data)


@dataclass
class ApplicationLog:
    """
    Journal d'une application de suggestions

    Attributes:
        id: Identifiant unique (ex: "AJU-2026-0001")
        timestamp: Date/heure d'application
        user: Utilisateur ayant appliqué (optionnel)
        items: Liste des suggestions appliquées
        totaux: Totaux agrégés (hours, chf)
        snapshot_before: État des grilles avant application
        snapshot_after: État des grilles après application
        config_used: Configuration utilisée pour générer les suggestions
    """
    id: str
    timestamp: str
    items: List[Suggestion]
    totaux: Dict[str, float]  # {'hours': -24.0, 'chf': -1092.0}
    snapshot_before: Dict[str, Any]
    snapshot_after: Dict[str, Any]
    user: Optional[str] = None
    config_used: Optional[SuggestionConfig] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convertit en dictionnaire"""
        return {
            'id': self.id,
            'timestamp': self.timestamp,
            'user': self.user,
            'items': [s.to_dict() for s in self.items],
            'totaux': self.totaux,
            'snapshot_before': self.snapshot_before,
            'snapshot_after': self.snapshot_after,
            'config_used': self.config_used.to_dict() if self.config_used else None
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'ApplicationLog':
        """Crée un log depuis un dictionnaire"""
        data_copy = data.copy()
        if 'items' in data_copy:
            data_copy['items'] = [Suggestion.from_dict(s) for s in data_copy['items']]
        if 'config_used' in data_copy and data_copy['config_used']:
            data_copy['config_used'] = SuggestionConfig.from_dict(data_copy['config_used'])
        return cls(**data_copy)

    def format_summary(self) -> str:
        """Formatte un résumé pour affichage"""
        ts = datetime.fromisoformat(self.timestamp).strftime('%d/%m/%Y %H:%M')
        h = self.totaux.get('hours', 0)
        c = self.totaux.get('chf', 0)
        n = len(self.items)

        sign_h = "+" if h > 0 else ""
        sign_c = "+" if c > 0 else ""

        return (
            f"{self.id} - {ts}\n"
            f"{n} suggestion(s) : {sign_h}{h:.1f}h ({sign_c}{c:.0f} CHF)"
        )


@dataclass
class AjustementPropose:
    """
    Structure du paquet d'ajustement envoyé par le Simulateur

    Attributes:
        total_delta_hours: Total d'heures à ajuster (négatif pour réduire)
        total_delta_chf: Total CHF à ajuster (négatif pour réduire)
        distribution: Répartition par catégorie {category: {delta_hours, delta_chf, percentage}}
        locks: Verrous définis par l'utilisateur {categories: [], perimetres: [], dates: []}
        timestamp: Horodatage de création
    """
    total_delta_hours: float
    total_delta_chf: float
    distribution: Dict[str, Dict[str, float]]
    locks: Dict[str, List[str]] = field(default_factory=lambda: {
        'categories': [], 'perimetres': [], 'dates': []
    })
    timestamp: str = field(default_factory=lambda: datetime.now().strftime("%Y-%m-%d %H:%M:%S"))

    def to_dict(self) -> Dict[str, Any]:
        """Convertit en dictionnaire"""
        return {
            'total_delta_hours': self.total_delta_hours,
            'total_delta_chf': self.total_delta_chf,
            'distribution': self.distribution,
            'locks': self.locks,
            'timestamp': self.timestamp
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'AjustementPropose':
        """Crée depuis un dictionnaire"""
        return cls(
            total_delta_hours=data.get('total_delta_hours', 0.0),
            total_delta_chf=data.get('total_delta_chf', 0.0),
            distribution=data.get('distribution', {}),
            locks=data.get('locks', {'categories': [], 'perimetres': [], 'dates': []}),
            timestamp=data.get('timestamp', datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
        )

    def get_category_delta_hours(self, category: str) -> float:
        """Récupère le delta d'heures pour une catégorie"""
        return self.distribution.get(category, {}).get('delta_hours', 0.0)

    def get_category_delta_chf(self, category: str) -> float:
        """Récupère le delta CHF pour une catégorie"""
        return self.distribution.get(category, {}).get('delta_chf', 0.0)


def generate_application_id(year: int, sequence: int) -> str:
    """
    Génère un ID unique pour une application

    Args:
        year: Année concernée
        sequence: Numéro de séquence (1, 2, 3, ...)

    Returns:
        ID au format "AJU-YYYY-NNNN"
    """
    return f"AJU-{year}-{sequence:04d}"


def create_suggestion_from_row(row_data: Dict[str, Any]) -> Suggestion:
    """
    Crée une Suggestion depuis une ligne de données brutes

    Args:
        row_data: Dictionnaire avec les données

    Returns:
        Instance de Suggestion
    """
    return Suggestion(
        date=row_data.get('date'),
        periode=row_data.get('periode', ''),
        perimetre=row_data.get('perimetre', ''),
        categorie=row_data.get('categorie', ''),
        delta_hours=float(row_data.get('delta_hours', 0.0)),
        delta_chf=float(row_data.get('delta_chf', 0.0)),
        score=float(row_data.get('score', 0.0)),
        motifs=row_data.get('motifs', []),
        conflits=row_data.get('conflits', []),
        slot_indices=row_data.get('slot_indices')
    )
