from decimal import Decimal
from flask import Blueprint, jsonify, request, current_app
from backend.app.db import db
from backend.app.models import Platform, Service, Setting
from backend.app.pricing.pricing_service import PricingService, PricingSettings, PricingError
from backend.app.auth.session import require_user
from backend.app.services.ledger_service import get_owner_balance

catalog_bp = Blueprint("catalog", __name__, url_prefix="/api")

def get_pricing_service() -> PricingService:
    rate_setting = Setting.query.filter_by(key="usd_to_ghs_rate").first()
    markup_setting = Setting.query.filter_by(key="flat_markup_ghs").first()

    usd_rate = Decimal(rate_setting.value) if rate_setting else current_app.config["DEFAULT_USD_TO_GHS"]
    flat_markup = Decimal(markup_setting.value) if markup_setting else current_app.config["DEFAULT_FLAT_MARKUP_GHS"]

    settings = PricingSettings(usd_to_ghs_rate=usd_rate, flat_markup_ghs=flat_markup)
    return PricingService(settings)


@catalog_bp.get("/platforms")
def get_platforms():
    platforms = Platform.query.filter_by(active=True).all()
    return jsonify({
        "platforms": [{"id": p.id, "name": p.name} for p in platforms]
    }), 200


from backend.app.providers.platform_mapper import normalize_platform_name

@catalog_bp.get("/services")
def get_services():
    platform_name = request.args.get("platform")
    query = Service.query.filter_by(enabled=True)
    if platform_name:
        canonical = normalize_platform_name(platform_name)
        if canonical:
            query = query.filter_by(platform=canonical)
        else:
            query = query.filter(Service.platform.ilike(f"%{platform_name.strip()}%"))

    services = query.all()
    pricing = get_pricing_service()

    result = []
    for s in services:
        display_rate = pricing.customer_facing_rate_per_1000(Decimal(str(s.rate_usd_per_1000)))
        result.append({
            "id": s.id,
            "platform": s.platform,
            "category": s.category,
            "name": s.name,
            "description": s.description or f"High-quality {s.platform} {s.name}",
            "min_quantity": s.min_qty,
            "max_quantity": s.max_qty,
            "price_per_1000_ghs": f"{display_rate:.2f}",
            "refill_available": s.refill_available,
            "speed": "Fast"
        })

    return jsonify({"services": result}), 200


@catalog_bp.get("/services/<int:service_id>")
def get_service_detail(service_id: int):
    service = db.session.get(Service, service_id)
    if not service or not service.enabled:
        return jsonify({"error": "Service not found or inactive"}), 404

    pricing = get_pricing_service()
    display_rate = pricing.customer_facing_rate_per_1000(Decimal(str(service.rate_usd_per_1000)))

    return jsonify({
        "id": service.id,
        "platform": service.platform,
        "category": service.category,
        "name": service.name,
        "description": service.description,
        "min_quantity": service.min_qty,
        "max_quantity": service.max_qty,
        "price_per_1000_ghs": f"{display_rate:.2f}",
        "refill_available": service.refill_available,
    }), 200


@catalog_bp.post("/orders/preview")
def preview_order():
    data = request.get_json(silent=True) or {}
    service_id = data.get("service_id")
    quantity = data.get("quantity")

    if not service_id or quantity is None:
        return jsonify({"error": "service_id and quantity are required"}), 400

    try:
        quantity = int(quantity)
        service_id = int(service_id)
    except (ValueError, TypeError):
        return jsonify({"error": "Invalid service_id or quantity"}), 400

    service = db.session.get(Service, service_id)
    if not service or not service.enabled:
        return jsonify({"error": "Service not found or unavailable"}), 404

    # Validate platform enabled
    plat = Platform.query.filter_by(name=service.platform, active=True).first()
    if not plat:
        return jsonify({"error": f"Platform '{service.platform}' is currently disabled"}), 400

    pricing = get_pricing_service()
    try:
        quote = pricing.quote_service(
            service_id=service.id,
            provider_rate_usd_per_1000=Decimal(str(service.rate_usd_per_1000)),
            quantity=quantity,
            min_qty=service.min_qty,
            max_qty=service.max_qty
        )
    except PricingError as exc:
        return jsonify({"error": str(exc)}), 400

    user = require_user()
    available_balance = get_owner_balance(user.id)
    sufficient = available_balance >= quote.customer_price_ghs

    return jsonify({
        "service_cost_ghs": f"{quote.provider_cost_ghs:.2f}",
        "processing_fee_ghs": f"{quote.markup_ghs:.2f}",
        "total_ghs": f"{quote.customer_price_ghs:.2f}",
        "balance_ghs": f"{available_balance:.2f}",
        "sufficient": sufficient
    }), 200
