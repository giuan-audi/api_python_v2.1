# app/workers/processors/base.py
from abc import ABC, abstractmethod
from typing import List, Optional, Dict, Any, Tuple
import json
from sqlalchemy.orm import Session
from app.database import SessionLocal
from app.models import Request, Status, TaskType, Epic, Feature, UserStory, Task, Bug, Issue, PBI, TestCase, Action, WBS #, Project
from app.utils import rabbitmq, parsers
from app.agents.llm_agent import LLMAgent, InvalidModelError
from datetime import datetime
import pika
from pydantic import ValidationError
from sqlalchemy.exc import IntegrityError
import logging
from uuid import UUID
from app.utils import rabbitmq

logger = logging.getLogger(__name__)

PARENT_MODEL_MAP = {
    TaskType.EPIC: Epic,
    TaskType.FEATURE: Feature,
    TaskType.USER_STORY: UserStory,
    TaskType.TASK: Task,
    TaskType.BUG: Bug,
    TaskType.ISSUE: Issue,
    TaskType.PBI: PBI,
    TaskType.TEST_CASE: TestCase,
    # TaskType.PROJECT: Project,
}

class WorkItemProcessor(ABC):
    def __init__(self):
        self.db: Session = SessionLocal()
        self.producer = rabbitmq.RabbitMQProducer()
        self.llm_agent = LLMAgent()
        self.parent_model_map = PARENT_MODEL_MAP # Tornando atributo de instância

    @abstractmethod
    def _process_item(
        self,
        task_type_enum: TaskType,
        parent: Optional[int], # ID do pai hierárquico original (pode ser None)
        prompt_tokens: int,
        completion_tokens: int,
        work_item_id: Optional[str],
        parent_board_id: Optional[str],
        generated_text: str,
        artifact_id: Optional[int] = None, # ID do item (se reprocessamento)
        project_id: Optional[UUID] = None, # UUID do projeto
        parent_type: Optional[TaskType] = None # Tipo do pai hierárquico original (pode ser None)
    ) -> Tuple[List[int], int]:
        """
        Método abstrato para processar a criação ou atualização de um item
        após a chamada da LLM. Implementado por WorkItemCreator e WorkItemReprocessor.
        """
        pass

    def process(
        self,
        request_id_interno: str,
        task_type: str,
        prompt_data: dict,
        language: Optional[str] = "português",
        parent_type_str: Optional[str] = None, # Tipo do pai (obrigatório para /generate e /independent com pai)
        llm_config: Optional[dict] = None,
        work_item_id: Optional[str] = None,
        parent_board_id: Optional[str] = None,
        type_test: Optional[str] = None,
        artifact_id: Optional[int] = None, # ID do item se for reprocessamento
        project_id_str: Optional[str] = None # UUID do projeto (obrigatório para /independent)
    ):
        """
        Orquestra o processamento completo de uma requisição (criação ou reprocessamento).
        Valida inputs, chama LLM, processa a resposta, atualiza DB e notifica.
        """
        project_uuid: Optional[UUID] = None
        parent_id_from_req: Optional[int] = None
        parent_type_enum_from_req: Optional[TaskType] = None
        db_request: Optional[Request] = None
        generated_text: str = "" # Inicializar para bloco finally/except
        task_type_enum: Optional[TaskType] = None # Inicializar

        try:
            logger.info(f"Processando request_id: {request_id_interno}, task_type: {task_type}, artifact_id: {artifact_id}, project_id_str: {project_id_str}, parent_type_str: {parent_type_str}")

            try:
                task_type_enum = TaskType(task_type)
            except ValueError:
                self._handle_initial_error(request_id_interno, f"Task type inválido: {task_type}")
                return

            if project_id_str:
                try:
                    project_uuid = UUID(project_id_str)
                except ValueError:
                    self._handle_initial_error(request_id_interno, f"Project ID inválido (formato UUID esperado): {project_id_str}")
                    return

            # --- Busca Requisição DB ---
            db_request = self.db.query(Request).filter(Request.request_id == request_id_interno).first()
            if not db_request:
                logger.error(f"Requisição {request_id_interno} não encontrada no banco de dados.")
                # Não podemos atualizar status, a notificação será mínima se a task falhar
                return # Interrompe aqui, a falha será pega pelo wrapper da task

            # Se project_uuid não veio da task (ex: rota /generate ou /reprocess), tenta pegar do DBRequest
            if project_uuid is None and db_request.project_id:
                 project_uuid = db_request.project_id
                 logger.info(f"Usando project_id {project_uuid} do DBRequest {request_id_interno}")

            # --- Determinar e Validar Pai (Hierárquico) ---
            parent_id_hierarquico: Optional[int] = None
            parent_type_enum_hierarquico: Optional[TaskType] = None

            if artifact_id is not None: # Reprocessamento
                # Buscar pai e tipo do item existente
                existing_item_info = self._get_original_parent_info(task_type_enum, artifact_id)
                if existing_item_info:
                    parent_id_hierarquico = existing_item_info.get("parent_id")
                    parent_type_enum_hierarquico = existing_item_info.get("parent_type")
                    # Pegar project_id do item existente se ainda não tivermos
                    if project_uuid is None and existing_item_info.get("project_id"):
                         project_uuid = existing_item_info.get("project_id")
                         logger.info(f"Usando project_id {project_uuid} do artefato existente {artifact_id} durante reprocessamento.")
                # Aviso se pai não for encontrado (mas continua, conforme decisão)
                if not existing_item_info or (parent_id_hierarquico is None and parent_type_enum_hierarquico is None and task_type_enum != TaskType.EPIC):
                     logger.warning(f"Não foi possível determinar o pai hierárquico original para reprocessamento do artefato {artifact_id} ({task_type_enum.value}). Continuando.")

            else: # Criação (/generate ou /independent)
                if db_request.parent:
                    try:
                        parent_id_hierarquico = int(db_request.parent)
                    except (ValueError, TypeError):
                         # Usa o helper centralizado
                         self._handle_processing_error(db_request, task_type_enum, f"Parent ID inválido no registro da requisição: {db_request.parent}", project_uuid)
                         return

                # Usa parent_type_str que veio como argumento da task
                if parent_type_str:
                     try:
                         parent_type_enum_hierarquico = TaskType(parent_type_str)
                     except ValueError:
                         self._handle_processing_error(db_request, task_type_enum, f"Parent type inválido: {parent_type_str}", project_uuid)
                         return

                # Validar consistência (pai ID precisa de tipo)
                if parent_id_hierarquico is not None and parent_type_enum_hierarquico is None:
                    self._handle_processing_error(db_request, task_type_enum, "Parent ID fornecido sem Parent Type.", project_uuid)
                    return
                # *** VALIDAÇÃO DE EXISTÊNCIA DO PAI ***
                if parent_id_hierarquico is not None and parent_type_enum_hierarquico is not None:
                    # Só valida no DB se o tipo do pai NÃO for 'project'
                    if parent_type_enum_hierarquico != TaskType.PROJECT:
                        if not self._validate_parent_exists(parent_id_hierarquico, parent_type_enum_hierarquico):
                            self._handle_processing_error(db_request, task_type_enum, f"Pai não encontrado: ID={parent_id_hierarquico}, Tipo={parent_type_enum_hierarquico.value}", project_uuid)
                            return
                    else:
                        logger.info(f"Validação de existência pulada para pai tipo 'project' (ID={parent_id_hierarquico}).")

            # --- Processamento Principal (LLM e DB Item) ---
            try:
                effective_language = language if language else "português"
                logger.info(f"Iniciando chamada LLM para ReqID: {request_id_interno}, Idioma: {effective_language}")

                processed_prompt_data = self.process_prompt_data(prompt_data, type_test, effective_language)

                if llm_config:
                    self.configure_llm_agent(self.llm_agent, llm_config)

                llm_response = self.llm_agent.generate_text(processed_prompt_data, llm_config)
                generated_text = llm_response["text"]
                prompt_tokens = llm_response["prompt_tokens"]
                completion_tokens = llm_response["completion_tokens"]
                logger.debug(f"Texto gerado pela LLM: {generated_text[:500]}...")

                # Chamar implementação de _process_item
                item_ids, new_version = self._process_item(
                    task_type_enum=task_type_enum,
                    parent=parent_id_hierarquico, # Passa o ID do pai hierárquico
                    prompt_tokens=prompt_tokens,
                    completion_tokens=completion_tokens,
                    work_item_id=work_item_id,
                    parent_board_id=parent_board_id,
                    generated_text=generated_text,
                    artifact_id=artifact_id,
                    project_id=project_uuid, # Passa o UUID do projeto
                    parent_type=parent_type_enum_hierarquico # Passa o tipo do pai hierárquico
                )

                # Commit e Notificação de Sucesso
                self.db.commit()
                logger.info(f"Commit realizado com sucesso para ReqID: {request_id_interno}.")
                self.update_request_status(request_id_interno, Status.COMPLETED)
                self.send_notification(
                    request_id=request_id_interno,
                    project_id=project_uuid,
                    parent=str(parent_id_hierarquico) if parent_id_hierarquico is not None else None,
                    parent_type=parent_type_enum_hierarquico.value if parent_type_enum_hierarquico else None,
                    task_type=task_type_enum.value,
                    status=Status.COMPLETED,
                    error_message=None,
                    item_ids=item_ids,
                    version=new_version,
                    work_item_id=work_item_id,
                    parent_board_id=parent_board_id,
                    is_reprocessing=(artifact_id is not None)
                )

            # --- Tratamento de Erros no Processamento Principal ---
            # Usar o helper centralizado _handle_failure aqui seria ideal (pensar na proxima melhorai)
            except InvalidModelError as e:
                self._handle_failure(request_id_interno, db_request, task_type_enum, e, work_item_id=work_item_id, parent_board_id=parent_board_id, project_id=project_uuid)
            except (json.JSONDecodeError, KeyError, ValidationError, ValueError) as e:
                self._handle_failure(request_id_interno, db_request, task_type_enum, e, rollback=True, work_item_id=work_item_id, parent_board_id=parent_board_id, project_id=project_uuid)
                 # Poderíamos passar generated_text para o log dentro de _handle_failure
            except IntegrityError as e:
                self._handle_failure(request_id_interno, db_request, task_type_enum, e, rollback=True, work_item_id=work_item_id, parent_board_id=parent_board_id, project_id=project_uuid)
            except pika.exceptions.AMQPConnectionError as e:
                # Erro de AMQP é especial, pois a notificação de falha também pode falhar
                self._handle_amqp_connection_error(request_id_interno, db_request, task_type_enum, e, work_item_id, parent_board_id, project_uuid)
            except Exception as e:
                # Usar helper para erros genéricos
                self._handle_failure(request_id_interno, db_request, task_type_enum, e, rollback=True, work_item_id=work_item_id, parent_board_id=parent_board_id, project_id=project_uuid)
                # raise # Não re-lançar aqui, deixar o wrapper da task logar se necessário

        finally:
            self.close_resources()
            logger.debug(f"Recursos liberados para ReqID: {request_id_interno}")


    # --- Métodos Auxiliares ---

    def _validate_parent_exists(self, parent_id: int, parent_type: TaskType) -> bool:
        """Verifica se um artefato pai com o ID e tipo fornecidos existe."""
        logger.debug(f"Validando existência do pai: ID={parent_id}, Tipo={parent_type.value}")
        ParentModel = self.parent_model_map.get(parent_type) # Usar atributo de instância
        if not ParentModel:
            logger.warning(f"Tipo de pai não mapeado para validação: {parent_type.value}.")
            return False
        try:
            exists = self.db.query(ParentModel.id).filter(ParentModel.id == parent_id).count() > 0
            if exists: logger.debug(f"Pai encontrado: ID={parent_id}, Tipo={parent_type.value}")
            else: logger.warning(f"Pai NÃO encontrado: ID={parent_id}, Tipo={parent_type.value}")
            return exists
        except Exception as e:
            logger.error(f"Erro ao validar existência do pai (ID={parent_id}, Tipo={parent_type.value}): {e}", exc_info=True)
            return False

    def _get_original_parent_info(self, task_type: TaskType, artifact_id: int) -> Optional[Dict[str, Any]]:
        """Busca ID, Tipo e Project ID do pai original de um artefato existente."""
        logger.debug(f"Buscando info do pai original para: Tipo={task_type.value}, ID={artifact_id}")
        ArtifactModel = PARENT_MODEL_MAP.get(task_type) # Modelo do *próprio* artefato
        if not ArtifactModel:
            logger.warning(f"Modelo não encontrado para buscar pai original: {task_type.value}")
            return None

        artifact = self.db.query(ArtifactModel).filter(ArtifactModel.id == artifact_id).first()
        if not artifact:
            logger.warning(f"Artefato não encontrado para buscar pai original: ID={artifact_id}, Tipo={task_type.value}")
            return None

        parent_id: Optional[int] = getattr(artifact, 'parent', None) # Pega parent se existir
        parent_type_str: Optional[str] = getattr(artifact, 'parent_type', None) # Pega parent_type se existir
        project_id_uuid: Optional[UUID] = getattr(artifact, 'project_id', None)

        parent_type_enum: Optional[TaskType] = None
        if parent_type_str:
            try:
                parent_type_enum = TaskType(parent_type_str)
            except ValueError:
                 logger.warning(f"Parent type inválido ('{parent_type_str}') armazenado para artefato ID {artifact_id}.")

        # Caso especial para Epic (sem pai artefato)
        if task_type == TaskType.EPIC:
             parent_id = None # Epic não tem pai artefato
             parent_type_enum = None

        logger.debug(f"Info pai original encontrada: ID={parent_id}, Tipo={parent_type_enum}, Projeto={project_id_uuid}")
        return {"parent_id": parent_id, "parent_type": parent_type_enum, "project_id": project_id_uuid}


    def process_prompt_data(self, prompt_data: dict, type_test: Optional[str], language: str) -> dict:
        """Processa os dados do prompt injetando user_input, type_test e language."""
        prompt_data_dict = prompt_data.copy()
        if 'user_input' in prompt_data_dict and isinstance(prompt_data_dict.get('user'), str) and '{user_input}' in prompt_data_dict['user']:
            prompt_data_dict['user'] = prompt_data_dict['user'].replace("{user_input}", str(prompt_data_dict['user_input']))
        elif 'user_input' in prompt_data_dict:
            logger.warning("Placeholder {user_input} não encontrado no prompt 'user'.")

        replacement_type_test = type_test if type_test is not None else ''
        placeholder_language = "{language}"

        for key in ['system', 'user', 'assistant']:
            if key in prompt_data_dict and isinstance(prompt_data_dict[key], str):
                if "{type_test}" in prompt_data_dict[key]:
                     prompt_data_dict[key] = prompt_data_dict[key].replace("{type_test}", replacement_type_test)
                if placeholder_language in prompt_data_dict[key]:
                    prompt_data_dict[key] = prompt_data_dict[key].replace(placeholder_language, language)
                    logger.debug(f"Placeholder {placeholder_language} substituído por '{language}' no prompt '{key}'.")

        if placeholder_language not in prompt_data_dict.get('system',''):
             logger.warning(f"Placeholder {placeholder_language} não encontrado no prompt 'system'.")

        return prompt_data_dict


    def configure_llm_agent(self, agent: LLMAgent, config: dict):
        """Configura o LLMAgent com base no dicionário de configuração."""
        agent.chosen_llm = config.get("llm", agent.chosen_llm)
        model_to_set = config.get("model")
        if model_to_set:
            if agent.chosen_llm == "openai": agent.openai_model = model_to_set
            elif agent.chosen_llm == "gemini": agent.gemini_model = model_to_set
        agent.temperature = config.get("temperature", agent.temperature)
        agent.max_tokens = config.get("max_tokens", agent.max_tokens)
        agent.top_p = config.get("top_p", agent.top_p)


    def get_existing_items(self, db: Session, task_type: TaskType, parent: int, parent_type: Optional[TaskType] = None):
        """Busca itens ativos existentes com base no pai e tipo de pai."""
        logger.debug(f"Buscando itens existentes tipo {task_type.value} para pai ID {parent} e tipo pai {parent_type.value if parent_type else 'N/A'}")
        ItemModel = PARENT_MODEL_MAP.get(task_type) # Modelo do item filho
        if not ItemModel or not hasattr(ItemModel, 'parent'):
             return []

        query = db.query(ItemModel).filter(
            ItemModel.parent == parent,
            ItemModel.is_active == True
        )
        if parent_type and hasattr(ItemModel, 'parent_type'):
           query = query.filter(ItemModel.parent_type == parent_type.value)
           logger.debug(f"Filtrando também por parent_type = {parent_type.value}")

        return query.all()

    def get_new_version(self, existing_items: list) -> int:
        """Calcula a nova versão com base nos itens existentes."""
        return max((item.version or 0) for item in existing_items) + 1 if existing_items else 1


    def deactivate_existing_items(self, db: Session, items: list, task_type: TaskType):
        """Desativa itens existentes e suas ações (se for TestCase)."""
        if not items: return
        logger.info(f"Desativando {len(items)} item(ns) existente(s) do tipo {task_type.value}")
        now = datetime.now()
        for item in items:
            item.is_active = False
            item.updated_at = now
            if task_type == TaskType.TEST_CASE and hasattr(item, 'actions'):
                 # Desativar ações associadas
                 self.db.query(Action).filter(Action.test_case_id == item.id, Action.is_active == True).update({"is_active": False})
                 # logger.debug(f"Ações desativadas para TestCase ID {item.id}") # Logar pode ser verboso


    def update_request_status(self, request_id: str, status: Status, error_message: str = None):
        """Atualiza o status da requisição no banco de dados."""
        logger.info(f"Atualizando status para ReqID: {request_id} => {status.value}")
        try:
            # Usar with self.db.begin_nested() talvez? Ou garantir sessão separada?
            # Por enquanto, assume que a sessão principal está ok.
            db_request = self.db.query(Request).filter(Request.request_id == request_id).with_for_update().first() # Lock para update
            if db_request:
                db_request.status = status.value
                db_request.updated_at = datetime.now()
                if status == Status.COMPLETED:
                    db_request.processed_at = datetime.now()
                if status == Status.FAILED:
                    db_request.error_message = error_message if error_message else "Falha no processamento"
                # Commit é feito externamente ou precisa ser feito aqui? 🤔
                # O fluxo atual sugere que o commit principal é feito após _process_item
                # mas para falhas, precisamos commitar a atualização de status.
                # Vamos commitar aqui explicitamente para garantir a atualização do status em caso de falha.
                self.db.commit()
                logger.info(f"Status atualizado e commitado para ReqID: {request_id}")
            else:
                logger.warning(f"Requisição {request_id} não encontrada para atualização de status.")
        except Exception as e:
            logger.error(f"Erro ao atualizar status para ReqID {request_id}: {e}", exc_info=True)
            self.db.rollback() # Rollback da tentativa de atualização de status


    def send_notification(self, request_id: str, project_id: Optional[UUID], parent: Optional[str],
                          parent_type: Optional[str], task_type: str, status: Status,
                          error_message: Optional[str], item_ids: Optional[List[int]] = None,
                          version: Optional[int] = None, work_item_id: Optional[str] = None,
                          parent_board_id: Optional[str] = None, is_reprocessing: bool = False):
        """Envia notificação para o RabbitMQ."""
        project_id_str = str(project_id) if project_id else None
        notification_data = {
            "request_id": request_id, "project_id": project_id_str, "parent": parent,
            "parent_type": parent_type, "task_type": task_type, "status": status.value,
            "error_message": error_message, "item_ids": item_ids if item_ids is not None else [],
            "version": version, "work_item_id": work_item_id, "parent_board_id": parent_board_id,
            "is_reprocessing": is_reprocessing
        }
        try:
            self.producer.publish(notification_data, rabbitmq.NOTIFICATION_QUEUE)
            logger.info(f"Notificação enviada para ReqID: {request_id}")
        except Exception as e:
            logger.error(f"Falha CRÍTICA ao enviar notificação para ReqID {request_id}: {e}", exc_info=True)
            # O que fazer aqui? O status no DB pode estar COMPLETED ou FAILED.
            # Retentar aqui é complicado sem saber o estado da transação principal.
            # Confiar no retry do publish e no monitoramento.


    # --- Handlers de Erro (Refatorados para usar _handle_failure) ---

    def _handle_failure(self, request_id: str, db_request: Optional[Request], task_type: TaskType,
                        error: Exception, status_code: Status = Status.FAILED,
                        rollback: bool = True, log_traceback: bool = True,
                        work_item_id: Optional[str] = None, parent_board_id: Optional[str] = None,
                        project_id: Optional[UUID] = None):
        """Método centralizado para lidar com falhas no processamento."""
        error_message = f"Falha no processamento: {error.__class__.__name__}: {str(error)[:500]}" # Limita tamanho da msg
        logger.error(f"{error_message} para ReqID: {request_id}", exc_info=log_traceback)

        if rollback: # Tentar rollback se aplicável
            try:
                # Verificar se a sessão está ativa antes de rollback
                if self.db.is_active:
                     self.db.rollback()
                     logger.info(f"Rollback realizado para ReqID: {request_id}")
            except Exception as rb_exc:
                logger.error(f"Erro durante o rollback para ReqID {request_id}: {rb_exc}", exc_info=True)

        # Tentar atualizar o status no DB (já faz commit interno)
        self.update_request_status(request_id, status_code, error_message)

        # Tentar enviar notificação
        parent_from_req = db_request.parent if db_request else None
        parent_type_from_req = None # Precisaria buscar o parent_type da request ou do item
        # Se db_request existe, tenta pegar o parent_type dele (se adicionarmos a coluna)
        if db_request and hasattr(db_request, 'parent_type'): parent_type_from_req = db_request.parent_type

        self.send_notification(
            request_id=request_id,
            project_id=project_id,
            parent=parent_from_req,
            parent_type=parent_type_from_req, # Usa o tipo do pai da request se disponível
            task_type=task_type.value,
            status=status_code,
            error_message=error_message,
            item_ids=None, version=None, # Sem item_ids/version em caso de falha
            work_item_id=work_item_id,
            parent_board_id=parent_board_id,
            is_reprocessing=False # Assumir que não é reprocessamento no erro? Ou verificar artifact_id?
        )

    def _handle_initial_error(self, request_id: str, error_message: str):
         """Lida com erros que ocorrem antes de buscar db_request."""
         logger.error(f"Erro inicial para ReqID {request_id}: {error_message}")
         # Tentar enviar uma notificação mínima sem dados do DB
         try:
             producer_task = rabbitmq.RabbitMQProducer()
             notification_data = {"request_id": request_id, "status": Status.FAILED.value, "error_message": error_message}
             producer_task.publish(notification_data, rabbitmq.NOTIFICATION_QUEUE)
         except Exception as mq_exc:
             logger.error(f"Falha ao enviar notificação de erro inicial para ReqID {request_id}: {mq_exc}", exc_info=True)
         finally:
             if 'producer_task' in locals() and producer_task: producer_task.close()


    def _handle_processing_error(self, db_request: Request, task_type: TaskType, error_message: str, project_id: Optional[UUID]):
         """Lida com erros durante a fase de processamento (validação de pai, etc.)."""
         self._handle_failure(db_request.request_id, db_request, task_type, ValueError(error_message), rollback=False, project_id=project_id)


    def handle_invalid_model_error(self, request_id: str, db_request: Request, task_type: TaskType,
                                error: InvalidModelError, work_item_id: Optional[str],
                                parent_board_id: Optional[str], project_id: Optional[UUID] = None):
        self._handle_failure(request_id, db_request, task_type, error, rollback=True, work_item_id=work_item_id, parent_board_id=parent_board_id, project_id=project_id)


    def handle_parsing_error(self, request_id: str, db_request: Request, task_type: TaskType,
                            error: Exception, generated_text: str, work_item_id: Optional[str],
                            parent_board_id: Optional[str], project_id: Optional[UUID] = None):
        logger.debug(f"Resposta problemática para ReqID {request_id}: {generated_text[:500]}...") # Log específico do parsing
        self._handle_failure(request_id, db_request, task_type, error, rollback=True, work_item_id=work_item_id, parent_board_id=parent_board_id, project_id=project_id)


    def handle_integrity_error(self, request_id: str, db_request: Request, task_type: TaskType,
                            error: IntegrityError, work_item_id: Optional[str],
                            parent_board_id: Optional[str], project_id: Optional[UUID] = None):
        self._handle_failure(request_id, db_request, task_type, error, rollback=True, work_item_id=work_item_id, parent_board_id=parent_board_id, project_id=project_id)


    def handle_amqp_connection_error(self, request_id: str, db_request: Request, task_type: TaskType,
                                    error: pika.exceptions.AMQPConnectionError, work_item_id: Optional[str],
                                    parent_board_id: Optional[str], project_id: Optional[UUID] = None):
        # Erro AMQP é especial, o status no DB pode já ter sido commitado (COMPLETED ou FAILED anterior)
        error_message = f"Erro de conexão com RabbitMQ: {error}"
        logger.error(f"{error_message} para ReqID: {request_id}", exc_info=True)
        # Tentamos atualizar status para FAILED (pode não mudar se já for FAILED, ou sobrescrever COMPLETED)
        self.update_request_status(request_id, Status.FAILED, error_message)
        # A notificação de erro provavelmente falhará de novo, mas tentamos.
        # send_notification é chamado dentro de _handle_failure se usássemos ele,
        # mas aqui chamamos diretamente para clareza da situação especial.
        self.send_notification(
            request_id=request_id, project_id=project_id, parent=db_request.parent if db_request else None,
            parent_type=None, # Não temos certeza do tipo aqui
            task_type=task_type.value, status=Status.FAILED, error_message=error_message,
            work_item_id=work_item_id, parent_board_id=parent_board_id
        )

    def handle_generic_error(self, request_id: str, db_request: Request, task_type: TaskType,
                            error: Exception, work_item_id: Optional[str],
                            parent_board_id: Optional[str], project_id: Optional[UUID] = None):
        self._handle_failure(request_id, db_request, task_type, error, rollback=True, work_item_id=work_item_id, parent_board_id=parent_board_id, project_id=project_id)


    def close_resources(self):
        """Fecha conexões com recursos externos."""
        if self.db and self.db.is_active:
            try:
                self.db.close()
                logger.debug("Conexão com banco de dados fechada")
            except Exception as e:
                logger.error(f"Erro ao fechar conexão com banco: {e}", exc_info=True)
        if self.producer:
            try:
                self.producer.close()
            except Exception as e:
                logger.error(f"Erro ao fechar conexão com RabbitMQ: {e}", exc_info=True)
