import asyncio
import csv
import json
import sys
import time

sys.path.insert(0, ".")
from app.classifiers.jev import JevModel
from app.classifiers.base import WebsiteMetadata
from app.policy.engine import PolicyEngine

# Usage:
#   python evaluation/evaluate.py evaluation/dataset_example.csv
# CSV columns: domain,title,description,keywords(| separated),headings(| separated),expected(RELATED|NOT_RELATED)
# Offline: uses metadata from CSV (no network). Measures Jev-only (Test A, v1).


async def main(path: str):
    jev = JevModel(mode="heuristic")
    policy = PolicyEngine(0.90, 0.90, "1.0")
    rows = list(csv.DictReader(open(path, encoding="utf-8")))
    y_true, y_pred, lat = [], [], []
    reviews = 0
    for r in rows:
        md = WebsiteMetadata(
            domain=r["domain"], title=r.get("title", ""), description=r.get("description", ""),
            keywords=[k for k in r.get("keywords", "").split("|") if k],
            headings=[h for h in r.get("headings", "").split("|") if h],
        )
        t0 = time.perf_counter()
        res = await jev.classify(md)
        dt = (time.perf_counter() - t0) * 1000
        lat.append(dt)
        dec = policy.decide(res).decision
        if dec == "REVIEW":
            reviews += 1
            continue  # reviews excluded from precision/recall, tracked separately
        pred = "RELATED" if dec == "ALLOW" else "NOT_RELATED"
        y_true.append(r["expected"])
        y_pred.append(pred)
    lat.sort()
    def pct(p):
        return lat[min(len(lat) - 1, int(round(p / 100 * (len(lat) - 1))))] if lat else 0
    tp = sum(1 for t, p in zip(y_true, y_pred) if t == "RELATED" and p == "RELATED")
    fp = sum(1 for t, p in zip(y_true, y_pred) if t == "NOT_RELATED" and p == "RELATED")
    fn = sum(1 for t, p in zip(y_true, y_pred) if t == "RELATED" and p == "NOT_RELATED")
    tn = sum(1 for t, p in zip(y_true, y_pred) if t == "NOT_RELATED" and p == "NOT_RELATED")
    n = len(y_true) or 1
    out = {
        "n_scored": len(y_true), "n_reviews": reviews,
        "review_rate": reviews / max(1, len(rows)),
        "accuracy": (tp + tn) / n,
        "precision": tp / max(1, tp + fp),
        "recall": tp / max(1, tp + fn),
        "f1": (2 * tp / max(1, 2 * tp + fp + fn)),
        "false_positive_rate": fp / max(1, fp + tn),
        "false_negative_rate": fn / max(1, fn + tp),
        "p50_ms": pct(50), "p95_ms": pct(95), "p99_ms": pct(99),
    }
    print(json.dumps(out, indent=2))


if __name__ == "__main__":
    asyncio.run(main(sys.argv[1] if len(sys.argv) > 1 else "evaluation/dataset_example.csv"))
