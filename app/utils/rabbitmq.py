from tenacity import retry, stop_after_attempt, wait_fixed, retry_if_exception_type
import pika
import json
import logging
import os
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)

RABBITMQ_HOST = os.getenv("RABBITMQ_HOST")
RABBITMQ_QUEUE = os.getenv("RABBITMQ_QUEUE")
RABBITMQ_USER = os.getenv("RABBITMQ_USER", "guest")
RABBITMQ_PASSWORD = os.getenv("RABBITMQ_PASSWORD", "guest")
NOTIFICATION_QUEUE = "notification_queue"


class RabbitMQProducer:
    def __init__(self):
        self.connection = None
        self.channel = None
        self._connect()

    def _connect(self):
        try:
            credentials = pika.PlainCredentials(RABBITMQ_USER, RABBITMQ_PASSWORD)
            parameters = pika.ConnectionParameters(
                host=RABBITMQ_HOST, credentials=credentials, heartbeat=600, blocked_connection_timeout=300)
            self.connection = pika.BlockingConnection(parameters)
            self.channel = self.connection.channel()
            self.channel.queue_declare(queue=RABBITMQ_QUEUE, durable=True)
            self.channel.queue_declare(queue=NOTIFICATION_QUEUE, durable=True) # Declara a nova fila
            logger.info(f"Conectado ao RabbitMQ em {RABBITMQ_HOST}")
        except pika.exceptions.AMQPConnectionError as e:
            logger.error(f"Erro ao conectar ao RabbitMQ: {e}", exc_info=True)
            raise

    @retry(
            retry=retry_if_exception_type(pika.exceptions.AMQPError), # Tenta em erros AMQP
            stop=stop_after_attempt(3), # Tenta 3 vezes no total
            wait=wait_fixed(2), # Espera 2 segundos entre tentativas
            reraise=True # Re-levanta a exceção se todas as tentativas falharem
        )
    def publish(self, message: dict, queue_name: str = RABBITMQ_QUEUE): # Método genérico para publicar
        if not self.connection or not self.connection.is_open:
            self._connect()
        try:
            self.channel.basic_publish(
                exchange='',
                routing_key=queue_name,  # Usa o nome da fila fornecido
                body=json.dumps(message),
                properties=pika.BasicProperties(delivery_mode=2)
            )
            logger.debug(f"Mensagem publicada no RabbitMQ (fila {queue_name}): {message}")
        except pika.exceptions.AMQPError as e:
            logger.error(f"Erro ao publicar mensagem no RabbitMQ: {e}", exc_info=True)
            self._connect() # Tenta reconectar em caso de erro de publicação
            raise
        except pika.exceptions.AMQPChannelError as e:
            logger.warning(f"Erro de canal ao publicar, tentando recriar canal: {e}")
             # Recriar canal pode ser complexo, talvez reconectar seja mais simples
            self._connect()
            raise # Re-levanta para retry
        except Exception as e: # Capturar outros erros
            logger.error(f"Erro inesperado ao publicar: {e}", exc_info=True)
            raise # Re-levanta

    def close(self):
        if self.connection and self.connection.is_open:
            self.connection.close()
            logger.info("Conexão RabbitMQ fechada.")

    def __del__(self):
        self.close()


class RabbitMQConsumer: # Classe consumer não muda
    def __init__(self, callback):
        self.connection = None
        self.channel = None
        self.callback = callback
        self._connect()

    def _connect(self):
        try:
            credentials = pika.PlainCredentials(RABBITMQ_USER, RABBITMQ_PASSWORD)
            parameters = pika.ConnectionParameters(
                host=RABBITMQ_HOST, credentials=credentials, heartbeat=600, blocked_connection_timeout=300)
            self.connection = pika.BlockingConnection(parameters)
            self.channel = self.connection.channel()
            self.channel.queue_declare(queue=RABBITMQ_QUEUE, durable=True) # Mantem a declaração da fila de task
            logger.info(f"Conectado ao RabbitMQ em {RABBITMQ_HOST}, queue: {RABBITMQ_QUEUE}")
            self.channel.basic_qos(prefetch_count=1)
        except pika.exceptions.AMQPConnectionError as e:
            logger.error(f"Erro ao conectar ao RabbitMQ: {e}", exc_info=True)
            raise


    @retry(stop=stop_after_attempt(3), wait=wait_fixed(2), retry_error_callback=lambda retry_state: logger.warning(f"Tentativa de reconexão ao RabbitMQ ({retry_state.attempt_number}/{retry_state.outcome_sentinel})..."))
    def start_consuming(self):
        try:
            self.channel.basic_consume(queue=RABBITMQ_QUEUE, on_message_callback=self._process_message)
            logger.info("Consumer RabbitMQ aguardando mensagens...")
            self.channel.start_consuming()
        except pika.exceptions.AMQPConnectionError as e:
            logger.error(f"Erro de conexão AMQP durante consumo: {e}", exc_info=True)
            self._connect()
            raise

    def _process_message(self, ch, method, properties, body):
        try:
            self.callback(ch, method, properties, body)
        except Exception as e:
            logger.error(f"Erro ao processar mensagem: {e}", exc_info=True)
            ch.basic_nack(delivery_tag=method.delivery_tag, requeue=True)
    
    def close(self):
        if self.connection and self.connection.is_open:
            self.connection.close()
            logger.info("Conexão RabbitMQ Consumer fechada.")

    def __del__(self):
        self.close()
