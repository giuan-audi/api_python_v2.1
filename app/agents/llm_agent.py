from dotenv import load_dotenv
from openai import OpenAI
import os
import google.generativeai as genai
import logging
from tenacity import retry, stop_after_attempt, wait_fixed, retry_if_exception_type
import requests
import openai
import google.api_core.exceptions

load_dotenv()

logger = logging.getLogger(__name__)


class InvalidModelError(Exception):  # Exceção personalizada
    """Exceção para modelos de LLM inválidos ou descontinuados."""
    pass


class LLMAgent:
    def __init__(self):
        self.openai_client = None
        self.gemini_client = None
        self.chosen_llm = os.getenv("CHOSEN_LLM", "openai")
        self.openai_model = os.getenv("OPENAI_MODEL", "gpt-3.5-turbo-0125")
        self.gemini_model = os.getenv("GEMINI_MODEL", "gemini-pro")
        self.temperature = float(os.getenv("TEMPERATURE", 0.75))
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

    @retry(
        retry=retry_if_exception_type((
            openai.APITimeoutError,
            openai.APIConnectionError,
            openai.RateLimitError,
            google.api_core.exceptions.ServiceUnavailable,
            google.api_core.exceptions.ResourceExhausted,
            requests.exceptions.RequestException
        )),
        stop=stop_after_attempt(5),
        wait=wait_fixed(2),
        reraise=True
    )
    def generate_text(self, prompt_data: dict, llm_config: dict = None) -> dict:
        logger.info(f"Gerando texto com LLM")

        chosen_llm = self.chosen_llm
        openai_model = self.openai_model
        gemini_model = self.gemini_model
        temperature = self.temperature
        max_tokens = self.max_tokens
        top_p = self.top_p

        if llm_config:
            chosen_llm = llm_config.get("llm", chosen_llm)
            temperature = llm_config.get("temperature", temperature)
            max_tokens = llm_config.get("max_tokens", max_tokens)
            top_p = llm_config.get("top_p", top_p)
            if chosen_llm == "openai":
                model = llm_config.get("model")
                if model is not None:
                    openai_model = model
            elif chosen_llm == "gemini":
                model = llm_config.get("model")
                if model is not None:
                    gemini_model = model
            else:
                error_message = f"LLM desconhecida: {self.chosen_llm}"
                logger.error(error_message)
                raise ValueError(error_message)

        if chosen_llm == 'openai':
            if openai_model is None:
                openai_model = os.getenv("OPENAI_MODEL", "gpt-3.5-turbo-0125")
            model_to_use = openai_model
        else:
            if gemini_model is None:
                gemini_model = os.getenv("GEMINI_MODEL", "gemini-pro")
            model_to_use = gemini_model
        
        formatted_prompt_log = f"Prompt Data para LLM ({chosen_llm}): {prompt_data}"
        logger.info(formatted_prompt_log)

        try:
            if chosen_llm == "openai":
                client = self.get_openai_client()
                response = client.chat.completions.create(
                    model=model_to_use,
                    messages=[
                        {"role": "system", "content": prompt_data.get("system", "")},
                        {"role": "user", "content": prompt_data.get("user", "")},
                        {"role": "assistant", "content": prompt_data.get("assistant", "")}
                    ],
                    temperature=temperature,
                    max_tokens=max_tokens,
                    top_p=top_p
                )
                # teste de log.
                logger.info(f"Resposta da OpenAI: {response.choices[0].message.content}")

                prompt_tokens = response.usage.prompt_tokens
                completion_tokens = response.usage.completion_tokens

                return {
                    "text": response.choices[0].message.content,
                    "prompt_tokens": prompt_tokens,
                    "completion_tokens": completion_tokens,
                }

            elif chosen_llm == "gemini":
                client = self.get_gemini_client()

                request = f"""
                system: {prompt_data.get("system", "")}
                user: {prompt_data.get("user", "")}
                assistant: {prompt_data.get("assistant", "")}
                """

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
                    max_output_tokens=max_tokens,
                    temperature=temperature
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
                error_message = f"LLM desconhecida: {chosen_llm}"
                logger.error(error_message)
                raise ValueError(error_message)

        except openai.NotFoundError as e:  # Captura erro específico da OpenAI
            error_message = f"Modelo OpenAI inválido/descontinuado: {model_to_use}. Erro: {e}"
            logger.error(error_message, exc_info=True)
            raise InvalidModelError(error_message) from e  # Lança exceção personalizada

        except google.api_core.exceptions.NotFound as e:  # Captura erro específico do Gemini (se for NotFound)
            error_message = f"Modelo Gemini inválido/descontinuado: {model_to_use}. Erro: {e}"
            logger.error(error_message, exc_info=True)
            raise InvalidModelError(error_message) from e

        except Exception as e: #Exceções genericas
            logger.error(f"Erro ao gerar texto com LLM {chosen_llm}: {e}", exc_info=True)
            raise
