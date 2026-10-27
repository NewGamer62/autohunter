import json
import logging
from pathlib import Path
from typing import Dict, Any, Optional

from src.models import CarAd, AuditResult
from src.auditor.semantic import SemanticAuditor, normalize_text

logger = logging.getLogger(__name__)


class CarAuditor:
    def __init__(self, engines_db_path: Optional[Path] = None):
        if engines_db_path is None:
            engines_db_path = Path(__file__).resolve().parent.parent.parent / "config" / "engines_db.json"
        
        self.engines_db = self._load_engines_db(engines_db_path)
        self.semantic_auditor = SemanticAuditor()

    def _load_engines_db(self, path: Path) -> Dict[str, Any]:
        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            logger.error(f"Erreur chargement base moteurs {path}: {e}")
            return {"golden_engines": [], "blacklisted_engines": []}

    def audit(self, ad: CarAd) -> AuditResult:
        full_text = f"{ad.title} {ad.description}"
        norm_text = normalize_text(full_text)

        pros = []
        cons = []
        warnings = []
        disqualified = False
        disqualify_reason = None

        # -------------------------------------------------------------
        # AXE 1 : Évaluation Financière & Prix (30 points)
        # -------------------------------------------------------------
        price_score = 0
        if ad.price <= 0:
            disqualified = True
            disqualify_reason = "Prix nul ou non spécifié"
        elif ad.price < 700:
            disqualified = True
            disqualify_reason = f"Prix suspect ({ad.price} €) : arnaque potentielle ou véhicule donneur de pièces"
        else:
            # Pour un budget max 5000 € :
            # Les pépites se situent entre 1 500 € et 3 800 € pour des citadines / compactes saines
            if 1500 <= ad.price <= 3500:
                price_score = 30
                pros.append(f"Positionnement prix idéal ({ad.price:,.0f} €) : forte marge de rentabilité/revente")
            elif 3501 <= ad.price <= 4500:
                price_score = 24
                pros.append(f"Prix correct ({ad.price:,.0f} €) en phase avec le haut du marché")
            elif 4501 <= ad.price <= 5000:
                price_score = 16
                cons.append(f"Prix plafond ({ad.price:,.0f} €) : négociation requise")
            else: # Entre 700 et 1499
                price_score = 22
                warnings.append(f"Prix très bas ({ad.price:,.0f} €) : vérifier minutieusement corrosion et embrayage")

        # -------------------------------------------------------------
        # AXE 2 : Fiabilité Moteur & Boîte (30 points)
        # -------------------------------------------------------------
        engine_score = 12 # Score par défaut si moteur indéterminé
        engine_identified = False

        # 1. Vérification Blacklist stricte
        for bl in self.engines_db.get("blacklisted_engines", []):
            for pattern in bl["patterns"]:
                if pattern in norm_text:
                    disqualified = True
                    disqualify_reason = f"Moteur à haut risque de casse : {bl['name']} ({bl['reason']})"
                    engine_score = 0
                    cons.append(f"DANGER MÉCANIQUE : {bl['name']}")
                    break
            if disqualified:
                break

        # 2. Vérification Golden Engines (si non blacklisté)
        if not disqualified:
            for ge in self.engines_db.get("golden_engines", []):
                brand_match = ge["brand"].lower() in norm_text
                model_match = any(m.lower() in norm_text for m in ge["models"])
                engine_match = any(e.lower() in norm_text for e in ge["engines"])

                if (brand_match and model_match) or (model_match and engine_match) or (brand_match and engine_match):
                    engine_score = ge["reliability_score"]
                    pros.append(f"Motorisation réputée fiable : {ge['brand']} ({ge['notes']})")
                    engine_identified = True
                    break

            if not engine_identified:
                warnings.append("Motorisation exacte non certifiée dans la description : vérification manuelle requise")

        # -------------------------------------------------------------
        # AXE 3 : Analyse Sémantique & Mots-clés (20 points)
        # -------------------------------------------------------------
        sem_res = self.semantic_auditor.audit(ad.title, ad.description)
        semantic_score = sem_res["score"]
        
        if sem_res["disqualified"] and not disqualified:
            disqualified = True
            disqualify_reason = " ; ".join(sem_res["disqualify_reasons"])

        pros.extend(sem_res["pros"])
        cons.extend(sem_res["cons"])

        # -------------------------------------------------------------
        # AXE 4 : Historique, Transparence & Kilométrage (20 points)
        # -------------------------------------------------------------
        history_score = 6 # Score de base

        # Contrôle technique mentionné positif
        if any(w in norm_text for w in ["ct ok", "ct vierge", "controle technique ok", "controle technique valide", "ct valide"]):
            history_score += 6
            pros.append("Contrôle technique valide mentionné")
        else:
            cons.append("Absence de mention explicite de validité du Contrôle Technique")

        # Factures et carnet
        if any(w in norm_text for w in ["carnet", "factures", "dossier entretien"]):
            history_score += 4
            pros.append("Dossier de factures ou carnet d'entretien présent")

        # Kilométrage par rapport à l'âge
        if ad.mileage:
            if ad.mileage < 120000:
                history_score += 4
                pros.append(f"Kilométrage particulièrement bas pour le budget ({ad.mileage:,} km)")
            elif ad.mileage <= 180000:
                history_score += 2
            else:
                cons.append(f"Kilométrage élevé ({ad.mileage:,} km) : prévoir contrôles suspensions et cardans")

        history_score = min(20, history_score)

        # -------------------------------------------------------------
        # Calcul du Score Global / 100 et Verdict
        # -------------------------------------------------------------
        if disqualified:
            total_score = 0
            verdict = "À FUIR (DISQUALIFIÉ)"
        else:
            total_score = price_score + engine_score + semantic_score + history_score
            if total_score >= 88:
                verdict = "PÉPITE ABSOLUE"
            elif total_score >= 80:
                verdict = "TRÈS BONNE AFFAIRE"
            elif total_score >= 65:
                verdict = "AFFAIRE CORRECTE"
            else:
                verdict = "DÉCONSEILLÉ"

        return AuditResult(
            ad_id=ad.id,
            total_score=total_score,
            is_disqualified=disqualified,
            disqualification_reason=disqualify_reason,
            price_score=price_score,
            engine_score=engine_score,
            semantic_score=semantic_score,
            history_score=history_score,
            pros=pros,
            cons=cons,
            warnings=warnings,
            verdict=verdict
        )
