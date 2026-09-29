"""Deterministic policy: AI gives evidence, Python makes the final decision."""
from dataclasses import dataclass
from app.classifiers.base import DecisionResult


@dataclass
class PolicyDecision:
    decision: str  # ALLOW | BLOCK | REVIEW
    reason: str


class PolicyEngine:
    def __init__(self, allow_threshold: float = 0.90, block_threshold: float = 0.90, policy_version: str = "1.0"):
        self.allow_threshold = allow_threshold
        self.block_threshold = block_threshold
        self.policy_version = policy_version

    def decide(self, result: DecisionResult) -> PolicyDecision:
        if result.error is not None:
            return PolicyDecision("REVIEW", f"model_unreliable:{result.error}"[:120])
        if result.related and result.confidence >= self.allow_threshold:
            return PolicyDecision("ALLOW", "high_confidence_related")
        if not result.related and result.confidence >= self.block_threshold:
            return PolicyDecision("BLOCK", "high_confidence_not_related")
        return PolicyDecision("REVIEW", "low_confidence")

    def ttl_for(self, decision: str, allow_ttl: int, block_ttl: int, review_ttl: int) -> int:
        return {"ALLOW": allow_ttl, "BLOCK": block_ttl}.get(decision, review_ttl)
