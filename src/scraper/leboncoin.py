import json
import logging
import re
from typing import List, Dict, Any, Optional
from src.models import CarAd
from src.scraper.base import BaseScraper

logger = logging.getLogger(__name__)


class LeboncoinScraper(BaseScraper):
    SEARCH_BASE_URL = "https://www.leboncoin.fr/recherche"

    def __init__(self, headless: bool = True):
        self.headless = headless

    def fetch_latest_ads(self, search_config: Dict[str, Any]) -> List[CarAd]:
        """Tente d'extraire les annonces via Playwright Stealth ou fallback."""
        max_price = search_config.get("max_price", 5000)
        min_price = search_config.get("min_price", 800)
        max_km = search_config.get("max_mileage", 210000)

        # URL de recherche ciblée voitures essence < 5000 € sur toute la France
        # Catégorie 2 = Voitures
        target_url = f"{self.SEARCH_BASE_URL}?category=2&fuel=1&price={min_price}-{max_price}&mileage=min-{max_km}&sort=time"

        try:
            return self._fetch_via_playwright(target_url)
        except ImportError:
            logger.warning("[Leboncoin] Module 'playwright' non installé. Pour contourner le bot-shield DataDome, exécutez: pip install playwright && playwright install chromium")
            return []
        except Exception as e:
            logger.error(f"[Leboncoin] Erreur scraping : {e}")
            return []

    def _fetch_via_playwright(self, url: str) -> List[CarAd]:
        from playwright.sync_api import sync_playwright

        ads: List[CarAd] = []
        with sync_playwright() as p:
            browser = p.chromium.launch(
                headless=self.headless,
                args=[
                    "--disable-blink-features=AutomationControlled",
                    "--no-sandbox",
                    "--disable-infobars",
                    "--disable-dev-shm-usage"
                ]
            )
            context = browser.new_context(
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
                locale="fr-FR",
                viewport={"width": 1920, "height": 1080}
            )

            # Injection du script anti-détection DataDome / bot
            context.add_init_script("""
                Object.defineProperty(navigator, 'webdriver', {
                    get: () => undefined
                });
            """)

            page = context.new_page()
            logger.info(f"[Leboncoin] Navigation vers {url}")
            
            try:
                page.goto(url, wait_until="domcontentloaded", timeout=30000)
                page.wait_for_timeout(3000) # Délai naturel

                # Vérification de présence du challenge DataDome
                if "datadome" in page.content().lower() or "captcha" in page.content().lower():
                    logger.warning("[Leboncoin] Challenge DataDome / Captcha détecté par Leboncoin.")
                    browser.close()
                    return []

                # Récupération des données structurées __NEXT_DATA__
                next_data_handle = page.query_selector("script#__NEXT_DATA__")
                if next_data_handle:
                    raw_json = next_data_handle.inner_text()
                    ads = self._parse_lbc_next_data(raw_json)
                    logger.info(f"[Leboncoin] {len(ads)} annonces extraites via __NEXT_DATA__.")
                else:
                    logger.info("[Leboncoin] Pas de script __NEXT_DATA__, tentative extraction DOM...")
                    ads = self._parse_lbc_dom(page)

            except Exception as e:
                logger.error(f"[Leboncoin] Erreur pendant la navigation : {e}")
            finally:
                browser.close()

        return ads

    def _parse_lbc_next_data(self, raw_json: str) -> List[CarAd]:
        ads = []
        try:
            data = json.loads(raw_json)
            raw_ads = data.get("props", {}).get("pageProps", {}).get("searchData", {}).get("ads", [])
            for item in raw_ads:
                ad_id = str(item.get("list_id", ""))
                url = item.get("url", f"https://www.leboncoin.fr/ad/voitures/{ad_id}")
                title = item.get("subject", "Annonce auto")
                price = float(item.get("price", [0])[0] if isinstance(item.get("price"), list) else item.get("price", 0))
                
                # Attributs personnalisés Leboncoin (regroupés par key)
                attrs = {a.get("key"): a.get("value") for a in item.get("attributes", []) if isinstance(a, dict)}
                
                year = int(attrs.get("regdate")) if attrs.get("regdate") and attrs.get("regdate").isdigit() else None
                mileage = int(attrs.get("mileage")) if attrs.get("mileage") and attrs.get("mileage").isdigit() else None
                fuel = attrs.get("fuel", "essence")
                transmission = attrs.get("gearbox", "manuelle")
                
                location_dict = item.get("location", {})
                city = location_dict.get("city", "")
                zipcode = location_dict.get("zipcode", "")
                location = f"{city} ({zipcode})" if city else "France"

                images = item.get("images", {}).get("urls", [])
                description = item.get("body", title)

                ads.append(CarAd(
                    id=f"lbc_{ad_id}",
                    source="leboncoin",
                    url=url,
                    title=title,
                    price=price,
                    year=year,
                    mileage=mileage,
                    fuel=fuel,
                    transmission=transmission,
                    location=location,
                    description=description,
                    images=images
                ))
        except Exception as e:
            logger.error(f"[Leboncoin] Erreur décodage JSON: {e}")
        return ads

    def _parse_lbc_dom(self, page) -> List[CarAd]:
        ads = []
        # Sélecteurs DOM de secours
        cards = page.query_selector_all("a[data-test-id='ad']")
        for c in cards:
            try:
                href = c.get_attribute("href")
                if not href:
                    continue
                full_url = f"https://www.leboncoin.fr{href}" if href.startswith("/") else href
                title_elem = c.query_selector("p[data-qa-id='aditem_title']")
                title = title_elem.inner_text() if title_elem else "Véhicule"
                
                price_elem = c.query_selector("span[data-qa-id='adview_price']")
                price_text = price_elem.inner_text() if price_elem else "0"
                price_num = float(re.sub(r"[^\d]", "", price_text) or 0)

                ads.append(CarAd(
                    id=f"lbc_{hash(full_url)}",
                    source="leboncoin",
                    url=full_url,
                    title=title,
                    price=price_num,
                    description=title
                ))
            except Exception:
                continue
        return ads
