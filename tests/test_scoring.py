import pytest
from pathlib import Path
from src.models import CarAd
from src.auditor.scoring import CarAuditor
from src.database.repository import AdRepository

CONFIG_DIR = Path(__file__).resolve().parent.parent / "config"


@pytest.fixture
def auditor():
    return CarAuditor(CONFIG_DIR / "engines_db.json")


@pytest.fixture
def temp_repo(tmp_path):
    db_file = tmp_path / "test_autohunter.db"
    return AdRepository(db_path=db_file)


def test_puretech_is_disqualified(auditor):
    ad = CarAd(
        id="test_puretech",
        source="leboncoin",
        url="https://leboncoin.fr/ad/1",
        title="Peugeot 208 1.2 PureTech 82ch",
        price=4200,
        year=2014,
        mileage=95000,
        description="Belle 208 essence 1.2 puretech, CT ok."
    )
    result = auditor.audit(ad)
    assert result.is_disqualified is True
    assert result.total_score == 0
    assert "PureTech" in result.disqualification_reason


def test_vag_tsi_ea111_is_disqualified(auditor):
    ad = CarAd(
        id="test_tsi",
        source="leboncoin",
        url="https://leboncoin.fr/ad/2",
        title="Golf 5 1.4 TSI 140 ch",
        price=3900,
        year=2007,
        mileage=140000,
        description="Golf 5 1.4 tsi avec toit ouvrant, bon état général."
    )
    result = auditor.audit(ad)
    assert result.is_disqualified is True
    assert result.total_score == 0
    assert "EA111" in result.disqualification_reason or "TSI" in result.disqualification_reason


def test_without_ct_is_disqualified(auditor):
    ad = CarAd(
        id="test_no_ct",
        source="leboncoin",
        url="https://leboncoin.fr/ad/3",
        title="Renault Clio 2 1.2 16v",
        price=1200,
        year=2003,
        mileage=160000,
        description="Clio 2 roule très bien, vendue sans contrôle technique car pas le temps."
    )
    result = auditor.audit(ad)
    assert result.is_disqualified is True
    assert result.total_score == 0
    assert "sans CT" in result.disqualification_reason or "sans contrôle technique" in result.disqualification_reason.lower()


def test_golden_toyota_yaris_scores_high(auditor):
    ad = CarAd(
        id="test_yaris",
        source="leboncoin",
        url="https://leboncoin.fr/ad/4",
        title="Toyota Yaris 1.3 VVT-i Luna",
        price=2800,
        year=2006,
        mileage=105000,
        description="Toyota Yaris essence première main, CT vierge fait la semaine dernière, carnet d'entretien complet avec toutes factures, dort dans un garage, distribution à chaîne."
    )
    result = auditor.audit(ad)
    assert result.is_disqualified is False
    assert result.total_score >= 85
    assert result.engine_score == 30
    assert result.price_score == 30
    assert result.verdict in ("PÉPITE ABSOLUE", "TRÈS BONNE AFFAIRE")


def test_golden_honda_civic_scores_high(auditor):
    ad = CarAd(
        id="test_civic",
        source="lacentrale",
        url="https://lacentrale.fr/ad/5",
        title="Honda Civic 8 1.8 i-VTEC Type S",
        price=3400,
        year=2008,
        mileage=115000,
        description="Honda Civic 1.8 i-vtec essence, 1ere main, CT ok, toutes factures disponibles."
    )
    result = auditor.audit(ad)
    assert result.is_disqualified is False
    assert result.total_score >= 80
    assert result.engine_score == 30


def test_repository_save_and_deduplication(temp_repo, auditor):
    ad = CarAd(
        id="ad_test_repo",
        source="leboncoin",
        url="https://leboncoin.fr/ad/unique_123",
        title="Toyota Yaris 1.0 essence",
        price=2200,
        year=2005,
        mileage=125000,
        description="CT ok, roule nickel."
    )
    assert temp_repo.is_seen(ad.id) is False
    
    res = auditor.audit(ad)
    temp_repo.save_ad(ad, res)

    assert temp_repo.is_seen(ad.id) is True
    top_deals = temp_repo.get_top_deals(limit=5, min_score=60)
    assert len(top_deals) == 1
    assert top_deals[0]["id"] == "ad_test_repo"
