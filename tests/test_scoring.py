import pytest
from pathlib import Path
from src.models import CarAd
from src.auditor.scoring import CarAuditor
from src.database.repository import AdRepository

CONFIG_DIR = Path(__file__).resolve().parent.parent / "config"


@pytest.fixture
def default_auditor():
    """Auditeur par défaut excluant le Segment A (mini-citadines) au profit de B, C, D."""
    return CarAuditor(
        engines_db_path=CONFIG_DIR / "engines_db.json",
        segments_db_path=CONFIG_DIR / "segments_db.json",
        allowed_segments=["B", "C", "D"],
        target_models=["Civic", "C30", "Golf"]
    )


@pytest.fixture
def permissive_auditor():
    """Auditeur autorisant tous les segments (A, B, C, D) sans restriction de gabarit."""
    return CarAuditor(
        engines_db_path=CONFIG_DIR / "engines_db.json",
        segments_db_path=CONFIG_DIR / "segments_db.json",
        allowed_segments=["A", "B", "C", "D"]
    )


@pytest.fixture
def temp_repo(tmp_path):
    db_file = tmp_path / "test_autohunter.db"
    return AdRepository(db_path=db_file)


def test_puretech_is_disqualified(default_auditor):
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
    result = default_auditor.audit(ad)
    assert result.is_disqualified is True
    assert result.total_score == 0
    assert "PureTech" in result.disqualification_reason


def test_vag_tsi_ea111_is_disqualified(default_auditor):
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
    result = default_auditor.audit(ad)
    assert result.is_disqualified is True
    assert result.total_score == 0
    assert "EA111" in result.disqualification_reason or "TSI" in result.disqualification_reason


def test_segment_a_excluded_when_not_allowed(default_auditor):
    """Vérifie qu'une mini-citadine (Segment A : C2, Twingo) est exclue si Segment A n'est pas autorisé."""
    ad_c2 = CarAd(
        id="test_c2",
        source="leboncoin",
        url="https://leboncoin.fr/ad/c2",
        title="Citroën C2 1.4 Furio",
        price=2200,
        year=2006,
        mileage=110000,
        description="Citroën C2 essence, CT ok."
    )
    result = default_auditor.audit(ad_c2)
    assert result.is_disqualified is True
    assert result.total_score == 0
    assert "Segment A" in result.disqualification_reason

    ad_twingo = CarAd(
        id="test_twingo",
        source="leboncoin",
        url="https://leboncoin.fr/ad/twingo",
        title="Renault Twingo 1.2 16v",
        price=1800,
        year=2005,
        mileage=120000,
        description="Twingo essence, CT ok."
    )
    result_twingo = default_auditor.audit(ad_twingo)
    assert result_twingo.is_disqualified is True
    assert "Segment A" in result_twingo.disqualification_reason


def test_segment_a_accepted_when_allowed(permissive_auditor):
    """Vérifie qu'une mini-citadine (Segment A) est acceptée si la config autorise le Segment A."""
    ad_c2 = CarAd(
        id="test_c2_allowed",
        source="leboncoin",
        url="https://leboncoin.fr/ad/c2_ok",
        title="Citroën C2 1.4 Furio Essence",
        price=2200,
        year=2006,
        mileage=110000,
        description="Citroën C2 essence moteur TU, CT vierge, carnet d'entretien complet."
    )
    result = permissive_auditor.audit(ad_c2)
    assert result.is_disqualified is False
    assert result.total_score >= 80


def test_segment_c_golden_volvo_c30_scores_high(default_auditor):
    """Vérifie qu'une compacte/coupé Segment C (Volvo C30) obtient un score d'excellence."""
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
    result = default_auditor.audit(ad)
    assert result.is_disqualified is False
    assert result.total_score >= 85
    assert result.engine_score >= 28
    assert result.verdict in ("PÉPITE ABSOLUE", "TRÈS BONNE AFFAIRE")


def test_segment_c_golden_honda_civic_scores_high(default_auditor):
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
    result = default_auditor.audit(ad)
    assert result.is_disqualified is False
    assert result.total_score >= 80
    assert result.engine_score == 30


def test_repository_save_and_deduplication(temp_repo, default_auditor):
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
    
    res = default_auditor.audit(ad)
    temp_repo.save_ad(ad, res)

    assert temp_repo.is_seen(ad.id) is True
    top_deals = temp_repo.get_top_deals(limit=5, min_score=60)
    assert len(top_deals) == 1
    assert top_deals[0]["id"] == "ad_test_repo"
