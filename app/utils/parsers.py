import json
from typing import List, Any, Dict
from app.models import Epic, Feature, UserStory, Task, Bug, Issue, PBI, TestCase, Gherkin, Action, WBS
from app.schemas.schemas import EpicResponse, FeatureResponse, UserStoryResponse, TaskResponse, BugResponse, IssueResponse, PBIResponse, TestCaseResponse, GherkinResponse, ActionResponse, WBSResponse
from pydantic import ValidationError
import logging

logger = logging.getLogger(__name__)


def parse_epic_response(response: str, prompt_tokens: int, completion_tokens: int) -> Epic:
    try:
        data = json.loads(response)
        validated_response = EpicResponse(**data)
        return Epic(
            title=validated_response.title,
            description=validated_response.description,
            tags=validated_response.tags,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
        )
    except (json.JSONDecodeError, KeyError, ValidationError) as e:
        error_message = f"Erro ao parsear resposta de Épico: {str(e)}"
        logger.error(error_message, exc_info=True)
        raise ValueError(error_message)


def parse_feature_response(response: str, parent_id: int, prompt_tokens: int, completion_tokens: int) -> List[Feature]:
    try:
        features = json.loads(response)
        validated_features = [FeatureResponse(**feat) for feat in features]
        return [
            Feature(
                parent=parent_id,
                title=validated_feat.title,
                description=validated_feat.description,
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
            ) for validated_feat in validated_features
        ]
    except (json.JSONDecodeError, KeyError, ValidationError) as e:
        error_message = f"Erro ao parsear resposta de Feature: {str(e)}"
        logger.error(error_message, exc_info=True)
        raise ValueError(error_message)


def parse_user_story_response(response: str, parent_id: int, prompt_tokens: int, completion_tokens: int) -> List[UserStory]:
    try:
        user_stories = json.loads(response)
        validated_user_stories = [UserStoryResponse(**story["userStory"]) for story in user_stories]
        return [
            UserStory(
                parent=parent_id,
                title=validated_story.title,
                description=validated_story.description,
                acceptance_criteria=validated_story.acceptance_criteria,
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
            ) for validated_story in validated_user_stories
        ]
    except (json.JSONDecodeError, KeyError, ValidationError) as e:
        error_message = f"Erro ao parsear resposta de User Story: {str(e)}"
        logger.error(error_message, exc_info=True)
        raise ValueError(error_message)


def parse_task_response(response: str, parent_id: int, prompt_tokens: int, completion_tokens: int) -> List[Task]:
    try:
        tasks = json.loads(response)
        validated_tasks = [TaskResponse(**task["task"]) for task in tasks]
        return [
            Task(
                parent=parent_id,
                title=validated_task.title,
                description=validated_task.description,
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
            ) for validated_task in validated_tasks
        ]
    except (json.JSONDecodeError, KeyError, ValidationError) as e:
        error_message = f"Erro ao parsear resposta de Task: {str(e)}"
        logger.error(error_message, exc_info=True)
        raise ValueError(error_message)


def parse_test_case_response(response: str, parent_id: int, prompt_tokens: int, completion_tokens: int) -> List[TestCase]:
    try:
        test_case_data = json.loads(response)
        validated_test_case = TestCaseResponse(**test_case_data)  # Valida o caso de teste principal
        # Crie o TestCase
        test_case = TestCase(
            parent=parent_id,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            # Não definimos title aqui, pois vem do Gherkin
        )

        # Crie o Gherkin (1:1 com TestCase)
        gherkin_data = validated_test_case.gherkin
        gherkin = Gherkin(
            title=gherkin_data.title,
            scenario=gherkin_data.scenario,
            given=gherkin_data.given,
            when=gherkin_data.when,
            then=gherkin_data.then
        )
        test_case.gherkin = gherkin  # Associa o Gherkin ao TestCase

        # Crie as Actions (1:N com TestCase)
        for action_data in validated_test_case.actions:
            #validated_action = ActionResponse(**action_data)  # Valida cada ação - Removido, redundante
            action = Action(
                step=action_data.step,  # Acessa diretamente os atributos
                expected_result=action_data.expected_result  # Acessa diretamente os atributos
            )
            test_case.actions.append(action)  # Adiciona a ação à lista de ações do TestCase

        return [test_case]  # Retorna uma lista com um único TestCase

    except (json.JSONDecodeError, KeyError, ValidationError) as e:
        error_message = f"Erro ao parsear resposta de TestCase: {str(e)}"
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


def parse_wbs_response(response: str, parent_id: int, prompt_tokens: int, completion_tokens: int) -> WBS:
    '''Função para criar a WBS'''
    try:
        data = json.loads(response)
        validated_response = WBSResponse(**data)
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
