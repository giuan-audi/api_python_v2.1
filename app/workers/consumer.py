from celery import Celery
import os
from app.workers.processors.creation import WorkItemCreator
from app.workers.processors.reprocessing import WorkItemReprocessor
from typing import Optional

celery_app = Celery(
    'tasks',
    broker=os.environ.get('CELERY_BROKER_URL', 'pyamqp://guest:guest@rabbitmq:5672//'),
    backend=os.environ.get('CELERY_RESULT_BACKEND', 'db+postgresql://postgres:adm1234@host.docker.internal:5432/postgres'),
    include=['app.workers.consumer']
)

celery_app.conf.task_serializer = 'json'
celery_app.conf.result_serializer = 'json'
celery_app.conf.accept_content = ['json']
celery_app.conf.timezone = 'UTC'
celery_app.conf.enable_utc = True

# --- Tarefa de Criação (Atualizada) ---
@celery_app.task(name="process_demand_task")
def process_message_task(
    request_id_interno, 
    task_type, 
    prompt_data, 
    llm_config=None, 
    work_item_id=None, 
    parent_board_id=None, 
    type_test=None  # Adicionado como opcional
):
    creator = WorkItemCreator()
    creator.process(
        request_id_interno, 
        task_type, 
        prompt_data, 
        llm_config, 
        work_item_id, 
        parent_board_id, 
        type_test  # Passa type_test para o processador
    )

# --- Tarefa de Reprocessamento (Atualizada) ---
@celery_app.task(name="reprocess_work_item_task")
def reprocess_work_item_task(
    request_id_interno: str,
    artifact_type: str,
    artifact_id: int,
    prompt_data: dict,
    llm_config: Optional[dict] = None,
    work_item_id: Optional[int] = None,
    parent_board_id: Optional[int] = None,
    type_test: Optional[str] = None  # Adicionado como opcional
):
    reprocessor = WorkItemReprocessor()
    reprocessor.process(
        request_id_interno,
        artifact_type,
        prompt_data,
        llm_config,
        work_item_id,
        parent_board_id,
        type_test,  # Passa type_test para o processador
        artifact_id
    )
