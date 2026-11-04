# Avisos de terceiros

O pi-memory é distribuído sob a licença MIT (arquivo `LICENSE`). Ele não copia código de
terceiros: usa as bibliotecas abaixo como dependências, instaladas pelo `pip` com as licenças
delas. Versões conferidas em 2026-11-04 nos metadados dos pacotes instalados.

## Dependências

| Pacote | Quando é instalado | Licença |
|---|---|---|
| [httpx](https://github.com/encode/httpx) | sempre (pacote base) | BSD-3-Clause |
| [fastembed](https://github.com/qdrant/fastembed) | extras `fastembed`, `local`, `all` | Apache-2.0 |
| [qdrant-client](https://github.com/qdrant/qdrant-client) | extras `qdrant`, `local`, `all` | Apache-2.0 |
| [pypdf](https://github.com/py-pdf/pypdf) | extras `pdf`, `local`, `all` | BSD-3-Clause |
| [chromadb](https://github.com/chroma-core/chroma) | extras `chroma`, `all` | Apache-2.0 |
| [mcp](https://github.com/modelcontextprotocol/python-sdk) | extras `mcp`, `all` (servidor MCP: `pi-memory serve-mcp`) | MIT |
| [pytest](https://github.com/pytest-dev/pytest) | extra `dev` | MIT |
| [ruff](https://github.com/astral-sh/ruff) | extra `dev` | MIT |
| [nbformat](https://github.com/jupyter/nbformat), [nbclient](https://github.com/jupyter/nbclient), [ipykernel](https://github.com/ipython/ipykernel) | só para gerar os notebooks de exemplo | BSD-3-Clause |
| [playwright](https://github.com/microsoft/playwright-python) | só para o teste opcional no navegador (`pytest -m browser`) | Apache-2.0 |

Cada pacote traz as próprias dependências, com as licenças delas.

## Modelos e serviços

Modelos e serviços **não** são distribuídos com o pi-memory: quem usa a biblioteca os baixa ou
contrata e fica sob os termos deles.

| Modelo / serviço | Onde aparece | Termos |
|---|---|---|
| `intfloat/multilingual-e5-large` (via FastEmbed) | embedding padrão | licença MIT (cartão do modelo) |
| `qwen2.5:14b` (via Ollama) | modelo de linguagem padrão | Apache-2.0 (cartão do modelo Qwen2.5-14B) |
| `nomic-embed-text` (via Ollama) | exemplos e testes | Apache-2.0 (cartão do modelo) |
| Ollama | motor local | MIT |
| API do Gemini, API da OpenAI, API da Anthropic | motores opcionais de nuvem | termos de uso de cada provedor |

## Dados

Todos os documentos, conversas e nomes usados em testes, avaliação (`eval/`) e exemplos
(`examples/`) são fictícios e foram criados para este projeto.
