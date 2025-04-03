# app/workers/processors/creation.py
from typing import List, Optional, Tuple
from app.workers.processors.base import WorkItemProcessor
from app.models import Status, TaskType, Epic, Feature, UserStory, Task, TestCase, WBS, Bug, Issue, PBI, Action
from app.utils import parsers
from sqlalchemy.orm import Session
import logging
from datetime import datetime

logger = logging.getLogger(__name__)

class WorkItemCreator(WorkItemProcessor):
    def _process_item(self, task_type_enum: TaskType, parent: int, prompt_tokens: int, completion_tokens: int,
                      work_item_id: Optional[int], parent_board_id: Optional[int], generated_text: str,
                      artifact_id: Optional[int] = None) -> Tuple[List[int], int]:
        """
        Processa a criação de um novo artefato (Epic, Feature, etc.).
        """
        # Lógica existente para criação de novos itens (mantida igual)
        existing_items = self.get_existing_items(self.db, task_type_enum, parent)
        new_version = self.get_new_version(existing_items)
        self.deactivate_existing_items(self.db, existing_items, task_type_enum)

        item_ids = self.create_new_items(
            self.db, task_type_enum, generated_text, parent,
            prompt_tokens, completion_tokens, new_version, work_item_id, parent_board_id
        )

        return item_ids, new_version

    def create_new_items(self, db: Session, task_type: TaskType, generated_text: str, parent: int,
                         prompt_tokens: int, completion_tokens: int, version: int,
                         work_item_id: Optional[str], parent_board_id: Optional[str]) -> List[int]:
        """
        Cria novos itens no banco de dados com base no tipo de tarefa e no texto gerado pela LLM.
        Retorna uma lista de IDs dos itens criados.
        """
        # Mapeamento de parsers e modelos para cada tipo de tarefa
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
            TaskType.AUTOMATION_SCRIPT: (parsers.parse_automation_script_response, None), # Parser retorna string, não modelo
        }

        # Obtém o parser e o modelo correspondente ao tipo de tarefa
        parser, model = parser_map[task_type]
        item_ids = [] # Lista para armazenar IDs dos itens criados/atualizados

        # --- Caso especial para AUTOMATION_SCRIPT ---
        if task_type == TaskType.AUTOMATION_SCRIPT:
            logger.info(f"Processando AUTOMATION_SCRIPT para TestCase ID: {parent}")
            try:
                # Parseia o script (o parser recebe tokens mas só retorna string)
                # A função parser aqui é parse_automation_script_response
                automation_script = parser(generated_text, prompt_tokens, completion_tokens)

                # Busca o TestCase pai usando o ID passado como 'parent'
                parent_test_case = db.query(TestCase).filter(TestCase.id == parent).first()

                if parent_test_case:
                    # Atualiza o conteúdo do script no TestCase pai
                    parent_test_case.script = automation_script

                    # *** CORREÇÃO: ATUALIZA OS TOKENS NO TESTCASE PAI ***
                    # Soma os novos tokens aos existentes (ou inicia com 0 se for None)
                    parent_test_case.prompt_tokens = (parent_test_case.prompt_tokens or 0) + prompt_tokens
                    parent_test_case.completion_tokens = (parent_test_case.completion_tokens or 0) + completion_tokens
                    # Atualiza o timestamp de modificação
                    parent_test_case.updated_at = datetime.now()

                    logger.info(f"Script e Tokens atualizados para TestCase ID {parent}: prompt={prompt_tokens}, completion={completion_tokens}")

                    # Não precisa de add(), pois estamos modificando um objeto existente
                    db.flush() # Garante que as alterações sejam enviadas ao DB antes do refresh
                    db.refresh(parent_test_case) # Sincroniza o estado do objeto com o DB
                    item_ids.append(parent_test_case.id) # Adiciona o ID do TestCase atualizado
                    # Retorna a lista contendo o ID do TestCase pai atualizado
                    return item_ids
                else:
                    # Caso o TestCase pai não seja encontrado
                    error_message = f"TestCase pai com ID {parent} não encontrado para Automation Script."
                    logger.error(error_message)
                    # Lança a exceção para ser tratada no método process()
                    raise ValueError(error_message)
            except ValueError as e:
                 # Captura erro do parser ou do TestCase não encontrado
                 logger.error(f"Erro ao processar Automation Script para TestCase ID {parent}: {e}", exc_info=True)
                 raise # Re-lança a exceção

        # --- Caso especial para EPIC ---
        elif task_type == TaskType.EPIC:
            # O parser parse_epic_response recebe (response, prompt_tokens, completion_tokens)
            new_epic = parser(generated_text, prompt_tokens, completion_tokens)
            new_epic.version = version
            new_epic.is_active = True
            # No caso de Epic, 'parent' representa o team_project_id
            new_epic.team_project_id = parent
            new_epic.work_item_id = work_item_id
            new_epic.parent_board_id = parent_board_id
            # Não precisa setar created_at/updated_at aqui, o DB faz isso via server_default/onupdate
            db.add(new_epic)
            db.flush() # Envia o comando INSERT para o DB e obtém o ID gerado
            db.refresh(new_epic) # Atualiza o objeto new_epic com o ID e outros defaults do DB
            item_ids.append(new_epic.id)
            # Retorna a lista contendo o ID do novo Epic
            return item_ids

        # --- Caso especial para WBS ---
        elif task_type == TaskType.WBS:
            # O parser parse_wbs_response recebe (response, parent_id, prompt_tokens, completion_tokens)
            new_wbs = parser(generated_text, parent, prompt_tokens, completion_tokens)
            new_wbs.version = version
            new_wbs.is_active = True
            # No caso de WBS, 'parent' é a FK para o Epic pai
            new_wbs.parent = parent
            new_wbs.work_item_id = work_item_id
            new_wbs.parent_board_id = parent_board_id
            db.add(new_wbs)
            db.flush()
            db.refresh(new_wbs)
            item_ids.append(new_wbs.id)
            # Retorna a lista contendo o ID da nova WBS
            return item_ids

        # --- Caso geral para FEATURE, USER_STORY, TASK, TEST_CASE, BUG, ISSUE, PBI ---
        else:
            # Para os outros tipos, os parsers geralmente retornam uma lista de objetos
            # A assinatura padrão dos parsers é (response, parent_id, prompt_tokens, completion_tokens)

            # Não precisa buscar itens existentes aqui, isso já foi feito em _process_item
            # que chamou get_existing_items e deactivate_existing_items

            # Parseia os novos itens (pode retornar uma lista)
            new_items = parser(generated_text, parent, prompt_tokens, completion_tokens)

            # Certifica que new_items seja sempre uma lista para iterar
            if not isinstance(new_items, list):
                # Se o parser retornou um único objeto, coloca-o em uma lista
                # (Embora a maioria dos parsers já retorne lista, é bom garantir)
                 if new_items is not None: # Verifica se não é None
                     new_items = [new_items]
                 else:
                     new_items = [] # Se for None, define como lista vazia


            # Configura os novos itens antes de adicionar ao banco
            for item in new_items:
                # Define os campos comuns para todos os novos itens
                item.version = version
                item.is_active = True
                # 'parent' já foi definido dentro do parser para esses tipos
                item.work_item_id = work_item_id
                item.parent_board_id = parent_board_id

                # Lógica específica para TEST_CASE: configurar Actions
                if task_type == TaskType.TEST_CASE and hasattr(item, 'actions'):
                    for action in item.actions:
                        # Define a versão e o status ativo para cada nova Action
                        action.version = version
                        action.is_active = True
                        # A FK test_case_id será definida automaticamente pelo relacionamento SQLAlchemy

            # Adiciona todos os novos itens à sessão do banco de dados
            if new_items: # Verifica se a lista não está vazia
                 db.add_all(new_items)
                 db.flush() # Envia os comandos INSERT para o DB e obtém os IDs

                 # Coleta os IDs dos novos itens criados
                 item_ids.extend([item.id for item in new_items if hasattr(item, 'id')])

            # Retorna a lista de IDs dos novos itens criados
            return item_ids
