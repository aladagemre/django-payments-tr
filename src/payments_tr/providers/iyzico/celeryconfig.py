"""
Celery configuration for django-iyzico subscription management.

Add this to your project's Celery configuration to enable
automated subscription billing.

Example:
    # In your project's celery.py:
    from payments_tr.providers.iyzico.celeryconfig import CELERY_BEAT_SCHEDULE as IYZICO_SCHEDULE

    app.conf.beat_schedule.update(IYZICO_SCHEDULE)
"""

from celery.schedules import crontab

# Celery Beat schedule for subscription tasks
CELERY_BEAT_SCHEDULE = {
    # Process subscriptions due for billing (daily at 2 AM)
    "process-due-subscriptions": {
        "task": "payments_tr.iyzico.process_due_subscriptions",
        "schedule": crontab(hour=2, minute=0),
        "options": {
            "expires": 3600,  # Task expires after 1 hour
        },
    },
    # Retry failed payments (every 6 hours)
    "retry-failed-payments": {
        "task": "payments_tr.iyzico.retry_failed_payments",
        "schedule": crontab(hour="*/6", minute=0),
        "options": {
            "expires": 3600,
        },
    },
    # Expire cancelled subscriptions (daily at 3 AM)
    "expire-cancelled-subscriptions": {
        "task": "payments_tr.iyzico.expire_cancelled_subscriptions",
        "schedule": crontab(hour=3, minute=0),
        "options": {
            "expires": 3600,
        },
    },
    # Check trial expirations (daily at 1 AM)
    "check-trial-expiration": {
        "task": "payments_tr.iyzico.check_trial_expiration",
        "schedule": crontab(hour=1, minute=0),
        "options": {
            "expires": 3600,
        },
    },
    # Check expiring payment methods (daily at 4 AM)
    "check-expiring-payment-methods": {
        "task": "payments_tr.iyzico.check_expiring_payment_methods",
        "schedule": crontab(hour=4, minute=0),
        "options": {
            "expires": 3600,
        },
    },
}


# Optional: Celery task routes
CELERY_TASK_ROUTES = {
    "payments_tr.iyzico.*": {
        "queue": "subscriptions",
        "routing_key": "subscription",
    },
}


# Optional: Task time limits
CELERY_TASK_TIME_LIMITS = {
    "payments_tr.iyzico.process_due_subscriptions": 3600,  # 1 hour
    "payments_tr.iyzico.retry_failed_payments": 3600,  # 1 hour
    "payments_tr.iyzico.charge_subscription": 300,  # 5 minutes
}


# Optional: Task soft time limits (warning before hard limit)
CELERY_TASK_SOFT_TIME_LIMITS = {
    "payments_tr.iyzico.process_due_subscriptions": 3000,  # 50 minutes
    "payments_tr.iyzico.retry_failed_payments": 3000,  # 50 minutes
    "payments_tr.iyzico.charge_subscription": 240,  # 4 minutes
}
