from fastapi import APIRouter, HTTPException, Depends, status
from app.schemas.schemas import Request as RequestSchema, Response, IndependentCreationRequest, StatusResponse, LLMConfig, ReprocessRequest
from app.database import get_db
from sqlalchemy.orm import Session
from app.models import Request as DBRequest, TaskType, Status, Epic, Feature, UserStory, Task, TestCase, WBS, Bug, Issue, PBI
import uuid
from app.workers.consumer import process_message_task, reprocess_work_item_task, process_independent_creation_task
from pydantic import ValidationError
from sqlalchemy.exc import IntegrityError
import logging

router = APIRouter()
logger = logging.getLogger(__name__)

MODEL_MAP = {
    TaskType.EPIC: Epic,
    TaskType.FEATURE: Feature,
    TaskType.USER_STORY: UserStory,
    TaskType.TASK: Task,
    TaskType.TEST_CASE: TestCase,
    TaskType.WBS: WBS,
    TaskType.BUG: Bug,
    TaskType.ISSUE: Issue,
    TaskType.PBI: PBI
}


@router.post("/generate/", response_model=Response, status_code=status.HTTP_201_CREATED)
async def generate(request: RequestSchema, db: Session = Depends(get_db)):
    logger.info(f"Requisição POST /generate/ recebida. Task Type: {request.task_type}, Parent ID: {request.parent}") # Log correto
    try:
        db_request = DBRequest(
            request_id=str(uuid.uuid4()),
            parent=str(request.parent),
            parent_type=request.parent_type.value,
            task_type=request.task_type.value,
            status=Status.PENDING.value,
            project_id=None,
            artifact_type=None,
            artifact_id=None
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
            "parent_type": request.parent_type.value,
            "language": request.language,
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
    logger.info(f"Requisição POST /reprocess/{artifact_type}/{artifact_id} recebida.")

    try:
        task_type_enum = TaskType(artifact_type)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Tipo de artefato inválido: {artifact_type}"
        )

    # Buscar o artefato existente
    model = MODEL_MAP.get(task_type_enum)
    if not model:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Tipo de artefato não suportado: {artifact_type}"
        )

    existing_artifact = db.query(model).filter(model.id == artifact_id).first()
    if not existing_artifact:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Artefato {artifact_type} com ID {artifact_id} não encontrado"
        )

    # Determinar o parent_id com base no tipo de artefato
    if task_type_enum == TaskType.EPIC:
        parent_id = existing_artifact.team_project_id
    elif task_type_enum in [TaskType.FEATURE, TaskType.USER_STORY, TaskType.TASK, TaskType.TEST_CASE, TaskType.WBS]:
        parent_id = existing_artifact.parent
    elif task_type_enum == TaskType.BUG:
        parent_id = existing_artifact.user_story_id
    elif task_type_enum == TaskType.ISSUE:
        parent_id = existing_artifact.user_story_id
    elif task_type_enum == TaskType.PBI:
        parent_id = existing_artifact.feature_id
    else:
        parent_id = None

    # Criar a requisição de reprocessamento
    request_id = str(uuid.uuid4())
    try:
        db_request = DBRequest(
            request_id=request_id,
            task_type=task_type_enum.value,
            status=Status.PENDING.value,
            parent=str(parent_id) if parent_id is not None else None,  # Corrigido
            artifact_type=artifact_type,
            artifact_id=artifact_id
        )
        db.add(db_request)
        db.commit()
        db.refresh(db_request)
    except Exception as e:
        db.rollback()
        logger.error(f"Erro ao salvar requisição de reprocessamento: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Erro ao salvar requisição no banco de dados."
        )

    # Preparar argumentos para a task Celery
    task_args = {
        "request_id_interno": request_id,
        "artifact_type": artifact_type,
        "artifact_id": artifact_id,
        "prompt_data": request.prompt_data.model_dump(),
        "llm_config": request.llm_config.model_dump() if request.llm_config else None,
        "language": request.language,
        "work_item_id": request.work_item_id,
        "parent_board_id": request.parent_board_id,
        "type_test": request.type_test
    }

    try:
        reprocess_work_item_task.delay(**task_args)
    except TypeError as e:
        logger.error(f"Erro ao enfileirar task Celery: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Erro ao enfileirar task Celery: {str(e)}"
        )

    return Response(
        request_id=request_id,
        response={"status": "queued"}
    )

# --- ROTA PARA CRIAÇÃO DE ARTEFATOS INDEPENDENTE ---
@router.post("/independent/", response_model=Response, status_code=status.HTTP_201_CREATED)
async def create_independent(request: IndependentCreationRequest, db: Session = Depends(get_db)):
    """
    Cria um artefato de forma mais independente, exigindo project_id
    e permitindo um parent opcional.
    """
    logger.info(f"Requisição POST /independent/ recebida. Task Type: {request.task_type}, Project ID: {request.project_id}, Parent ID: {request.parent}")

    # Gerar ID único para a requisição interna
    request_id_interno = str(uuid.uuid4())

    try:
        # Criar registro da requisição no banco de dados
        db_request = DBRequest(
            request_id=request_id_interno,
            project_id=request.project_id,
            parent=str(request.parent) if request.parent is not None else None,
            parent_type=request.parent_type.value if request.parent_type else None,
            task_type=request.task_type.value,
            status=Status.PENDING.value,
            artifact_type=None,
            artifact_id=None
        )
        db.add(db_request)
        db.commit()
        db.refresh(db_request)
        logger.info(f"Registro DBRequest criado para /independent/ com request_id: {request_id_interno}")

    except IntegrityError as e:
        logger.error(f"Erro de integridade ao salvar requisição /independent/ no banco: {e}")
        db.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=f"Erro de integridade: {e}")
    except Exception as e:
        logger.error(f"Erro inesperado ao salvar requisição /independent/ no banco: {e}", exc_info=True)
        db.rollback()
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Erro interno ao salvar requisição: {str(e)}")

    # Preparar os argumentos para a nova task Celery
    # Usar configurações da LLM da requisição, se fornecidas, ou usar padrões (embora LLMConfig() não seja o ideal aqui, mantendo a lógica)
    llm_config = request.llm_config or LLMConfig() # Ou apenas passar o dicionário se ele existir

    task_args = {
        "request_id_interno": request_id_interno,
        "project_id": str(request.project_id), # Passar project_id como string para Celery/JSON
        "parent": request.parent, # Passar parent (int ou None)
        "parent_type": request.parent_type.value if request.parent_type else None,
        "task_type": request.task_type.value,
        "prompt_data": request.prompt_data.model_dump(),
        "llm_config": llm_config.model_dump() if request.llm_config else None,
        "language": request.language,
        "work_item_id": request.work_item_id,
        "parent_board_id": request.parent_board_id,
        "type_test": request.type_test
    }

    # Enviar a nova task para o Celery
    try:
        # Chamar a NOVA task Celery
        process_independent_creation_task.delay(**task_args)
        logger.info(f"Task Celery 'process_independent_creation_task' enfileirada para request_id: {request_id_interno}.")
    except Exception as e: # Capturar exceção mais genérica ao enfileirar
        logger.error(f"Erro ao enfileirar task Celery 'process_independent_creation_task': {e}", exc_info=True)
        # Considerar reverter o DBRequest ou marcar como falha se o enfileiramento falhar?
        # Por ora, apenas logamos e retornamos erro 500.
        # TODO: Avaliar estratégia de compensação se o enfileiramento falhar após salvar no DB.
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Erro ao enfileirar tarefa de processamento: {str(e)}"
        )

    # Retornar resposta de sucesso para o cliente
    return Response(
        request_id=request_id_interno,
        response={"status": "queued"}
    )
