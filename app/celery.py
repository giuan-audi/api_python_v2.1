from celery import Celery
import os

celery_app = Celery(
    'tasks',  # Nome do app Celery (pode ser qualquer nome)
    broker=os.environ.get('CELERY_BROKER_URL', 'pyamqp://guest:guest@rabbitmq:5672//'),
    backend=os.environ.get('CELERY_RESULT_BACKEND', 'db+postgresql://postgres:adm1234@host.docker.internal:5432/postgres'),
    include=['app.workers.consumer']
)

# Configuracoes opcionais (exemplo)
celery_app.conf.task_serializer = 'json'
celery_app.conf.result_serializer = 'json'
celery_app.conf.accept_content = ['json']
celery_app.conf.timezone = 'UTC'
celery_app.conf.enable_utc = True
