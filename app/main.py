from fastapi import FastAPI
from app.routers import generation
# from app.database import create_tables
import logging
from contextlib import asynccontextmanager  # <--- Importar asynccontextmanager

logger = logging.getLogger(__name__)

@asynccontextmanager  # <--- Decorador
async def lifespan(app: FastAPI):  # <--- Função lifespan, recebe a app como argumento
    # Startup logic (create tables)
    try:
        pass
        # create_tables()
        # logger.info("Tabelas criadas com sucesso (se não existiam).")
    except Exception as e:
        pass
        # logger.error(f"Erro ao criar tabelas: {e}", exc_info=True)
    yield  # <---  Ponto de "pausa" entre startup e shutdown
    # Shutdown logic (nothing to do here, in this case)


def create_app() -> FastAPI:
    """
    Cria e configura a instância da aplicação FastAPI.
    """
    app = FastAPI(
        title="AI Demand Management API",
        description="API para integracao com Azure DevOps e LLMs",
        version="1.0.0",
        openapi_tags=[{
            "name": "Generation",
            "description": "Endpoints para geracao de artefatos"
        }],
        lifespan=lifespan,  # <--- Passa a função lifespan
    )

    # Rotas
    app.include_router(generation.router, prefix="/generation", tags=["generation"])

    return app
