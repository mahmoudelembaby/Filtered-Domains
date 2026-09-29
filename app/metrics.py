"""In-memory metrics + Prometheus exposition (no external service needed)."""
from __future__ import annotations
import statistics
import threading
from collections import deque


class Metrics:
    def __init__(self, max_lat: int = 10000):
        self._lock = threading.Lock()
        self.total = 0
        self.cache_hits = 0
        self.jev_requests = 0
        self.reviews = 0
        self.allows = 0
        self.blocks = 0
        self.latencies: deque[float] = deque(maxlen=max_lat)

    def observe(self, *, cache_hit: bool, jev_called: bool, decision: str, latency_ms: float) -> None:
        with self._lock:
            self.total += 1
            if cache_hit:
                self.cache_hits += 1
            if jev_called:
                self.jev_requests += 1
            if decision == "REVIEW":
                self.reviews += 1
            elif decision == "ALLOW":
                self.allows += 1
            elif decision == "BLOCK":
                self.blocks += 1
            self.latencies.append(latency_ms)

    def snapshot(self) -> dict:
        with self._lock:
            lat = sorted(self.latencies)
            def pct(p: float) -> float:
                if not lat:
                    return 0.0
                k = min(len(lat) - 1, max(0, int(round((p / 100.0) * (len(lat) - 1)))))
                return lat[k]
            total = self.total or 1
            return {
                "total_requests": self.total,
                "cache_hit_rate": self.cache_hits / total,
                "jev_request_rate": self.jev_requests / total,
                "review_rate": self.reviews / total,
                "allow": self.allows,
                "block": self.blocks,
                "review": self.reviews,
                "avg_latency_ms": (sum(lat) / len(lat)) if lat else 0.0,
                "p50_latency_ms": pct(50),
                "p95_latency_ms": pct(95),
                "p99_latency_ms": pct(99),
            }

    def prometheus(self) -> str:
        s = self.snapshot()
        lines = [
            "# HELP website_filter_requests_total Total classify requests",
            "# TYPE website_filter_requests_total counter",
            f"website_filter_requests_total {self.total}",
            "# HELP website_filter_cache_hit_rate Cache hit rate",
            "# TYPE website_filter_cache_hit_rate gauge",
            f"website_filter_cache_hit_rate {s['cache_hit_rate']}",
            "# HELP website_filter_review_rate Review rate",
            "# TYPE website_filter_review_rate gauge",
            f"website_filter_review_rate {s['review_rate']}",
            "# HELP website_filter_p95_latency_ms P95 latency",
            "# TYPE website_filter_p95_latency_ms gauge",
            f"website_filter_p95_latency_ms {s['p95_latency_ms']}",
        ]
        return "\n".join(lines) + "\n"


metrics = Metrics()
