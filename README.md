### API em python para conexão com C# e utilização do ChatGPT

## .env
Após clonar o repositório, é necessário criar um .env na reaiz do projeto com as seguintes informações:

DATABASE_URL=postgresql://postgres:adm1234@db:5433/postgres
OPENAI_API_KEY=sk-proj-Y4qzKWiktbnSvpBn
GOOGLE_API_KEY=AIzaSyDx
CHOSEN_LLM=openai

## Docker
Após criar o .env, para executar precisará criar e executar a imagem (docker-compose up --build --force-recreate -d). Caso queira monitorar pode ser com docker-compose logs -f api.

## Swagger
Para acompanhar a documentação e fazer testes com a API, pode acessar no endereço: http://localhost:8000/docs.
