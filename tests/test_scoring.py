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
        title="Peugeot 308 1.2 PureTech 110ch",
        price=4200,
        year=2014,
        mileage=95000,
        description="Belle 308 essence 1.2 puretech, CT ok."
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


def test_citroen_c2_is_disqualified_for_titan(auditor):
    """Vérifie que la Citroën C2 est immédiatement éliminée pour un conducteur d'1m93."""
    ad = CarAd(
        id="test_c2",
        source="leboncoin",
        url="https://leboncoin.fr/ad/c2_test",
        title="Citroën C2 1.4 VTR Essence",
        price=2200,
        year=2006,
        mileage=110000,
        description="Citroën C2 en très bon état, CT vierge, carnet d'entretien."
    )
    result = auditor.audit(ad)
    assert result.is_disqualified is True
    assert result.total_score == 0
    assert "1m93" in result.disqualification_reason or "titan" in result.disqualification_reason.lower()


def test_twingo_is_disqualified_for_titan(auditor):
    """Vérifie que la Twingo est disqualifiée pour cause de gabarit insuffisant."""
    ad = CarAd(
        id="test_twingo",
        source="leboncoin",
        url="https://leboncoin.fr/ad/twingo_test",
        title="Renault Twingo 1.2 16v Expression",
        price=1900,
        year=2005,
        mileage=120000,
        description="Twingo essence, CT valide."
    )
    result = auditor.audit(ad)
    assert result.is_disqualified is True
    assert result.total_score == 0
    assert "1m93" in result.disqualification_reason or "titan" in result.disqualification_reason.lower()


def test_peugeot_206_is_disqualified_for_titan(auditor):
    """Vérifie que la 206 (pédalier étroit et pas de recul) est disqualifiée."""
    ad = CarAd(
        id="test_206",
        source="leboncoin",
        url="https://leboncoin.fr/ad/206_test",
        title="Peugeot 206 1.4 75ch Quiksilver",
        price=2300,
        year=2004,
        mileage=130000,
        description="206 essence propre, distribution neuve."
    )
    result = auditor.audit(ad)
    assert result.is_disqualified is True
    assert result.total_score == 0
    assert "1m93" in result.disqualification_reason or "titan" in result.disqualification_reason.lower()


def test_golden_volvo_c30_scores_high(auditor):
    """Vérifie qu'un coupé stylé et taillé pour les grands (Volvo C30) obtient un score d'excellence."""
    ad = CarAd(
        id="test_c30",
        source="leboncoin",
        url="https://leboncoin.fr/ad/c30_test",
        title="Volvo C30 1.6 Kinetic Essence 100ch",
        price=3200,
        year=2008,
        mileage=125000,
        description="Superbe Volvo C30 1.6 essence, 1ere main, CT vierge fait hier, carnet complet avec factures Volvo, dort au garage."
    )
    result = auditor.audit(ad)
    assert result.is_disqualified is False
    assert result.total_score >= 85
    assert result.engine_score >= 28
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
        title="Honda Civic 1.4 i-vtec",
        price=2600,
        year=2007,
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
