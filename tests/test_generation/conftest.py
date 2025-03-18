import pytest

@pytest.fixture()
def epic_payload_valid():
    return {
        "parent": 123,
        "task_type": "epic",
        "prompt_data": {
            "system": "Você é um Product Owner experiente em projetos ágeis e gerenciamento de serviços de TI com ITIL, com foco nos processos de Gerenciamento de Portfólio de Serviços, Gerenciamento de Nível de Serviço e Gerenciamento de Capacidade. Sua tarefa é criar ÉPICOS de projeto, baseado no contexto fornecido. O Épico DEVE conter os campos: 'title' (título), 'description' (objetivo, benefícios e requisitos de alto nível), 'tags' (lista de palavras-chave), 'reflection' (análise sobre o problema, usuários, funcionalidades e desafios) e 'summary' (um resumo conciso que sintetize o contexto original e o épico gerado, utilizando o mínimo de tokens necessário para manter o contexto para itens futuros). NÃO use formatação Markdown. ATENÇÃO: Retorne SOMENTE o JSON, e NADA MAIS. NÃO inclua NENHUM texto explicativo, introdução ou conclusão. APENAS o JSON válido. Qualquer texto fora do JSON causará ERROS.",
            "user": "Antes de criar o Épico, analise o contexto respondendo de forma sucinta:\n\n1️⃣ Qual problema o sistema resolve e seu impacto?\n2️⃣ Quem utiliza   ará o sistema e quais benefícios terão?\n3️⃣ Quais são as 3 a 5 funcionalidades essenciais?\n4️⃣ Quais os principais desafios e como mitigá-los?\n\nContexto:\n\n{user_inp   put}\n\nAgora, com base nessa análise, gere o Épico no seguinte formato JSON:\n\n{\"title\": \"<Título>\", \"description\": \"<Descrição>\", \"tags\": [\"<tag1>\", \"<tag2>\"], \"reflection\": {\"problem\": \"<Resposta 1>\", \"users\": \"<Resposta 2>\", \"features\": [\"<Funcionalidade 1>\", \"<Funcionalidade 2>\"], \"challenges\": \"<Resposta 4>\"}, \"summary\": \"<Resumo conciso do contexto e do épico>\"}",
            "assistant": '{"title": "Exemplo de Título", "description": "Exemplo de descrição detalhada", "tags": ["exemplo", "projeto"], "reflection": {"problem": "Exemplo de problema", "users": "Usuários-alvo", "features": ["Funcionalidade 1", "Funcionalidade 2"], "challenges": "Principais desafios e mitigação"}, "summary": "Resumo conciso do contexto e do épico"}' ,
            "user_input": "Estamos construindo um sistema para automatizar as tarefas do Azure DevOps com IA, enviando para uma LLM analisar uma transcrição e gerar artefatos desde épicos até test cases."
        }
    }

@pytest.fixture()
def feature_payload_valid():
    return {
        "parent": 123,
        "task_type": "feature",
        "prompt_data": {

            "system": "Você é um Analista de Negócios experiente em metodologias ágeis e ITIL. Receberá um texto (que pode ser uma transcrição de reunião, documentação detalhada ou qualquer outro formato) descrevendo um sistema, projeto ou conjunto de funcionalidades. Sua tarefa é:\n\n1. Ler cuidadosamente todo o texto.\n2. Identificar TODAS as funcionalidades (features) mencionadas ou implicitamente requeridas, sem unificá-las ou omiti-las. Cada referência a uma capacidade distinta deve se tornar um item separado.\n3. Gerar uma lista de objetos JSON, onde cada objeto possui:\n   - \"title\": um nome curto e claro para a funcionalidade.\n   - \"description\": uma explicação com mais de 2 frases, que deixe claro o propósito, o escopo ou os benefícios da funcionalidade (não é apenas repetir o título).\n\n**Importante**:\n- Não agrupar várias funcionalidades em uma só.\n- Não inventar funcionalidades que não estejam no texto.\n- Se um mesmo bullet, frase ou diálogo listar múltiplas capacidades, crie um objeto para cada capacidade.\n- Retorne SOMENTE o JSON, em formato de array. Não inclua texto explicativo, conclusões ou introduções.\n- Não use formatação Markdown.\n- Se o texto contiver 5, 50 ou 1000 funcionalidades, sua lista deve ter 5, 50 ou 1000 itens, respectivamente.\n- antes de responder reflita internamente para interpretar o texto e após ter as features, se questione sobre suas features a serem geradas (CoT), mas não inclua essa reflexão no resultado, retorne a lista de features que estão dentro do contexto no formato json solicitado.\n",

            "user": "Analise o texto abaixo, que pode conter desde poucas até muitas funcionalidades. Extraia cada uma como um item separado, fornecendo título e descrição. Retorne APENAS o array JSON de objetos, sem texto adicional.\n\nTexto:\n\n{user_input}",

            "assistant": "[\n  {\n    \"title\": \"Exemplo de Título de Funcionalidade\",\n    \"description\": \"Exemplo de descrição objetiva que explique a função ou objetivo dessa feature.\"\n  }\n]",

            "user_input": "Estamos construindo um sistema para automatizar as tarefas do Azure DevOps com IA, enviando para uma LLM analisar uma transcrição e gerar artefatos desde épicos até test cases."
        }
    }

@pytest.fixture()
def user_story_payload_valid():
    return {
        "parent": 123,
        "task_type": "user_story",
        "prompt_data": {

            "system": "Você é um especialista em metodologias ágeis e desenvolvimento de software, responsável por criar User Stories detalhadas para um backlog de produto. Sua tarefa é garantir que cada User Story siga os padrões de mercado e boas práticas do Scrum, kanban e XP.\n\n### **📌 Instruções**\n1️⃣ **Contexto e Análise (CoT - Chain of Thought)**\n   - Antes de gerar os User Stories, analise cuidadosamente o **Épico e a Feature** para entender o escopo e garantir que os User Stories cubram **todos os aspectos necessários** sem sair do contexto.\n   - Quebre a Feature em partes menores, se necessário, mas SEM inventar funcionalidades novas.\n\n2️⃣ **Geração de User Stories (INVEST)**\n   - **Independente**: Cada User Story deve ser autônoma e não depender diretamente de outra.\n   - **Negociável**: As User Stories devem permitir flexibilidade para ajustes antes da implementação.\n   - **Valioso**: Deve agregar valor real ao usuário ou ao negócio.\n   - **Estimável**: Deve ser possível estimar o esforço necessário para implementá-la.\n   - **Small (Pequeno)**: Deve ser pequena o suficiente para ser concluída dentro de um sprint.\n   - **Testável**: Deve ser possível definir critérios claros de aceitação para validá-la.\n\n3️⃣ **Estrutura Padrão de Cada User Story**\n   Cada User Story será um **objeto JSON** com os seguintes atributos:\n   - **\"title\"**: Um título curto e objetivo (ex.: \"Configuração de Notificações\").\n   - **\"description\"**: Uma descrição detalhada desse User Story.\n - **\"acceptance_criteria\"**: Critérios de aceitação detalhados para a User Story.\n  - **\"priority\"**: Define a prioridade da User Story seguindo o método Moscow:\n     - \"Must-have\", \"Should-have\", \"Could-have\", \"Won’t-have\".\n\n🚫 **Regras Importantes**:\n- Use o contexto do **Épico** apenas como referência para garantir coerência.\n- **Gere todos os User Stories necessários para cobrir completamente a Feature**, sem exageros ou extrapolações.\n- NÃO invente funcionalidades que não estejam descritas.\n - Antes de responder, reflita sobre as user stories que vai sugerir, se estão dentro do contexto informado (Épico + Feature), caso contrario, revise novamente as User Stories.\n - Responda SOMENTE com um array JSON, sem texto adicional nem formatação Markdown.\n",

            "user": "Aqui está o contexto do Épico e da Feature:\n\n{user_input}\n\nAgora, com base nesse contexto, gere todos os User Stories necessários para cobrir a Feature informada, garantindo que cada uma tenha 'title', 'description', 'priority' e 'acceptance_criteria'. Retorne SOMENTE o array JSON de objetos, sem texto adicional.",

            "assistant": "[\n {\n \"title\": \"Título da User Story 1\",\n \"description\": \"Como um [tipo de usuário], eu quero [objetivo/desejo] para que [motivo/benefício].\",\n \"acceptance_criteria\": \"Critérios de aceitação detalhados para a User Story 1.\",\n  \"priority\": \"Must-have\"\n  },\n {\n \"title\": \"Título da User Story 2\",\n \"description\": \"Como um [tipo de usuário], eu quero [objetivo/desejo] para que [motivo/benefício].\",\n \"acceptance_criteria\": \"Critérios de aceitação detalhados para a User Story 2.\",\n  \"priority\": \"Could-have\"\n }\n]",

            "user_input": "['epic': 'Desenvolver um sistema que utilize inteligência artificial para analisar transcrições e automaticamente gerar artefatos de projeto, desde épicos até casos de teste, integrado com Azure DevOps. Benefícios incluem aumento de eficiência, redução de erros manuais e agilidade no desenvolvimento de software. Requisitos de alto nível englobam integração com Azure DevOps, capacidade de processamento de linguagem natural e interface amigável para revisão e ajuste dos artefatos gerados.', 'Feature': {'title': 'Arquitetura Dividida', 'description': 'O sistema possui uma arquitetura com backend e frontend separados, permitindo uma manutenção e atualização mais eficiente dos componentes individuais.'}]"
        }
    }

@pytest.fixture()
def task_payload_valid():
    return {
        "parent": 123,
        "task_type": "task",
        "prompt_data": {
            "system": "Você é um Gerente de Projetos Ágeis experiente em Scrum, canban e XP. Sua tarefa é criar uma lista de TASKS (atividades) a partir de uma User Story fornecida. Cada Task deve representar um passo concreto e implementável, sem inventar nada que não esteja no escopo da User Story.\n\n### Instruções:\n1. **Analise cuidadosamente a User Story** (incluindo sua descrição e critérios de aceitação) antes de gerar as Tasks. Reflita sobre as tasks que gerou e verifique se falta mais alguma ou se estão fora do contexto informado (CoT), mas não inclua essa análise na resposta.\n2. **Gere todas as Tasks necessárias** para implementar a User Story, mas sem extrapolar ou omitir partes.\n3. Cada Task deve ser um objeto JSON contendo:\n   - **\"title\"**: um título curto e claro.\n   - **\"description\"**: uma descrição detalhada do que deve ser feito nessa Task.\n   - **\"estimate\"**: uma estimativa de esforço, podendo ser em Story Points(com fibonacci).\n4. **Não unifique** várias atividades em uma só Task. Se houver múltiplos passos (5, 20 ou 600), crie múltiplas Tasks (5, 20 ou 600).\n5. **Retorne SOMENTE o array JSON** de objetos, sem formatação Markdown nem texto adicional.\n",

            "user": "Aqui está a User Story para referência:\n\n{user_input}\n\nCrie as Tasks necessárias para implementar completamente essa User Story, incluindo a estimativa de esforço em cada Task. Retorne APENAS o array JSON.",

            "assistant": "[\n  {\n    \"title\": \"Título da Task 1\",\n    \"description\": \"Descrição detalhada da Task 1.\",\n    \"estimate\": \"4h\"\n  },\n  {\n    \"title\": \"Título da Task 2\",\n    \"description\": \"Descrição detalhada da Task 2.\",\n    \"estimate\": \"2 Story Points\"\n  }\n]",

            "user_input": "{'description': 'Como desenvolvedor, quero criar um backend independente que seja responsável pelo processamento de linguagem natural e integração com Azure DevOps, para que possamos ter uma manutenção e atualização eficiente.', 'acceptance_criteria': '1. O backend deve ser capaz de processar transcrições usando inteligência artificial. 2. O backend deve integrar-se com Azure DevOps para gerar artefatos de projeto. 3. O backend deve ser modular para facilitar atualizações futuras.'}"
        }
    }

@pytest.fixture()
def test_case_payload_valid():
    return {
        "parent": 123,
        "task_type": "test_case",
        "prompt_data": {

            "system": "Você é um Analista de Qualidade de Software sênior, certificado em ISTQB e especialista em metodologias ágeis (Scrum, kanban, XP) e BDD. Sua tarefa é criar casos de teste com base em uma User Story fornecida, seguindo padrões de mercado e boas práticas de testes (ex.: análise de valor-limite, partição de equivalência, testes de cenário, testes de risco, etc.).\n\n### Instruções\n1. **Analisar o contexto da User Story** (descrição, critérios de aceitação) e pensar internamente (CoT) sobre os cenários relevantes, mas não incluir essa análise na resposta.\n2. **Gerar quantos forem necessários** para cobrir os cenários positivos, negativos e edge cases.\n3. Cada caso de teste deve ser um objeto JSON contendo:\n   - **\"title\"**: título curto e descritivo (ex.: \"Verificar login com credenciais corretas\").\n   - **\"priority\"**: criticidade do teste (ex.: \"High\", \"Medium\", \"Low\").\n   - **\"gherkin\"**: objeto com 'scenario', 'given', 'when', 'then' (no formato Gherkin).\n   - **\"actions\"**: lista de passos ('step') e resultado esperado ('expected_result').\n\n4. **Não use formatação Markdown**, não adicione texto fora do JSON. Retorne APENAS uma lista (array) de objetos JSON.\n5. **Referencie boas práticas de testes** (ex.: boundary analysis, equivalence partitioning, cenários de erro) para ampliar a cobertura.\n\n### Observação\n- Se a User Story requer login, inclua cenários de sucesso e falha (senhas inválidas, campos em branco, etc.) com prioridades diferentes.\n- Se a User Story for mais complexa, adicione quantos testes forem necessários para garantir a cobertura total.\n- Antes de gerar os testes, reflita sobre os teste e o contexto do use story fornecido, se atendem ao que foi solicitado.\n",
            
            "user": "Crie os casos de teste necessários para a seguinte User Story:\n\n{user_input}\n\nRetorne SOMENTE o array JSON de objetos, sem texto adicional.",
            
            "assistant": "[\n  {\n    \"title\": \"Exemplo de Título do Caso de Teste\",\n    \"priority\": \"High\",\n    \"gherkin\": {\n      \"scenario\": \"Exemplo de cenário\",\n      \"given\": \"Exemplo de Given\",\n      \"when\": \"Exemplo de When\",\n      \"then\": \"Exemplo de Then\"\n    },\n    \"actions\": [\n      {\n        \"step\": \"Exemplo de ação\",\n        \"expected_result\": \"Exemplo de resultado esperado\"\n      }\n    ]\n  }\n]",
            
            "user_input": "{'description': 'Como desenvolvedor, quero criar um backend independente que seja responsável pelo processamento de linguagem natural e integração com Azure DevOps, para que possamos ter uma manutenção e atualização eficiente.', 'acceptance_criteria': '1. O backend deve ser capaz de processar transcrições usando inteligência artificial. 2. O backend deve integrar-se com Azure DevOps para gerar artefatos de projeto. 3. O backend deve ser modular para facilitar atualizações futuras.'}"
        
        }
    }

@pytest.fixture()
def wbs_payload_valid():
    return {
        "parent": 123,
        "task_type": "wbs",
        "prompt_data": {

            "system": "Você é um Analista de Negócios experiente em metodologias ágeis e ITIL. Receberá um texto (que pode ser uma transcrição de reunião, documentação detalhada ou qualquer outro formato) descrevendo um sistema, projeto ou conjunto de funcionalidades. Sua tarefa é:\n\n1. Ler cuidadosamente todo o texto.\n2. Identificar TODAS as funcionalidades (features) mencionadas ou implicitamente requeridas, sem unificá-las ou omiti-las. Cada referência a uma capacidade distinta deve se tornar um item separado.\n3. Gerar uma lista de objetos JSON, onde cada objeto possui:\n   - \"title\": um nome curto e claro para a funcionalidade.\n   - \"description\": uma explicação com mais de 2 frases, que deixe claro o propósito, o escopo ou os benefícios da funcionalidade (não é apenas repetir o título).\n\n**Importante**:\n- Não agrupar várias funcionalidades em uma só.\n- Não inventar funcionalidades que não estejam no texto.\n- Se um mesmo bullet, frase ou diálogo listar múltiplas capacidades, crie um objeto para cada capacidade.\n- Retorne SOMENTE o JSON, em formato de array. Não inclua texto explicativo, conclusões ou introduções.\n- Não use formatação Markdown.\n- Se o texto contiver 5, 50 ou 1000 funcionalidades, sua lista deve ter 5, 50 ou 1000 itens, respectivamente.\n- antes de responder reflita internamente para interpretar o texto e após ter as features, se questione sobre suas features a serem geradas (CoT), mas não inclua essa reflexão no resultado, retorne a lista de features que estão dentro do contexto no formato json solicitado.\n",

            "user": "Analise o texto abaixo, que pode conter desde poucas até muitas funcionalidades. Extraia cada uma como um item separado, fornecendo título e descrição. Retorne APENAS o array JSON de objetos, sem texto adicional.\n\nTexto:\n\n{user_input}",

            "assistant": "[\n  {\n    \"title\": \"Exemplo de Título de Funcionalidade\",\n    \"description\": \"Exemplo de descrição objetiva que explique a função ou objetivo dessa feature.\"\n  }\n]",

            "user_input": "Estamos construindo um sistema para automatizar as tarefas do Azure DevOps com IA, enviando para uma LLM analisar uma transcrição e gerar artefatos desde épicos até test cases."
        }
    }

@pytest.fixture()
def automation_script_payload_valid():
    return {
        "parent": 123,
        "task_type": "automation_script",
        "prompt_data": {

            "system": "Você é um especialista em automação de testes com {type_test}. Sua tarefa é gerar um script de teste {type_test} COMPLETO e VÁLIDO, em formato de comentário, com base no Caso de Teste fornecido, escrito em Gherkin (BDD). Gere o script COMPLETO, incluindo a estrutura básica (describe, it, beforeEach, etc.) e os comandos {type_test} para cada passo (given, when, then). Use identificadores CSS ou XPaths fictícios, mas representativos, para os elementos da interface (ex: #username, #password, .btn-login). Adicione comentários explicativos para cada passo. A saída DEVE ser APENAS o script {type_test} dentro de um comentário de bloco (/* ... */), e NADA MAIS. NÃO inclua NENHUM texto explicativo fora do comentário.",

            "user": "Gere o script de automação em {type_test} para o seguinte Caso de Teste (em Gherkin):\n\n{user_input}\n\nRetorne APENAS o script como um comentário de bloco, sem nenhum texto adicional ou formatação Markdown.",

            "assistant": "/*\n/// <reference types=Cypress />\n\ndescribe('Login de Usuário', () => {\n beforeEach(() => {\n cy.visit('https://exemplo.com/login') // Visita a página de login\n });\n\n it('Deve logar com sucesso com credenciais válidas', () => {\n // \"given\": O usuário está na página de login\n // (já estamos lá por causa do beforeEach)\n\n // \"when\": Ele insere um e-mail válido e uma senha correta\n cy.get('#username').type('usuario@exemplo.com') // Digita o e-mail\n cy.get('#password').type('senha123') // Digita a senha\n cy.get('.btn-login').click() // Clica no botão de login\n\n // \"then\": O sistema autentica o usuário e redireciona para o dashboard\n cy.url().should('include', '/dashboard') // Verifica se a URL contém '/dashboard'\n cy.get('.user-profile').should('be.visible') // Verifica se um elemento do perfil do usuário está visível\n });\n});\n*/",

            "user_input": "{\"scenario\": \"Identifica\\u00e7\\u00e3o correta de elementos chave em uma transcri\\u00e7\\u00e3o\", \"given\": \"Que uma transcri\\u00e7\\u00e3o v\\u00e1lida \\u00e9 fornecida ao sistema\", \"when\": \"O sistema processa a transcri\\u00e7\\u00e3o\", \"then\": \"O sistema deve identificar e destacar os elementos chave como features, tarefas e requisitos t\\u00e9cnicos com precis\\u00e3o de pelo menos 90%\"}"

        }
    }

@pytest.fixture()
def epic_payload_parsing_error_prompt(): # New fixture for error-inducing prompt - CODIGO CORRIGIDO
    return {
        "parent": 123,
        "task_type": "epic",
        "prompt_data": {
            "system": "Você é um Product Owner experiente em projetos ágeis...",
            "user": "Gere um Épico em JSON, MAS **RETORNE APENAS O CAMPO 'description' E NADA MAIS** para simular um erro de parsing.", # Prompt corrigido para induzir erro de parsing
            "assistant": '{"description": "Descrição sem título"}', # Assistant response omits 'title' - CODIGO CORRIGIDO
            "user_input": "Contexto para Epic..."
        }
    }
