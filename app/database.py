from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from .models import Base
from dotenv import load_dotenv
import os
import logging

logger = logging.getLogger(__name__)

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")
if not DATABASE_URL:
    logger.error("Variável de ambiente DATABASE_URL não configurada.")  # LOG ANTES DE LANÇAR A EXCEÇÃO
    raise ValueError("DATABASE_URL environment variable not set")

print(f"Using database: {DATABASE_URL}")

# Adicionar timeout global (opcional)
engine = create_engine(DATABASE_URL, connect_args={"options": "-c statement_timeout=5000"})  # Timeout de 5 segundos (5000 ms)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# def create_tables():
#     Base.metadata.create_all(bind=engine)
