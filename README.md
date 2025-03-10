### API em python para conexão com C# e utilização do ChatGPT

## .env
Após clonar o repositório, é necessário criar um .env na reaiz do projeto.

## Docker
Após criar o .env, para executar precisará criar e executar a imagem (docker-compose up --build --force-recreate -d). Caso queira monitorar pode ser com docker-compose logs -f api.

## Swagger
Para acompanhar a documentação e fazer testes com a API, pode acessar no endereço: http://localhost:8000/docs.


## Fluxo da arquitetura API Python


### API Python (FastAPI):

Recebe as requisições do backend .NET no endpoint /generate/.

Valida os dados da requisição (usando Pydantic).

Cria um registro na tabela requests (com request_id, parent, task_type, status inicial "pending").

Enfileira uma task Celery (process_demand_task) com os dados da requisição (request_id_interno, task_type, prompt_data, llm_config).

Retorna uma resposta HTTP 201 Created imediatamente para o backend .NET, contendo o request_id interno da API Python. Não espera pelo resultado da task Celery.

Fornece o endpoint /status/{request_id} para que o backend .NET possa consultar o status da requisição.


### Celery Worker:

Executa em um processo separado (container Docker separado).

Consome tasks da fila task_queue do RabbitMQ.

Executa a função process_message_task:

Obtém os dados da task (incluindo request_id_interno e request_id_client).

Converte request_id_client para inteiro.

Chama a LLM (llm_agent.generate_text) para gerar o texto (Épico, Feature, etc.).

Faz o parsing da resposta da LLM.

Salva os dados gerados no banco de dados PostgreSQL.

Atualiza o status da requisição na tabela requests (para "completed" ou "failed").

Publica uma mensagem de notificação na fila notification_queue do RabbitMQ, informando o backend .NET sobre o resultado (sucesso ou falha).

Implementa retentativas automáticas (com backoff exponencial) em caso de falhas temporárias da LLM.


### RabbitMQ:

Atua como o message broker, gerenciando as filas de mensagens.

task_queue: Fila usada pelo Celery para as tasks de geração de itens.

notification_queue: Fila usada para notificar o backend .NET sobre o resultado do processamento.


### LLM (OpenAI/Gemini):

Recebe o prompt (preparado pelo Celery Worker) e gera o texto (Épico, Feature, etc.).

Retorna o texto gerado e a contagem de tokens (prompt e resposta).


### PostgreSQL:

Banco de dados relacional usado para armazenar os dados gerados (Épicos, Features, etc.), o status das requisições e outras informações relevantes.
