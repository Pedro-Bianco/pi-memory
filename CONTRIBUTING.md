# Como contribuir

Obrigado pelo interesse! Issues e pull requests são bem-vindos, em português.

## Preparar o ambiente

```bash
git clone https://github.com/Pedro-Bianco/pi-memory
cd pi-memory
python -m venv .venv && . .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -e ".[local,chroma,mcp,dev]"
```

## Antes de abrir um pull request

```bash
ruff check                 # estilo (linhas até 100 caracteres)
pytest                     # testes rápidos: sem rede e sem modelos
pytest -m real_engines     # opcional: com Ollama/FastEmbed de verdade
pytest -m browser          # opcional: página de administração no Chrome (pip install playwright)
```

Todo pull request passa pela CI em Windows, Linux e macOS com Python 3.10 a 3.13.

## Regras do projeto

- **Código, nomes e comentários em inglês; documentação, mensagens de erro e prompts em
  português do Brasil.**
- **Só dados fictícios** em código, testes, exemplos e avaliação (ex.: "Ana Exemplo", "Cidade
  Exemplo", "NF-4521"). Nunca dados pessoais reais, credenciais ou chaves.
- **Medir antes de afirmar**: números de qualidade ou desempenho vêm de `eval/run.py` e ficam em
  `eval/results/`; as tabelas do README são geradas por `python eval/report.py --write`. Mudança
  em prompt ou limiar só entra com a medição de antes e depois.
- **Peças trocáveis**: nenhum código fora de `engines/`, `readers/`, `prompts/`, `render/` e
  `servers/` pode depender de um motor específico (há um teste que verifica).
- **Mesmo JSON em todo lugar**: operação nova entra em `src/pi_memory/operations.py` e
  `schemas.json`, e o teste de paridade cobre biblioteca, HTTP, MCP e linha de comando.
- **Falha clara**: erros são exceções da biblioteca com mensagem em português dizendo o que fazer;
  toda chamada externa tem tempo limite; na dúvida, guardar (nunca apagar por engano).
- **Simplicidade**: entre duas soluções, a com menos código e menos dependências.

## Motor, banco ou leitor novo

Implemente a interface de `src/pi_memory/interfaces.py` (veja `docs/GUIA.md`, seção 15), coloque a
dependência como extra opcional no `pyproject.toml`, e:

- banco: passe na bateria `tests/contract/test_store_contract.py`;
- motor HTTP: teste de contrato com `httpx.MockTransport` e, se possível, teste real marcado
  `real_engines` que é pulado quando o serviço ou a chave não existe;
- registre a licença em `THIRD_PARTY_NOTICES.md`.

## Relatar problemas

Abra uma issue com o que você fez, o que esperava e o que aconteceu (com a mensagem de erro). Não
inclua dados pessoais. Falhas de segurança: veja `SECURITY.md`.
