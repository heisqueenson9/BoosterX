import os
import pytest
from decimal import Decimal
from backend.app import create_app, db
from backend.app.models import Platform, Service, Setting
from backend.app.pricing.pricing_service import PricingService, PricingSettings
from backend.app.providers.fake_provider import FakeProvider
from backend.app.workers.sync_services import sync_services_worker

@pytest.fixture
def app():
    db_path = os.path.join(os.path.dirname(__file__), "test_m3.db")
    if os.path.exists(db_path):
        os.remove(db_path)
    app = create_app()
    app.config.update({
        "TESTING": True,
        "SQLALCHEMY_DATABASE_URI": f"sqlite:///{db_path}",
        "SECRET_KEY": "test-secret-key",
        "PROVIDER_MODE": "fake"
    })
    with app.app_context():
        db.create_all()
        runner = app.test_cli_runner()
        runner.invoke(args=["seed"])
        yield app
        db.session.remove()
        db.drop_all()
    if os.path.exists(db_path):
        try:
            os.remove(db_path)
        except Exception:
            pass

@pytest.fixture
def client(app):
    return app.test_client()

def test_pricing_calculation():
    settings = PricingSettings(usd_to_ghs_rate=Decimal("10.70"), flat_markup_ghs=Decimal("5.00"))
    pricing = PricingService(settings)
    
    quote = pricing.quote_service(
        service_id=1,
        provider_rate_usd_per_1000=Decimal("1.40"),
        quantity=2500,
        min_qty=100,
        max_qty=100000
    )
    # cost = (1.40 / 1000) * 2500 * 10.70 = 37.45
    # customer_price = 37.45 + 5.00 = 42.45
    assert quote.provider_cost_ghs == Decimal("37.45")
    assert quote.customer_price_ghs == Decimal("42.45")

def test_service_sync_worker(app):
    with app.app_context():
        res = sync_services_worker()
        assert res["status"] == "success"
        assert res["added"] > 0

        # Check synced services
        services = Service.query.all()
        assert len(services) > 0
        for s in services:
            assert s.platform in ["TikTok", "Instagram", "Facebook", "X", "Telegram"]
            assert s.enabled is False  # New services start disabled per spec

def test_catalog_endpoints(client, app):
    with app.app_context():
        sync_services_worker()
        # Enable Instagram service for catalog testing
        svc = Service.query.filter_by(platform="Instagram").first()
        svc.enabled = True
        db.session.commit()
        svc_id = svc.id

    # GET /api/platforms
    res_p = client.get("/api/platforms")
    assert res_p.status_code == 200
    p_data = res_p.get_json()
    assert len(p_data["platforms"]) == 5

    # GET /api/services?platform=Instagram
    res_s = client.get("/api/services?platform=Instagram")
    assert res_s.status_code == 200
    s_data = res_s.get_json()
    assert len(s_data["services"]) == 1

    # POST /api/orders/preview
    csrf = client.post("/api/session").get_json()["csrf_token"]
    res_prev = client.post("/api/orders/preview", json={
        "service_id": svc_id,
        "quantity": 1000
    }, headers={"X-CSRF-Token": csrf})
    assert res_prev.status_code == 200
    prev_data = res_prev.get_json()
    assert "service_cost_ghs" in prev_data
    assert prev_data["processing_fee_ghs"] == "5.00"
    assert "total_ghs" in prev_data
    assert "sufficient" in prev_data
