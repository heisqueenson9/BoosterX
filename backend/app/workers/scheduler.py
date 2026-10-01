import time
import logging
from datetime import datetime, timedelta
from redis import Redis
from rq import Queue
from rq_scheduler import Scheduler

from backend.app import create_app
from backend.app.workers.sync_services import sync_services_worker
from backend.app.workers.order_worker import check_pending_orders, expire_payments
from backend.app.workers.fx_worker import refresh_fx_rate

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("boostx.scheduler")

def run_scheduler():
    app = create_app()
    logger.info("Initializing BoostX Worker Scheduler...")
    
    redis_url = app.config.get("REDIS_URL", "redis://localhost:6379/0")
    try:
        redis_conn = Redis.from_url(redis_url)
        redis_conn.ping()
        logger.info(f"Connected to Redis at {redis_url}")
        
        queue = Queue("default", connection=redis_conn)
        scheduler = Scheduler(queue=queue, connection=redis_conn)

        # Clear old scheduled jobs
        for job in scheduler.get_jobs():
            scheduler.cancel(job)

        # Register recurring jobs
        logger.info("Registering worker jobs on intervals...")
        scheduler.schedule(
            scheduled_time=datetime.utcnow(),
            func=check_pending_orders,
            interval=120,  # Every 2 minutes
            repeat=None
        )
        scheduler.schedule(
            scheduled_time=datetime.utcnow(),
            func=expire_payments,
            interval=300,  # Every 5 minutes
            repeat=None
        )
        scheduler.schedule(
            scheduled_time=datetime.utcnow(),
            func=sync_services_worker,
            interval=3600, # Every 60 minutes
            repeat=None
        )
        scheduler.schedule(
            scheduled_time=datetime.utcnow(),
            func=refresh_fx_rate,
            interval=3600, # Every 60 minutes
            repeat=None
        )
        logger.info("Scheduler running...")
        scheduler.run()

    except Exception as exc:
        logger.warning(f"Redis not available or RQ scheduler error ({exc}). Falling back to in-process scheduler loop.")
        run_fallback_loop(app)

def run_fallback_loop(app):
    """Fallback in-process loop when Redis is not active in simple local dev environments."""
    logger.info("Starting in-process scheduled task loop...")
    last_order_check = 0
    last_expire_check = 0
    last_sync = 0
    last_fx = 0

    while True:
        now = time.time()
        with app.app_context():
            # Check pending orders (every 120s)
            if now - last_order_check >= 120:
                try:
                    check_pending_orders(app)
                except Exception as e:
                    logger.error(f"Error in check_pending_orders: {e}")
                last_order_check = now

            # Expire payments (every 300s)
            if now - last_expire_check >= 300:
                try:
                    expire_payments(app)
                except Exception as e:
                    logger.error(f"Error in expire_payments: {e}")
                last_expire_check = now

            # Sync services (every 3600s)
            if now - last_sync >= 3600:
                try:
                    sync_services_worker(app)
                except Exception as e:
                    logger.error(f"Error in sync_services_worker: {e}")
                last_sync = now

            # Refresh FX rate (every 3600s)
            if now - last_fx >= 3600:
                try:
                    refresh_fx_rate(app)
                except Exception as e:
                    logger.error(f"Error in refresh_fx_rate: {e}")
                last_fx = now

        time.sleep(10)

if __name__ == "__main__":
    run_scheduler()
