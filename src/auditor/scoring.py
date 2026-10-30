import json
import logging
import re
from pathlib import Path
from typing import Dict, Any, Optional, List, Tuple

from src.models import CarAd, AuditResult
from src.auditor.semantic import SemanticAuditor, normalize_text

logger = logging.getLogger(__name__)


class CarAuditor:
    def __init__(
        self,
        engines_db_path: Optional[Path] = None,
        segments_db_path: Optional[Path] = None,
        allowed_segments: Optional[List[str]] = None,
        target_models: Optional[List[str]] = None
    ):
        base_config_dir = Path(__file__).resolve().parent.parent.parent / "config"
        
        if engines_db_path is None:
            engines_db_path = base_config_dir / "engines_db.json"
        if segments_db_path is None:
            segments_db_path = base_config_dir / "segments_db.json"
        
        self.engines_db = self._load_json(engines_db_path)
        self.segments_db = self._load_json(segments_db_path).get("segments", {})
        self.allowed_segments = [s.upper() for s in allowed_segments] if allowed_segments else None
        self.target_models = [m.lower() for m in target_models] if target_models else []
        self.semantic_auditor = SemanticAuditor()

    def _load_json(self, path: Path) -> Dict[str, Any]:
        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            logger.error(f"Erreur chargement fichier JSON {path}: {e}")
            return {}

    def identify_segment(self, norm_title: str, norm_text: str) -> Optional[Tuple[str, Dict[str, Any]]]:
        """Identifie le segment automobile européen (A, B, C, D) selon le modèle."""
        # Trier les modèles du plus long au plus court pour éviter les collisions (ex: 'c30' avant 'c3')
        all_models = []
        for seg_code, seg_info in self.segments_db.items():
            for model_pattern in seg_info.get("models", []):
                all_models.append((len(model_pattern), model_pattern, seg_code, seg_info))
        all_models.sort(key=lambda x: x[0], reverse=True)

        # 1. Vérification prioritaire sur le titre de l'annonce
        for _, model_pattern, seg_code, seg_info in all_models:
            pattern_re = r"\b" + re.escape(model_pattern.strip()) + r"\b"
            if re.search(pattern_re, norm_title):
                return seg_code, seg_info

        # 2. Recherche de secours dans la description
        for _, model_pattern, seg_code, seg_info in all_models:
            pattern_re = r"\b" + re.escape(model_pattern.strip()) + r"\b"
            if re.search(pattern_re, norm_text):
                return seg_code, seg_info

        return None

    def audit(self, ad: CarAd) -> AuditResult:
        full_text = f"{ad.title} {ad.description}"
        norm_text = normalize_text(full_text)
        norm_title = normalize_text(ad.title)

        pros = []
        cons = []
        warnings = []
        disqualified = False
        disqualify_reason = None

        # -------------------------------------------------------------
        # AXE 0 : Filtrage par Segments Automobiles Européens (A, B, C, D)
        # -------------------------------------------------------------
        segment_match = self.identify_segment(norm_title, norm_text)
        if segment_match:
            seg_code, seg_info = segment_match
            if self.allowed_segments is not None and seg_code not in self.allowed_segments:
                disqualified = True
                disqualify_reason = f"Segment automobile exclu par configuration : Segment {seg_code} ({seg_info['name']})"
                cons.append(f"SEGMENT EXCLU : Segment {seg_code} ({seg_info['name']})")
            else:
                pros.append(f"Segment automobile : {seg_code} ({seg_info['name']})")

        # Vérification des modèles favoris / ciblés
        for target in self.target_models:
            if re.search(r"\b" + re.escape(target) + r"\b", norm_title):
                pros.append(f"Modèle prioritaire ciblé : {target.capitalize()}")
                break

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
            # Les pépites se situent entre 1 500 € et 3 800 € pour des compactes / coupés sains
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
        if not disqualified:
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

        # 2. Vérification Golden Engines (si non blacklisté et non disqualifié)
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
