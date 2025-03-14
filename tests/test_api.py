import pytest
from fastapi.testclient import TestClient
from app.main import create_app
from app.models import Request, Status, TaskType # Importe os modelos e enums
from app.database import get_db  # Descomente se precisar de acesso direto ao DB
from sqlalchemy.orm import Session

# Fixture para criar uma instância da aplicação para os testes
@pytest.fixture(scope="module")
def client():
    app = create_app()
    with TestClient(app) as client:
        yield client

# --- Testes para a rota /generate ---

def test_generate_epic(client):
    data = {
        "parent": 6,  # ID do projeto pai (fictício)
        "task_type": "epic",
        "prompt_data": {
            "system": "Você é um Product Owner experiente...",
            "user": "Antes de criar o Épico, analise o contexto...\n\n{user_input}\n\n...",
            "assistant": "{\"title\": \"Exemplo de Título\", ...}",
            "user_input": "Estamos construindo um sistema para automatizar as tarefas do Azure DevOps com IA..."
        },
        "llm_config": {
            "llm": "openai",
            "model": "gpt-4-turbo",  # Use um modelo válido
            "temperature": 0.65,
            "max_tokens": 3500,
            "top_p": 1.0
        },
        "work_item_id": "asd123",  # Remova se não estiver usando
        "parent_board_id": "123asd",  # Remova se não estiver usando
        "type_test": None
    }
    response = client.post("/generation/generate/", json=data)
    assert response.status_code == 201
    assert "request_id" in response.json()

def test_generate_wbs(client):
    data = {
        "parent": 5,
        "task_type": "wbs",
        "prompt_data": {
            "system": "Você é um especialista em gerenciamento de projetos...",
            "user": "Analise o texto a seguir e crie uma WBS completa...\n\nTexto:\n\n{user_input}",
            "assistant": "{\n  \"wbs\": [\n    {\n      \"title\": \"Exemplo de Épico...\",\n ...",
            "user_input": "Estamos construindo um sistema para automatizar as tarefas do Azure DevOps com IA..."
        },
        "llm_config": {
            "llm": "openai",
            "model": "gpt-4-turbo",
            "temperature": 0.65,
            "max_tokens": 4096,
            "top_p": 0.95
        },
        "work_item_id": "asd123",
        "parent_board_id": "123asd",
        "type_test": None
    }
    response = client.post("/generation/generate/", json=data)
    assert response.status_code == 201
    assert "request_id" in response.json()


def test_generate_feature(client):
    data = {
        "parent": 13,
        "task_type": "feature",
        "prompt_data": {
            "system": "Você é um Analista de Negócios experiente...",
            "user": "Analise o texto abaixo...\n\nTexto:\n\n{user_input}",
            "assistant": "[\n  {\n    \"title\": \"Exemplo de Título de Funcionalidade\",\n    \"description\": \"Exemplo de descrição...\"\n  }\n]",
            "user_input": "Estamos construindo um sistema para automatizar as tarefas do Azure DevOps com IA..."
        },
        "llm_config": {
            "llm": "openai",
            "model": "gpt-4-turbo",
            "temperature": 0.65,
            "max_tokens": 4096,
            "top_p": 1.0
        },
        "work_item_id": "asd123",
        "parent_board_id": "123asd",
        "type_test": None
    }
    response = client.post("/generation/generate/", json=data)
    assert response.status_code == 201
    assert "request_id" in response.json()


def test_generate_user_story(client):
    data = {
        "parent": 334,
        "task_type": "user_story",
        "prompt_data": {
            "system": "Você é um especialista em metodologias ágeis...",
            "user": "Aqui está o contexto do Épico e da Feature:\n\n{user_input}\n\nAgora, com base nesse contexto...",
            "assistant": "[\n {\n \"title\": \"Título da User Story 1\",\n ...",
            "user_input": "['epic': 'Desenvolver um sistema...', 'Feature': {'title': 'Arquitetura Dividida', 'description': '...'}]"  # Formato correto
        },
        "llm_config": {
            "llm": "openai",
            "model": "gpt-4-turbo",
            "temperature": 0.65,
            "max_tokens": 4096,
            "top_p": 1.0
        },
        "work_item_id": "asd123",
        "parent_board_id": "123asd",
        "type_test": None
    }
    response = client.post("/generation/generate/", json=data)
    assert response.status_code == 201
    assert "request_id" in response.json()

def test_generate_task(client):
    data = {
        "parent": 37,
        "task_type": "task",
        "prompt_data": {
            "system": "Você é um Gerente de Projetos Ágeis experiente...",
            "user": "Aqui está a User Story para referência:\n\n{user_input}\n\nCrie as Tasks...",
            "assistant": "[\n  {\n    \"title\": \"Título da Task 1\",\n    \"description\": \"Descrição detalhada da Task 1.\",\n    \"estimate\": \"4h\"\n  },\n ...",
            "user_input": "{'description': 'Como desenvolvedor, quero criar um backend independente...', 'acceptance_criteria': '...'}"
        },
         "llm_config": {
            "llm": "openai",
            "model": "gpt-4-turbo",
            "temperature": 0.65,
            "max_tokens": 4096,
            "top_p": 0.95
        },
        "work_item_id": "asd123",
        "parent_board_id": "123asd",
        "type_test": None
    }
    response = client.post("/generation/generate/", json=data)
    assert response.status_code == 201
    assert "request_id" in response.json()


def test_generate_test_case(client):
    data = {
        "parent": 5,
        "task_type": "test_case",
        "prompt_data": {
            "system": "Você é um Analista de Qualidade de Software sênior...",
            "user": "Crie os casos de teste necessários para a seguinte User Story:\n\n{user_input}\n\nRetorne SOMENTE...",
            "assistant": "[\n  {\n    \"title\": \"Exemplo de Título do Caso de Teste\",\n ...",
            "user_input": "{'description': 'Como desenvolvedor, quero criar um backend independente...', 'acceptance_criteria': '...'}"
        },
        "llm_config": {
            "llm": "openai",
            "model": "gpt-4-turbo",
            "temperature": 0.55,
            "max_tokens": 4096,
            "top_p": 0.95
        },
        "work_item_id": "123a",
        "parent_board_id": "1s",
        "type_test": "cypress"  # Incluir type_test, mesmo que não seja usado no prompt
    }
    response = client.post("/generation/generate/", json=data)
    assert response.status_code == 201
    assert "request_id" in response.json()


def test_generate_automation_script(client):
    data = {
        "parent": 34,  # Substitua pelo ID de um TestCase existente
        "task_type": "automation_script",
        "prompt_data": {
            "system": "Você é um especialista em automação de testes com {type_test}...",
            "user": "Gere um script de automação em {type_test} para o seguinte Caso de Teste (em Gherkin):\n\n{user_input}...",
            "assistant": "/*\n/// <reference types=Cypress />\n\ndescribe('Login de Usuário', ...",
            "user_input": "{\"scenario\": \"Identificação correta de elementos chave...\", \"given\": \"Que uma transcrição válida...\", \"when\": \"O sistema processa...\", \"then\": \"O sistema deve identificar...\"}"
        },
        "llm_config": {
            "llm": "openai",
            "model": "gpt-4-turbo",
            "temperature": 0.6,
            "max_tokens": 2048,
            "top_p": 1
        },
        "work_item_id": "asd123",  # Remova se não estiver usando
        "parent_board_id": "13asd",  # Remova se não estiver usando
        "type_test": "Cypress"  # Substitua pelo framework desejado (Cypress, Selenium, etc.)
    }
    response = client.post("/generation/generate/", json=data)
    assert response.status_code == 201
    assert "request_id" in response.json()

# --- Testes para a rota /reprocess ---

def test_reprocess_epic(client):
    # 1. (Opcional) Criar um Épico de teste no banco de dados (se necessário)

    epic_id = 1  # ID do Épico existente (substitua pelo ID real)
    data = {
        "prompt_data": {
            "system": "Você é um Product Owner experiente...",
            "user": "Antes de criar o Épico, analise o contexto...\n\n{user_input}\n\n...",
            "assistant": "{\"title\": \"Exemplo de Título\", ...}",
            "user_input": "{'title': 'Sistema de Gestão Integrada para Escola de Música', 'description': '... descrição original ...', 'observação': '... nova observação...'}"
        },
        "llm_config": {
            "llm": "openai",
            "model": "gpt-4-turbo",
            "temperature": 0.65,
            "max_tokens": 3500,
            "top_p": 1.0
        },
        "type_test": None
    }
    response = client.post(f"/generation/reprocess/epic/{epic_id}", json=data)  # Usar a rota correta
    assert response.status_code == 202
    assert "request_id" in response.json()

def test_reprocess_wbs(client):
    wbs_id = 1
    data = {
        "prompt_data": {
            "system": "Você é um especialista em gerenciamento de projetos...",
            "user": "Analise o texto a seguir e crie uma WBS completa...\n\nTexto:\n\n{user_input}",
            "assistant": "{\n  \"wbs\": [\n    {\n      \"title\": \"Exemplo de Épico...\",\n ...",
            "user_input": "{ \"WBS\": { \"wbs\": [ { \"title\": \"Épico: Automação de Azure DevOps com IA\", \"type\": \"epic\", \"children\": [ { \"title\": \"Feature: Análise de Transcrições com LLM\", \"type\": \"feature\", \"children\": [ { \"title\": \"User Story: Como sistema, quero enviar transcrições para LLM para análise\", \"type\": \"user story\", \"children\": [ { \"title\": \"Task: Desenvolver interface de comunicação com LLM\", \"type\": \"task\", \"children\": [] }, { \"title\": \"Task: Implementar envio de dados para LLM\", \"type\": \"task\", \"children\": [] } ] } ] }, { \"title\": \"Feature: Geração de Artefatos de Projeto\", \"type\": \"feature\", \"children\": [ { \"title\": \"User Story: Como sistema, quero gerar épicos a partir da análise de LLM\", \"type\": \"user story\", \"children\": [ { \"title\": \"Task: Desenvolver módulo de criação de épicos\", \"type\": \"task\", \"children\": [] } ] }, { \"title\": \"User Story: Como sistema, quero gerar features a partir da análise de LLM\", \"type\": \"user story\", \"children\": [ { \"title\": \"Task: Desenvolver módulo de criação de features\", \"type\": \"task\", \"children\": [] } ] }, { \"title\": \"User Story: Como sistema, quero gerar user stories a partir da análise de LLM\", \"type\": \"user story\", \"children\": [ { \"title\": \"Task: Desenvolver módulo de criação de user stories\", \"type\": \"task\", \"children\": [] } ] }, { \"title\": \"User Story: Como sistema, quero gerar test cases a partir da análise de LLM\", \"type\": \"user story\", \"children\": [ { \"title\": \"Task: Desenvolver módulo de criação de test cases\", \"type\": \"task\", \"children\": [] } ] } ] } ] } ] }, \"observação\": \"precisamos criar features voltadas para processamento de linguagem natural (PLN) e seus possíveis filhos derivados dessa feature, de forma imperativa essa deve ser a nossa primeira feature.\" }"
        },
        "llm_config": {
            "llm": "openai",
            "model": "gpt-4-turbo",
            "temperature": 0.65,
            "max_tokens": 4096,
            "top_p": 0.95
        },
        "type_test": None
    }
    response = client.post(f"/generation/reprocess/wbs/{wbs_id}", json=data)
    assert response.status_code == 202
    assert "request_id" in response.json()

def test_reprocess_feature(client):
    feature_id = 1
    data = {
        "prompt_data": {
            "system": "Você é um Analista de Negócios experiente...",
            "user": "Analise o texto abaixo...\n\nTexto:\n\n{user_input}",
            "assistant": "[\n  {\n    \"title\": \"Exemplo de Título de Funcionalidade\",\n    \"description\": \"Exemplo de descrição...\"\n  }\n]",
            "user_input": "{'title': 'Geração de Épicos', 'description': 'O sistema deverá ter a capacidade de gerar épicos automaticamente a partir das análises realizadas pela LLM...', 'observação': '...nova observação...'}"
        },
        "llm_config": {
            "llm": "openai",
            "model": "gpt-4-turbo",
            "temperature": 0.65,
            "max_tokens": 4096,
            "top_p": 1.0
        },
        "type_test": None
    }
    response = client.post(f"/generation/reprocess/feature/{feature_id}", json=data)
    assert response.status_code == 202
    assert "request_id" in response.json()

def test_reprocess_user_story(client):
    user_story_id = 1
    data = {
        "prompt_data": {
            "system": "Você é um especialista em metodologias ágeis...",
            "user": "Aqui está o contexto do Épico e da Feature:\n\n{user_input}\n\nAgora, com base nesse contexto...",
            "assistant": "[\n {\n \"title\": \"Título da User Story 1\",\n ...",
            "user_input": "{\"title\": \"Desenvolvimento do Frontend\", \"description\": \"Como desenvolvedor, quero criar a arquitetura do frontend separada do backend para facilitar a interação do usuário e atualizações de interface...\", \"acceptance_criteria\": \"...\", \"observações\": \"...detalhes adicionais...\"}"
        },
        "llm_config": {
            "llm": "openai",
            "model": "gpt-4-turbo",
            "temperature": 0.55,
            "max_tokens": 4096,
            "top_p": 0.95
        },
        "type_test": None
    }
    response = client.post(f"/generation/reprocess/user_story/{user_story_id}", json=data)
    assert response.status_code == 202
    assert "request_id" in response.json()

def test_reprocess_task(client):
    task_id = 1
    data = {
        "prompt_data": {
            "system": "Você é um Gerente de Projetos Ágeis experiente...",
            "user": "Aqui está a User Story para referência:\n\n{user_input}\n\nCrie as Tasks...",
            "assistant": "[\n  {\n    \"title\": \"Título da Task 1\",\n    \"description\": \"Descrição detalhada da Task 1.\",\n    \"estimate\": \"4h\"\n  },\n ...",
            "user_input": "{'title': 'Implementar API de Login', 'description': 'Como usuário, quero poder fazer login no sistema...', 'acceptance_criteria': '...'}"
        },
        "llm_config": {
            "llm": "openai",
            "model": "gpt-4-turbo",
            "temperature": 0.65,
            "max_tokens": 4096,
            "top_p": 0.95
        },
        "type_test": None
    }
    response = client.post(f"/generation/reprocess/task/{task_id}", json=data)
    assert response.status_code == 202
    assert "request_id" in response.json()

def test_reprocess_test_case(client):
    test_case_id = 1
    data = {
      "prompt_data": {
        "system": "Você é um Analista de Qualidade de Software sênior...",
        "user": "Crie os casos de teste necessários para a seguinte User Story:\n\n{user_input}\n\nRetorne SOMENTE...",
        "assistant": "[\n {\n \"title\": \"Exemplo de Título do Caso de Teste\",\n ...",
        "user_input": "{'title': 'Falha no processamento de transcrição com IA', 'gherkin': '...','actions': ['...']}"

      },
      "llm_config": {
        "llm": "openai",
        "model": "gpt-4-turbo",
        "temperature": 0.55,
        "max_tokens": 4096,
        "top_p": 0.95
      },
       "type_test": "Cypress"
    }
    response = client.post(f"/generation/reprocess/test_case/{test_case_id}", json=data)
    assert response.status_code == 202
    assert "request_id" in response.json()
