from pydantic import BaseModel, Field, validator, root_validator
from typing import Dict, List, Optional, Any
from enum import Enum
from datetime import datetime
from uuid import UUID
# from models import TaskTypeEnum


class LLMConfig(BaseModel):
    llm: Optional[str] = Field("openai", description="LLM a ser usada (openai ou gemini).")
    model: Optional[str] = Field(None, description="Modelo da LLM a ser usado.")
    temperature: Optional[float] = Field(0.7, description="Temperatura para geração de texto (0.0 a 1.0).")
    max_tokens: Optional[int] = Field(1000, description="Número máximo de tokens a serem gerados.")
    top_p: Optional[float] = Field(None, description="Top P para amostragem de nucleus (OpenAI).")

    @validator('llm')
    def check_llm_valid(cls, value):
        if value not in ["openai", "gemini"]:
            raise ValueError("LLM deve ser 'openai' ou 'gemini'")
        return value

    @validator('temperature')
    def check_temperature_range(cls, value):
        if value is not None and (value < 0.0 or value > 1.0):
            raise ValueError("Temperatura deve estar entre 0.0 e 1.0")
        return value

    @validator('top_p')
    def check_top_p_valid(cls, value):
        if value is not None and (value < 0.0 or value > 1.0):
            raise ValueError("Top P deve estar entre 0.0 e 1.0")
        return value


class TaskTypeEnum(str, Enum):
    EPIC = "epic"
    FEATURE = "feature"
    USER_STORY = "user_story"
    TASK = "task"
    BUG = "bug"
    ISSUE = "issue"
    PBI = "pbi"
    TEST_CASE = 'test_case'
    WBS = "wbs"
    AUTOMATION_SCRIPT = "automation_script"
    PROJECT = "project"

class PromptData(BaseModel):
    system: str = Field(..., description="Prompt para definir o papel do sistema.")
    user: str = Field(..., description="Prompt principal do usuário.")
    assistant: str = Field("", description="Exemplo de resposta do assistente (opcional).")
    user_input: str = Field(..., description="Input do usuário a ser injetado no prompt user.")


class Request(BaseModel):
    parent: int = Field(..., description="ID do item pai (Épico, Feature, etc.) gerado pelo cliente.")
    parent_type: TaskTypeEnum = Field(..., description="Tipo do artefato pai.")
    task_type: TaskTypeEnum = Field(..., description="Tipo de tarefa a ser gerada (epic, feature, user_story, task, bug, issue, pbi, test_case).")
    prompt_data: PromptData = Field(..., description="Dados do prompt para a LLM.")
    language: Optional[str] = Field("português", description="Idioma para a resposta da LLM (padrão: português).")
    llm_config: Optional[LLMConfig] = Field(None, description="Configurações da LLM (opcional).")
    work_item_id: Optional[str] = Field(None, description="ID do item de trabalho no Azure DevOps (opcional).")
    parent_board_id: Optional[str] = Field(None, description="ID do quadro pai no Azure DevOps (opcional).")
    type_test: Optional[str] = Field(None, description="Tipo de teste (opcional). Ex: cypress")


class ReprocessRequest(BaseModel):
    prompt_data: PromptData = Field(..., description="Dados do prompt para a LLM.")
    language: Optional[str] = Field("português", description="Idioma para a resposta da LLM (padrão: português).")
    llm_config: Optional[LLMConfig] = Field(None, description="Configurações da LLM (opcional).")
    type_test: Optional[str] = Field(None, description="Tipo de teste (opcional). Ex: cypress")
    work_item_id: Optional[str] = Field(None, description="ID do item de trabalho no Azure DevOps (opcional).")
    parent_board_id: Optional[str] = Field(None, description="ID do quadro pai no Azure DevOps (opcional).")


class Response(BaseModel):
    request_id: str = Field(..., description="ID da requisição da API (interno).")
    response: Dict = Field(..., description="Resposta da API (ex: {'status': 'queued'}).")


class StatusResponse(BaseModel):
    request_id: str = Field(..., description="ID da requisição da API (interno).")
    project_id: Optional[str] = Field(None, description="ID do Projeto (UUID) associado à requisição, se disponível.")
    parent: int = Field(..., description="ID do item pai.")
    task_type: str = Field(..., description="Tipo da tarefa.")
    status: str = Field(..., description="Status da requisição (pending, completed, failed).")
    created_at: datetime = Field(..., description="Data de criação da requisição.")
    processed_at: Optional[datetime] = Field(None, description="Data de processamento da requisição (se completada).")
    artifact_type: str = Field(..., description="Tipo de artefato")
    artifact_id: int = Field(..., description="ID do artefato")


class IndependentCreationRequest(BaseModel):
    project_id: UUID = Field(..., description="ID do Projeto (UUID) ao qual o artefato pertence.")
    task_type: TaskTypeEnum = Field(..., description="Tipo de tarefa a ser gerada (epic, feature, user_story, task, etc.).")
    prompt_data: PromptData = Field(..., description="Dados do prompt para a LLM (inclui user_input).")
    language: Optional[str] = Field("português", description="Idioma para a resposta da LLM (padrão: português).")
    parent: Optional[int] = Field(None, description="ID do item pai (opcional para esta rota).") # Opcional
    parent_type: Optional[TaskTypeEnum] = Field(None, description="Tipo do artefato pai (obrigatório se parent ID for fornecido).")
    llm_config: Optional[LLMConfig] = Field(None, description="Configurações da LLM (opcional).")
    work_item_id: Optional[str] = Field(None, description="ID do item de trabalho no Azure DevOps (opcional).")
    parent_board_id: Optional[str] = Field(None, description="ID do quadro pai no Azure DevOps (opcional).")
    type_test: Optional[str] = Field(None, description="Tipo de teste (opcional). Ex: cypress")

    @root_validator(pre=False, skip_on_failure=True)
    def check_parent_type_if_parent_exists(cls, values):
        parent_id = values.get('parent')
        parent_type_value = values.get('parent_type') # Usa o nome correto aqui
        if parent_id is not None and parent_type_value is None:
            raise ValueError('parent_type é obrigatório quando parent ID é fornecido')
        return values


class ReflectionResponse(BaseModel):
    problem: str = Field(..., description="Descrição do problema que o sistema resolve e seu impacto.")
    users: str = Field(..., description="Público-alvo do sistema e seus benefícios.")
    features: List[str] = Field(..., description="Lista de funcionalidades essenciais.")
    challenges: str = Field(..., description="Principais desafios e estratégias de mitigação.")

class EpicResponse(BaseModel):
    title: str = Field(..., description="Título do Épico.")
    description: str = Field(..., description="Descrição detalhada do Épico.")
    tags: List[str] = Field(default_factory=list, description="Lista de tags associadas ao Épico.")
    reflection: Dict[str, Any] = Field(..., description="Reflexão sobre o Épico (perguntas e respostas).")
    summary: Optional[str] = Field(None, description="Resumo conciso do Épico.")

class FeatureResponse(BaseModel):
    title: str = Field(..., description="Título da Feature.")
    description: str = Field(..., description="Descrição detalhada da Feature.")
    acceptance_criteria: Optional[List[str]] = Field(None, description="Lista de critérios de aceite da Feature (opcional).")
    summary: Optional[str] = Field(None)

class UserStoryResponse(BaseModel):
    title: str = Field(..., description="Título da User Story.")
    description: str = Field(..., description="Descrição detalhada da User Story.")
    acceptance_criteria: str = Field(..., description="Critérios de aceite da User Story.")
    priority: str = Field(..., description="Prioridade da User Story.")
    dod: Optional[str] = Field(None, description="Definition of Done (DoD)")
    dor: Optional[str] = Field(None, description="Definition of Ready (DoR)")
    summary: Optional[str] = Field(None)

class TaskResponse(BaseModel):
    title: str = Field(..., description="Título da Task.")
    description: str = Field(..., description="Descrição detalhada da Task.")
    summary: Optional[str] = Field(None)
    estimate: str = Field(..., description="Estimativa de tempo da Task.")

# ---  Schemas para Bug, Issue e PBI  ---
class BugResponse(BaseModel):# Não vamos alterar por enquanto
    title: str = Field(..., description="Título do Bug.")
    reproSteps: str = Field(..., description="Passos para reprodução do Bug.")
    systemInfo: str = Field(..., description="Informações do sistema onde o Bug ocorre.")
    tags: List[str] = Field(default_factory=list, description="Lista de tags associadas ao Bug.")

class IssueResponse(BaseModel):# Não vamos alterar por enquanto
    title: str = Field(..., description="Título da Issue.")
    description: str = Field(..., description="Descrição detalhada da Issue.")
    tags: List[str] = Field(default_factory=list, description="Lista de tags associadas à Issue.")

class PBIResponse(BaseModel):# Não vamos alterar por enquanto
    title: str = Field(..., description="Título do PBI.")
    description: str = Field(..., description="Descrição detalhada do PBI.")
    tags: List[str] = Field(default_factory=list, description="Lista de tags associadas ao PBI.")

# ---  Schemas para Test Case  ---
# Removido GherkinResponse, pois agora será um dicionário

class ActionResponse(BaseModel):  # Schema para cada ação dentro de um caso de teste
    step: str = Field(..., description="Passo da ação.")
    expected_result: str = Field(..., description="Resultado esperado da ação.")

class TestCaseResponse(BaseModel):  # Schema para a resposta completa de um caso de teste
    priority: str = Field(..., description="Prioridade do caso de teste.")
    title: str = Field(..., description="Título do caso de teste")
    gherkin: Dict[str, Any] = Field(..., description="Dados Gherkin do caso de teste.")
    actions: List[ActionResponse] = Field(..., description="Lista de ações do caso de teste.")

# --- Schema para WBS ---
class WBSResponse(BaseModel):
    wbs: List[Dict[str, Any]] = Field(..., description="Estrutura da WBS em formato JSON.")

# --- Schema para Automation Script ---
class AutomationScriptResponse(BaseModel):
    script: str = Field(..., description="Script de automação gerado (em formato de comentário).")
