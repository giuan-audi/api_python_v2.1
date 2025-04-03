# app/workers/processors/creation.py
from typing import List, Optional, Tuple
from app.workers.processors.base import WorkItemProcessor
from app.models import Status, TaskType, Epic, Feature, UserStory, Task, TestCase, WBS, Bug, Issue, PBI, Action
from app.utils import parsers
from sqlalchemy.orm import Session
import logging

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
                     work_item_id: Optional[int], parent_board_id: Optional[int]) -> List[int]:
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
            TaskType.AUTOMATION_SCRIPT: (parsers.parse_automation_script_response, None),
        }

        # Obtém o parser e o modelo correspondente ao tipo de tarefa
        parser, model = parser_map[task_type]
        item_ids = []

        # --- Caso especial para AUTOMATION_SCRIPT ---
        if task_type == TaskType.AUTOMATION_SCRIPT:
            logger.info(f"Processando AUTOMATION_SCRIPT: {generated_text}")
            automation_script = parser(generated_text, prompt_tokens, completion_tokens) # <--- Parse o script

            # *** ENCONTRE O TEST CASE PAI ***
            parent_test_case = db.query(TestCase).filter(TestCase.id == parent).first() # <--- Assumindo que 'parent' é o ID do TestCase
            if parent_test_case: # *** VERIFIQUE SE O TEST CASE PAI EXISTE ***
                parent_test_case.script = automation_script # <--- Salve o script no TestCase PAI
                db.flush() # *** FLUSH PARA OBTER O ID ***
                db.refresh(parent_test_case) # *** REFRESH PARA SINCRONIZAR O ESTADO ***
                item_ids.append(parent_test_case.id) # <--- Adicione o ID do TestCase PAI
                return item_ids
            else: # *** TRATAMENTO DE ERRO SE O TEST CASE PAI NÃO EXISTIR ***
                error_message = f"TestCase pai com ID {parent} não encontrado para Automation Script."
                logger.error(error_message)
                raise ValueError(error_message)

        # --- Caso especial para EPIC ---
        if task_type == TaskType.EPIC:
            new_epic = parser(generated_text, prompt_tokens, completion_tokens)
            new_epic.version = version
            new_epic.is_active = True
            new_epic.team_project_id = parent  # Usa parent como team_project_id
            new_epic.work_item_id = work_item_id
            new_epic.parent_board_id = parent_board_id
            db.add(new_epic)
            db.flush()
            db.refresh(new_epic)
            item_ids.append(new_epic.id)
            return item_ids

        # --- Caso especial para WBS ---
        if task_type == TaskType.WBS:
            new_wbs = parser(generated_text, parent, prompt_tokens, completion_tokens)
            new_wbs.version = version
            new_wbs.is_active = True
            new_wbs.parent = parent  # Usa parent como parent_id
            new_wbs.work_item_id = work_item_id
            new_wbs.parent_board_id = parent_board_id
            db.add(new_wbs)
            db.flush()
            db.refresh(new_wbs)
            item_ids.append(new_wbs.id)
            return item_ids

        # --- Caso geral para FEATURE, USER_STORY, TASK, TEST_CASE, BUG, ISSUE, PBI ---
        # Obtém os itens existentes para desativá-los
        existing_items = self.get_existing_items(db, task_type, parent)
        new_version = self.get_new_version(existing_items)
        self.deactivate_existing_items(db, existing_items, task_type)

        # Parseia os novos itens
        new_items = parser(generated_text, parent, prompt_tokens, completion_tokens)

        # Configura os novos itens
        for item in new_items:
            item.version = new_version
            item.is_active = True
            item.work_item_id = work_item_id
            item.parent_board_id = parent_board_id

            # Caso especial para TEST_CASE (adiciona ações)
            if task_type == TaskType.TEST_CASE:
                for action in item.actions:
                    action.version = new_version
                    action.is_active = True

        # Adiciona os novos itens ao banco de dados
        db.add_all(new_items)
        db.flush()

        # Retorna os IDs dos novos itens
        item_ids.extend([item.id for item in new_items])
        return item_ids
