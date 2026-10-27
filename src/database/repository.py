import json
import sqlite3
from pathlib import Path
from typing import List, Optional, Dict, Any
from src.models import CarAd, AuditResult


class AdRepository:
    def __init__(self, db_path: Optional[Path] = None):
        if db_path is None:
            db_dir = Path(__file__).resolve().parent.parent.parent / "data"
            db_dir.mkdir(parents=True, exist_ok=True)
            self.db_path = db_dir / "autohunter.db"
        else:
            self.db_path = db_path
            self.db_path.parent.mkdir(parents=True, exist_ok=True)

        self._init_db()

    def _get_connection(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self) -> None:
        with self._get_connection() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS ads (
                    id TEXT PRIMARY KEY,
                    source TEXT NOT NULL,
                    url TEXT NOT NULL UNIQUE,
                    title TEXT NOT NULL,
                    price REAL NOT NULL,
                    year INTEGER,
                    mileage INTEGER,
                    fuel TEXT,
                    transmission TEXT,
                    location TEXT,
                    description TEXT,
                    images_json TEXT,
                    score INTEGER NOT NULL,
                    is_disqualified INTEGER NOT NULL,
                    verdict TEXT NOT NULL,
                    audit_json TEXT NOT NULL,
                    alerted INTEGER DEFAULT 0,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            conn.execute("CREATE INDEX IF NOT EXISTS idx_ads_score ON ads(score)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_ads_alerted ON ads(alerted)")

    def is_seen(self, ad_id: str) -> bool:
        with self._get_connection() as conn:
            cur = conn.execute("SELECT 1 FROM ads WHERE id = ?", (ad_id,))
            return cur.fetchone() is not None

    def save_ad(self, ad: CarAd, audit: AuditResult) -> None:
        with self._get_connection() as conn:
            conn.execute("""
                INSERT OR REPLACE INTO ads (
                    id, source, url, title, price, year, mileage, fuel,
                    transmission, location, description, images_json,
                    score, is_disqualified, verdict, audit_json, alerted
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                ad.id,
                ad.source,
                ad.url,
                ad.title,
                ad.price,
                ad.year,
                ad.mileage,
                ad.fuel,
                ad.transmission,
                ad.location,
                ad.description,
                json.dumps(ad.images, ensure_ascii=False),
                audit.total_score,
                1 if audit.is_disqualified else 0,
                audit.verdict,
                json.dumps(audit.to_dict(), ensure_ascii=False),
                0
            ))

    def mark_alerted(self, ad_id: str) -> None:
        with self._get_connection() as conn:
            conn.execute("UPDATE ads SET alerted = 1 WHERE id = ?", (ad_id,))

    def get_top_deals(self, limit: int = 10, min_score: int = 80) -> List[Dict[str, Any]]:
        with self._get_connection() as conn:
            cur = conn.execute("""
                SELECT id, source, url, title, price, year, mileage, score, verdict, audit_json, created_at
                FROM ads
                WHERE is_disqualified = 0 AND score >= ?
                ORDER BY score DESC, price ASC
                LIMIT ?
            """, (min_score, limit))
            rows = cur.fetchall()
            return [dict(row) for row in rows]
