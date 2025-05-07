from celery import Celery
import logging
import os
from typing import Optional, Dict, Any
from uuid import UUID
from datetime import datetime
from sqlalchemy.orm import Session 
from app.workers.processors.creation import WorkItemCreator
from app.workers.processors.reprocessing import WorkItemReprocessor
from app.database import SessionLocal
from app.models import Request, Status, TaskType
from app.utils.rabbitmq import RabbitMQProducer, NOTIFICATION_QUEUE
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)

broker_url = os.environ.get('CELERY_BROKER_URL')
backend_url = os.environ.get('CELERY_RESULT_BACKEND')

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
celery_app.conf.task_acks_late = True # Para garantir que a task só seja removida da fila após sucesso ou falha explícita
# celery_app.conf.worker_prefetch_multiplier = 1 # Para processar uma task por vez por worker

# --- Função Helper para Handler de Exceção da Task ---
def _handle_task_exception(request_id: str, task_type_str: Optional[str], exception: Exception):
    """
    Tenta atualizar o status da requisição no DB para FAILED e enviar
    uma notificação mínima quando ocorre uma exceção não tratada na task.
    """
    logger.error(f"Erro EXCEPCIONAL não tratado na task para ReqID {request_id}: {exception}", exc_info=True)
    db_task = None
    producer_task = None
    error_message = f"Erro na task Celery: {exception.__class__.__name__}: {str(exception)[:200]}" # Mensagem truncada

    # 1. Tentar atualizar status no DB
    try:
        logger.info(f"Tentando atualizar status para FAILED no DB para ReqID {request_id} via task exception handler.")
        db_task = SessionLocal()
        req = db_task.query(Request).filter(Request.request_id == request_id).first()
        if req:
            if req.status != Status.COMPLETED.value: # Só atualiza se não estiver COMPLETED
                req.status = Status.FAILED.value
                req.error_message = error_message
                req.updated_at = datetime.now()
                db_task.commit()
                logger.info(f"Status atualizado para FAILED no DB para ReqID {request_id}.")
            else:
                 logger.warning(f"ReqID {request_id} já estava COMPLETED. Não atualizando status via task exception handler.")
        else:
            logger.warning(f"Não foi possível encontrar ReqID {request_id} no DB para atualizar status na task exception.")
    except Exception as db_exc:
        logger.error(f"Erro ao tentar atualizar status no DB via task exception handler para ReqID {request_id}: {db_exc}", exc_info=True)
        if db_task: db_task.rollback()
    finally:
        if db_task: db_task.close()

    # 2. Tentar enviar notificação mínima de falha
    try:
        logger.info(f"Tentando enviar notificação de falha mínima para ReqID {request_id} via task exception handler.")
        producer_task = RabbitMQProducer()
        # Tenta obter o project_id da request se possível (embora possa falhar se a request não foi encontrada)
        project_id_from_req = None
        if 'req' in locals() and req and hasattr(req, 'project_id'):
             project_id_from_req = str(req.project_id) if req.project_id else None

        notification_data = {
            "request_id": request_id, "status": Status.FAILED.value,
            "error_message": error_message,
            "project_id": project_id_from_req, "parent": None, "parent_type": None, "task_type": task_type_str,
            "item_ids": [], "version": None, "work_item_id": None, "parent_board_id": None, "is_reprocessing": False
        }
        producer_task.publish(notification_data, NOTIFICATION_QUEUE)
        logger.info(f"Notificação de falha mínima enviada para ReqID {request_id}.")
    except Exception as mq_exc:
            logger.error(f"Erro ao tentar enviar notificação via task exception handler para ReqID {request_id}: {mq_exc}", exc_info=True)
    finally:
        if producer_task: producer_task.close()


@celery_app.task(name="process_demand_task", bind=True) # bind=True para acessar self se precisar de retries do Celery
def process_message_task(
    self, # Adicionado self por causa do bind=True
    request_id_interno: str,
    task_type: str,
    prompt_data: Dict[str, Any],
    parent_type: str,
    language: Optional[str] = "português",
    llm_config: Optional[Dict[str, Any]] = None,
    work_item_id: Optional[str] = None,
    parent_board_id: Optional[str] = None,
    type_test: Optional[str] = None
):
    creator = None
    try:
        logger.info(f"[Task process_demand_task] Iniciando para ReqID {request_id_interno}")
        creator = WorkItemCreator()
        # Passa parent_type_str para o processador
        creator.process(
            request_id_interno=request_id_interno,
            task_type=task_type,
            prompt_data=prompt_data,
            parent_type_str=parent_type,
            language=language,
            llm_config=llm_config,
            work_item_id=work_item_id,
            parent_board_id=parent_board_id,
            type_test=type_test,
            project_id_str=None, # Rota original não passa project_id
            artifact_id=None
        )
        logger.info(f"[Task process_demand_task] Concluída (lógica interna define status) para ReqID {request_id_interno}")
    except Exception as task_exc:
        # Usa a função helper para tratar a exceção
        _handle_task_exception(request_id_interno, task_type, task_exc)
        # Re-lançar se quiser que Celery marque como falha explicitamente
        # raise


@celery_app.task(name="reprocess_work_item_task", bind=True)
def reprocess_work_item_task(
    self,
    request_id_interno: str,
    artifact_type: str, # task_type no processador
    artifact_id: int,
    prompt_data: Dict[str, Any],
    language: Optional[str] = "português",
    llm_config: Optional[Dict[str, Any]] = None,
    work_item_id: Optional[str] = None,
    parent_board_id: Optional[str] = None,
    type_test: Optional[str] = None
):
    reprocessor = None
    try:
        logger.info(f"[Task reprocess_work_item_task] Iniciando para ReqID {request_id_interno}, Artefato {artifact_type}:{artifact_id}")
        reprocessor = WorkItemReprocessor()
        reprocessor.process(
            request_id_interno=request_id_interno,
            task_type=artifact_type, # Passar artifact_type como task_type
            prompt_data=prompt_data,
            language=language,
            llm_config=llm_config,
            work_item_id=work_item_id,
            parent_board_id=parent_board_id,
            type_test=type_test,
            artifact_id=artifact_id,
            project_id_str=None,
            parent_type_str=None
        )
        logger.info(f"[Task reprocess_work_item_task] Concluída (lógica interna define status) para ReqID {request_id_interno}")
    except Exception as task_exc:
        _handle_task_exception(request_id_interno, artifact_type, task_exc)
        # raise


@celery_app.task(name="process_independent_creation_task", bind=True)
def process_independent_creation_task(
    self,
    request_id_interno: str,
    project_id: str, # Recebe como string
    parent: Optional[int], # Recebe o parent_id opcional (será usado pelo process para buscar no DBRequest)
    task_type: str,
    prompt_data: Dict[str, Any],
    parent_type: Optional[str] = None, # <-- ADICIONADO para receber parent_type (string ou None)
    language: Optional[str] = "português",
    llm_config: Optional[Dict[str, Any]] = None,
    work_item_id: Optional[str] = None,
    parent_board_id: Optional[str] = None,
    type_test: Optional[str] = None
):
    creator = None
    try:
        logger.info(f"[Task process_independent_creation_task] Iniciando para ReqID {request_id_interno}")
        creator = WorkItemCreator()
        # Passa project_id_str e parent_type_str para o processador
        # O 'parent' opcional desta task NÃO é passado diretamente para process,
        # pois process o obterá do DBRequest.
        creator.process(
            request_id_interno=request_id_interno,
            project_id_str=project_id, # Passa a string
            task_type=task_type,
            prompt_data=prompt_data,
            parent_type_str=parent_type, # <-- PASSANDO parent_type
            language=language,
            llm_config=llm_config,
            work_item_id=work_item_id,
            parent_board_id=parent_board_id,
            type_test=type_test,
            artifact_id=None # Não é reprocessamento
        )
        logger.info(f"[Task process_independent_creation_task] Concluída (lógica interna define status) para ReqID {request_id_interno}")
    except Exception as task_exc:
        _handle_task_exception(request_id_interno, task_type, task_exc)
        # raise
