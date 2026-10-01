import os
import json
import click
from flask.cli import AppGroup
from backend.app.db import db
from backend.app.models import User, UserRole, UserStatus, Platform, Service, Setting
from backend.app.utils.phone import normalize_phone

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
        """Seed default platforms, settings, mock services, and initial admin."""
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

        # 4. Seed initial admin if specified in ENV or missing
        admin_email = os.getenv("ADMIN_EMAIL", "admin@boostx.com")
        admin_password = os.getenv("ADMIN_PASSWORD")
        if not admin_password:
            if app.config.get("TESTING") or app.debug:
                admin_password = "AdminPass123!"
            else:
                click.echo("ADMIN_PASSWORD not set; skipping admin creation. Set ADMIN_EMAIL/ADMIN_PASSWORD or run `flask create-admin`.")

        admin_user = User.query.filter_by(email=admin_email).first() if admin_password else None
        if admin_password and not admin_user:
            admin_user = User(
                public_user_id=User.new_public_id(UserRole.ADMIN),
                full_name="Enock Admin",
                email=admin_email,
                phone=normalize_phone("0202979378"),
                password_hash="",
                role=UserRole.ADMIN,
                status=UserStatus.ACTIVE
            )
            admin_user.set_password(admin_password)
            db.session.add(admin_user)
            db.session.commit()
            click.echo(f"Initial admin created ({admin_email}).")
        
        click.echo("Seeding complete!")

    @app.cli.command("create-admin")
    @click.option("--email", prompt="Admin Email", required=True)
    @click.option("--password", prompt="Admin Password", hide_input=True, confirmation_prompt=True, required=True)
    @click.option("--name", default="Administrator", help="Admin Full Name")
    def create_admin_command(email, password, name):
        """Create an administrator account from CLI."""
        email_clean = email.strip().lower()
        if User.query.filter_by(email=email_clean).first():
            click.echo(f"Error: User with email {email_clean} already exists.")
            return
        
        admin = User(
            public_user_id=User.new_public_id(UserRole.ADMIN),
            full_name=name,
            email=email_clean,
            phone=None,
            password_hash="",
            role=UserRole.ADMIN,
            status=UserStatus.ACTIVE
        )
        admin.set_password(password)
        db.session.add(admin)
        db.session.commit()
        click.echo(f"Admin account created for {email_clean} ({admin.public_user_id}).")
