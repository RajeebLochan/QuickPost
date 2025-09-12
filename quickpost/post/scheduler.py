import logging
import os
from apscheduler.schedulers.background import BackgroundScheduler
from django.core.cache import cache

logger = logging.getLogger(__name__)

def refresh_quote_job():
    """Job to refresh the daily quote in the cache every 12 hours"""
    try:
        # Import here to avoid circular imports
        from .views import get_daily_quote
        
        quote = get_daily_quote()
        cache.set('daily_quote', quote, None)  # No expiration time
        logger.info(f"Quote refreshed successfully: {quote}")
        print(f"[APScheduler] Quote refreshed: {quote}")
    except Exception as e:
        logger.error(f"Error refreshing quote: {e}")
        print(f"[APScheduler] Error refreshing quote: {e}")

# Global scheduler instance
scheduler = None

def start_scheduler():
    """Start the background scheduler"""
    global scheduler
    
    if scheduler is not None:
        return  # Scheduler already running
    
    scheduler = BackgroundScheduler()
    
    # Add the job to run every 12 hours
    scheduler.add_job(
        refresh_quote_job,
        'interval',
        hours=12,
        id='refresh_daily_quote',
        name='Refresh Daily Quote',
        replace_existing=True,
        max_instances=1
    )
    
    # Run the job immediately on startup to ensure we have a quote
    scheduler.add_job(
        refresh_quote_job,
        'date',
        id='refresh_quote_startup',
        name='Refresh Quote on Startup',
        replace_existing=True
    )
    
    scheduler.start()
    logger.info("APScheduler started successfully")
    print("[APScheduler] Scheduler started - Quote will refresh every 12 hours")

def stop_scheduler():
    """Stop the background scheduler"""
    global scheduler
    if scheduler is not None:
        scheduler.shutdown()
        scheduler = None
        logger.info("APScheduler stopped")
        print("[APScheduler] Scheduler stopped")
