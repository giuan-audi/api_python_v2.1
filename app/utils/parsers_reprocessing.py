# parsers_reprocessing.py
import json
import re
import logging
from typing import Dict, Any
from pydantic import ValidationError
from app.schemas.schemas import (
    EpicResponse, FeatureResponse, UserStoryResponse, TaskResponse,
    BugResponse, IssueResponse, PBIResponse, TestCaseResponse, WBSResponse, AutomationScriptResponse
)

logger = logging.getLogger(__name__)

def parse_epic_update(response: str) -> dict:
    """
    Processa a resposta para atualizar um Epic e retorna um dicionário com os dados.
    """
    try:
        data = json.loads(response)
        validated = EpicResponse(**data)
        return {
            "title": validated.title,
            "description": validated.description,
            "tags": validated.tags,
            "summary": validated.summary if hasattr(validated, "summary") else None,
            "reflection": validated.reflection
        }
    except (json.JSONDecodeError, ValidationError) as e:
        raise ValueError(f"Erro ao parsear Epic para reprocessamento: {e}")

def parse_feature_update(response: str) -> Dict[str, Any]:
    """
    Processa a resposta JSON da LLM para atualização de uma Feature.
    Espera que 'acceptance_criteria' no JSON seja uma lista de strings.
    Retorna um dicionário com os dados validados, incluindo a lista de acceptance_criteria.

    Args:
        response: A string JSON retornada pela LLM.

    Returns:
        Um dicionário contendo os dados atualizados da Feature.

    Raises:
        ValueError: Se ocorrer um erro durante o parsing ou validação.
    """
    logger.debug("Parsing Feature response para reprocessamento.")
    try:
        data = json.loads(response)
        # Lida com resposta sendo um objeto único ou uma lista (pega o primeiro)
        if isinstance(data, list):
            if not data:
                raise ValueError("Resposta JSON para atualização de Feature está vazia.")
            data = data[0]
        elif not isinstance(data, dict):
             raise ValueError(f"Formato de resposta inválido para atualização de Feature. Esperava lista ou objeto, recebeu {type(data)}.")

        # Valida os dados usando o schema FeatureResponse atualizado
        validated = FeatureResponse(**data)

        # Cria o dicionário com os dados validados
        update_dict = {
            "title": validated.title,
            "description": validated.description,
            # Retorna a lista (ou None) diretamente. O processador formatará.
            "acceptance_criteria": validated.acceptance_criteria,
            "summary": validated.summary # Será None se não existir no schema/resposta
        }
        logger.info("Parsing de atualização de Feature concluído com sucesso.")
        return update_dict

    except ValidationError as e:
        error_message = f"Erro de validação Pydantic ao parsear Feature para reprocessamento: {e}"
        logger.error(error_message, exc_info=True)
        logger.debug(f"Resposta JSON problemática (Update Feature): {response}")
        raise ValueError(error_message) from e
    except json.JSONDecodeError as e:
        error_message = f"Erro ao decodificar JSON da resposta de Feature para reprocessamento: {e}"
        logger.error(error_message, exc_info=True)
        logger.debug(f"Resposta JSON problemática (Update Feature): {response}")
        raise ValueError(error_message) from e
    except Exception as e: # Captura outros erros inesperados
        error_message = f"Erro inesperado ao parsear Feature para reprocessamento: {str(e)}"
        logger.error(error_message, exc_info=True)
        raise ValueError(error_message) from e

def parse_user_story_update(response: str) -> dict:
    """
    Processa a resposta para atualizar uma User Story e retorna um dicionário com os dados.
    """
    try:
        data = json.loads(response)
        if isinstance(data, list):
            data = data[0]
        validated = UserStoryResponse(**data)
        return {
            "title": validated.title,
            "description": validated.description,
            "acceptance_criteria": validated.acceptance_criteria,
            "priority": validated.priority
        }
    except (json.JSONDecodeError, ValidationError) as e:
        raise ValueError(f"Erro ao parsear User Story para reprocessamento: {e}")

def parse_task_update(response: str) -> dict:
    """
    Processa a resposta para atualizar uma Task e retorna um dicionário com os dados.
    """
    try:
        data = json.loads(response)
        if isinstance(data, list):
            data = data[0]
        validated = TaskResponse(**data)
        return {
            "title": validated.title,
            "description": validated.description,
            "estimate": validated.estimate
        }
    except (json.JSONDecodeError, ValidationError) as e:
        raise ValueError(f"Erro ao parsear Task para reprocessamento: {e}")

def parse_bug_update(response: str) -> dict:
    """
    Processa a resposta para atualizar um Bug e retorna um dicionário com os dados.
    """
    try:
        data = json.loads(response)
        if isinstance(data, list):
            data = data[0]
        validated = BugResponse(**data)
        return {
            "title": validated.title,
            "description": validated.description
            # Inclua outros campos se necessário
        }
    except (json.JSONDecodeError, ValidationError) as e:
        raise ValueError(f"Erro ao parsear Bug para reprocessamento: {e}")

def parse_issue_update(response: str) -> dict:
    """
    Processa a resposta para atualizar uma Issue e retorna um dicionário com os dados.
    """
    try:
        data = json.loads(response)
        if isinstance(data, list):
            data = data[0]
        validated = IssueResponse(**data)
        return {
            "title": validated.title,
            "description": validated.description
            # Inclua outros campos se necessário
        }
    except (json.JSONDecodeError, ValidationError) as e:
        raise ValueError(f"Erro ao parsear Issue para reprocessamento: {e}")

def parse_pbi_update(response: str) -> dict:
    """
    Processa a resposta para atualizar um PBI e retorna um dicionário com os dados.
    """
    try:
        data = json.loads(response)
        if isinstance(data, list):
            data = data[0]
        validated = PBIResponse(**data)
        return {
            "title": validated.title,
            "description": validated.description
            # Inclua outros campos se necessário
        }
    except (json.JSONDecodeError, ValidationError) as e:
        raise ValueError(f"Erro ao parsear PBI para reprocessamento: {e}")

def parse_test_case_update(response: str) -> dict:
    """
    Processa a resposta para atualizar um TestCase e retorna um dicionário com os dados,
    incluindo a lista de ações.
    """
    try:
        data = json.loads(response)
        if isinstance(data, list):
            data = data[0]
        validated = TestCaseResponse(**data)
        return {
            "title": validated.title,
            "gherkin": json.dumps(validated.gherkin),
            "priority": validated.priority,
            "actions": [
                {"step": action.step, "expected_result": action.expected_result}
                for action in validated.actions
            ]
        }
    except (json.JSONDecodeError, ValidationError) as e:
        raise ValueError(f"Erro ao parsear TestCase para reprocessamento: {e}")

def parse_wbs_update(response: str) -> dict:
    """
    Processa a resposta para atualizar um WBS e retorna um dicionário com os dados.
    """
    try:
        data = json.loads(response)
        if isinstance(data, list):
            data = data[0]
        validated = WBSResponse(**data)
        return {
            "wbs": validated.wbs
        }
    except (json.JSONDecodeError, ValidationError) as e:
        raise ValueError(f"Erro ao parsear WBS para reprocessamento: {e}")

def parse_automation_script_update(response: str) -> dict:
    """
    Processa a resposta para atualizar um script de automação, extraindo o script limpo.
    O script deve estar contido dentro de um bloco de comentário (/* ... */).
    """
    try:
        if not re.match(r'^/\*.*\*/$', response, re.DOTALL):
            raise ValueError("Script deve estar dentro de um comentário de bloco /* */")
        # Remove os delimitadores de comentário
        clean_script = re.sub(r'^/\*|\*/$', '', response, flags=re.DOTALL).strip()
        # Valida o script com o schema
        AutomationScriptResponse(script=clean_script)
        return {"script": clean_script}
    except (ValueError, ValidationError) as e:
        raise ValueError(f"Erro ao parsear Automation Script para reprocessamento: {e}")
