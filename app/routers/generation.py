from fastapi import APIRouter, HTTPException, Depends, status
from app.schemas.schemas import Request as RequestSchema, Response, StatusResponse, LLMConfig, ReprocessRequest
from app.database import get_db
from sqlalchemy.orm import Session
from app.models import Request as DBRequest, TaskType, Status
import uuid
from app.workers.consumer import process_message_task, reprocess_work_item_task
from pydantic import ValidationError
from sqlalchemy.exc import IntegrityError
import logging

router = APIRouter()
logger = logging.getLogger(__name__)


@router.post("/generate/", response_model=Response, status_code=status.HTTP_201_CREATED)
async def generate(request: RequestSchema, db: Session = Depends(get_db)):
    logger.info(f"Requisição POST /generate/ recebida. Task Type: {request.task_type}, Parent ID: {request.parent}") # Log correto
    try:
        db_request = DBRequest(
            request_id=str(uuid.uuid4()),
            parent=str(request.parent),  # Usar o 'parent' (agora como string)
            task_type=request.task_type.value,
            status=Status.PENDING.value
        )
        db.add(db_request)
        db.commit()
        db.refresh(db_request)  # Importante para obter o ID gerado

        # Usar configurações da LLM da requisição, se fornecidas, ou usar padrões
        llm_config = request.llm_config or LLMConfig()

        # Preparar os argumentos para a task Celery
        task_args = {
            "request_id_interno": db_request.request_id,  # Passar o ID interno da requisição
            "task_type": request.task_type.value,  # Passar o task_type como string (valor do enum)
            "prompt_data": request.prompt_data.model_dump(),  # Passar os dados do prompt
            "llm_config": llm_config.model_dump(),  # Passar as configurações da LLM (opcional)
            "work_item_id": request.work_item_id,  # <-- Passando para a task
            "parent_board_id": request.parent_board_id,
            "type_test": request.type_test
        }

        # Enviar a task para o Celery
        process_message_task.delay(**task_args)  # Usar ** para desempacotar o dicionário

        logger.info(f"Task Celery 'process_demand_task' enfileirada para request_id: {db_request.request_id}.")

        return Response(
            request_id=db_request.request_id,  # Retornar o ID interno da requisição
            response={"status": "queued"}
        )

    except ValidationError as e:
        logger.error(f"Erro de validação na requisição POST /generate/: {e}")
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Erro de validação: {e}")  # Retornar 400 Bad Request

    except IntegrityError as e:
        logger.error(f"Erro de integridade ao salvar requisição no banco: {e}")
        db.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=f"Erro de integridade: {e}")  # Retornar 409 Conflict

    except Exception as e:
        logger.error(f"Erro ao processar requisição POST /generate/: {e}", exc_info=True)
        db.rollback()
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Erro interno ao processar requisição: {str(e)}")


@router.get("/status/{request_id}", response_model=StatusResponse)
async def get_status(request_id: str, db: Session = Depends(get_db)):
    logger.info(f"Requisição GET /status/{request_id} recebida.")
    request = db.query(DBRequest).filter(DBRequest.request_id == request_id).first()

    if not request:
        logger.warning(f"Requisição {request_id} não encontrada.")
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Request not found")

    logger.info(f"Status da requisição {request_id} retornado.")
    return StatusResponse(
        request_id=request.request_id,
        parent=request.parent,  # Retornar o parent (que era o request_id_client)
        task_type=request.task_type,
        status=request.status,
        created_at=request.created_at,
        processed_at=request.processed_at
    )


# --- NOVA ROTA PARA REPROCESSAMENTO ---
@router.post("/reprocess/{artifact_type}/{artifact_id}", response_model=Response, status_code=status.HTTP_202_ACCEPTED)
async def reprocess(
    artifact_type: str, 
    artifact_id: int, 
    request: ReprocessRequest, 
    db: Session = Depends(get_db)
):
    """
    Reprocessa um artefato existente, gerando uma nova versão com base no input do usuário.
    """
    logger.info(f"Requisição POST /reprocess/{artifact_type}/{artifact_id} recebida.")

    # --- Validação do Tipo de Artefato ---
    try:
        task_type_enum = TaskType(artifact_type)  # Converte a string para o enum TaskType
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, 
            detail=f"Tipo de artefato inválido: {artifact_type}"
        )

    # --- Criação do ID da Requisição (UUID) ---
    request_id = str(uuid.uuid4())

    # --- Salvar a Requisição no Banco de Dados (com status PENDING) ---
    try:
        db_request = DBRequest(
            request_id=request_id,
            task_type=task_type_enum.value,  # Salva o tipo de tarefa (string)
            status=Status.PENDING.value,
            parent=artifact_id,  # Salva o ID do artefato como 'parent'
            artifact_type=artifact_type,  # Salva o tipo de artefato
            artifact_id=artifact_id  # Salva o ID do artefato
        )
        db.add(db_request)
        db.commit()
        db.refresh(db_request)
    except Exception as e:
        db.rollback()
        logger.error(f"Erro ao salvar requisição de reprocessamento no banco: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, 
            detail="Erro ao salvar requisição no banco de dados."
        )

    # --- Preparar os Argumentos para a Task Celery ---
    task_args = {
        "request_id_interno": db_request.request_id,  # ID interno da requisição
        "artifact_type": artifact_type,  # Tipo de artefato (string)
        "artifact_id": artifact_id,  # ID do artefato
        "prompt_data": request.prompt_data.model_dump(),  # Dados do prompt (incluindo user_input)
        "llm_config": request.llm_config.model_dump() if request.llm_config else None,  # Configurações da LLM (opcional)
        "work_item_id": None,  # Não é necessário no reprocessamento
        "parent_board_id": None,  # Não é necessário no reprocessamento
        "type_test": request.type_test  # Passa o type_test para a task
    }

    # --- Enfileirar a Task Celery ---
    try:
        reprocess_work_item_task.delay(**task_args)  # Usa a nova task Celery
    except TypeError as e:
        logger.error(f"Erro ao enfileirar task Celery: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, 
            detail=f"Erro ao enfileirar task Celery: {str(e)}"
        )

    logger.info(f"Task Celery 'reprocess_work_item_task' enfileirada para request_id: {request_id}.")

    # --- Retornar Resposta (202 Accepted) ---
    return Response(
        request_id=request_id,  # Retorna o ID da requisição
        response={"status": "queued"}  # Indica que a requisição foi enfileirada
    )
