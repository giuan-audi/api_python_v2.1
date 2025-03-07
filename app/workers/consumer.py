import json
from app.agents.llm_agent import LLMAgent, InvalidModelError
from app.database import SessionLocal
from sqlalchemy.orm import Session
from app.models import Request, Status, TaskType, Epic, Feature, UserStory, Task, Bug, Issue, PBI, TestCase, Action, WBS
from app.utils import parsers, rabbitmq
import logging
from datetime import datetime
from app.celery import celery_app
from sqlalchemy.exc import IntegrityError
import pika
import openai
import google.api_core.exceptions
import requests
from pydantic import ValidationError
from typing import List, Optional

logger = logging.getLogger(__name__)
llm_agent = LLMAgent()


@celery_app.task(
    name="generate_work_item_task",  # Nome mais específico
    retry_kwargs={  # Configurações de retry (controladas pelo Tenacity)
        "max_retries": 5,
        "retry_backoff": True,
        "retry_backoff_max": 60,
        "retry_jitter": True
    },
    time_limit=600  # Timeout global (10 minutos)
)
def process_message_task(request_id_interno: str, task_type: str, prompt_data: dict,
                         llm_config: Optional[dict] = None, work_item_id: Optional[int] = None,
                         parent_board_id: Optional[int] = None, type_test: Optional[str] = None):
    db = SessionLocal()
    producer = rabbitmq.RabbitMQProducer()  # Instancia o producer
    try:
        logger.info(f"Task Celery 'generate_work_item_task' iniciada para request_id: {request_id_interno}, task_type: {task_type}")

        # Validação do task_type usando o Enum
        try:
            task_type_enum = TaskType(task_type)
        except ValueError as e:
            error_message = f"Task type inválido: {task_type}"
            logger.error(error_message)
            update_request_status(db, request_id_interno, Status.FAILED, error_message)
            send_notification(producer, request_id_interno, None, task_type, Status.FAILED, error_message) #parent era None
            return

        # Buscando a requisição no banco para obter o parent
        db_request = db.query(Request).filter(Request.request_id == request_id_interno).first()
        if not db_request:
            error_message = f"Requisição {request_id_interno} não encontrada"
            logger.error(error_message)
            send_notification(producer, request_id_interno, None, task_type, Status.FAILED, error_message) #parent era None
            return

        parent_str = db_request.parent  # parent como string
        try:
            parent = int(parent_str)  # CONVERTER para INT
        except ValueError as e:
            error_message = f"Parent inválido: {db_request.parent}"
            logger.error(error_message)
            update_request_status(db, request_id_interno, Status.FAILED, error_message)
            send_notification(producer, request_id_interno, None, task_type, Status.FAILED, error_message) #parent era None
            return

        # --- LÓGICA PARA TRATAR O SCRIPT DE AUTOMAÇÃO (JÁ EXISTIA, E ESTAVA CORRETA!) ---
        if task_type_enum == TaskType.AUTOMATION_SCRIPT:
            # Buscar o TestCase pelo ID (parent), e NÃO pelo parent da User Story!
            test_case = db.query(TestCase).filter(TestCase.id == parent, TestCase.is_active == True).first()  # CORRIGIDO
            if test_case:
                # Gerando texto com LLM Agent
                logger.info(f"Chamando LLMAgent para gerar texto para request_id: {request_id_interno}, task_type: {task_type}")

                # Injetar user_input no prompt user
                prompt_data_dict = process_prompt_data(prompt_data, type_test)

                # Configurar LLM
                if llm_config:
                    configure_llm_agent(llm_agent, llm_config)

                # Gerar texto
                llm_response = llm_agent.generate_text(prompt_data_dict, llm_config)
                generated_text = llm_response["text"]
                prompt_tokens = llm_response["prompt_tokens"]
                completion_tokens = llm_response["completion_tokens"]

                logger.debug(f"Texto gerado pela LLM para request_id {request_id_interno}: {generated_text}")
                # Somar os tokens aos valores existentes (se existirem)
                total_prompt_tokens = (test_case.prompt_tokens or 0) + prompt_tokens
                total_completion_tokens = (test_case.completion_tokens or 0) + completion_tokens

                test_case.script = generated_text
                test_case.prompt_tokens = total_prompt_tokens  # Atualiza com a soma
                test_case.completion_tokens = total_completion_tokens  # Atualiza com a soma
                db.commit()
                item_id = [test_case.id]
                logger.info(f"Script de automação gerado e salvo para TestCase ID: {parent}")
                update_request_status(db, request_id_interno, Status.COMPLETED)

                # --- Publicar mensagem de notificação no RabbitMQ ---
                notification_message = {
                    "request_id": request_id_interno,
                    "parent": db_request.parent,
                    "task_type": task_type_enum.value,
                    "status": "completed",
                    "error_message": None,
                    "item_ids": item_id,
                    "version": test_case.version,
                    "work_item_id": work_item_id,
                    "parent_board_id": parent_board_id
                }
                producer.publish(notification_message, rabbitmq.NOTIFICATION_QUEUE)
                logger.info(f"Mensagem de notificação publicada para request_id: {request_id_interno}")
                return  # Importante: retornar após o processamento do script

            else:
                error_message = f"Nenhum TestCase ativo encontrado para o ID {parent}."
                logger.error(error_message)
                update_request_status(db, request_id_interno, Status.FAILED, error_message)
                 # --- Publicar mensagem de notificação no RabbitMQ ---
                notification_message = {
                    "request_id": request_id_interno,
                    "parent": db_request.parent,
                    "task_type": task_type_enum.value,
                    "status": "failed",
                    "error_message": error_message,  # Mensagem específica
                    "item_ids": None,
                    "version": None,
                    "work_item_id": work_item_id,
                    "parent_board_id": parent_board_id
                }
                producer.publish(notification_message, rabbitmq.NOTIFICATION_QUEUE)
                logger.info(f"Mensagem de notificação de ERRO publicada para request_id: {request_id_interno}")
                return

        # --- RESTANTE DA LÓGICA (PARA OUTROS TIPOS DE WORK ITEMS) ---

        # Processamento do LLM
        try:  # <---  BLOCO TRY EXTERNO (para capturar exceções de LLM, parsing, etc.)
            logger.info(f"Chamando LLMAgent para request_id: {request_id_interno}")

            # Ajustar prompt_data
            prompt_data_dict = process_prompt_data(prompt_data, type_test)

            # Configurar LLM
            if llm_config:
                configure_llm_agent(llm_agent, llm_config)

            # Gerar texto
            llm_response = llm_agent.generate_text(prompt_data_dict, llm_config)
            generated_text = llm_response["text"]
            prompt_tokens = llm_response["prompt_tokens"]
            completion_tokens = llm_response["completion_tokens"]

            logger.debug(f"Texto gerado pela LLM para request_id {request_id_interno}: {generated_text}")

            # Processar resposta e versionamento
            item_ids, new_version = process_llm_response(
                db, task_type_enum, generated_text, parent,
                prompt_tokens, completion_tokens, work_item_id, parent_board_id
            )

            # Commit final
            db.commit()
            update_request_status(db, request_id_interno, Status.COMPLETED)
            send_notification(
                producer, request_id_interno, db_request.parent,
                task_type_enum.value, Status.COMPLETED, None, item_ids, new_version,
                work_item_id, parent_board_id
            )

        except InvalidModelError as e:  # <---  CAPTURA InvalidModelError
            handle_invalid_model_error(db, producer, request_id_interno, db_request, task_type_enum, e, work_item_id, parent_board_id)
            return  # <---  IMPORTANTE!  Retorna após tratar o erro.

        except (json.JSONDecodeError, KeyError, ValidationError) as e:  # <---  CAPTURA erros de parsing/validação
            handle_parsing_error(db, producer, request_id_interno, db_request, task_type_enum, e, generated_text, work_item_id, parent_board_id)
            return  # <---  IMPORTANTE!  Retorna após tratar o erro.

        except IntegrityError as e:  # <---  CAPTURA erros de integridade do banco
            handle_integrity_error(db, producer, request_id_interno, db_request, task_type_enum, e, work_item_id, parent_board_id)
            return  # <---  IMPORTANTE!  Retorna após tratar o erro.

        except pika.exceptions.AMQPConnectionError as e:  # <---  CAPTURA erros de conexão com o RabbitMQ
            logger.error(f"Erro de conexão com RabbitMQ: {e}", exc_info=True)
            return # Não atualiza status, pois não houve conexão

        except Exception as e:  # <---  CAPTURA qualquer outro erro inesperado
            handle_generic_error(db, producer, request_id_interno, db_request, task_type_enum, e, work_item_id, parent_board_id)
            raise  # Relança para o Celery tratar retentativas (para erros *recuperáveis*)

    finally:
        close_resources(db, producer)
        logger.debug("Recursos liberados")


def process_prompt_data(prompt_data: dict, type_test: Optional[str]) -> dict:
    """Processa e ajusta os dados do prompt"""
    prompt_data_dict = prompt_data.copy()
    
    if 'user_input' in prompt_data_dict:
        prompt_data_dict['user'] = prompt_data_dict['user'].replace(
            "{user_input}", prompt_data_dict['user_input']
        )
        del prompt_data_dict['user_input']
    
    if type_test:
        prompt_data_dict['system'] = prompt_data_dict['system'].replace("{type_test}", type_test)
        prompt_data_dict['user'] = prompt_data_dict['user'].replace("{type_test}", type_test)
    
    return prompt_data_dict


def configure_llm_agent(agent: LLMAgent, config: dict):
    """Configura o LLMAgent com as configurações fornecidas"""
    agent.chosen_llm = config.get("llm", agent.chosen_llm)
    
    if config.get("llm") == "openai":
        agent.openai_model = config.get("model", agent.openai_model)
    elif config.get("llm") == "gemini":
        agent.gemini_model = config.get("model", agent.gemini_model)
    
    agent.temperature = config.get("temperature", agent.temperature)
    agent.max_tokens = config.get("max_tokens", agent.max_tokens)
    agent.top_p = config.get("top_p", agent.top_p)


def process_llm_response(db: Session, task_type: TaskType, generated_text: str, parent: int,
                         prompt_tokens: int, completion_tokens: int, work_item_id: Optional[int],
                         parent_board_id: Optional[int]) -> (List[int], int):
    """Processa a resposta do LLM e gerencia o versionamento"""
    existing_items = get_existing_items(db, task_type, parent)
    new_version = get_new_version(existing_items)
    deactivate_existing_items(db, existing_items, task_type)

    item_ids = create_new_items(
        db, task_type, generated_text, parent,
        prompt_tokens, completion_tokens, new_version, work_item_id, parent_board_id
    )
    if task_type == TaskType.EPIC:
        return item_ids, new_version
    else:
        return item_ids, new_version


def get_existing_items(db: Session, task_type: TaskType, parent: int):
    """Obtém itens existentes ativos"""
    model_map = {
        TaskType.EPIC: (Epic, Epic.team_project_id),
        TaskType.FEATURE: (Feature, Feature.parent),
        TaskType.USER_STORY: (UserStory, UserStory.parent),
        TaskType.TASK: (Task, Task.parent),
        TaskType.BUG: (Bug, Bug.issue_id),
        TaskType.ISSUE: (Issue, Issue.user_story_id),
        TaskType.PBI: (PBI, PBI.feature_id),
        TaskType.TEST_CASE: (TestCase, TestCase.parent),
        TaskType.WBS: (WBS, WBS.parent),
        # TaskType.AUTOMATION_SCRIPT: (None, None),  <-- REMOVER ESTA LINHA!
    }

    model, filter_column = model_map[task_type]
    return db.query(model).filter(filter_column == parent, model.is_active == True).all()



def get_new_version(existing_items: list) -> int:
    """Calcula a nova versão com base nos itens existentes"""
    return max(item.version for item in existing_items) + 1 if existing_items else 1


def deactivate_existing_items(db: Session, items: list, task_type: TaskType):
    """Desativa itens existentes e seus dependentes"""
    for item in items:
        item.is_active = False
        item.updated_at = datetime.now()
        if task_type == TaskType.TEST_CASE:  # Desativar Actions
            for action in item.actions:
                action.is_active = False


def create_new_items(db: Session, task_type: TaskType, generated_text: str, parent: int,
                     prompt_tokens: int, completion_tokens: int, version: int,
                     work_item_id: Optional[int], parent_board_id: Optional[int]) -> List[int]:
    """Cria novos itens com base no tipo de tarefa"""
    parser_map = {
        TaskType.EPIC: (parsers.parse_epic_response, Epic),
        TaskType.FEATURE: (parsers.parse_feature_response, Feature),
        TaskType.USER_STORY: (parsers.parse_user_story_response, UserStory),
        TaskType.TASK: (parsers.parse_task_response, Task),
        TaskType.BUG: (parsers.parse_bug_response, Bug),
        TaskType.ISSUE: (parsers.parse_issue_response, Issue),
        TaskType.PBI: (parsers.parse_pbi_response, PBI),
        TaskType.TEST_CASE: (parsers.parse_test_case_response, TestCase),
        TaskType.WBS: (parsers.parse_wbs_response, WBS),
        # TaskType.AUTOMATION_SCRIPT: ...  <-- REMOVER QUALQUER MENÇÃO AQUI!
    }

    parser, model = parser_map[task_type]

    item_ids = []

    if task_type == TaskType.EPIC:  # TRATAMENTO ESPECIAL PARA EPIC
        new_epic = parser(generated_text, prompt_tokens, completion_tokens)
        new_epic.version = version
        new_epic.is_active = True
        new_epic.team_project_id = parent  # Usando parent como team_project_id
        new_epic.work_item_id = work_item_id
        new_epic.parent_board_id = parent_board_id
        
        db.add(new_epic)
        db.flush()  # Gera o ID
        db.refresh(new_epic)  # Atualiza o objeto com o ID do banco
        
        item_ids.append(new_epic.id)  # <--- ADICIONA O ID À LISTA

    elif task_type == TaskType.WBS: 
        new_items = parser(generated_text, parent, prompt_tokens, completion_tokens) # <--- CORRETO! (Com parent)
        new_wbs = new_items  # parser_wbs_response retorna UM objeto WBS, não uma lista
        new_wbs.version = version
        new_wbs.is_active = True
        new_wbs.parent = parent  # parent_id para WBS (é 'parent', não 'team_project_id'!)
        new_wbs.work_item_id = work_item_id
        new_wbs.parent_board_id = parent_board_id
        db.add(new_wbs)
        db.flush()
        db.refresh(new_wbs)
        item_ids.append(new_wbs.id)  # Adiciona ID do WBS à lista

    else:  # TRATAMENTO PARA FEATURE, USER_STORY, TASK, TEST_CASE, BUG, ISSUE, PBI (LISTAS)
        new_items = parser(generated_text, parent, prompt_tokens, completion_tokens) # <--- CORRETO! (Com parent)
        for item in new_items:
            item.version = version
            item.is_active = True
            item.work_item_id = work_item_id
            item.parent_board_id = parent_board_id
            if task_type == TaskType.TEST_CASE:
                for action in item.actions:
                    action.version = version
                    action.is_active = True
        db.add_all(new_items)
        db.flush()
        item_ids.extend([item.id for item in new_items]) # Adiciona IDs da lista

    return item_ids

def handle_invalid_model_error(db: Session, producer: rabbitmq.RabbitMQProducer,
                               request_id: str, db_request: Request,
                               task_type: TaskType, error: InvalidModelError,
                               work_item_id: Optional[int], parent_board_id: Optional[int]):
    """Trata erros de modelo inválido"""
    error_message = f"Erro de modelo LLM: {error}"
    logger.error(error_message, exc_info=True)
    
    # Atualizar banco de dados
    update_request_status(db, request_id, Status.FAILED, error_message)
    
    # Publicar notificação
    notification_data = {
        "request_id": request_id,
        "parent": db_request.parent,
        "task_type": task_type.value,
        "status": Status.FAILED.value,
        "error_message": error_message,
        "item_ids": None,
        "version": None,
        "work_item_id": work_item_id,
        "parent_board_id": parent_board_id
    }
    
    try:
        producer.publish(notification_data, rabbitmq.NOTIFICATION_QUEUE)
        logger.info(f"Notificação de erro publicada para {request_id}")
    except Exception as e:
        logger.error(f"Falha ao publicar notificação de erro: {e}", exc_info=True)


def handle_parsing_error(db: Session, producer: rabbitmq.RabbitMQProducer,
                         request_id: str, db_request: Request,
                         task_type: TaskType, error: Exception,
                         generated_text: str, work_item_id: Optional[int],
                         parent_board_id: Optional[int]):
    """Trata erros de parsing"""
    error_message = f"Erro de parsing/validação: {error}"
    logger.error(error_message, exc_info=True)
    
    if isinstance(error, ValidationError):
        logger.error(f"Detalhes da validação: {error.errors()}")
    
    logger.debug(f"Resposta problemática: {generated_text}")
    db.rollback()
    update_request_status(db, request_id, Status.FAILED, error_message)
    send_notification(
        producer, request_id, db_request.parent,
        task_type.value, Status.FAILED, error_message,
        None, None, work_item_id, parent_board_id
    )


def handle_integrity_error(db: Session, producer: rabbitmq.RabbitMQProducer,
                           request_id: str, db_request: Request,
                           task_type: TaskType, error: IntegrityError,
                           work_item_id: Optional[int], parent_board_id: Optional[int]):
    """Trata erros de integridade do banco"""
    error_message = f"Erro de integridade: {error}"
    logger.error(error_message, exc_info=True)
    db.rollback()
    update_request_status(db, request_id, Status.FAILED, error_message)
    send_notification(
        producer, request_id, db_request.parent,
        task_type.value, Status.FAILED, error_message,
        None, None, work_item_id, parent_board_id
    )


def handle_generic_error(db: Session, producer: rabbitmq.RabbitMQProducer,
                         request_id: str, db_request: Request,
                         task_type: TaskType, error: Exception,
                         work_item_id: Optional[int], parent_board_id: Optional[int]):
    """Trata erros genéricos"""
    error_message = f"Erro inesperado: {error}"
    logger.error(error_message, exc_info=True)
    update_request_status(db, request_id, Status.FAILED, error_message)
    send_notification(
        producer, request_id, db_request.parent,
        task_type.value, Status.FAILED, error_message,
        None, None, work_item_id, parent_board_id
    )


def send_notification(producer: rabbitmq.RabbitMQProducer,
                      request_id: str, parent: str,
                      task_type: str, status: Status,
                      error_message: Optional[str],
                      item_ids: Optional[List[int]] = None,
                      version: Optional[int] = None,
                      work_item_id: Optional[int] = None,
                      parent_board_id: Optional[int] = None):
    """Envia notificação para o RabbitMQ"""
    notification_data = {
        "request_id": request_id,
        "parent": parent,
        "task_type": task_type,
        "status": status.value,
        "error_message": error_message,
        "item_ids": item_ids if item_ids is not None else [],
        "version": version,
        "work_item_id": work_item_id,
        "parent_board_id": parent_board_id
    }

    try:
        producer.publish(notification_data, rabbitmq.NOTIFICATION_QUEUE)
        logger.info(f"Notificação enviada para {request_id}")
    except Exception as e:
        logger.error(f"Falha ao enviar notificação: {e}", exc_info=True)


def update_request_status(db: Session, request_id: str,
                          status: Status, error_message: str = None):
    """Atualiza o status da requisição no banco de dados"""
    logger.info(f"Atualizando status para {request_id} => {status.value}")
    
    try:
        db_request = db.query(Request).filter(Request.request_id == request_id).first()
        if db_request:
            db_request.status = status.value
            db_request.updated_at = datetime.now()
            
            if status == Status.COMPLETED:
                db_request.processed_at = datetime.now()
            elif status == Status.FAILED:
                db_request.error_message = error_message
            
            db.commit()
            logger.info(f"Status atualizado para {request_id}")
        else:
            logger.warning(f"Requisição {request_id} não encontrada para atualização")
    except Exception as e:
        logger.error(f"Erro ao atualizar status: {e}", exc_info=True)
        db.rollback()


def close_resources(db: Session, producer: rabbitmq.RabbitMQProducer):
    """Fecha conexões com recursos externos"""
    try:
        db.close()
        logger.debug("Conexão com banco de dados fechada")
    except Exception as e:
        logger.error(f"Erro ao fechar conexão com banco: {e}")
    
    try:
        producer.close()
        logger.debug("Conexão com RabbitMQ fechada")
    except Exception as e:
        logger.error(f"Erro ao fechar conexão com RabbitMQ: {e}")
