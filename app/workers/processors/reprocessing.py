# reprocessing.py
from typing import List, Optional, Tuple
from app.workers.processors.base import WorkItemProcessor
from app.models import Status, TaskType, Epic, Feature, UserStory, Task, TestCase, WBS, Bug, Issue, PBI, Action
from datetime import datetime
import logging

logger = logging.getLogger(__name__)

class WorkItemReprocessor(WorkItemProcessor):
    def _process_item(
        self,
        task_type_enum: TaskType,
        parent: int,  # Agora recebe o parent corretamente
        prompt_tokens: int,
        completion_tokens: int,
        work_item_id: Optional[int],
        parent_board_id: Optional[int],
        generated_text: str,
        artifact_id: Optional[int] = None  # Recebe o artifact_id
    ) -> Tuple[List[int], int]:
        """
        Reprocessa um artefato existente, atualizando seus campos.
        Atualiza os campos comuns e específicos de cada tipo sem criar registros duplicados.
        """
        existing_item = self._get_existing_item(task_type_enum, artifact_id)
        
        if not existing_item:
            raise ValueError(f"Item do tipo {task_type_enum} com ID {artifact_id} não encontrado.")

        # Determina o parent_id correto
        parent_id = existing_item.team_project_id if task_type_enum == TaskType.EPIC else existing_item.parent

        # Extrai os dados atualizados via parser de reprocessamento (retorna um dicionário)
        updated_data = self._parse_updated_item(
            task_type_enum, generated_text, parent_id, prompt_tokens, completion_tokens
        )

        # Atualiza os campos comuns (tokens, versão e data)
        existing_item.prompt_tokens += prompt_tokens
        existing_item.completion_tokens += completion_tokens
        existing_item.version += 1
        existing_item.updated_at = datetime.now()

        # Atualiza campos específicos conforme o tipo do artefato
        if task_type_enum == TaskType.TEST_CASE:
            # TestCase: possui title, gherkin, priority e actions (não possui description)
            existing_item.title = updated_data.get("title", existing_item.title)
            existing_item.gherkin = updated_data.get("gherkin", existing_item.gherkin)
            existing_item.priority = updated_data.get("priority", existing_item.priority)
            self._update_actions(existing_item, updated_data.get("actions", []))
        elif task_type_enum == TaskType.WBS:
            # WBS: possui apenas o campo 'wbs'
            existing_item.wbs = updated_data.get("wbs", existing_item.wbs)
        else:
            # Demais artefatos: possuem title e description
            existing_item.title = updated_data.get("title", existing_item.title)
            existing_item.description = updated_data.get("description", existing_item.description)
            if task_type_enum == TaskType.EPIC:
                existing_item.tags = updated_data.get("tags", existing_item.tags)
                existing_item.summary = updated_data.get("summary", existing_item.summary)
                existing_item.reflection = updated_data.get("reflection", existing_item.reflection)

        self.db.commit()
        return [existing_item.id], existing_item.version

    def _get_existing_item(self, task_type: TaskType, artifact_id: int):
        """
        Retorna o item existente com base no tipo e ID.
        """
        model_map = {
            TaskType.EPIC: Epic,
            TaskType.FEATURE: Feature,
            TaskType.USER_STORY: UserStory,
            TaskType.TASK: Task,
            TaskType.BUG: Bug,
            TaskType.ISSUE: Issue,
            TaskType.PBI: PBI,
            TaskType.TEST_CASE: TestCase,
            TaskType.WBS: WBS,
        }
        model = model_map.get(task_type)
        if model is None:
            raise ValueError(f"Modelo para {task_type} não encontrado.")
        return self.db.query(model).filter_by(id=artifact_id).first()

    def _parse_updated_item(
        self,
        task_type: TaskType,
        generated_text: str,
        parent_id: int,
        prompt_tokens: int,
        completion_tokens: int
    ) -> dict:
        """
        Utiliza o parser de reprocessamento para extrair os dados atualizados do artefato.
        Retorna um dicionário com os campos necessários para atualizar o registro.
        """
        from app.utils import parsers_reprocessing as prp
        parser_map = {
            TaskType.EPIC: prp.parse_epic_update,
            TaskType.FEATURE: prp.parse_feature_update,
            TaskType.USER_STORY: prp.parse_user_story_update,
            TaskType.TASK: prp.parse_task_update,
            TaskType.BUG: prp.parse_bug_update,
            TaskType.ISSUE: prp.parse_issue_update,
            TaskType.PBI: prp.parse_pbi_update,
            TaskType.TEST_CASE: prp.parse_test_case_update,
            TaskType.WBS: prp.parse_wbs_update,
            TaskType.AUTOMATION_SCRIPT: prp.parse_automation_script_update,
        }
        parser = parser_map.get(task_type)
        if not parser:
            raise ValueError(f"Parser para {task_type} não encontrado.")
        return parser(generated_text)

    def _update_actions(self, test_case: TestCase, new_actions: List[dict]):
        """
        Atualiza as ações de um TestCase existente com base nos dados do dicionário.
        Remove as ações antigas e adiciona as novas, evitando duplicação.
        """
        # Remove as ações antigas
        for action in list(test_case.actions):
            self.db.delete(action)
        test_case.actions.clear()
        from app.models import Action
        for action_data in new_actions:
            new_action = Action(
                step=action_data.get("step"),
                expected_result=action_data.get("expected_result")
            )
            test_case.actions.append(new_action)
