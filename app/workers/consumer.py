from celery import Celery
import os
from app.workers.processors.creation import WorkItemCreator
from app.workers.processors.reprocessing import WorkItemReprocessor
from typing import Optional, Dict, Any
from uuid import UUID

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

# --- Tarefa de Criação ---
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

# --- Tarefa de Reprocessamento ---
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

# --- TAREFA DE CRIAÇÃO INDEPENDENTE (via /independent/) ---
@celery_app.task(name="process_independent_creation_task")
def process_independent_creation_task(
    request_id_interno: str,
    project_id: str, # <-- Recebe e PASSA como string
    parent: Optional[int],
    task_type: str,
    prompt_data: Dict[str, Any],
    llm_config: Optional[Dict[str, Any]] = None,
    work_item_id: Optional[str] = None,
    parent_board_id: Optional[str] = None,
    type_test: Optional[str] = None
):
    """
    Task Celery para processar a criação de artefatos iniciada pela
    rota /independent/, que inclui um project_id obrigatório e um parent opcional.
    """
    # Instanciar o processador de criação
    creator = WorkItemCreator()

    # Chamar o método process do WorkItemCreator, passando todos os parâmetros.
    # A validação do project_id (string para UUID) será feita DENTRO do método process.
    creator.process(
        request_id_interno=request_id_interno,
        project_id_str=project_id, # Passa o project_id como string
        task_type=task_type,
        prompt_data=prompt_data,
        llm_config=llm_config,
        work_item_id=work_item_id,
        parent_board_id=parent_board_id,
        type_test=type_test,
        artifact_id=None # Não é reprocessamento
    )
