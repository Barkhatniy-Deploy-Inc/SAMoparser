from __future__ import annotations

import os

from celery import Celery

from celery import Celery

celery_app = Celery("samoparser")
celery_app.conf.broker_url = os.getenv("REDIS_URL", "redis://localhost:6379/0")
celery_app.conf.result_backend = os.getenv("REDIS_URL", "redis://localhost:6379/0")
