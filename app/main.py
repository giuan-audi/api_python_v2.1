from fastapi import FastAPI
from app.routers import generation
from app.database import create_tables

app = FastAPI(
    title="AI Demand Management API",
    description="API para integracao com Azure DevOps e LLMs",
    version="1.0.0",
    openapi_tags=[{
        "name": "Generation",
        "description": "Endpoints para geracao de artefatos"
    }]
)


# Cria as tabelas ao iniciar
@app.on_event("startup")
def startup_event():
    create_tables()


app.include_router(generation.router, prefix="/generation", tags=["generation"])
