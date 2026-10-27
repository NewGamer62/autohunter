from dataclasses import dataclass, field
from typing import List, Optional, Dict, Any


@dataclass
class CarAd:
    id: str
    source: str
    url: str
    title: str
    price: float
    year: Optional[int] = None
    mileage: Optional[int] = None
    fuel: Optional[str] = "essence"
    transmission: Optional[str] = "manuelle"
    location: Optional[str] = "France"
    description: str = ""
    images: List[str] = field(default_factory=list)
    published_at: Optional[str] = None


@dataclass
class AuditResult:
    ad_id: str
    total_score: int
    is_disqualified: bool = False
    disqualification_reason: Optional[str] = None
    
    # Détail des 4 axes de score
    price_score: int = 0      # /30
    engine_score: int = 0     # /30
    semantic_score: int = 0   # /20
    history_score: int = 0    # /20
    
    # Points d'audit synthétiques
    pros: List[str] = field(default_factory=list)
    cons: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    
    # Recommandation globale
    verdict: str = "À ÉVALUER"  # "PÉPITE ABSOLUE", "TRÈS BONNE AFFAIRE", "CORRECT", "À FUIR"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "ad_id": self.ad_id,
            "total_score": self.total_score,
            "is_disqualified": self.is_disqualified,
            "disqualification_reason": self.disqualification_reason,
            "scores": {
                "price": self.price_score,
                "engine": self.engine_score,
                "semantic": self.semantic_score,
                "history": self.history_score,
            },
            "pros": self.pros,
            "cons": self.cons,
            "warnings": self.warnings,
            "verdict": self.verdict,
        }
