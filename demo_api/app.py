from __future__ import annotations

from flask import Flask, jsonify, request

from demo_api.services.pricing import build_quote


def create_app() -> Flask:
    app = Flask(__name__)

    @app.get("/health")
    def health():
        return jsonify({"status": "ok"})

    @app.post("/quote")
    def quote():
        payload = request.get_json(force=True) or {}
        subtotal = float(payload.get("subtotal", 0))
        is_vip = bool(payload.get("is_vip", False))
        expedited = bool(payload.get("expedited", False))
        return jsonify(build_quote(subtotal=subtotal, is_vip=is_vip, expedited=expedited))

    return app


app = create_app()
