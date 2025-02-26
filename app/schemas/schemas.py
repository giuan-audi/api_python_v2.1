from pydantic import BaseModel, Field, validator
from typing import Dict, List, Optional, Any
from enum import Enum
from datetime import datetime


# ... (LLMConfig, TaskTypeEnum, PromptData, Request, Response, StatusResponse - SEM MUDANÇAS) ...
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
    WBS = "wbs" # Adicionado


class PromptData(BaseModel):
    system: str = Field(..., description="Prompt para definir o papel do sistema.")
    user: str = Field(..., description="Prompt principal do usuário.")
    assistant: str = Field("", description="Exemplo de resposta do assistente (opcional).")
    user_input: str = Field(..., description="Input do usuário a ser injetado no prompt user.")


class Request(BaseModel):
    parent: int = Field(..., description="ID do item pai (Épico, Feature, etc.) gerado pelo cliente.")  # Renomeado e agora é INT
    task_type: TaskTypeEnum = Field(..., description="Tipo de tarefa a ser gerada (epic, feature, user_story, task, bug, issue, pbi, test_case).")
    prompt_data: PromptData = Field(..., description="Dados do prompt para a LLM.")
    llm_config: Optional[LLMConfig] = Field(None, description="Configurações da LLM (opcional).")
    work_item_id: Optional[str] = Field(None, description="ID do item de trabalho no Azure DevOps (opcional).")  # Adicionado
    parent_board_id: Optional[str] = Field(None, description="ID do quadro pai no Azure DevOps (opcional).")   # Adicionado
    type_test: Optional[str] = Field(None, description="Tipo de teste (opcional). Ex: cypress") # Adicionado


class Response(BaseModel):
    request_id: str = Field(..., description="ID da requisição da API (interno).")
    response: Dict = Field(..., description="Resposta da API (ex: {'status': 'queued'}).")


class StatusResponse(BaseModel):
    request_id: str = Field(..., description="ID da requisição da API (interno).")
    parent: int = Field(..., description="ID do item pai.")  # Renomeado e confirmado como int
    task_type: str = Field(..., description="Tipo da tarefa.")
    status: str = Field(..., description="Status da requisição (pending, completed, failed).")
    created_at: datetime = Field(..., description="Data de criação da requisição.")
    processed_at: Optional[datetime] = Field(None, description="Data de processamento da requisição (se completada).")


class ReflectionResponse(BaseModel): # Precisa do response
    problem: str
    users: str
    features: List[str]
    challenges: str


class EpicResponse(BaseModel):
    title: str = Field(..., description="Título do Épico.")
    description: str = Field(..., description="Descrição detalhada do Épico.")
    tags: List[str] = Field(default_factory=list, description="Lista de tags associadas ao Épico.")
    reflection: ReflectionResponse = Field(..., description="Reflexão sobre o Épico") # Adicionado


# ---  Schemas para os de Feature, user story, task, test case ---
class FeatureResponse(BaseModel):
    title: str = Field(..., description="Título da Feature.")
    description: str = Field(..., description="Descrição detalhada da Feature.")
    reflection: Dict[str, Any] = Field(..., description="Reflexão sobre a Feature.")


class UserStoryResponse(BaseModel):
    title: str = Field(..., description="Título da User Story.")
    description: str = Field(..., description="Descrição detalhada da User Story.")
    acceptance_criteria: str = Field(..., description="Critérios de aceite da User Story.")


class TaskResponse(BaseModel):
    title: str = Field(..., description="Título da Task.")
    description: str = Field(..., description="Descrição detalhada da Task.")


# ---  Schemas para Bug, Issue e PBI (Não serão alterados por enquanto) ---
class BugResponse(BaseModel):
    title: str = Field(..., description="Título do Bug.")
    reproSteps: str = Field(..., description="Passos para reprodução do Bug.")
    systemInfo: str = Field(..., description="Informações do sistema onde o Bug ocorre.")
    tags: List[str] = Field(default_factory=list, description="Lista de tags associadas ao Bug.")


class IssueResponse(BaseModel):
    title: str = Field(..., description="Título da Issue.")
    description: str = Field(..., description="Descrição detalhada da Issue.")
    tags: List[str] = Field(default_factory=list, description="Lista de tags associadas à Issue.")


class PBIResponse(BaseModel):
    title: str = Field(..., description="Título do PBI.")
    description: str = Field(..., description="Descrição detalhada do PBI.")
    tags: List[str] = Field(default_factory=list, description="Lista de tags associadas ao PBI.")


# --- Schemas para Test Case ---
class GherkinResponse(BaseModel):
    feature: str = Field(..., description="Funcionalidade sendo testada (Feature).")
    title: str = Field(..., description="Título do cenário Gherkin.")
    scenario: str = Field(..., description="Descrição do cenário Gherkin.")
    given: str = Field(..., description="Pré-condições do cenário (Dado que...).")
    when: str = Field(..., description="Ações do cenário (Quando...).")
    then: str = Field(..., description="Resultados esperados do cenário (Então...).")


class ActionResponse(BaseModel):
    step: str = Field(..., description="Passo da ação.")
    expected_result: str = Field(..., description="Resultado esperado da ação.")


class TestCaseResponse(BaseModel):
    # Removido o id, pois será gerado automaticamente
    parent: int = Field(..., description="ID da User Story associada.")
    gherkin: GherkinResponse = Field(..., description="Dados Gherkin do caso de teste.")
    actions: List[ActionResponse] = Field(..., description="Lista de ações do caso de teste.")


#--- Schema para WBS ---
class WBSResponse(BaseModel): # Schema para WBS
    wbs: List[Dict[str, Any]] = Field(..., description="Estrutura da WBS em formato JSON.")
