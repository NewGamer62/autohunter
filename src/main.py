import argparse
import logging
import random
import sys
import time
from pathlib import Path
import yaml

# S'assurer que la racine du projet est dans sys.path (permet d'exécuter `python src/main.py` sans ModuleNotFoundError)
ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

# Forcer l'encodage UTF-8 pour la console Windows
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from src.models import CarAd
from src.database.repository import AdRepository
from src.auditor.scoring import CarAuditor
from src.notifier.discord import DiscordNotifier
from src.scraper.lacentrale import LaCentraleScraper
from src.scraper.leboncoin import LeboncoinScraper

# Configuration du logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%H:%M:%S"
)
logger = logging.getLogger("AutoHunter")


def load_config(config_path: Path) -> dict:
    if not config_path.exists():
        logger.error(f"Fichier de configuration introuvable : {config_path}")
        sys.exit(1)
    with open(config_path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


class AutoHunterOrchestrator:
    def __init__(self, config_dir: Path):
        self.config = load_config(config_dir / "config.yaml")
        self.repo = AdRepository()
        self.auditor = CarAuditor(config_dir / "engines_db.json")
        
        discord_url = self.config.get("notifier", {}).get("discord_webhook_url", "")
        self.notifier = DiscordNotifier(webhook_url=discord_url)

        headless = self.config.get("daemon", {}).get("headless_browser", True)
        self.scrapers = [
            LaCentraleScraper(),
            LeboncoinScraper(headless=headless)
        ]

    def run_cycle(self) -> int:
        """Exécute un cycle de veille, d'audit et d'alerte."""
        search_config = self.config.get("search", {})
        min_alert_score = self.config.get("auditor", {}).get("min_alert_score", 80)
        
        logger.info("--- Début du cycle d'audit AutoHunter ---")
        all_ads = []
        for scraper in self.scrapers:
            try:
                ads = scraper.fetch_latest_ads(search_config)
                all_ads.extend(ads)
            except Exception as e:
                logger.error(f"Erreur avec {scraper.__class__.__name__}: {e}")

        new_ads_count = 0
        alerts_sent = 0

        for ad in all_ads:
            if self.repo.is_seen(ad.id):
                continue

            new_ads_count += 1
            audit_result = self.auditor.audit(ad)
            self.repo.save_ad(ad, audit_result)

            logger.info(f"Annonce auditée : [{audit_result.total_score}/100] {ad.title[:60]} -> {audit_result.verdict}")

            # Alerte si le score atteint ou dépasse le seuil
            if not audit_result.is_disqualified and audit_result.total_score >= min_alert_score:
                logger.info(f"🚨 PÉPITE IDENTIFIÉE ! Envoi alerte ({audit_result.total_score}/100)")
                sent = self.notifier.notify(ad, audit_result)
                if sent:
                    self.repo.mark_alerted(ad.id)
                alerts_sent += 1

        logger.info(f"Cycle terminé : {new_ads_count} nouvelles annonces traitées, {alerts_sent} alerte(s) déclenchée(s).")
        return alerts_sent

    def display_top_deals(self, limit: int = 10) -> None:
        deals = self.repo.get_top_deals(limit=limit)
        if not deals:
            print("Aucune pépite enregistrée en base pour le moment.")
            return

        print("\n" + "=" * 80)
        print(f"🏆 TOP {len(deals)} DES MEILLEURES AFFAIRES DÉTECTÉES EN BASE")
        print("=" * 80)
        for i, d in enumerate(deals, 1):
            print(f"{i}. [{d['score']}/100] {d['title']} - {d['price']:,.0f} €")
            print(f"   Km : {d['mileage']} km | Année : {d['year']} | Source : {d['source'].capitalize()}")
            print(f"   Verdict : {d['verdict']} | URL : {d['url']}")
            print("-" * 80)


def main():
    parser = argparse.ArgumentParser(description="AutoHunter — Veille et Audit Auto d'Occasion")
    parser.add_argument("--once", action="store_true", help="Exécute un seul cycle de surveillance et quitte")
    parser.add_argument("--daemon", action="store_true", help="Lance la surveillance en continu avec jitter anti-détection")
    parser.add_argument("--top", type=int, nargs="?", const=10, help="Affiche les meilleures affaires enregistrées")
    parser.add_argument("--audit-text", type=str, help="Audite rapidement une description de voiture passée en argument")
    args = parser.parse_args()

    project_root = Path(__file__).resolve().parent.parent
    config_dir = project_root / "config"
    orchestrator = AutoHunterOrchestrator(config_dir)

    if args.top:
        orchestrator.display_top_deals(limit=args.top)
        return

    if args.audit_text:
        ad = CarAd(
            id="cli_test",
            source="direct",
            url="https://example.com/test",
            title="Véhicule test",
            price=2500,
            mileage=110000,
            year=2007,
            description=args.audit_text
        )
        res = orchestrator.auditor.audit(ad)
        orchestrator.notifier._print_local_alert(ad, res)
        return

    if args.daemon:
        min_delay = orchestrator.config.get("daemon", {}).get("min_delay_seconds", 480)
        max_delay = orchestrator.config.get("daemon", {}).get("max_delay_seconds", 900)
        logger.info(f"Mode Démon activé. Intervalle aléatoire entre {min_delay}s et {max_delay}s.")
        try:
            while True:
                orchestrator.run_cycle()
                sleep_time = random.randint(min_delay, max_delay)
                logger.info(f"Mise en veille pendant {sleep_time // 60} min {sleep_time % 60} s...")
                time.sleep(sleep_time)
        except KeyboardInterrupt:
            logger.info("Arrêt propre du démon AutoHunter reçu.")
            sys.exit(0)
    else:
        # Par défaut : exécution unique
        orchestrator.run_cycle()


if __name__ == "__main__":
    main()
