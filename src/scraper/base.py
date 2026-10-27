from abc import ABC, abstractmethod
from typing import List, Dict, Any
from src.models import CarAd


class BaseScraper(ABC):
    @abstractmethod
    def fetch_latest_ads(self, search_config: Dict[str, Any]) -> List[CarAd]:
        """Récupère les dernières annonces selon la configuration de recherche."""
        pass
