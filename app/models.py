from sqlalchemy import Column, String, Integer, Text, DateTime, ForeignKey, JSON, Boolean
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
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


class Status(enum.Enum):
    PENDING = "pending"
    COMPLETED = "completed"
    FAILED = "failed"


class Epic(Base):
    __tablename__ = "epics"
    id = Column(Integer, primary_key=True)
    team_project_id = Column(Integer)  # Correto (Integer)
    title = Column(String)
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
    reflection = Column(JSON)
    work_item_id = Column(String, nullable=True)
    parent_board_id = Column(String, nullable=True)


class Feature(Base):
    __tablename__ = "features"
    id = Column(Integer, primary_key=True)
    parent = Column(Integer, ForeignKey('epics.id'))
    title = Column(String)
    description = Column(Text)
    version = Column(Integer, default=1)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    feedback = Column(Text, nullable=True)
    prompt_tokens = Column(Integer, nullable=True)
    completion_tokens = Column(Integer, nullable=True)
    summary = Column(Text, nullable=True)
    reflection = Column(JSON)
    work_item_id = Column(String, nullable=True)
    parent_board_id = Column(String, nullable=True)


class UserStory(Base):
    __tablename__ = "user_stories"
    id = Column(Integer, primary_key=True)
    parent = Column(Integer, ForeignKey('features.id'))
    title = Column(String)
    description = Column(Text)
    acceptance_criteria = Column(Text)
    version = Column(Integer, default=1)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    feedback = Column(Text, nullable=True)
    prompt_tokens = Column(Integer, nullable=True)
    completion_tokens = Column(Integer, nullable=True)
    summary = Column(Text, nullable=True)
    reflection = Column(JSON)
    work_item_id = Column(String, nullable=True)
    parent_board_id = Column(String, nullable=True)


class Task(Base):
    __tablename__ = "tasks"
    id = Column(Integer, primary_key=True)
    parent = Column(Integer, ForeignKey('user_stories.id'))
    title = Column(String)
    description = Column(Text)
    version = Column(Integer, default=1)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    feedback = Column(Text, nullable=True)
    prompt_tokens = Column(Integer, nullable=True)
    completion_tokens = Column(Integer, nullable=True)
    summary = Column(Text, nullable=True)
    reflection = Column(JSON)
    work_item_id = Column(String, nullable=True)
    parent_board_id = Column(String, nullable=True)


class Bug(Base):  # Não vamos alterar por enquanto
    __tablename__ = "bugs"
    id = Column(Integer, primary_key=True)
    issue_id = Column(Integer, ForeignKey('issues.id'), nullable=True)
    user_story_id = Column(Integer, ForeignKey('user_stories.id'), nullable=True)
    title = Column(String)
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
    reflection = Column(JSON)
    work_item_id = Column(String, nullable=True)
    parent_board_id = Column(String, nullable=True)



class Issue(Base):# Não vamos alterar por enquanto
    __tablename__ = "issues"
    id = Column(Integer, primary_key=True)
    user_story_id = Column(Integer, ForeignKey('user_stories.id'))
    title = Column(String)
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
    reflection = Column(JSON)
    work_item_id = Column(String, nullable=True)
    parent_board_id = Column(String, nullable=True)


class PBI(Base):# Não vamos alterar por enquanto
    __tablename__ = "pbis"
    id = Column(Integer, primary_key=True)
    feature_id = Column(Integer, ForeignKey('features.id'))
    title = Column(String)
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
    reflection = Column(JSON)
    work_item_id = Column(String, nullable=True)
    parent_board_id = Column(String, nullable=True)


class Request(Base):
    __tablename__ = "requests"
    id = Column(Integer, primary_key=True)
    request_id = Column(String, unique=True)
    parent = Column(Integer)  # Renomeado e agora é Integer
    task_type = Column(String)
    status = Column(String)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    processed_at = Column(DateTime(timezone=True))
    error_message = Column(Text)
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())


# ---  Tabelas para Test Case (Gherkin e Actions) ---
class TestCase(Base):
    __tablename__ = "test_cases"
    id = Column(Integer, primary_key=True)
    parent = Column(Integer, ForeignKey('user_stories.id'))  # Chave estrangeira para User Story
    version = Column(Integer, default=1)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    feedback = Column(Text, nullable=True)
    prompt_tokens = Column(Integer, nullable=True)
    completion_tokens = Column(Integer, nullable=True)
    summary = Column(Text, nullable=True)          # Adicionado (nullable)
    reflection = Column(JSON)       # Adicionado (nullable)
    work_item_id = Column(String, nullable=True)     # Adicionado (nullable)
    parent_board_id = Column(String, nullable=True)  # Adicionado (nullable)

    gherkin = relationship("Gherkin", uselist=False, back_populates="test_case")  # Relacionamento 1:1 com Gherkin
    actions = relationship("Action", back_populates="test_case")  # Relacionamento 1:N com Action


class Gherkin(Base):
    __tablename__ = "gherkin"
    id = Column(Integer, primary_key=True)
    test_case_id = Column(Integer, ForeignKey('test_cases.id'))  # Chave estrangeira para TestCase
    title = Column(String)  # Mantido o title no Gherkin
    scenario = Column(Text)
    given = Column(Text)
    when = Column(Text)
    then = Column(Text)
    version = Column(Integer, default=1) # Adicionado
    is_active = Column(Boolean, default=True) # Adicionado
    test_case = relationship("TestCase", back_populates="gherkin") # Relacionamento com TestCase


class Action(Base):
    __tablename__ = "actions"
    id = Column(Integer, primary_key=True)
    test_case_id = Column(Integer, ForeignKey('test_cases.id'))  # Chave estrangeira para TestCase
    step = Column(Text)
    expected_result = Column(Text)
    version = Column(Integer, default=1) # Adicionado
    is_active = Column(Boolean, default=True) # Adicionado
    test_case = relationship("TestCase", back_populates="actions") # Relacionamento com TestCase


# --- Tabela para WBS ---
class WBS(Base):
    __tablename__ = "wbs"
    id = Column(Integer, primary_key=True)
    parent = Column(Integer, ForeignKey('epics.id'))  # Chave estrangeira para Epic
    wbs = Column(JSON)  # Armazena a WBS como JSON
    version = Column(Integer, default=1)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    feedback = Column(Text, nullable=True)
    prompt_tokens = Column(Integer, nullable=True)
    completion_tokens = Column(Integer, nullable=True)
    summary = Column(Text, nullable=True)
    reflection = Column(JSON)
    work_item_id = Column(String, nullable=True)
    parent_board_id = Column(String, nullable=True)


# --- Tabela para Automation Script ---
class AutomationScript(Base):
    __tablename__ = "automation_scripts"
    id = Column(Integer, primary_key=True)
    parent = Column(Integer, ForeignKey('test_cases.id'))  # Chave estrangeira para TestCase
    script = Column(Text) # Tipo TEXT para armazenar scripts longos
    version = Column(Integer, default=1)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    feedback = Column(Text, nullable=True)
    prompt_tokens = Column(Integer, nullable=True)
    completion_tokens = Column(Integer, nullable=True)
    summary = Column(Text, nullable=True)
    reflection = Column(Text, nullable=True)
    work_item_id = Column(String, nullable=True)
    parent_board_id = Column(String, nullable=True)
