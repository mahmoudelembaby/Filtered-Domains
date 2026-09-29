"""Gradio frontend for website-filter v1. Calls the FastAPI backend."""
from __future__ import annotations
import os
import httpx
import gradio as gr

BACKEND_URL = os.getenv("BACKEND_URL", "http://127.0.0.1:8000").rstrip("/")
ADMIN_KEY = os.getenv("ADMIN_API_KEY", "")

TIMEOUT = 30.0


def _headers() -> dict:
    return {"X-Admin-Key": ADMIN_KEY} if ADMIN_KEY else {}


def api_post(path: str, payload: dict, admin: bool = False) -> dict:
    try:
        with httpx.Client(timeout=TIMEOUT) as c:
            r = c.post(f"{BACKEND_URL}{path}", json=payload,
                       headers=_headers() if admin else {})
            if r.status_code >= 400:
                return {"error": f"{r.status_code}: {r.text[:500]}"}
            return r.json()
    except Exception as e:
        return {"error": f"backend unreachable ({BACKEND_URL}): {e}"}


def api_get(path: str, admin: bool = False):
    try:
        with httpx.Client(timeout=TIMEOUT) as c:
            r = c.get(f"{BACKEND_URL}{path}", headers=_headers() if admin else {})
            if r.status_code == 404:
                return {"error": "unknown domain (not classified yet)"}
            if r.status_code >= 400:
                return {"error": f"{r.status_code}: {r.text[:500]}"}
            return r.json()
    except Exception as e:
        return {"error": f"backend unreachable ({BACKEND_URL}): {e}"}


def api_delete(path: str):
    try:
        with httpx.Client(timeout=TIMEOUT) as c:
            r = c.delete(f"{BACKEND_URL}{path}", headers=_headers())
            if r.status_code >= 400:
                return {"error": f"{r.status_code}: {r.text[:500]}"}
            return r.json()
    except Exception as e:
        return {"error": f"backend unreachable: {e}"}


def fmt_result(res: dict) -> tuple[str, str, str]:
    if "error" in res:
        return f"ERROR: {res['error']}", "", str(res)
    color = {"ALLOW": "🟢 ALLOW", "BLOCK": "🔴 BLOCK", "REVIEW": "🟡 REVIEW"}.get(
        res.get("decision"), str(res.get("decision")))
    summary = (
        f"Domain: {res.get('domain')}\nDecision: {res.get('decision')}\n"
        f"Related: {res.get('related')}\nConfidence: {res.get('confidence')}\n"
        f"Model: {res.get('model')}\nCache hit: {res.get('cache_hit')} | "
        f"Fallback: {res.get('fallback_used')}"
    )
    return color, summary, str(res)


def do_classify(domain: str):
    if not (domain or "").strip():
        return "Enter a domain", "", ""
    return fmt_result(api_post("/classify", {"domain": domain.strip()}))


def do_lookup(domain: str):
    if not (domain or "").strip():
        return "Enter a domain", ""
    res = api_get(f"/domain/{domain.strip()}")
    if isinstance(res, dict) and "error" in res:
        return f"ERROR: {res['error']}", str(res)
    return f"{res.get('domain')} → {res.get('decision')} (conf {res.get('confidence')})", str(res)


def do_reviews():
    res = api_get("/admin/reviews?limit=50", admin=True)
    if isinstance(res, dict) and "error" in res:
        return res["error"], []
    rows = [[r.get("domain"), r.get("decision"), r.get("confidence"),
             r.get("model"), r.get("classified_at")] for r in res]
    return f"{len(rows)} items needing review", rows


def do_override(domain: str, decision: str, reason: str, created_by: str):
    if not (domain or "").strip():
        return "Enter a domain"
    res = api_post("/admin/override",
                   {"domain": domain.strip(), "decision": decision,
                    "reason": reason or "", "created_by": created_by or ""}, admin=True)
    return str(res)


def do_delete_override(domain: str):
    if not (domain or "").strip():
        return "Enter a domain"
    return str(api_delete(f"/admin/override/{domain.strip()}"))


def do_invalidate(domain: str):
    if (domain or "").strip():
        return str(api_post("/admin/cache/invalidate", {"domain": domain.strip()}, admin=True))
    return str(api_post("/admin/cache/invalidate", {"all": True}, admin=True))


def do_metrics():
    res = api_get("/admin/metrics", admin=True)
    return str(res)


with gr.Blocks(title="website-filter v1") as demo:
    gr.Markdown("# website-filter v1 — Jev-only\nGlobal ALLOW / BLOCK / REVIEW. No per-department rules.")
    with gr.Tab("Classify"):
        d_in = gr.Textbox(label="Domain", placeholder="github.com")
        btn = gr.Button("Classify", variant="primary")
        decision = gr.Textbox(label="Decision")
        summary = gr.Textbox(label="Summary", lines=6)
        raw = gr.Textbox(label="Raw JSON", lines=6)
        btn.click(do_classify, inputs=d_in, outputs=[decision, summary, raw])
    with gr.Tab("Lookup"):
        l_in = gr.Textbox(label="Domain")
        l_btn = gr.Button("Lookup cached")
        l_sum = gr.Textbox(label="Result")
        l_raw = gr.Textbox(label="Raw JSON", lines=8)
        l_btn.click(do_lookup, inputs=l_in, outputs=[l_sum, l_raw])
    with gr.Tab("Admin"):
        gr.Markdown("Requires `ADMIN_API_KEY` if set on backend (sent as X-Admin-Key).")
        rev_btn = gr.Button("Load reviews")
        rev_status = gr.Textbox(label="Status")
        rev_table = gr.Dataframe(
            headers=["domain", "decision", "confidence", "model", "classified_at"],
            label="REVIEW queue")
        rev_btn.click(do_reviews, outputs=[rev_status, rev_table])
        with gr.Row():
            o_domain = gr.Textbox(label="Domain")
            o_decision = gr.Dropdown(["MANUAL_ALLOW", "MANUAL_BLOCK"], value="MANUAL_BLOCK",
                                     label="Override")
        with gr.Row():
            o_reason = gr.Textbox(label="Reason")
            o_by = gr.Textbox(label="Created by")
        with gr.Row():
            o_btn = gr.Button("Set override")
            o_del = gr.Button("Delete override")
        o_out = gr.Textbox(label="Result")
        o_btn.click(do_override, inputs=[o_domain, o_decision, o_reason, o_by], outputs=o_out)
        o_del.click(do_delete_override, inputs=o_domain, outputs=o_out)
        with gr.Row():
            inv_in = gr.Textbox(label="Domain to invalidate (empty = all)")
            inv_btn = gr.Button("Invalidate cache")
        inv_out = gr.Textbox(label="Result")
        inv_btn.click(do_invalidate, inputs=inv_in, outputs=inv_out)
        m_btn = gr.Button("Metrics")
        m_out = gr.Textbox(label="Metrics", lines=8)
        m_btn.click(do_metrics, outputs=m_out)

if __name__ == "__main__":
    demo.launch(server_name="127.0.0.1", server_port=7860)
