import json
from app.agents.llm_agent import LLMAgent
from app.database import SessionLocal
from sqlalchemy.orm import Session
from app.models import Request, Status, TaskType, Epic, Feature, UserStory, Task, Bug, Issue, PBI, TestCase, Gherkin, Action, WBS
from app.utils import parsers, rabbitmq
import logging
from datetime import datetime
from app.celery import celery_app
import pika
import openai
import google.api_core.exceptions
import requests

logger = logging.getLogger(__name__)
llm_agent = LLMAgent()


@celery_app.task(
    name="process_demand_task",
    autoretry_for=(
        openai.APITimeoutError,
        openai.APIConnectionError,
        openai.RateLimitError,
        google.api_core.exceptions.ServiceUnavailable,
        google.api_core.exceptions.ResourceExhausted,
        requests.exceptions.RequestException,
    ),
    retry_kwargs={
        "max_retries": 5,
        "retry_backoff": True,
        "retry_backoff_max": 60,
        "retry_jitter": True
    }
)
def process_message_task(request_id_interno, task_type, prompt_data, llm_config=None):
    db = SessionLocal()
    producer = rabbitmq.RabbitMQProducer()  # Instancia o producer
    try:
        logger.info(f"Task Celery 'process_demand_task' iniciada para request_id: {request_id_interno}, task_type: {task_type}")

        # Validando task_type usando o Enum
        try:
            task_type_enum = TaskType(task_type)
        except ValueError:
            error_message = f"Task type inválido recebido: {task_type}"
            logger.error(error_message)
            update_request_status(db, request_id_interno, Status.FAILED, error_message)
            return

        # Buscando a requisição no banco para obter o parent
        db_request = db.query(Request).filter(Request.request_id == request_id_interno).first()
        if not db_request:
            error_message = f"Requisição com request_id {request_id_interno} não encontrada no banco de dados."
            logger.error(error_message)
            return

        parent_str = db_request.parent  #  parent como STRING
        try:
            parent = int(parent_str)  # CONVERTER para INT
        except ValueError:
            error_message = f"parent inválido (não é um inteiro): {parent_str}"
            logger.error(error_message)
            update_request_status(db, request_id_interno, Status.FAILED, error_message)
            return

        # Gerando texto com LLM Agent
        logger.info(f"Chamando LLMAgent para gerar texto para request_id: {request_id_interno}, task_type: {task_type}")

        # Injetar user_input no prompt user
        prompt_data_dict = prompt_data.copy()
        if 'user_input' in prompt_data_dict:
            prompt_data_dict['user'] = prompt_data_dict['user'].replace("{user_input}", prompt_data_dict['user_input'])
            del prompt_data_dict['user_input']

        # Usar as configurações da LLM recebidas, se fornecidas, ou usar padrões do LLMAgent
        if llm_config:
            llm_agent.chosen_llm = llm_config.get("llm", llm_agent.chosen_llm)
            if llm_config.get("llm") == "openai":
                llm_agent.openai_model = llm_config.get("model", llm_agent.openai_model)
            elif llm_config.get("llm") == "gemini":
                llm_agent.gemini_model = llm_config.get("model", llm_agent.gemini_model)
            llm_agent.temperature = llm_config.get("temperature", llm_agent.temperature)
            llm_agent.max_tokens = llm_config.get("max_tokens", llm_agent.max_tokens)
            llm_agent.top_p = llm_config.get("top_p", llm_agent.top_p)

        llm_response = llm_agent.generate_text(prompt_data_dict)
        generated_text = llm_response["text"]
        prompt_tokens = llm_response["prompt_tokens"]
        completion_tokens = llm_response["completion_tokens"]

        logger.debug(f"Texto gerado pela LLM para request_id {request_id_interno}: {generated_text}")

        # --- LÓGICA DE VERSIONAMENTO E ATIVAÇÃO/DESATIVAÇÃO ---
        try:
            logger.info(f"Parsing e salvando resposta para request_id: {request_id_interno}, task_type: {task_type_enum.value}")

            # 1. Obter itens existentes do mesmo tipo e com o mesmo parent/epic_id/feature_id/etc.
            if task_type_enum == TaskType.EPIC:
                existing_items = db.query(Epic).filter(Epic.team_project_id == parent, Epic.is_active == True).all()  # Filtrar por team_project_id e is_active
            elif task_type_enum == TaskType.FEATURE:
                existing_items = db.query(Feature).filter(Feature.parent == parent, Feature.is_active == True).all()  # Usar parent
            elif task_type_enum == TaskType.USER_STORY:
                existing_items = db.query(UserStory).filter(UserStory.parent == parent, UserStory.is_active == True).all()  # Usar parent
            elif task_type_enum == TaskType.TASK:
                existing_items = db.query(Task).filter(Task.parent == parent, Task.is_active == True).all()  # Usar parent
            elif task_type_enum == TaskType.BUG:
                existing_items = db.query(Bug).filter(Bug.issue_id == parent, Bug.is_active == True).all()  # Ajuste conforme necessário
            elif task_type_enum == TaskType.ISSUE:
                existing_items = db.query(Issue).filter(Issue.user_story_id == parent, Issue.is_active == True).all()  # Ajuste conforme necessário
            elif task_type_enum == TaskType.PBI:
                existing_items = db.query(PBI).filter(PBI.feature_id == parent, PBI.is_active == True).all()
            elif task_type_enum == TaskType.TEST_CASE:
                existing_items = db.query(TestCase).filter(TestCase.parent == parent, TestCase.is_active == True).all()
            elif task_type_enum == TaskType.WBS:
                existing_items = db.query(WBS).filter(WBS.parent == parent, WBS.is_active == True).all()
            else:
                error_message = f"Task type desconhecido: {task_type_enum.value}"
                logger.error(error_message)
                update_request_status(db, request_id_interno, Status.FAILED, error_message)
                return

            # 2. Desativar itens existentes
            for item in existing_items:
                item.is_active = False
                item.updated_at = datetime.now()

            # 3. Determinar a nova versão
            if existing_items:
                max_version = max(item.version for item in existing_items)
                new_version = max_version + 1
            else:
                new_version = 1

            # 4. Criar e adicionar os novos itens
            if task_type_enum == TaskType.EPIC:
                new_epic = parsers.parse_epic_response(generated_text, prompt_tokens, completion_tokens)
                new_epic.team_project_id = str(db_request.parent)  # Salva o team_project_id
                new_epic.version = new_version
                new_epic.is_active = True
                db.add(new_epic)
                db.flush()  # Força o INSERT e a obtenção do ID autoincremental
                db.refresh(new_epic) # Atualiza o objeto new_epic com os dados do banco (incluindo o ID)
                item_id = [new_epic.id]    # <---  AGORA o ID está disponível!
            elif task_type_enum == TaskType.FEATURE:
                new_features = parsers.parse_feature_response(generated_text, parent, prompt_tokens, completion_tokens)
                for feature in new_features:
                    feature.version = new_version
                    feature.is_active = True
                db.add_all(new_features)
                db.flush()  # Força o INSERT
                item_id = [f.id for f in new_features]  # IDs agora disponíveis
            elif task_type_enum == TaskType.USER_STORY:
                new_user_stories = parsers.parse_user_story_response(generated_text, parent, prompt_tokens, completion_tokens)
                for us in new_user_stories:
                    us.version = new_version
                    us.is_active = True
                db.add_all(new_user_stories)
                db.flush()  # Força o INSERT
                item_id = [us.id for us in new_user_stories]  # IDs agora disponíveis
            elif task_type_enum == TaskType.TASK:
                new_tasks = parsers.parse_task_response(generated_text, parent, prompt_tokens, completion_tokens)
                for task in new_tasks:
                    task.version = new_version
                    task.is_active = True
                db.add_all(new_tasks)
                db.flush()  # Força o INSERT
                item_id = [t.id for t in new_tasks]  # IDs agora disponíveis
            elif task_type_enum == TaskType.BUG:
                new_bugs = parsers.parse_bug_response(generated_text, parent, parent, prompt_tokens, completion_tokens)  # Corrigido: request_id_client para issue_id e user_story_id
                for bug in new_bugs:
                    bug.version = new_version
                    bug.is_active = True
                db.add_all(new_bugs)
                db.flush()  # Força o INSERT
                item_id = [b.id for b in new_bugs] # Lista de IDs
            elif task_type_enum == TaskType.ISSUE:
                new_issues = parsers.parse_issue_response(generated_text, parent, prompt_tokens, completion_tokens)
                for issue in new_issues:
                    issue.version = new_version
                    issue.is_active = True
                db.add_all(new_issues)
                db.flush()  # Força o INSERT
                item_id = [i.id for i in new_issues]   # Lista de IDs
            elif task_type_enum == TaskType.PBI:
                new_pbis = parsers.parse_pbi_response(generated_text, parent, prompt_tokens, completion_tokens)
                for pbi in new_pbis:
                    pbi.version = new_version
                    pbi.is_active = True
                db.add_all(new_pbis)
                db.flush()  # Força o INSERT
                item_id = [p.id for p in new_pbis]  # Lista de IDs

            elif task_type_enum == TaskType.TEST_CASE:
                new_test_cases = parsers.parse_test_case_response(generated_text, parent, prompt_tokens, completion_tokens)
                for test_case in new_test_cases:
                    test_case.version = new_version
                    test_case.is_active = True
                    # Definir version e is_active para Gherkin e Actions
                    if test_case.gherkin:
                        test_case.gherkin.version = new_version
                        test_case.gherkin.is_active = True
                    for action in test_case.actions:
                        action.version = new_version
                        action.is_active = True
                db.add_all(new_test_cases)  # Salva TestCase, Gherkin e Actions em cascata
                db.flush()
                item_id = [tc.id for tc in new_test_cases]  # Lista de IDs dos test cases
            elif task_type_enum == TaskType.WBS:
                new_wbs = parsers.parse_wbs_response(generated_text, parent, prompt_tokens, completion_tokens)
                new_wbs.version = new_version  # Define a versão
                new_wbs.is_active = True  # Define como ativo
                db.add(new_wbs)  # Adiciona o novo WBS ao banco
                db.flush()
                db.refresh(new_wbs)  # Atualiza o objeto para obter o ID gerado
                item_id = [new_wbs.id]   # Cria uma lista com o ID do novo WBS

            db.commit()
            logger.info(f"Resposta processada e salva no banco de dados para request_id: {request_id_interno}, task_type: {task_type_enum.value}")
            update_request_status(db, request_id_interno, Status.COMPLETED)

            # --- Publicar mensagem de notificação no RabbitMQ ---
            # Adapta para lista, se necessário.
            if not isinstance(item_id, list):
                item_id = [item_id]
            notification_message = {
                "request_id": request_id_interno,  # ID interno da API Python
                "parent": db_request.parent,  # ID original do backend .NET (agora 'parent')
                "task_type": task_type_enum.value,
                "status": "completed",  # Sempre "completed" aqui, erros já foram tratados
                "error_message": None,  # Sem erros aqui
                "item_ids": item_id,  # IDs dos itens criados/atualizados (lista)
                "version": new_version  # Versão do item
            }
            producer.publish(notification_message, rabbitmq.NOTIFICATION_QUEUE)
            logger.info(f"Mensagem de notificação publicada para request_id: {request_id_interno}")

        except Exception as e_parse:  # Capturar exceções de parsing/banco de dados
            error_message = f"Erro ao fazer parsing ou salvar resposta para request_id {request_id_interno}: {e_parse}"
            logger.error(error_message, exc_info=True)
            db.rollback()
            update_request_status(db, request_id_interno, Status.FAILED, error_message)
            # --- Publicar mensagem de notificação de ERRO no RabbitMQ ---
            notification_message = {
                "request_id": request_id_interno,
                "parent": db_request.parent,  # Usar parent
                "task_type": task_type_enum.value,
                "status": "failed",  # Status de erro
                "error_message": error_message,  # Mensagem de erro detalhada
                "item_ids": None,  # Não há item_id em caso de erro
                "version": None  # Não há versão em caso de erro
            }
            producer.publish(notification_message, rabbitmq.NOTIFICATION_QUEUE) #mesmo em caso de erro, vamos notificar
            logger.info(f"Mensagem de notificação de ERRO publicada para request_id: {request_id_interno}")
            return

        except pika.exceptions.AMQPConnectionError as e_conn:
            error_message = f"Erro de conexão com o RabbitMQ: {e_conn}"
            logger.error(error_message, exc_info=True)
            return
        except pika.exceptions.AMQPChannelError as e_channel:
            error_message = f"Erro no canal RabbitMQ: {e_channel}"
            logger.error(error_message, exc_info=True)
            if request_id_interno:
                update_request_status(db, request_id_interno, Status.FAILED, error_message)
            return
        except pika.exceptions.NackError as e_nack:
            error_message = f"Erro ao publicar mensagem no RabbitMQ (NACK): {e_nack}"
            logger.error(error_message, exc_info=True)
            if request_id_interno:
                update_request_status(db, request_id_interno, Status.FAILED, error_message)
            return
        except json.JSONDecodeError as e_json:
            error_message = f"Erro ao decodificar JSON da mensagem do RabbitMQ: {e_json}"
            logger.error(error_message, exc_info=True)
            if request_id_interno:
                update_request_status(db, request_id_interno, Status.FAILED, error_message)
            return
        except Exception as e_generic:
            error_message = f"Erro genérico ao processar task Celery: {e_generic}"
            logger.error(error_message, exc_info=True)
            if request_id_interno:
                update_request_status(db, request_id_interno, Status.FAILED, error_message)
            raise

    finally:
        db.close()
        producer.close() # Garante que a conexão do producer seja fechada
        logger.debug("Sessão do banco de dados fechada.")


def update_request_status(db: Session, request_id: str, status: Status, error_message: str = None):
    """Função auxiliar para atualizar o status da requisição no banco de dados."""
    try:
        db_request = db.query(Request).filter(Request.request_id == request_id).first()
        if db_request:
            db_request.status = status.value
            if status == Status.COMPLETED:
                db_request.processed_at = datetime.now(tz=db_request.created_at.tzinfo)
            elif status == Status.FAILED and error_message:
                db_request.error_message = error_message
            db_request.updated_at = datetime.now()
            db.commit()
            logger.info(f"Status da requisição {request_id} atualizado para {status.value}.")
        else:
            logger.warning(f"Requisição {request_id} não encontrada para atualizar status.")
    except Exception as e:
        logger.error(f"Erro ao atualizar status da requisição {request_id} para {status.value}: {e}", exc_info=True)
        db.rollback()
