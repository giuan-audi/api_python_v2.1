from fastapi import APIRouter, HTTPException, Depends, status
from app.schemas.schemas import Request as RequestSchema, Response, StatusResponse, LLMConfig
from app.database import get_db
from sqlalchemy.orm import Session
from app.models import Request as DBRequest, TaskType, Status
import uuid
from app.workers.consumer import process_message_task
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
