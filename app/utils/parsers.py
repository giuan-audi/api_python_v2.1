import json
from typing import List, Any, Dict
from app.models import Epic, Feature, UserStory, Task, Bug, Issue, PBI, TestCase, Action, WBS
from app.schemas.schemas import EpicResponse, FeatureResponse, UserStoryResponse, TaskResponse, BugResponse, IssueResponse, PBIResponse, TestCaseResponse, ActionResponse, WBSResponse, AutomationScriptResponse
from pydantic import ValidationError
import logging
import re

logger = logging.getLogger(__name__)

def parse_epic_response(response: str, prompt_tokens: int, completion_tokens: int) -> Epic:
    try:
        data = json.loads(response)
        validated_response = EpicResponse(**data)
        epic = Epic(
            title=validated_response.title,
            description=validated_response.description,
            tags=validated_response.tags,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            reflection=validated_response.reflection  # JSON object
        )
        # Adiciona o summary, se existir
        if hasattr(validated_response, 'summary') and validated_response.summary is not None:
            epic.summary = validated_response.summary
        return epic
    except (json.JSONDecodeError, KeyError, ValidationError) as e:
        error_message = f"Erro ao parsear resposta de Épico: {str(e)}"
        logger.error(error_message, exc_info=True)
        raise ValueError(error_message)


def parse_wbs_response(response: str, parent_id: int, prompt_tokens: int, completion_tokens: int) -> WBS:
    try:
        data = json.loads(response)
        validated_response = WBSResponse(**data)  # Usar WBSResponse
        return WBS(
            parent=parent_id,
            wbs=validated_response.wbs,  # Salva o JSON da WBS diretamente
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens
        )
    except (json.JSONDecodeError, KeyError, ValidationError) as e:
        error_message = f"Erro ao parsear resposta de WBS: {str(e)}"
        logger.error(error_message, exc_info=True)
        raise ValueError(error_message)


def parse_feature_response(response: str, parent_id: int, prompt_tokens: int, completion_tokens: int) -> List[Feature]:
    try:
        features_data = json.loads(response)

        # --- TRATAMENTO PARA LISTA OU OBJETO ÚNICO ---
        if isinstance(features_data, list):
            # Se for uma lista, processa normalmente
            validated_features = [FeatureResponse(**feat) for feat in features_data]
            features = []
            for feat in validated_features:
                new_feature = Feature(
                    parent=parent_id,
                    title=feat.title,
                    description=feat.description,
                    prompt_tokens=prompt_tokens,
                    completion_tokens=completion_tokens,
                    # reflection=feat.reflection
                )
                #Adiciona o summary
                if hasattr(feat, 'summary') and feat.summary is not None:
                    new_feature.summary = feat.summary
                features.append(new_feature)
            return features

        elif isinstance(features_data, dict):
            # Se for um único objeto, coloca em uma lista
            validated_feature = FeatureResponse(**features_data)
            feature = Feature(
                parent=parent_id,
                title=validated_feature.title,
                description=validated_feature.description,
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
                # reflection=validated_feature.reflection
            )
            #Adiciona o summary
            if hasattr(validated_feature, 'summary') and validated_feature.summary is not None:
                feature.summary = validated_feature.summary
            return [feature]  # Retorna uma lista com um único elemento

        else:
            # Se não for nem lista nem dicionário, lança um erro
            raise ValueError("Formato de resposta inválido para Feature. Esperava uma lista ou um objeto.")

    except (json.JSONDecodeError, KeyError, ValidationError) as e:
        error_message = f"Erro ao parsear resposta de Feature: {str(e)}"
        logger.error(error_message, exc_info=True)
        raise ValueError(error_message)

def parse_user_story_response(response: str, parent_id: int, prompt_tokens: int, completion_tokens: int) -> List[UserStory]:
    try:
        user_stories_data = json.loads(response)

        # --- TRATAMENTO PARA LISTA OU OBJETO ÚNICO ---
        if isinstance(user_stories_data, list):
            validated_user_stories = [UserStoryResponse(**story) for story in user_stories_data]
            return [
                UserStory(
                    parent=parent_id,
                    title=validated_story.title,
                    description=validated_story.description,
                    acceptance_criteria=validated_story.acceptance_criteria,
                    priority=validated_story.priority,  # <-- Adicionado
                    prompt_tokens=prompt_tokens,
                    completion_tokens=completion_tokens,
                ) for validated_story in validated_user_stories
            ]
        elif isinstance(user_stories_data, dict):
            validated_user_story = UserStoryResponse(**user_stories_data)
            return [UserStory(
                parent=parent_id,
                title=validated_user_story.title,
                description=validated_user_story.description,
                acceptance_criteria=validated_user_story.acceptance_criteria,
                priority=validated_user_story.priority,
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
            )]
        else:
            raise ValueError("Formato de resposta inválido para User Story. Esperava uma lista ou um objeto.")

    except (json.JSONDecodeError, KeyError, ValidationError) as e:
        error_message = f"Erro ao parsear resposta de User Story: {str(e)}"
        logger.error(error_message, exc_info=True)
        raise ValueError(error_message)

def parse_task_response(response: str, parent_id: int, prompt_tokens: int, completion_tokens: int) -> List[Task]:
    try:
        tasks_data = json.loads(response)

        if isinstance(tasks_data, list):
            validated_tasks = [TaskResponse(**task) for task in tasks_data]
            return [
                Task(
                    parent=parent_id,
                    title=validated_task.title,
                    description=validated_task.description,
                    estimate=validated_task.estimate,  # <-- Adicionado
                    prompt_tokens=prompt_tokens,
                    completion_tokens=completion_tokens,
                ) for validated_task in validated_tasks
            ]
        elif isinstance(tasks_data, dict):
            validated_task = TaskResponse(**tasks_data)
            return [Task(
                parent=parent_id,
                title=validated_task.title,
                description=validated_task.description,
                estimate=validated_task.estimate,  # <-- Adicionado
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
            )]
        else:
            raise ValueError("Formato de resposta inválido para Task. Esperava uma lista ou um objeto.")

    except (json.JSONDecodeError, KeyError, ValidationError) as e:
        error_message = f"Erro ao parsear resposta de Task: {str(e)}"
        logger.error(error_message, exc_info=True)
        raise ValueError(error_message)

# parsers.py (Exemplo para TestCase)
def parse_test_case_response(response: str, parent_id: int, prompt_tokens: int, completion_tokens: int) -> List[TestCase]:
    try:
        test_cases_data = json.loads(response)
        test_cases = []

        # Trata lista ou objeto único
        if isinstance(test_cases_data, list):
            for test_case_data in test_cases_data:
                validated_test_case = TestCaseResponse(**test_case_data)
                test_case = TestCase(
                    parent=parent_id,
                    title=validated_test_case.title,
                    gherkin=json.dumps(validated_test_case.gherkin),
                    priority=validated_test_case.priority,
                    prompt_tokens=prompt_tokens,
                    completion_tokens=completion_tokens
                )
                for action_data in validated_test_case.actions:
                    action = Action(step=action_data.step, expected_result=action_data.expected_result)
                    test_case.actions.append(action)
                test_cases.append(test_case)
        elif isinstance(test_cases_data, dict):
            validated_test_case = TestCaseResponse(**test_cases_data)
            test_case = TestCase(
                parent=parent_id,
                title=validated_test_case.title,
                gherkin=json.dumps(validated_test_case.gherkin),
                priority=validated_test_case.priority,
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens
            )
            for action_data in validated_test_case.actions:
                action = Action(step=action_data.step, expected_result=action_data.expected_result)
                test_case.actions.append(action)
            test_cases.append(test_case)
        else:
            raise ValueError("Formato inválido para TestCase.")
        
        return test_cases
    except (json.JSONDecodeError, ValidationError) as e:
        logger.error(f"Erro ao parsear TestCase: {str(e)}", exc_info=True)
        raise ValueError(f"Erro ao parsear TestCase: {str(e)}")
    

def parse_automation_script_response(generated_text: str, prompt_tokens: int, completion_tokens: int) -> str:
    """
    Extrai o script de automação do texto gerado pela LLM, validando o formato.
    Retorna apenas o script limpo (sem o comentário de bloco).
    """
    try:
        # Valida se o texto está dentro de um bloco /* */
        if not re.match(r'^/\*.*\*/$', generated_text, re.DOTALL):
            raise ValueError("Script deve estar dentro de um comentário de bloco /* */")

        # Remove os delimitadores de comentário
        clean_script = re.sub(r'^/\*|\*/$', '', generated_text, flags=re.DOTALL).strip()
        
        # Validação adicional via Pydantic (opcional, mas recomendado)
        AutomationScriptResponse(script=clean_script)
        
        return clean_script

    except (ValueError, ValidationError) as e:
        error_message = f"Erro ao validar script de automação: {str(e)}"
        logger.error(error_message, exc_info=True)
        raise ValueError(error_message)


def parse_bug_response(response: str, issue_id: int, user_story_id: int, prompt_tokens: int, completion_tokens: int) -> List[Bug]:# Não vamos alterar por enquanto
    try:
        bugs = json.loads(response)
        validated_bugs = [BugResponse(**bug_data["bug"]) for bug_data in bugs]
        return [
            Bug(
                user_story_id=user_story_id,
                issue_id=issue_id,
                title=validated_bug.title,
                repro_steps=validated_bug.reproSteps,
                system_info=validated_bug.systemInfo,
                tags=validated_bug.tags,
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens
            ) for _, validated_bug in zip(bugs, validated_bugs)
        ]
    except (json.JSONDecodeError, KeyError, ValidationError) as e:
        error_message = f"Erro ao parsear resposta de Bug: {str(e)}"
        logger.error(error_message, exc_info=True)
        raise ValueError(error_message)

def parse_issue_response(response: str, user_story_id: int, prompt_tokens: int, completion_tokens: int) -> List[Issue]:# Não vamos alterar por enquanto
    try:
        issues = json.loads(response)
        validated_issues = [IssueResponse(**issue_data["issue"]) for issue_data in issues]
        return [
            Issue(
                user_story_id=user_story_id,
                title=validated_issue.title,
                description=validated_issue.description,
                tags=validated_issue.tags,
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens
            ) for _, validated_issue in zip(issues, validated_issues)
        ]
    except (json.JSONDecodeError, KeyError, ValidationError) as e:
        error_message = f"Erro ao parsear resposta de Issue: {str(e)}"
        logger.error(error_message, exc_info=True)
        raise ValueError(error_message)

def parse_pbi_response(response: str, feature_id: int, prompt_tokens: int, completion_tokens: int) -> List[PBI]:# Não vamos alterar por enquanto
    try:
        pbis = json.loads(response)
        validated_pbis = [PBIResponse(**pbi_data["pbi"]) for pbi_data in pbis]
        return [
            PBI(
                feature_id=feature_id,
                title=validated_pbi.title,
                description=validated_pbi.description,
                tags=validated_pbi.tags,
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens
            ) for _, validated_pbi in zip(pbis, validated_pbis)
        ]
    except (json.JSONDecodeError, KeyError, ValidationError) as e:
        error_message = f"Erro ao parsear resposta de PBI: {str(e)}"
        logger.error(error_message, exc_info=True)
        raise ValueError(error_message)
