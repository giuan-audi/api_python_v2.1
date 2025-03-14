# app/workers/processors/base.py
from abc import ABC, abstractmethod
from typing import List, Optional, Dict, Any, Tuple
import json
from sqlalchemy.orm import Session
from app.database import SessionLocal
from app.models import Request, Status, TaskType, Epic, Feature, UserStory, Task, Bug, Issue, PBI, TestCase, Action, WBS
from app.utils import rabbitmq, parsers
from app.agents.llm_agent import LLMAgent, InvalidModelError
from datetime import datetime
import pika
from pydantic import ValidationError
from sqlalchemy.exc import IntegrityError
import logging

logger = logging.getLogger(__name__)

class WorkItemProcessor(ABC):
    def __init__(self):
        self.db: Session = SessionLocal()
        self.producer = rabbitmq.RabbitMQProducer()
        self.llm_agent = LLMAgent()

    @abstractmethod
    def _process_item(self, task_type_enum: TaskType, parent: int, prompt_tokens: int, completion_tokens: int,
                      work_item_id: Optional[int], parent_board_id: Optional[int], generated_text: str) -> Tuple[List[int], int]:
        pass

    def process(
        self,
        request_id_interno: str,
        task_type: str,
        prompt_data: dict,
        llm_config: Optional[dict] = None,
        work_item_id: Optional[int] = None,
        parent_board_id: Optional[int] = None,
        type_test: Optional[str] = None,  # Parâmetro já existente
        artifact_id: Optional[int] = None
    ):

        try:
            logger.info(f"Processando item para request_id: {request_id_interno}, task_type: {task_type}")

            try:
                task_type_enum = TaskType(task_type)
            except ValueError as e:
                error_message = f"Task type inválido: {task_type}"
                logger.error(error_message)
                self.update_request_status(request_id_interno, Status.FAILED, error_message)
                self.send_notification(request_id_interno, None, task_type, Status.FAILED, error_message)
                return

            db_request = self.db.query(Request).filter(Request.request_id == request_id_interno).first()
            if not db_request:
                error_message = f"Requisição {request_id_interno} não encontrada"
                logger.error(error_message)
                self.send_notification(request_id_interno, None, task_type, Status.FAILED, error_message)
                return

            # Determinar o parent corretamente
            if artifact_id is not None:
                parent = artifact_id  # Usar artifact_id para reprocessamento
            else:
                parent_str = db_request.parent
                try:
                    parent = int(parent_str)
                except ValueError as e:
                    error_message = f"Parent inválido: {db_request.parent}"
                    logger.error(error_message)
                    self.update_request_status(request_id_interno, Status.FAILED, error_message)
                    self.send_notification(request_id_interno, None, task_type, Status.FAILED, error_message)
                    return

            # --- Processamento do LLM ---
            try:
                logger.info(f"Chamando LLMAgent para request_id: {request_id_interno}")

                prompt_data_dict = self.process_prompt_data(prompt_data, type_test)

                if llm_config:
                    self.configure_llm_agent(self.llm_agent, llm_config)

                llm_response = self.llm_agent.generate_text(prompt_data_dict, llm_config)
                generated_text = llm_response["text"]
                prompt_tokens = llm_response["prompt_tokens"]
                completion_tokens = llm_response["completion_tokens"]

                logger.debug(f"Texto gerado pela LLM para request_id {request_id_interno}: {generated_text}")

                item_ids, new_version = self._process_item(task_type_enum, parent, prompt_tokens, completion_tokens, work_item_id, parent_board_id, generated_text)

                self.db.commit()
                self.update_request_status(request_id_interno, Status.COMPLETED)

                if task_type_enum == TaskType.EPIC or task_type_enum == TaskType.WBS:
                    parent = item_ids[0]
                self.send_notification(
                    request_id_interno, str(parent),
                    task_type_enum.value, Status.COMPLETED, None, item_ids, new_version,
                    work_item_id, parent_board_id
                )

            except InvalidModelError as e:
                self.handle_invalid_model_error(request_id_interno, db_request, task_type_enum, e, work_item_id, parent_board_id)
                return

            except (json.JSONDecodeError, KeyError, ValidationError) as e:
                self.handle_parsing_error(request_id_interno, db_request, task_type_enum, e, generated_text, work_item_id, parent_board_id)
                return

            except IntegrityError as e:
                self.handle_integrity_error(request_id_interno, db_request, task_type_enum, e, work_item_id, parent_board_id)
                return

            except pika.exceptions.AMQPConnectionError as e:
                logger.error(f"Erro de conexão com RabbitMQ: {e}", exc_info=True)
                return

            except Exception as e:
                self.handle_generic_error(request_id_interno, db_request, task_type_enum, e, work_item_id, parent_board_id)
                raise

        finally:
            self.close_resources()
            logger.debug("Recursos liberados")

    # --- Funções auxiliares (agora métodos da classe) ---
    def process_prompt_data(self, prompt_data: dict, type_test: Optional[str]) -> dict:
        prompt_data_dict = prompt_data.copy()
        if 'user_input' in prompt_data_dict:
            prompt_data_dict['user'] = prompt_data_dict['user'].replace(
                "{user_input}", prompt_data_dict['user_input']
            )
            del prompt_data_dict['user_input']

        replacement = type_test if type_test is not None else ''

        for key in ['system', 'user', 'assistant']:
            if key in prompt_data_dict:
                prompt_data_dict[key] = prompt_data_dict[key].replace("{type_test}", replacement)
        return prompt_data_dict

    def configure_llm_agent(self, agent: LLMAgent, config: dict):
        agent.chosen_llm = config.get("llm", agent.chosen_llm)
        if config.get("llm") == "openai":
            agent.openai_model = config.get("model", agent.openai_model)
        elif config.get("llm") == "gemini":
            agent.gemini_model = config.get("model", agent.gemini_model)
        agent.temperature = config.get("temperature", agent.temperature)
        agent.max_tokens = config.get("max_tokens", agent.max_tokens)
        agent.top_p = config.get("top_p", agent.top_p)

    def get_existing_items(self, db: Session, task_type: TaskType, parent: int):
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
            TaskType.AUTOMATION_SCRIPT: (None, None),  # Adicionado suporte para AUTOMATION_SCRIPT
        }
        model, filter_column = model_map[task_type]
        if model is None:
            return []
        return db.query(model).filter(filter_column == parent, model.is_active == True).all()

    def get_new_version(self, existing_items: list) -> int:
        return max(item.version for item in existing_items) + 1 if existing_items else 1

    def deactivate_existing_items(self, db: Session, items: list, task_type: TaskType):
        for item in items:
            item.is_active = False
            item.updated_at = datetime.now()
            if task_type == TaskType.TEST_CASE:
                for action in item.actions:
                    action.is_active = False

    def update_request_status(self, request_id: str, status: Status, error_message: str = None):
        """Atualiza o status da requisição no banco de dados."""
        logger.info(f"Atualizando status para {request_id} => {status.value}")
        try:
            db_request = self.db.query(Request).filter(Request.request_id == request_id).first()
            if db_request:
                db_request.status = status.value
                db_request.updated_at = datetime.now()
                if status == Status.COMPLETED:
                    db_request.processed_at = datetime.now()
                elif status == Status.FAILED:
                    db_request.error_message = error_message
                self.db.commit()
                logger.info(f"Status atualizado para {request_id}")
            else:
                logger.warning(f"Requisição {request_id} não encontrada para atualização")
        except Exception as e:
            logger.error(f"Erro ao atualizar status: {e}", exc_info=True)
            self.db.rollback()

    def send_notification(self, request_id: str, parent: str, task_type: str, status: Status,
                          error_message: Optional[str], item_ids: Optional[List[int]] = None,
                          version: Optional[int] = None, work_item_id: Optional[int] = None,
                          parent_board_id: Optional[int] = None):
        """Envia notificação para o RabbitMQ."""
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
            self.producer.publish(notification_data, rabbitmq.NOTIFICATION_QUEUE)
            logger.info(f"Notificação enviada para {request_id}")
        except Exception as e:
            logger.error(f"Falha ao enviar notificação: {e}", exc_info=True)

    def handle_invalid_model_error(self, request_id: str, db_request: Request, task_type: TaskType,
                                   error: InvalidModelError, work_item_id: Optional[int],
                                   parent_board_id: Optional[int]):
        """Trata erros de modelo inválido."""
        error_message = f"Erro de modelo LLM: {error}"
        logger.error(error_message, exc_info=True)
        self.update_request_status(request_id, Status.FAILED, error_message)
        self.send_notification(
            request_id, db_request.parent, task_type.value, Status.FAILED, error_message,
            None, None, work_item_id, parent_board_id
        )

    def handle_parsing_error(self, request_id: str, db_request: Request, task_type: TaskType,
                             error: Exception, generated_text: str, work_item_id: Optional[int],
                             parent_board_id: Optional[int]):
        """Trata erros de parsing."""
        error_message = f"Erro de parsing/validação: {error}"
        logger.error(error_message, exc_info=True)
        if isinstance(error, ValidationError):
            logger.error(f"Detalhes da validação: {error.errors()}")
        logger.debug(f"Resposta problemática: {generated_text}")
        self.db.rollback()
        self.update_request_status(request_id, Status.FAILED, error_message)
        self.send_notification(
            request_id, db_request.parent, task_type.value, Status.FAILED, error_message,
            None, None, work_item_id, parent_board_id
        )

    def handle_integrity_error(self, request_id: str, db_request: Request, task_type: TaskType,
                               error: IntegrityError, work_item_id: Optional[int],
                               parent_board_id: Optional[int]):
        """Trata erros de integridade do banco."""
        error_message = f"Erro de integridade: {error}"
        logger.error(error_message, exc_info=True)
        self.db.rollback()
        self.update_request_status(request_id, Status.FAILED, error_message)
        self.send_notification(
            request_id, db_request.parent, task_type.value, Status.FAILED, error_message,
            None, None, work_item_id, parent_board_id
        )

    def handle_generic_error(self, request_id: str, db_request: Request, task_type: TaskType,
                             error: Exception, work_item_id: Optional[int],
                             parent_board_id: Optional[int]):
        """Trata erros genéricos."""
        error_message = f"Erro inesperado: {error}"
        logger.error(error_message, exc_info=True)
        self.update_request_status(request_id, Status.FAILED, error_message)
        self.send_notification(
            request_id, db_request.parent, task_type.value, Status.FAILED, error_message,
            None, None, work_item_id, parent_board_id
        )

    def close_resources(self):
        """Fecha conexões com recursos externos."""
        try:
            self.db.close()
            logger.debug("Conexão com banco de dados fechada")
        except Exception as e:
            logger.error(f"Erro ao fechar conexão com banco: {e}")
        try:
            self.producer.close()
            logger.debug("Conexão com RabbitMQ fechada")
        except Exception as e:
            logger.error(f"Erro ao fechar conexão com RabbitMQ: {e}")
