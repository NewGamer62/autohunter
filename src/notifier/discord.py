import json
import logging
import urllib.request
import urllib.error
from typing import Optional
from src.models import CarAd, AuditResult

logger = logging.getLogger(__name__)


class DiscordNotifier:
    def __init__(self, webhook_url: Optional[str] = None):
        self.webhook_url = webhook_url

    def notify(self, ad: CarAd, audit: AuditResult) -> bool:
        """Envoie un embed Discord riche pour alerter l'utilisateur sur mobile."""
        if not self.webhook_url or not self.webhook_url.startswith("https://discord.com/api/webhooks/"):
            logger.info(f"[CONSOLE ALERT] Aucune URL Discord Webhook configurée. Affichage local :")
            self._print_local_alert(ad, audit)
            return False

        # Couleur selon le score : Vert pour pépite (>=88), Or pour bonne affaire (80-87), Rouge si disqualifié
        if audit.total_score >= 88:
            color = 0x2ECC71  # Vert émeraude
            emoji = "🏆"
        elif audit.total_score >= 80:
            color = 0xF1C40F  # Jaune or
            emoji = "⚡"
        else:
            color = 0xE74C3C  # Rouge
            emoji = "⚠️"

        pros_text = "\n".join([f"• {p}" for p in audit.pros[:4]]) if audit.pros else "Aucun point fort particulier"
        cons_text = "\n".join([f"• {c}" for c in (audit.cons + audit.warnings)[:4]]) if (audit.cons or audit.warnings) else "Rien à signaler"

        embed = {
            "title": f"{emoji} [{audit.total_score}/100] {ad.title[:200]}",
            "url": ad.url,
            "color": color,
            "description": f"**Verdict :** `{audit.verdict}`\n**Plateforme :** {ad.source.capitalize()}",
            "fields": [
                {"name": "💰 Prix", "value": f"**{ad.price:,.0f} €**", "inline": True},
                {"name": "📅 Année", "value": str(ad.year) if ad.year else "Non spécifié", "inline": True},
                {"name": "🛣️ Kilométrage", "value": f"{ad.mileage:,} km" if ad.mileage else "Non spécifié", "inline": True},
                {"name": "📍 Localisation", "value": ad.location or "France", "inline": True},
                {"name": "⛽ Énergie / Boîte", "value": f"{ad.fuel or 'Essence'} / {ad.transmission or 'Manuelle'}", "inline": True},
                {"name": "📊 Détail des scores", "value": f"Prix: `{audit.price_score}/30` | Moteur: `{audit.engine_score}/30`\nSémantique: `{audit.semantic_score}/20` | Hist.: `{audit.history_score}/20`", "inline": False},
                {"name": "✅ Points forts constatés", "value": pros_text, "inline": False},
                {"name": "🔍 Points de vigilance", "value": cons_text, "inline": False},
            ],
            "footer": {
                "text": "AutoHunter • Détecteur de pépites automobiles d'occasion"
            }
        }

        if ad.images:
            embed["thumbnail"] = {"url": ad.images[0]}

        payload = {
            "content": f"🚨 **PÉPITE DÉTECTÉE ({audit.total_score}/100)** — Une occasion sous les 5 000 € vient d'être validée par l'audit :",
            "embeds": [embed]
        }

        try:
            req = urllib.request.Request(
                self.webhook_url,
                data=json.dumps(payload).encode("utf-8"),
                headers={"Content-Type": "application/json", "User-Agent": "AutoHunter/1.0"}
            )
            with urllib.request.urlopen(req, timeout=10) as resp:
                if resp.status in (200, 204):
                    logger.info(f"Notification Discord transmise avec succès pour l'annonce {ad.id}")
                    return True
        except urllib.error.URLError as e:
            logger.error(f"Échec de l'envoi Discord pour {ad.id}: {e}")
        except Exception as e:
            logger.error(f"Erreur inattendue webhook Discord: {e}")

        return False

    def _print_local_alert(self, ad: CarAd, audit: AuditResult) -> None:
        border = "=" * 70
        try:
            print(f"\n{border}")
            print(f"🚨 [ALERTE DÉTECTION] Score: {audit.total_score}/100 - {audit.verdict}")
            print(f"Modèle : {ad.title}")
            print(f"Prix : {ad.price:,.0f} € | Année : {ad.year} | Km : {ad.mileage} km | Lieu : {ad.location}")
            print(f"URL : {ad.url}")
            print(f"Scores -> Prix: {audit.price_score}/30 | Moteur: {audit.engine_score}/30 | Texte: {audit.semantic_score}/20 | Hist: {audit.history_score}/20")
            if audit.pros:
                print("Atouts :")
                for p in audit.pros[:4]:
                    print(f"  + {p}")
            if audit.cons or audit.warnings:
                print("Vigilance :")
                for c in (audit.cons + audit.warnings)[:4]:
                    print(f"  - {c}")
            print(f"{border}\n")
        except UnicodeEncodeError:
            # Fallback en ascii propre si le terminal Windows refuse les emojis
            print(f"\n{border}")
            print(f"[ALERTE DETECTION] Score: {audit.total_score}/100 - {audit.verdict}")
            print(f"Modele : {ad.title}")
            print(f"Prix : {ad.price:,.0f} EUR | Annee : {ad.year} | Km : {ad.mileage} km")
            print(f"URL : {ad.url}")
            print(f"{border}\n")
