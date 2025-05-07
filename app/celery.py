from celery import Celery
import logging
import os
from dotenv import load_dotenv

load_dotenv()
logger = logging.getLogger(__name__)

broker_url = os.environ.get('CELERY_BROKER_URL')
backend_url = os.environ.get('CELERY_RESULT_BACKEND')

logger.info(f"IN APP/CELERY.PY - CELERY_BROKER_URL from env: '{broker_url}'")
logger.info(f"IN APP/CELERY.PY - CELERY_RESULT_BACKEND from env: '{backend_url}'")

if not broker_url:
    logger.critical("Variável de ambiente CELERY_BROKER_URL não definida!")
    raise ValueError("Variável de ambiente CELERY_BROKER_URL não definida!")
if not backend_url:
    logger.critical("Variável de ambiente CELERY_RESULT_BACKEND não definida!")
    raise ValueError("Variável de ambiente CELERY_RESULT_BACKEND não definida!")


celery_app = Celery(
    'tasks',
    broker=broker_url,
    backend=backend_url,
    include=['app.workers.consumer']
)

celery_app.conf.task_serializer = 'json'
celery_app.conf.result_serializer = 'json'
celery_app.conf.accept_content = ['json']
celery_app.conf.timezone = 'UTC'
celery_app.conf.enable_utc = True
