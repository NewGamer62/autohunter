import json
import logging
import re
import urllib.request
import urllib.parse
from bs4 import BeautifulSoup
from typing import List, Dict, Any, Optional
from src.models import CarAd
from src.scraper.base import BaseScraper

logger = logging.getLogger(__name__)


class LaCentraleScraper(BaseScraper):
    BASE_URL = "https://www.lacentrale.fr/listing"
    USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"

    def __init__(self, headless: bool = False):
        self.headless = headless

    def fetch_latest_ads(self, search_config: Dict[str, Any]) -> List[CarAd]:
        ads = []
        max_price = search_config.get("max_price", 5000)
        min_price = search_config.get("min_price", 800)
        max_km = search_config.get("max_mileage", 210000)
        
        params = {
            "energies": "ess",
            "priceMax": str(max_price),
            "priceMin": str(min_price),
            "mileageMax": str(max_km),
        }
        query_string = urllib.parse.urlencode(params)
        target_url = f"{self.BASE_URL}?{query_string}"

        # 1. Tentative HTTP directe
        try:
            req = urllib.request.Request(
                target_url,
                headers={
                    "User-Agent": self.USER_AGENT,
                    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
                    "Accept-Language": "fr-FR,fr;q=0.9,en-US;q=0.8,en;q=0.7",
                }
            )
            with urllib.request.urlopen(req, timeout=10) as response:
                html = response.read().decode("utf-8", errors="ignore")
                ads = self._parse_html(html)
                if ads:
                    logger.info(f"[La Centrale] {len(ads)} annonces extraites via HTTP.")
                    return ads
        except Exception:
            logger.debug("[La Centrale] Blocage HTTP détecté, basculement en mode Playwright stealth...")

        # 2. Fallback Playwright avec Chrome natif
        try:
            ads = self._fetch_via_playwright(target_url)
        except Exception as e:
            logger.warning(f"[La Centrale] Protection active ou interruption de navigation : {e}")

        return ads

    def _fetch_via_playwright(self, url: str) -> List[CarAd]:
        from playwright.sync_api import sync_playwright
        ads = []

        with sync_playwright() as p:
            launch_kwargs = {
                "headless": self.headless,
                "args": [
                    "--disable-blink-features=AutomationControlled",
                    "--no-sandbox"
                ],
                "ignore_default_args": ["--enable-automation"]
            }
            try:
                browser = p.chromium.launch(channel="chrome", **launch_kwargs)
            except Exception:
                browser = p.chromium.launch(**launch_kwargs)

            page = browser.new_page()
            try:
                page.goto(url, wait_until="domcontentloaded", timeout=30000)
                page.wait_for_timeout(3000)

                # Détection immédiate du challenge DataDome / Captcha pour éviter les erreurs de navigation
                content = page.content()
                if "captcha-delivery.com" in content or ("datadome" in content.lower() and "captcha" in content.lower()):
                    logger.warning("[La Centrale] Challenge DataDome / Captcha actif (Leboncoin prend le relais pour ce cycle).")
                    return []

                # Récupération sécurisée des données structurées
                try:
                    next_data_handle = page.query_selector("script#__NEXT_DATA__")
                    if next_data_handle:
                        ads = self._parse_json_data(next_data_handle.inner_text())
                except Exception as ex:
                    logger.debug(f"[La Centrale] Erreur lecture NEXT_DATA : {ex}")

                if not ads:
                    try:
                        ads = self._parse_html(page.content())
                    except Exception as ex:
                        logger.debug(f"[La Centrale] Erreur lecture DOM : {ex}")

                if ads:
                    logger.info(f"[La Centrale] {len(ads)} annonces extraites via Playwright.")
            except Exception as e:
                logger.warning(f"[La Centrale] Erreur durant la navigation : {e}")
            finally:
                browser.close()

        return ads

    def _parse_json_data(self, raw_json: str) -> List[CarAd]:
        ads = []
        try:
            data = json.loads(raw_json)
            listings = data.get("props", {}).get("pageProps", {}).get("searchResult", {}).get("items", [])
            for item in listings:
                ad = self._parse_json_item(item)
                if ad:
                    ads.append(ad)
        except Exception as e:
            logger.debug(f"[La Centrale] Erreur parsing JSON: {e}")
        return ads

    def _parse_html(self, html: str) -> List[CarAd]:
        ads = []
        soup = BeautifulSoup(html, "html.parser")

        script_tag = soup.find("script", id="__NEXT_DATA__")
        if script_tag and script_tag.string:
            parsed = self._parse_json_data(script_tag.string)
            if parsed:
                return parsed

        cards = soup.select("div[class*='searchCard'], a[class*='searchCard']")
        for card in cards:
            try:
                url_elem = card if card.name == "a" else card.find("a")
                if not url_elem or not url_elem.get("href"):
                    continue
                
                href = url_elem["href"]
                full_url = f"https://www.lacentrale.fr{href}" if href.startswith("/") else href
                
                ad_id_match = re.search(r"auto-occasion-annonce-([a-zA-Z0-9]+)\.html", href)
                ad_id = f"lc_{ad_id_match.group(1)}" if ad_id_match else f"lc_{hash(full_url)}"

                title_elem = card.select_one("h3, [class*='title'], [class*='Title']")
                title = title_elem.get_text(strip=True) if title_elem else "Véhicule d'occasion"

                price_elem = card.select_one("[class*='price'], [class*='Price']")
                price = 0.0
                if price_elem:
                    price_digits = re.sub(r"[^\d]", "", price_elem.get_text())
                    if price_digits:
                        price = float(price_digits)

                year = None
                mileage = None
                meta_elems = card.select("[class*='characteristic'], [class*='tag']")
                for m in meta_elems:
                    txt = m.get_text(strip=True)
                    if re.match(r"^20\d{2}$|^19\d{2}$", txt):
                        year = int(txt)
                    elif "km" in txt.lower():
                        km_digits = re.sub(r"[^\d]", "", txt)
                        if km_digits:
                            mileage = int(km_digits)

                img_elem = card.find("img")
                images = [img_elem["src"]] if img_elem and img_elem.get("src") else []

                ads.append(CarAd(
                    id=ad_id,
                    source="lacentrale",
                    url=full_url,
                    title=title,
                    price=price,
                    year=year,
                    mileage=mileage,
                    fuel="essence",
                    images=images,
                    description=title
                ))
            except Exception as e:
                logger.debug(f"[La Centrale] Erreur parsing carte : {e}")

        return ads

    def _parse_json_item(self, item: Dict[str, Any]) -> Optional[CarAd]:
        try:
            item_id = item.get("id") or str(item.get("reference", ""))
            url = f"https://www.lacentrale.fr/auto-occasion-annonce-{item_id}.html"
            title = f"{item.get('make', '')} {item.get('model', '')} {item.get('version', '')}".strip()
            price = float(item.get("pricing", {}).get("rawPrice", 0))
            year = int(item.get("year", 0)) if item.get("year") else None
            mileage = int(item.get("mileage", 0)) if item.get("mileage") else None
            images = item.get("photos", [])

            return CarAd(
                id=f"lc_{item_id}",
                source="lacentrale",
                url=url,
                title=title,
                price=price,
                year=year,
                mileage=mileage,
                fuel="essence",
                images=images,
                description=f"{title} - Année {year} - {mileage} km"
            )
        except Exception:
            return None
