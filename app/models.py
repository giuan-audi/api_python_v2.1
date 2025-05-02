from sqlalchemy import Column, String, Integer, Text, DateTime, ForeignKey, JSON, Boolean
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from sqlalchemy.dialects.postgresql import UUID
import enum

Base = declarative_base()


class TaskType(enum.Enum):
    EPIC = "epic"
    FEATURE = "feature"
    USER_STORY = "user_story"
    TASK = "task"
    BUG = "bug"
    ISSUE = "issue"
    PBI = "pbi"
    TEST_CASE = "test_case"
    WBS = "wbs"
    AUTOMATION_SCRIPT = "automation_script"
    PROJECT = "project"


class Status(enum.Enum):
    PENDING = "pending"
    COMPLETED = "completed"
    FAILED = "failed"


class Epic(Base):
    __tablename__ = "epics"
    id = Column(Integer, primary_key=True)  # ID interno (INT), autoincremental
    team_project_id = Column(Integer)  # ID do projeto da equipe (fornecido pelo backend .NET)
    parent_type = Column(String(50), nullable=True)
    title = Column(String)
    project_id = Column(UUID(as_uuid=True), nullable=True, index=True)
    description = Column(Text)
    tags = Column(JSON)
    version = Column(Integer, default=1)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    feedback = Column(Text, nullable=True)
    prompt_tokens = Column(Integer, nullable=True)
    completion_tokens = Column(Integer, nullable=True)
    summary = Column(Text, nullable=True)
    reflection = Column(JSON, nullable=True)
    work_item_id = Column(String, nullable=True)
    parent_board_id = Column(String, nullable=True)


class Feature(Base):
    __tablename__ = "features"
    id = Column(Integer, primary_key=True)
    parent = Column(Integer, ForeignKey('epics.id'))  # Chave estrangeira para epic (parent)
    parent_type = Column(String(50), nullable=True)
    title = Column(String)
    project_id = Column(UUID(as_uuid=True), nullable=True, index=True)
    description = Column(Text)
    version = Column(Integer, default=1)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    feedback = Column(Text, nullable=True)
    prompt_tokens = Column(Integer, nullable=True)
    completion_tokens = Column(Integer, nullable=True)
    summary = Column(Text, nullable=True)
    reflection = Column(JSON, nullable=True)
    work_item_id = Column(String, nullable=True)
    parent_board_id = Column(String, nullable=True)
    acceptance_criteria = Column(Text)


class UserStory(Base):
    __tablename__ = "user_stories"
    id = Column(Integer, primary_key=True)
    parent = Column(Integer, ForeignKey('features.id'))
    parent_type = Column(String(50), nullable=True)
    title = Column(String)
    project_id = Column(UUID(as_uuid=True), nullable=True, index=True)
    description = Column(Text)
    acceptance_criteria = Column(Text)
    priority = Column(String)
    dod = Column(Text, nullable=True)
    dor = Column(Text, nullable=True)
    version = Column(Integer, default=1)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    feedback = Column(Text, nullable=True)
    prompt_tokens = Column(Integer, nullable=True)
    completion_tokens = Column(Integer, nullable=True)
    summary = Column(Text, nullable=True)
    reflection = Column(JSON, nullable=True)
    work_item_id = Column(String, nullable=True)
    parent_board_id = Column(String, nullable=True)


class Task(Base):
    __tablename__ = "tasks"
    id = Column(Integer, primary_key=True)
    parent = Column(Integer, ForeignKey('user_stories.id'))  # Chave estrangeira para user story (parent)
    parent_type = Column(String(50), nullable=True)
    title = Column(String)
    project_id = Column(UUID(as_uuid=True), nullable=True, index=True)
    description = Column(Text)
    estimate = Column(String)
    version = Column(Integer, default=1)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    feedback = Column(Text, nullable=True)
    prompt_tokens = Column(Integer, nullable=True)
    completion_tokens = Column(Integer, nullable=True)
    summary = Column(Text, nullable=True)
    reflection = Column(JSON, nullable=True)
    work_item_id = Column(String, nullable=True)
    parent_board_id = Column(String, nullable=True)


class Bug(Base):  # Não vamos alterar por enquanto
    __tablename__ = "bugs"
    id = Column(Integer, primary_key=True)
    issue_id = Column(Integer, ForeignKey('issues.id'), nullable=True)
    user_story_id = Column(Integer, ForeignKey('user_stories.id'), nullable=True)
    title = Column(String)
    project_id = Column(UUID(as_uuid=True), nullable=True, index=True)
    repro_steps = Column(Text)
    system_info = Column(Text)
    tags = Column(JSON)
    version = Column(Integer, default=1)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    feedback = Column(Text, nullable=True)
    prompt_tokens = Column(Integer, nullable=True)
    completion_tokens = Column(Integer, nullable=True)
    summary = Column(Text, nullable=True)
    reflection = Column(JSON, nullable=True)
    work_item_id = Column(String, nullable=True)
    parent_board_id = Column(String, nullable=True)


class Issue(Base):# Não vamos alterar por enquanto
    __tablename__ = "issues"
    id = Column(Integer, primary_key=True)
    user_story_id = Column(Integer, ForeignKey('user_stories.id'))
    title = Column(String)
    project_id = Column(UUID(as_uuid=True), nullable=True, index=True)
    description = Column(Text)
    tags = Column(JSON)
    version = Column(Integer, default=1)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    feedback = Column(Text, nullable=True)
    prompt_tokens = Column(Integer, nullable=True)
    completion_tokens = Column(Integer, nullable=True)
    summary = Column(Text, nullable=True)
    reflection = Column(JSON, nullable=True)
    work_item_id = Column(String, nullable=True)
    parent_board_id = Column(String, nullable=True)


class PBI(Base):# Não vamos alterar por enquanto
    __tablename__ = "pbis"
    id = Column(Integer, primary_key=True)
    feature_id = Column(Integer, ForeignKey('features.id'))
    title = Column(String)
    project_id = Column(UUID(as_uuid=True), nullable=True, index=True)
    description = Column(Text)
    tags = Column(JSON)
    version = Column(Integer, default=1)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    feedback = Column(Text, nullable=True)
    prompt_tokens = Column(Integer, nullable=True)
    completion_tokens = Column(Integer, nullable=True)
    summary = Column(Text, nullable=True)
    reflection = Column(JSON, nullable=True)
    work_item_id = Column(String, nullable=True)
    parent_board_id = Column(String, nullable=True)


class Request(Base):
    __tablename__ = "requests"
    id = Column(Integer, primary_key=True)
    request_id = Column(String, unique=True)
    parent = Column(Integer)
    parent_type = Column(String(50), nullable=True)
    project_id = Column(UUID(as_uuid=True), nullable=True, index=True)
    task_type = Column(String)
    status = Column(String)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    processed_at = Column(DateTime(timezone=True))
    error_message = Column(Text)
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    artifact_type = Column(String)
    artifact_id = Column(Integer)


class TestCase(Base):
    __tablename__ = "test_cases"
    id = Column(Integer, primary_key=True)
    parent = Column(Integer, ForeignKey('user_stories.id'))  # Chave estrangeira para User Story
    parent_type = Column(String(50), nullable=True)
    title = Column(String)  # Adicionado title para o caso de teste
    project_id = Column(UUID(as_uuid=True), nullable=True, index=True)
    gherkin = Column(JSON)  # Agora armazena o Gherkin como JSON
    script = Column(Text, nullable=True)  # <-- Adicionado: Campo para o script de automação
    version = Column(Integer, default=1)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    feedback = Column(Text, nullable=True)
    prompt_tokens = Column(Integer, nullable=True)
    completion_tokens = Column(Integer, nullable=True)
    summary = Column(Text, nullable=True)
    reflection = Column(JSON, nullable=True)
    work_item_id = Column(String, nullable=True)
    parent_board_id = Column(String, nullable=True)
    priority = Column(String)

    actions = relationship("Action", back_populates="test_case")  # Relacionamento 1:N com Action


# A tabela Gherkin foi removida
class Action(Base):
    __tablename__ = "actions"
    id = Column(Integer, primary_key=True)
    test_case_id = Column(Integer, ForeignKey('test_cases.id'))  # Chave estrangeira para TestCase
    step = Column(Text)
    expected_result = Column(Text)
    version = Column(Integer, default=1) # Adicionado
    is_active = Column(Boolean, default=True) # Adicionado
    test_case = relationship("TestCase", back_populates="actions") # Relacionamento com TestCase


class WBS(Base):
    __tablename__ = "wbs"
    id = Column(Integer, primary_key=True)
    parent = Column(Integer, ForeignKey('epics.id'))  # Chave estrangeira para Epic
    parent_type = Column(String(50), nullable=True)
    project_id = Column(UUID(as_uuid=True), nullable=True, index=True)
    wbs = Column(JSON)  # Armazena a WBS como JSON
    version = Column(Integer, default=1)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    feedback = Column(Text, nullable=True)
    prompt_tokens = Column(Integer, nullable=True)
    completion_tokens = Column(Integer, nullable=True)
    summary = Column(Text, nullable=True)
    reflection = Column(JSON, nullable=True)
    work_item_id = Column(String, nullable=True)
    parent_board_id = Column(String, nullable=True)
