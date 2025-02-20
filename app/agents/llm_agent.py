from openai import OpenAI
import os
import google.generativeai as genai
from dotenv import load_dotenv
import logging

load_dotenv()

logger = logging.getLogger(__name__)

class LLMAgent:
    def __init__(self):
        self.openai_client = None
        self.gemini_client = None
        self.chosen_llm = os.getenv("CHOSEN_LLM", "openai")
        self.openai_model = os.getenv("OPENAI_MODEL", "gpt-3.5-turbo-0125")
        self.gemini_model = os.getenv("GEMINI_MODEL", "gemini-pro")
        self.temperature = float(os.getenv("TEMPERATURE", 0.7))
        self.max_tokens = int(os.getenv("MAX_TOKENS", 1000))
        self.top_p = float(os.getenv("TOP_P", 1.0))

    def get_openai_client(self):
        if self.openai_client is None:
            openai_api_key = os.getenv("OPENAI_API_KEY")
            if not openai_api_key:
                logger.error("Variável de ambiente OPENAI_API_KEY não configurada.")
                raise ValueError("OPENAI_API_KEY não configurada.")
            try:
                self.openai_client = OpenAI(api_key=openai_api_key)
                logger.info("Cliente OpenAI inicializado com sucesso.")
            except Exception as e:
                logger.error(f"Erro ao inicializar cliente OpenAI: {e}", exc_info=True)
                raise
        return self.openai_client

    def get_gemini_client(self):
        if self.gemini_client is None:
            gemini_api_key = os.getenv("GEMINI_API_KEY")
            if not gemini_api_key:
                logger.error("Variável de ambiente GEMINI_API_KEY não configurada.")
                raise ValueError("GEMINI_API_KEY não configurada.")
            try:
                genai.configure(api_key=gemini_api_key)
                self.gemini_client = genai.GenerativeModel(self.gemini_model)
                logger.info("Cliente Gemini inicializado com sucesso.")
            except Exception as e:
                logger.error(f"Erro ao inicializar cliente Gemini: {e}", exc_info=True)
                raise
        return self.gemini_client

    def generate_text(self, prompt_data: dict) -> dict:  # Retorna um dicionário
        logger.info(f"Gerando texto com LLM: {self.chosen_llm}")
        try:
            if self.chosen_llm == "openai":
                client = self.get_openai_client()
                response = client.chat.completions.create(
                    model=self.openai_model,
                    messages=[
                        {"role": "system", "content": prompt_data.get("system", "")},
                        {"role": "user", "content": prompt_data.get("user", "")},
                        {"role": "assistant", "content": prompt_data.get("assistant", "")}
                    ],
                    temperature=self.temperature,
                    max_tokens=self.max_tokens,
                    top_p=self.top_p
                )
                logger.debug(f"Resposta da OpenAI: {response.choices[0].message.content}")

                # --- Contagem de Tokens (OpenAI) ---
                prompt_tokens = response.usage.prompt_tokens
                completion_tokens = response.usage.completion_tokens

                return {
                    "text": response.choices[0].message.content,
                    "prompt_tokens": prompt_tokens,
                    "completion_tokens": completion_tokens,
                }

            elif self.chosen_llm == "gemini":
                client = self.get_gemini_client()

                # --- Contagem de Tokens (Gemini) - ANTES da requisição ---
                request = f"""
                system: {prompt_data.get("system", "")}
                user: {prompt_data.get("user", "")}
                assistant: {prompt_data.get("assistant", "")}
                """

                # Contagem ANTES da chamada
                token_count = client.count_tokens(request)
                prompt_tokens = token_count.total_tokens


                safety_settings = [
                    {
                        "category": "HARM_CATEGORY_HARASSMENT",
                        "threshold": "BLOCK_NONE"
                    },
                    {
                        "category": "HARM_CATEGORY_HATE_SPEECH",
                        "threshold": "BLOCK_NONE"
                    },
                    {
                        "category": "HARM_CATEGORY_SEXUALLY_EXPLICIT",
                        "threshold": "BLOCK_NONE"
                    },
                    {
                        "category": "HARM_CATEGORY_DANGEROUS_CONTENT",
                        "threshold": "BLOCK_NONE"
                    }
                ]

                generation_config = genai.types.GenerationConfig(
                    candidate_count=1,
                    max_output_tokens=self.max_tokens,
                    temperature=self.temperature
                )

                response = client.generate_content(
                    request,
                    generation_config=generation_config,
                    safety_settings=safety_settings
                )

                completion_tokens = client.count_tokens(response.text).total_tokens


                logger.debug(f"Resposta do Gemini: {response.text}")
                return {
                    "text": response.text,
                    "prompt_tokens": prompt_tokens,
                    "completion_tokens": completion_tokens,
                }
            else:
                error_message = f"LLM desconhecida: {self.chosen_llm}"
                logger.error(error_message)
                raise ValueError(error_message)

        except Exception as e:
            logger.error(f"Erro ao gerar texto com LLM {self.chosen_llm}: {e}", exc_info=True)
            raise
