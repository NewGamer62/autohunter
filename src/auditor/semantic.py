import re
import unicodedata
from typing import Dict, List, Tuple


def normalize_text(text: str) -> str:
    """Nettoie le texte en minuscules sans accents pour le matching robuste."""
    text = text.lower()
    text = unicodedata.normalize("NFKD", text)
    text = "".join([c for c in text if not unicodedata.combining(c)])
    return text


class SemanticAuditor:
    # Signaux éliminatoires directs (casse mécanique, non roulant, export/pièces)
    DISQUALIFYING_FLAGS: List[Tuple[str, str]] = [
        ("pour pieces", "Vendu pour pièces"),
        ("dans l'etat", "Mention explicite 'dans l'état'"),
        ("pour export", "Réservé à l'exportation / marchand"),
        ("sans controle technique", "Vendu sans contrôle technique"),
        ("sans ct", "Vendu sans CT"),
        ("ct a faire", "Contrôle technique à la charge de l'acheteur"),
        ("joint de culasse", "Joint de culasse suspect ou HS"),
        ("moteur tourne sur 3 cylindres", "Cylindre ou allumage HS"),
        ("boite de vitesse a changer", "Boîte de vitesse HS"),
        ("boite a changer", "Boîte de vitesse à remplacer"),
        ("bruit moteur", "Bruit moteur suspect"),
        ("accidentee", "Véhicule accidenté"),
        ("procedure ve", "Procédure VE (Véhicule Endommagé)"),
        ("procedure vge", "Procédure VGE (Gravement Endommagé)"),
    ]

    # Red flags sévères (déduction lourde de points)
    RED_FLAGS: List[Tuple[str, str, int]] = [
        ("frais a prevoir", "Mention de frais mécaniques à prévoir", 10),
        ("voyant allume", "Voyant moteur ou injection allumé", 12),
        ("voyant moteur", "Témoin moteur allumé au tableau de bord", 12),
        ("clim a recharger", "Climatisation HS (souvent fuite ou compresseur mort)", 5),
        ("perte de puissance", "Perte de puissance moteur signalée", 10),
        ("embrayage fatigue", "Embrayage usé à remplacer prochainement", 8),
        ("carrosserie abimee", "Défauts carrosserie marqués", 4),
        ("choc arriere", "Choc carrosserie signalé", 6),
        ("choc avant", "Choc carrosserie signalé", 6),
    ]

    # Green flags (garanties de soin, transparence et entretien)
    GREEN_FLAGS: List[Tuple[str, str, int]] = [
        ("premiere main", "Véhicule de première main", 5),
        ("1ere main", "Véhicule de première main", 5),
        ("carnet d'entretien", "Carnet d'entretien présent et tamponné", 4),
        ("carnet complet", "Historique d'entretien complet", 4),
        ("factures a l'appui", "Dossier de factures disponible", 4),
        ("toutes factures", "Factures complètes disponibles", 4),
        ("distribution faite", "Courroie / chaîne de distribution récente", 5),
        ("distribution neuve", "Distribution neuve", 5),
        ("ct vierge", "Contrôle technique vierge (zéro défaut)", 5),
        ("ct ok", "Contrôle technique valide", 3),
        ("controle technique ok", "Contrôle technique valide", 3),
        ("histovec", "Rapport officiel Histovec fourni", 4),
        ("dort dans un garage", "Véhicule stationné à l'abri en garage", 2),
        ("pneus neufs", "Pneumatiques neufs", 2),
        ("vidange faite", "Entretien / révision récente", 2),
    ]

    def audit(self, title: str, description: str) -> Dict:
        combined = f"{title} {description}"
        norm = normalize_text(combined)

        disqualified = False
        disqualify_reasons: List[str] = []
        pros: List[str] = []
        cons: List[str] = []

        # 1. Vérification des disqualifications
        for pattern, label in self.DISQUALIFYING_FLAGS:
            if re.search(r"\b" + re.escape(pattern) + r"\b", norm):
                disqualified = True
                disqualify_reasons.append(label)

        # 2. Score de base sémantique : 10/20
        semantic_score = 10

        # Déductions pour les red flags
        for pattern, label, penalty in self.RED_FLAGS:
            if re.search(r"\b" + re.escape(pattern) + r"\b", norm):
                cons.append(f"Alerte : {label} (-{penalty} pts)")
                semantic_score -= penalty

        # Bonus pour les green flags
        for pattern, label, bonus in self.GREEN_FLAGS:
            if re.search(r"\b" + re.escape(pattern) + r"\b", norm):
                pros.append(f"Atout : {label} (+{bonus} pts)")
                semantic_score += bonus

        # Bornage du score sémantique entre 0 et 20
        semantic_score = max(0, min(20, semantic_score))

        return {
            "score": semantic_score,
            "disqualified": disqualified,
            "disqualify_reasons": disqualify_reasons,
            "pros": pros,
            "cons": cons,
        }
