# reprocessing.py
from typing import List, Optional, Tuple
from app.workers.processors.base import WorkItemProcessor
from app.models import Status, TaskType, Epic, Feature, UserStory, Task, TestCase, WBS, Bug, Issue, PBI, Action
from datetime import datetime
import logging
from uuid import UUID

logger = logging.getLogger(__name__)

class WorkItemReprocessor(WorkItemProcessor):
    def _process_item(
        self,
        task_type_enum: TaskType,
        parent: Optional[int], # ID do pai hierárquico original (pode ser None)
        prompt_tokens: int,
        completion_tokens: int,
        work_item_id: Optional[str],
        parent_board_id: Optional[str],
        generated_text: str,
        artifact_id: Optional[int] = None, # ID do item sendo reprocessado (não pode ser None aqui)
        project_id: Optional[UUID] = None, # UUID do projeto (obtido do item existente)
        parent_type: Optional[TaskType] = None # Tipo do pai hierárquico original (pode ser None)
        # Adicionei parent_type aqui para consistência, embora não seja usado diretamente na lógica abaixo
    ) -> Tuple[List[int], int]:
        """
        Reprocessa um artefato existente, atualizando seus campos com base no texto gerado.
        Acumula tokens e incrementa a versão.

        Args:
            task_type_enum: O tipo do artefato sendo reprocessado.
            parent: O ID do pai hierárquico original (informativo).
            prompt_tokens: Tokens do prompt desta chamada LLM.
            completion_tokens: Tokens da completion desta chamada LLM.
            work_item_id: ID do item no Azure DevOps (se houver).
            parent_board_id: ID do quadro pai no Azure DevOps (se houver).
            generated_text: O texto JSON gerado pela LLM.
            artifact_id: O ID do artefato no banco de dados a ser atualizado.
            project_id: O UUID do projeto associado (informativo).
            parent_type: O tipo do pai hierárquico original (informativo).
        Returns:
            Uma tupla contendo uma lista com o ID do item atualizado e a nova versão.
        Raises:
            ValueError: Se o artifact_id for None ou o item não for encontrado.
        """
        logger.info(f"Iniciando _process_item para reprocessar {task_type_enum.value} ID: {artifact_id}")

        if artifact_id is None:
            raise ValueError("artifact_id não pode ser None para reprocessamento.")

        # Busca o item existente no banco de dados
        existing_item = self._get_existing_item(task_type_enum, artifact_id)
        if not existing_item:
            # Este erro deve ser tratado no método 'process' que chama este
            raise ValueError(f"Item do tipo {task_type_enum.value} com ID {artifact_id} não encontrado para reprocessamento.")

        # Determina o ID do pai a ser passado para o parser (pode ser necessário para contexto)
        # Usamos o pai armazenado no próprio item existente.
        parent_id_for_parser: Optional[int] = None
        if hasattr(existing_item, 'parent') and existing_item.parent is not None:
             parent_id_for_parser = existing_item.parent
        elif task_type_enum == TaskType.EPIC and hasattr(existing_item, 'team_project_id'):
             parent_id_for_parser = existing_item.team_project_id # Ou project_id? Verificar semântica.

        # Parseia a resposta da LLM usando o parser de reprocessamento apropriado
        # O parser retorna um dicionário com os campos atualizados
        updated_data = self._parse_updated_item(
            task_type=task_type_enum,
            generated_text=generated_text,
            parent_id=parent_id_for_parser, # Passa o pai do item existente
            prompt_tokens=prompt_tokens, # Passa tokens para consistência, embora parser pode não usar
            completion_tokens=completion_tokens
        )

        # Atualiza os campos comuns: acumula tokens, incrementa versão, atualiza timestamp
        existing_item.prompt_tokens = (existing_item.prompt_tokens or 0) + prompt_tokens
        existing_item.completion_tokens = (existing_item.completion_tokens or 0) + completion_tokens
        existing_item.version += 1
        existing_item.updated_at = datetime.now()
        # Atualiza work_item_id e parent_board_id se foram fornecidos na request de reprocessamento
        if work_item_id is not None: existing_item.work_item_id = work_item_id
        if parent_board_id is not None: existing_item.parent_board_id = parent_board_id

        # Atualiza campos específicos com base no tipo de artefato
        logger.debug(f"Atualizando campos específicos para {task_type_enum.value} ID: {artifact_id}")
        if task_type_enum == TaskType.FEATURE:
            existing_item.title = updated_data.get("title", existing_item.title)
            existing_item.description = updated_data.get("description", existing_item.description)
            # Formata a lista de AC (se existir) para string antes de salvar
            ac_list = updated_data.get("acceptance_criteria") # Parser retorna lista ou None
            if isinstance(ac_list, list):
                existing_item.acceptance_criteria = "\n".join(f"- {item}" for item in ac_list)
            elif ac_list is None:
                existing_item.acceptance_criteria = None
            else: # Se não for lista nem None
                logger.warning(f"Formato inesperado para acceptance_criteria no reprocessamento de Feature: {type(ac_list)}. Tentando salvar como string.")
                existing_item.acceptance_criteria = str(ac_list)
            existing_item.summary = updated_data.get("summary", existing_item.summary)

        elif task_type_enum == TaskType.TEST_CASE:
            existing_item.title = updated_data.get("title", existing_item.title)
            existing_item.gherkin = updated_data.get("gherkin", existing_item.gherkin) # Parser retorna JSON stringificado? Confirmar.
            existing_item.priority = updated_data.get("priority", existing_item.priority)
            self._update_actions(existing_item, updated_data.get("actions", [])) # Parser retorna lista de dicts

        elif task_type_enum == TaskType.WBS:
            existing_item.wbs = updated_data.get("wbs", existing_item.wbs) # Parser retorna JSON (dict/list)

        # Adicionar elif para outros tipos que precisam de tratamento especial (Bug, Issue, PBI, UserStory, Task se tiverem campos além de title/desc)
        elif task_type_enum == TaskType.USER_STORY:
             existing_item.title = updated_data.get("title", existing_item.title)
             existing_item.description = updated_data.get("description", existing_item.description)
             # User Story também tem acceptance_criteria, tratar igual Feature
             ac_list_us = updated_data.get("acceptance_criteria")
             if isinstance(ac_list_us, list):
                 existing_item.acceptance_criteria = "\n".join(f"- {item}" for item in ac_list_us)
             elif ac_list_us is None:
                 existing_item.acceptance_criteria = None
             else:
                 logger.warning(f"Formato inesperado para acceptance_criteria no reprocessamento de UserStory: {type(ac_list_us)}. Tentando salvar como string.")
                 existing_item.acceptance_criteria = str(ac_list_us)
             existing_item.priority = updated_data.get("priority", existing_item.priority) # Adicionar priority ao parser de US update

        elif task_type_enum == TaskType.TASK:
             existing_item.title = updated_data.get("title", existing_item.title)
             existing_item.description = updated_data.get("description", existing_item.description)
             existing_item.estimate = updated_data.get("estimate", existing_item.estimate) # Adicionar estimate ao parser de Task update

        # ... (adicionar lógica para Bug, Issue, PBI se necessário) ...

        # Caso Padrão (inclui Epic, e outros não tratados acima)
        else:
            existing_item.title = updated_data.get("title", existing_item.title)
            existing_item.description = updated_data.get("description", existing_item.description)
            # Campos específicos do Epic
            if task_type_enum == TaskType.EPIC:
                existing_item.tags = updated_data.get("tags", existing_item.tags) # Parser retorna lista
                existing_item.summary = updated_data.get("summary", existing_item.summary)
                existing_item.reflection = updated_data.get("reflection", existing_item.reflection) # Parser retorna dict/JSON

        # O commit é feito no método 'process' após esta função retornar
        self.db.flush() # Envia as alterações pendentes para o DB
        logger.info(f"_process_item concluído para {task_type_enum.value} ID: {artifact_id}. Nova versão: {existing_item.version}")
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
