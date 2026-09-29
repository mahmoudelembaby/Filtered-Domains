from app.policy.engine import PolicyEngine
from app.classifiers.base import DecisionResult


def _r(related, conf, err=None):
    return DecisionResult(related, conf, "jev", "1.x", 10.0, error=err)


def test_allow_block_review():
    p = PolicyEngine(0.90, 0.90, "1.0")
    assert p.decide(_r(True, 0.96)).decision == "ALLOW"
    assert p.decide(_r(False, 0.95)).decision == "BLOCK"
    assert p.decide(_r(True, 0.5)).decision == "REVIEW"
    assert p.decide(_r(False, 0.5)).decision == "REVIEW"
    assert p.decide(_r(True, 0.99, err="UNCERTAIN")).decision == "REVIEW"
    assert p.decide(_r(False, 0.0, err="METADATA_UNAVAILABLE")).decision == "REVIEW"
