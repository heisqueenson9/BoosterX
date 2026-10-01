import os
import json
import click
from flask.cli import AppGroup
from backend.app.db import db
from backend.app.models import Platform, Service, Setting

seed_cli = AppGroup("seed")

DEFAULT_PLATFORMS = ["TikTok", "Instagram", "Facebook", "X", "Telegram"]

DEFAULT_SETTINGS = {
    "payment_method": "Telecel Cash",
    "payment_name": "BOOSTX",
    "payment_number": "0202979378",
    "payment_instructions": "Send the exact amount shown — any network fee is added on top, not deducted.",
    "payment_active": "true",
    "payment_recipient_aliases": json.dumps(["BOOSTX", "BOOST X", "BOOSTX GHANA", "0202979378"]),
    "min_payment_ghs": "1.00",
    "max_payment_ghs": "10000.00",
    "usd_to_ghs_rate": "10.70",
    "flat_markup_ghs": "5.00",
    "partial_credit_enabled": "false",
    "refund_policy": "Failed 100%, Canceled before start 100%, Partial refunds pro-rata",
    "service_sync_interval": "3600"
}

DEFAULT_MOCK_SERVICES = [
    {
        "provider_service_id": 1,
        "platform": "Instagram",
        "category": "Instagram Followers",
        "name": "Instagram Followers (High Quality)",
        "type": "Default",
        "description": "Gradual delivery with refill protection. Profile must be public.",
        "rate_usd_per_1000": "1.4000",
        "min_qty": 100,
        "max_qty": 100000,
        "refill_available": True,
        "enabled": True
    },
    {
        "provider_service_id": 2,
        "platform": "TikTok",
        "category": "TikTok Views",
        "name": "TikTok Video Views (Instant)",
        "type": "Default",
        "description": "Stable views for public videos. Fast start.",
        "rate_usd_per_1000": "0.3000",
        "min_qty": 1000,
        "max_qty": 1000000,
        "refill_available": False,
        "enabled": True
    },
    {
        "provider_service_id": 3,
        "platform": "Facebook",
        "category": "Facebook Page Followers",
        "name": "Facebook Page Followers",
        "type": "Default",
        "description": "Page followers for public pages.",
        "rate_usd_per_1000": "1.1200",
        "min_qty": 100,
        "max_qty": 100000,
        "refill_available": True,
        "enabled": True
    },
    {
        "provider_service_id": 4,
        "platform": "X",
        "category": "X Likes",
        "name": "X (Twitter) Post Likes",
        "type": "Default",
        "description": "Likes for public posts.",
        "rate_usd_per_1000": "1.1200",
        "min_qty": 50,
        "max_qty": 50000,
        "refill_available": True,
        "enabled": True
    },
    {
        "provider_service_id": 5,
        "platform": "Telegram",
        "category": "Telegram Channel Members",
        "name": "Telegram Channel Members",
        "type": "Default",
        "description": "Members for public channels.",
        "rate_usd_per_1000": "1.8600",
        "min_qty": 100,
        "max_qty": 100000,
        "refill_available": True,
        "enabled": True
    }
]


def register_cli_commands(app):
    @app.cli.command("seed")
    def seed_command():
        """Seed default platforms, settings and (fake-provider mode) mock services."""
        click.echo("Seeding database...")
        
        # 1. Seed platforms
        for p_name in DEFAULT_PLATFORMS:
            plat = Platform.query.filter_by(name=p_name).first()
            if not plat:
                db.session.add(Platform(name=p_name, active=True))
        db.session.commit()
        click.echo("Platforms seeded.")
        
        # 2. Seed settings
        for key, val in DEFAULT_SETTINGS.items():
            setting = Setting.query.filter_by(key=key).first()
            if not setting:
                db.session.add(Setting(key=key, value=val))
        db.session.commit()
        click.echo("Settings seeded.")
        
        # 3. Seed initial default services if no enabled services exist
        if os.getenv("PROVIDER_MODE", "fake") != "live" and Service.query.filter_by(enabled=True).count() == 0:
            for s_data in DEFAULT_MOCK_SERVICES:
                existing = Service.query.filter_by(provider_service_id=s_data["provider_service_id"]).first()
                if not existing:
                    db.session.add(Service(**s_data))
                else:
                    existing.enabled = True
            db.session.commit()
            click.echo("Default enabled services seeded.")

        # The administrator is NOT seeded: it authenticates with the ADMIN_EMAIL /
        # ADMIN_PASSWORD environment variables (see auth/auth_service.py).
        if not (app.config.get("ADMIN_EMAIL") and app.config.get("ADMIN_PASSWORD")):
            click.echo("Warning: ADMIN_EMAIL / ADMIN_PASSWORD are not set; admin login is disabled.")

        click.echo("Seeding complete!")
