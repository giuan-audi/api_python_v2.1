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
from uuid import UUID

logger = logging.getLogger(__name__)

class WorkItemProcessor(ABC):
    def __init__(self):
        self.db: Session = SessionLocal()
        self.producer = rabbitmq.RabbitMQProducer()
        self.llm_agent = LLMAgent()

    @abstractmethod
    def _process_item(
        self,
        task_type_enum: TaskType,
        parent: int,
        prompt_tokens: int,
        completion_tokens: int,
        work_item_id: Optional[str], # Ajustado para str
        parent_board_id: Optional[str], # Ajustado para str
        generated_text: str,
        artifact_id: Optional[int] = None,
        project_id: Optional[UUID] = None  # Novo parâmetro
    ) -> Tuple[List[int], int]:
        pass

    def process(
        self,
        request_id_interno: str,
        task_type: str,
        prompt_data: dict,
        language: Optional[str] = "português",
        llm_config: Optional[dict] = None,
        work_item_id: Optional[str] = None, # Ajustado para str
        parent_board_id: Optional[str] = None, # Ajustado para str
        type_test: Optional[str] = None,
        artifact_id: Optional[int] = None,
        project_id_str: Optional[str] = None # <-- Recebe a string da Task
    ):
        project_uuid: Optional[UUID] = None # Variável para armazenar o UUID validado
        db_request = None # Inicializar para o bloco finally

        effective_language = language if language else "português"

        try:
            logger.info(f"Processando item para request_id: {request_id_interno}, task_type: {task_type}, project_id_str: {project_id_str}")

            # --- Validação Inicial (Task Type e Project ID) ---
            try:
                task_type_enum = TaskType(task_type)
            except ValueError as e:
                # Tratamento de erro já existente para task_type inválido
                error_message = f"Task type inválido: {task_type}"
                logger.error(error_message)
                # Tenta atualizar status se já tiver buscado db_request, senão só loga
                if db_request:
                     self.update_request_status(request_id_interno, Status.FAILED, error_message)
                     self.send_notification(request_id_interno, None, task_type, Status.FAILED, error_message) # project_id é None aqui
                return

            # Validação do project_id_str (se fornecido)
            if project_id_str is not None:
                try:
                    project_uuid = UUID(project_id_str)
                except ValueError: # Usar o ValueError built-in
                    error_message = f"Project ID inválido (formato UUID esperado): {project_id_str}"
                    logger.error(f"{error_message} para request_id: {request_id_interno}")
                    # Tentar buscar db_request para atualizar status
                    db_request = self.db.query(Request).filter(Request.request_id == request_id_interno).first()
                    if db_request:
                         self.update_request_status(request_id_interno, Status.FAILED, error_message)
                         # Passa project_id=None pois a conversão falhou
                         self.send_notification(request_id_interno, db_request.parent, task_type, Status.FAILED, error_message, project_id=None)
                    return # Interrompe o processamento

            # --- Busca da Requisição no DB ---
            db_request = self.db.query(Request).filter(Request.request_id == request_id_interno).first()
            if not db_request:
                error_message = f"Requisição {request_id_interno} não encontrada"
                logger.error(error_message)
                # project_uuid pode ser None ou ter sido validado
                self.send_notification(request_id_interno, None, task_type, Status.FAILED, error_message, project_id=project_uuid)
                return

            # --- Determinação do Parent Hierárquico ---
            parent_id_hierarquico: Optional[int] = None
            if artifact_id is not None: # REPROCESSAMENTO
                parent_id_hierarquico = self._get_original_parent_id(task_type_enum, artifact_id)
                if parent_id_hierarquico is None and task_type_enum != TaskType.EPIC: # Permitir Epic sem parent original definido?
                     error_message = f"Parent original não encontrado para artefato tipo: {task_type}, ID: {artifact_id}"
                     logger.error(error_message)
                     self.update_request_status(request_id_interno, Status.FAILED, error_message)
                     self.send_notification(request_id_interno, db_request.parent, task_type, Status.FAILED, error_message, project_id=project_uuid)
                     return
            elif db_request.parent is not None: # CRIAÇÃO (com parent fornecido na request, seja /generate ou /independent)
                try:
                    parent_id_hierarquico = int(db_request.parent)
                except ValueError:
                    error_message = f"Parent inválido na requisição DB: {db_request.parent}"
                    logger.error(error_message)
                    self.update_request_status(request_id_interno, Status.FAILED, error_message)
                    self.send_notification(request_id_interno, db_request.parent, task_type, Status.FAILED, error_message, project_id=project_uuid)
                    return
            # Se for criação pela rota /independent sem parent, parent_id_hierarquico permanecerá None

            # --- Processamento do LLM e Persistência ---
            # (try-except bloco para LLM, parsing, commit)
            try:
                logger.info(f"Chamando LLMAgent para request_id: {request_id_interno} com idioma: {effective_language}")
                processed_prompt_data = self.process_prompt_data(prompt_data, type_test, effective_language)
                if llm_config:
                    self.configure_llm_agent(self.llm_agent, llm_config)

                llm_response = self.llm_agent.generate_text(processed_prompt_data, llm_config)
                generated_text = llm_response["text"]
                prompt_tokens = llm_response["prompt_tokens"]
                completion_tokens = llm_response["completion_tokens"]
                logger.debug(f"Texto gerado pela LLM para request_id {request_id_interno}: {generated_text}")

                # Passa parent_id_hierarquico e project_uuid validados
                item_ids, new_version = self._process_item(
                    task_type_enum=task_type_enum,
                    parent=parent_id_hierarquico, # Pode ser None
                    prompt_tokens=prompt_tokens,
                    completion_tokens=completion_tokens,
                    work_item_id=work_item_id,
                    parent_board_id=parent_board_id,
                    generated_text=generated_text,
                    artifact_id=artifact_id,
                    project_id=project_uuid # Passa o UUID validado (ou None)
                )

                self.db.commit()
                self.update_request_status(request_id_interno, Status.COMPLETED)

                # Envia notificação passando o parent hierárquico e o project_uuid
                self.send_notification(
                    request_id=request_id_interno,
                    parent=str(parent_id_hierarquico) if parent_id_hierarquico is not None else None,
                    task_type=task_type_enum.value,
                    status=Status.COMPLETED,
                    error_message=None,
                    item_ids=item_ids,
                    version=new_version,
                    work_item_id=work_item_id,
                    parent_board_id=parent_board_id,
                    is_reprocessing=(artifact_id is not None),
                    project_id=project_uuid # Passa o UUID validado (ou None)
                )

            # (blocos except para InvalidModelError, parsing, IntegrityError, AMQPConnectionError, Exception genérica)
            # ... garantir que chamem send_notification passando project_uuid nos casos de erro ...
            except InvalidModelError as e:
                # (Usar self.handle_invalid_model_error, que chama send_notification)
                self.handle_invalid_model_error(request_id_interno, db_request, task_type_enum, e, work_item_id, parent_board_id, project_uuid) # Passa project_uuid
                return
            except (json.JSONDecodeError, KeyError, ValidationError) as e:
                # (Usar self.handle_parsing_error)
                self.handle_parsing_error(request_id_interno, db_request, task_type_enum, e, generated_text, work_item_id, parent_board_id, project_uuid) # Passa project_uuid
                return
            except IntegrityError as e:
                 # (Usar self.handle_integrity_error)
                self.handle_integrity_error(request_id_interno, db_request, task_type_enum, e, work_item_id, parent_board_id, project_uuid) # Passa project_uuid
                return
            except pika.exceptions.AMQPConnectionError as e:
                # (Usar self.handle_amqp_connection_error)
                self.handle_amqp_connection_error(request_id_interno, db_request, task_type_enum, e, work_item_id, parent_board_id, project_uuid) # Passa project_uuid
                return
            except Exception as e:
                # (Usar self.handle_generic_error)
                self.handle_generic_error(request_id_interno, db_request, task_type_enum, e, work_item_id, parent_board_id, project_uuid) # Passa project_uuid
                raise # Re-lança exceção genérica

        finally:
            self.close_resources()
            logger.debug("Recursos liberados")

    # --- Funções auxiliares (agora métodos da classe) ---

    def _get_original_parent_id(self, task_type: TaskType, artifact_id: int) -> Optional[int]:
        """
        Busca o ID do parent original de um artefato existente no banco de dados.
        Retorna None se o artefato ou seu parent não forem encontrados, ou se o tipo de artefato não for suportado.
        """
        model_map = {
            TaskType.FEATURE: (Feature, Feature.parent),
            TaskType.USER_STORY: (UserStory, UserStory.parent),
            TaskType.TASK: (Task, Task.parent),
            TaskType.BUG: (Bug, Bug.user_story_id),
            TaskType.ISSUE: (Issue, Issue.user_story_id),
            TaskType.PBI: (PBI, PBI.feature_id),
            TaskType.TEST_CASE: (TestCase, TestCase.parent),
            TaskType.WBS: (WBS, WBS.parent),
            TaskType.EPIC: (Epic, Epic.team_project_id), # Epic's parent is team_project_id in this context, or perhaps None if root level. Adjust if needed.
            TaskType.AUTOMATION_SCRIPT: (None, None),
        }
        model, parent_column = model_map.get(task_type, (None, None)) # Get model and parent column, default to None if type not found

        if model is None or parent_column is None:
            logger.warning(f"Tipo de artefato não suportado para buscar parent original: {task_type}")
            return None

        artifact = self.db.query(model).filter(model.id == artifact_id).first()
        if not artifact:
            logger.warning(f"Artefato não encontrado para tipo: {task_type}, ID: {artifact_id}")
            return None

        return getattr(artifact, parent_column.name) # Dynamically get parent ID using column name


    def process_prompt_data(self, prompt_data: dict, type_test: Optional[str], language: str) -> dict:
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
        
        # *** NOVO: Injetar language ***
        placeholder_language = "{language}"
        # Injetar principalmente no system prompt, mas verificar outros por segurança
        for key in ['system', 'user', 'assistant']:
             if key in prompt_data_dict and isinstance(prompt_data_dict[key], str) and placeholder_language in prompt_data_dict[key]:
                 prompt_data_dict[key] = prompt_data_dict[key].replace(placeholder_language, language)
                 logger.debug(f"Placeholder {placeholder_language} substituído por '{language}' no prompt '{key}'.")
             elif key=='system' and placeholder_language not in prompt_data_dict.get('system',''):
                 logger.warning(f"Placeholder {placeholder_language} não encontrado no prompt 'system'. A injeção de idioma pode não funcionar como esperado.")

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

    def send_notification(self, request_id: str, parent: Optional[str], task_type: str, status: Status, # <-- parent Optional[str]
                      error_message: Optional[str], item_ids: Optional[List[int]] = None,
                      version: Optional[int] = None, work_item_id: Optional[str] = None, # <-- str
                      parent_board_id: Optional[str] = None, # <-- str
                      is_reprocessing: bool = False,
                      project_id: Optional[UUID] = None): # <-- ACEITA UUID
        """Envia notificação para o RabbitMQ."""
        project_id_str = str(project_id) if project_id else None # <-- CONVERTE para string ou None

        notification_data = {
            "request_id": request_id,
            "project_id": project_id_str, # <-- ADICIONADO/ATUALIZADO
            "parent": parent, # Já era opcional e string
            "task_type": task_type,
            "status": status.value,
            "error_message": error_message,
            "item_ids": item_ids if item_ids is not None else [],
            "version": version,
            "work_item_id": work_item_id,
            "parent_board_id": parent_board_id,
            "is_reprocessing": is_reprocessing
        }

        try:
            self.producer.publish(notification_data, rabbitmq.NOTIFICATION_QUEUE)
            logger.info(f"Notificação enviada para {request_id}")
        except Exception as e:
            logger.error(f"Falha ao enviar notificação: {e}", exc_info=True)

    def handle_invalid_model_error(self, request_id: str, db_request: Request, task_type: TaskType,
                                error: InvalidModelError, work_item_id: Optional[str],
                                parent_board_id: Optional[str], project_id: Optional[UUID] = None):
        error_message = f"Erro de modelo LLM: {error}"
        logger.error(error_message, exc_info=True)
        self.update_request_status(request_id, Status.FAILED, error_message)
        self.send_notification(
            request_id, db_request.parent, task_type.value, Status.FAILED, error_message,
            None, None, work_item_id, parent_board_id, project_id=project_id # <--- PASS project_id
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

    def handle_amqp_connection_error(self, request_id: str, db_request: Request, task_type: TaskType,
                                     error: pika.exceptions.AMQPConnectionError, work_item_id: Optional[int],
                                     parent_board_id: Optional[int]):
        """Trata erros de conexão com RabbitMQ."""
        error_message = f"Erro de conexão com RabbitMQ: {error}"
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
