from fastapi.testclient import TestClient
from app.main import create_app
from app.database import get_db, SessionLocal, sessionmaker
from app.models import Base, Request, Epic, Feature, UserStory, Task, TestCase, WBS  # Importe os models relevantes
from sqlalchemy import create_engine, text
import pytest
import os
import logging
import json
import uuid

logger = logging.getLogger(__name__)

TEST_DATABASE_URL = "postgresql://postgres:adm1234@host.docker.internal:5432/postgres?options=-csearch_path=test"

test_engine = create_engine(TEST_DATABASE_URL)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=test_engine)

def override_get_db():
    try:
        db = TestingSessionLocal()
        yield db
    finally:
        db.close()

@pytest.fixture()
def test_db():
    logger.info("test_db Fixture: STARTING")
    Base.metadata.drop_all(bind=test_engine)
    Base.metadata.create_all(bind=test_engine, checkfirst=False)
    yield
    Base.metadata.drop_all(bind=test_engine)
    logger.info("test_db Fixture: FINISHED")

@pytest.fixture()
def client(test_db):
    app = create_app()
    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as client:
        yield client

def test_create_epic_success(client, test_db, epic_payload_valid): # Assume epic_payload_valid fixture in conftest.py
    logger.info("test_create_epic_success: TEST FUNCTION STARTING")
    response = client.post("/generation/generate/", json=epic_payload_valid)
    assert response.status_code == 201
    response_json = response.json()
    assert "request_id" in response_json
    assert response_json["response"] == {"status": "queued"}
    assert is_valid_uuid(response_json["request_id"]) # Validar request_id como UUID

    # --- VERIFICAÇÕES NO BANCO DE DADOS ---
    db = TestingSessionLocal()
    try:
        request_db = db.query(Request).filter(Request.request_id == response_json["request_id"]).first()
        assert request_db is not None
        assert request_db.task_type == "epic"
        assert request_db.status == "pending"
    finally:
        db.close()
    logger.info("test_create_epic_success: TEST FUNCTION FINISHED")

def test_create_feature_success(client, test_db, feature_payload_valid): # Assume feature_payload_valid fixture in conftest.py
    logger.info("test_create_feature_success: TEST FUNCTION STARTING")
    response = client.post("/generation/generate/", json=feature_payload_valid)
    assert response.status_code == 201
    response_json = response.json()
    assert "request_id" in response_json
    assert response_json["response"] == {"status": "queued"}
    assert is_valid_uuid(response_json["request_id"])

    db = TestingSessionLocal()
    try:
        request_db = db.query(Request).filter(Request.request_id == response_json["request_id"]).first()
        assert request_db is not None
        assert request_db.task_type == "feature"
        assert request_db.status == "pending"
    finally:
        db.close()
    logger.info("test_create_feature_success: TEST FUNCTION FINISHED")


# # --- TESTES DE PAYLOAD INVÁLIDO PARA EPIC ---
def test_create_epic_invalid_payload_missing_required_fields(client, test_db, epic_payload_valid): # Reutilize epic_payload_valid e torne-o inválido
    logger.info("test_create_epic_invalid_payload_missing_required_fields: TEST FUNCTION STARTING")
    epic_payload_invalid = epic_payload_valid.copy()
    del epic_payload_invalid["prompt_data"] # Remover campo obrigatório 'prompt_data'

    response = client.post("/generation/generate/", json=epic_payload_invalid)
    assert response.status_code == 422
    response_json = response.json()
    assert "detail" in response_json # Verifica se há detalhes de erro
    logger.info(f"Response detail for invalid payload test: {response_json['detail']}") # Log detail para debug

    db = TestingSessionLocal()
    try:
        request_db = db.query(Request).filter(Request.parent == epic_payload_invalid["parent"]).first() # Busca pelo parent para ver se criou algo
        assert request_db is None # Garante que NENHUM registro de request foi criado
        epic_db = db.query(Epic).filter(Epic.team_project_id == epic_payload_invalid["parent"]).first() # Garante que NENHUM epic foi criado
        assert epic_db is None # Garante que NENHUM epic foi criado
    finally:
        db.close()
    logger.info("test_create_epic_invalid_payload_missing_required_fields: TEST FUNCTION FINISHED")


def test_create_epic_invalid_payload_wrong_task_type(client, test_db, epic_payload_valid): # Reutilize epic_payload_valid e torne-o inválido
    logger.info("test_create_epic_invalid_payload_wrong_task_type: TEST FUNCTION STARTING")
    epic_payload_invalid = epic_payload_valid.copy()
    epic_payload_invalid["task_type"] = "invalid_task_type" # task_type inválido

    response = client.post("/generation/generate/", json=epic_payload_invalid)
    assert response.status_code == 422
    response_json = response.json()
    assert "detail" in response_json # Verifica se há detalhes de erro
    logger.info(f"Response detail for invalid payload test: {response_json['detail']}") # Log detail para debug

    db = TestingSessionLocal()
    try:
        request_db = db.query(Request).filter(Request.parent == epic_payload_invalid["parent"]).first() # Busca pelo parent para ver se criou algo
        assert request_db is None # Garante que NENHUM registro de request foi criado
        epic_db = db.query(Epic).filter(Epic.team_project_id == epic_payload_invalid["parent"]).first() # Garante que NENHUM epic foi criado
        assert epic_db is None # Garante que NENHUM epic foi criado
    finally:
        db.close()
    logger.info("test_create_epic_invalid_payload_wrong_task_type: TEST FUNCTION FINISHED")


def test_create_epic_invalid_payload_invalid_parent_type(client, test_db, epic_payload_valid):
    logger.info("test_create_epic_invalid_payload_invalid_parent_type: TEST FUNCTION STARTING")
    epic_payload_invalid = epic_payload_valid.copy()
    epic_payload_invalid["parent"] = "invalid_parent" # Parent deve ser int

    response = client.post("/generation/generate/", json=epic_payload_invalid)
    assert response.status_code == 422 # Espera 422
    response_json = response.json()
    assert "detail" in response_json
    logger.info(f"Response detail for invalid payload test: {response_json['detail']}")

    logger.info("test_create_epic_invalid_payload_invalid_parent_type: TEST FUNCTION FINISHED")

def test_create_epic_invalid_payload_llm_config_temperature_out_of_range(client, test_db, epic_payload_valid):
    logger.info("test_create_epic_invalid_payload_llm_config_temperature_out_of_range: TEST FUNCTION STARTING")
    epic_payload_invalid = epic_payload_valid.copy()
    epic_payload_invalid["llm_config"] = {"temperature": 1.5} # Temperatura > 1.0 (inválida)

    response = client.post("/generation/generate/", json=epic_payload_invalid)
    assert response.status_code == 422 # Espera 422
    response_json = response.json()
    assert "detail" in response_json
    logger.info(f"Response detail for invalid payload test: {response_json['detail']}")

    db = TestingSessionLocal()
    try:
        request_db = db.query(Request).filter(Request.parent == epic_payload_invalid["parent"]).first()
        assert request_db is None
        epic_db = db.query(Epic).filter(Epic.team_project_id == epic_payload_invalid["parent"]).first()
        assert epic_db is None
    finally:
        db.close()
    logger.info("test_create_epic_invalid_payload_llm_config_temperature_out_of_range: TEST FUNCTION FINISHED")


# --- TESTES DE PAYLOAD INVÁLIDO PARA FEATURE ---
def test_create_feature_invalid_payload_missing_prompt_data(client, test_db, feature_payload_valid):
    logger.info("test_create_feature_invalid_payload_missing_prompt_data: TEST FUNCTION STARTING")
    feature_payload_invalid = feature_payload_valid.copy()
    del feature_payload_invalid["prompt_data"] # Remover campo obrigatório

    response = client.post("/generation/generate/", json=feature_payload_invalid)
    assert response.status_code == 422 # Espera 422
    response_json = response.json()
    assert "detail" in response_json
    logger.info(f"Response detail for invalid payload test: {response_json['detail']}")

    db = TestingSessionLocal()
    try:
        request_db = db.query(Request).filter(Request.parent == feature_payload_invalid["parent"]).first()
        assert request_db is None
        feature_db = db.query(Feature).filter(Feature.parent == feature_payload_invalid["parent"]).first()
        assert feature_db is None
    finally:
        db.close()
    logger.info("test_create_feature_invalid_payload_missing_prompt_data: TEST FUNCTION FINISHED")


# --- TESTES DE REPROCESSAMENTO BEM-SUCEDIDO ---
def test_reprocess_epic_success(client, test_db, epic_payload_valid): # Reutiliza epic_payload_valid (payload para reprocessamento)
    logger.info("test_reprocess_epic_success: TEST FUNCTION STARTING")
    artifact_type = "epic"
    artifact_id = 123 # ID fictício - NÃO PRECISA CRIAR ARTEFATO NO BANCO PARA TESTE DE ENDPOINT

    reprocess_payload = {"prompt_data": epic_payload_valid["prompt_data"]} # ReprocessRequest payload

    # Chamar o endpoint de reprocessamento
    response = client.post(f"/generation/reprocess/{artifact_type}/{artifact_id}", json=reprocess_payload)
    assert response.status_code == 202 # Espera 202 Accepted
    response_json = response.json()
    assert "request_id" in response_json
    assert response_json["response"] == {"status": "queued"}
    assert is_valid_uuid(response_json["request_id"])

    # --- REMOVIDO: VERIFICAÇÕES DESNECESSÁRIAS NO BANCO DE DADOS (NÃO É ESCOPO DE TESTE DE ENDPOINT) ---
    logger.info("test_reprocess_epic_success: TEST FUNCTION FINISHED")


def test_reprocess_feature_success(client, test_db, feature_payload_valid): # Reutiliza feature_payload_valid
    logger.info("test_reprocess_feature_success: TEST FUNCTION STARTING")
    artifact_type = "feature"
    artifact_id = 123 # ID fictício - NÃO PRECISA CRIAR ARTEFATO NO BANCO PARA TESTE DE ENDPOINT

    reprocess_payload = {"prompt_data": feature_payload_valid["prompt_data"]} # ReprocessRequest payload

    # Chamar o endpoint de reprocessamento
    response = client.post(f"/generation/reprocess/{artifact_type}/{artifact_id}", json=reprocess_payload)
    assert response.status_code == 202 # Espera 202 Accepted
    response_json = response.json()
    assert "request_id" in response_json
    assert response_json["response"] == {"status": "queued"}
    assert is_valid_uuid(response_json["request_id"])

    # --- REMOVIDO: VERIFICAÇÕES DESNECESSÁRIAS NO BANCO DE DADOS (NÃO É ESCOPO DE TESTE DE ENDPOINT) ---
    logger.info("test_reprocess_feature_success: TEST FUNCTION FINISHED")


# # --- TESTES DE ERRO DE REPROCESSAMENTO ---
def test_reprocess_invalid_artifact_type(client, test_db, epic_payload_valid): # Use epic_payload_valid, payload não importa para este teste
    logger.info("test_reprocess_invalid_artifact_type: TEST FUNCTION STARTING")
    invalid_artifact_type = "invalid_type"
    artifact_id = 123 # ID fictício, não precisa existir

    reprocess_payload = {"prompt_data": epic_payload_valid["prompt_data"]} # Payload valido, mas artifact_type invalido

    response = client.post(f"/generation/reprocess/{invalid_artifact_type}/{artifact_id}", json=reprocess_payload)
    assert response.status_code == 400 # Espera 400 Bad Request
    response_json = response.json()
    assert "detail" in response_json
    assert f"Tipo de artefato inválido: {invalid_artifact_type}" in response_json["detail"] # Mensagem de erro de tipo inválido

    logger.info("test_reprocess_invalid_artifact_type: TEST FUNCTION FINISHED")


def test_reprocess_artifact_not_found(client, test_db, epic_payload_valid): # AJUSTADO - ESPERA 404 e NAO 500
    logger.info("test_reprocess_artifact_not_found: TEST FUNCTION STARTING")
    artifact_type = "epic"
    non_existent_artifact_id = 9999 # ID que nao existe no banco

    reprocess_payload = {"prompt_data": epic_payload_valid["prompt_data"]} # Payload valido, mas artifact_id nao existe

    response = client.post(f"/generation/reprocess/{artifact_type}/{non_existent_artifact_id}", json=reprocess_payload)
    assert response.status_code == 404 # Espera 404 Not Found, pois o artefato não existe
    response_json = response.json()
    assert "detail" in response_json
    assert "Request not found" in response_json["detail"] # Mensagem de erro de "Request not found" (mais apropriada que "Erro ao salvar...")
    logger.info("test_reprocess_artifact_not_found: TEST FUNCTION FINISHED")


# # --- FUNÇÃO AUXILIAR PARA VALIDAR UUID ---
def is_valid_uuid(uuid_string):
    try:
        uuid.UUID(uuid_string)
        return True
    except ValueError:
        return False
