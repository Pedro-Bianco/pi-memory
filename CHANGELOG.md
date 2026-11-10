# Mudanças

Formato baseado em [Keep a Changelog](https://keepachangelog.com/pt-BR/1.1.0/); versões seguem
[Versionamento Semântico](https://semver.org/lang/pt-BR/): mudança incompatível na API pública
exige nova versão MAJOR e nota de migração.

## [Não lançado]

## [0.1.0] - 2026-11-10

Primeira versão pública.

### Adicionado

- **Memória de longo prazo**: `memories.add` extrai fatos de conversas e decide guardar,
  substituir, apagar ou ignorar cada um, com recuo seguro para guardar quando a decisão não é
  clara; CRUD completo e busca por dono.
- **Base de conhecimento** em coleções: PDF, Word, planilhas (.xlsx, .csv), apresentações (com
  notas do orador), texto e Markdown; documentos digitados; citação de página, slide, aba ou
  seção; administração de coleções, documentos e trechos.
- **Busca híbrida** (significado + palavra exata, fusão DBSF) igual em qualquer banco: nativa no
  Qdrant, feita pela biblioteca no Chroma e no banco em memória.
- **Grafo** por assunto e por coleção, em JSON e numa página HTML que abre sem internet.
- **Motores trocáveis**: embeddings FastEmbed (padrão), Ollama, formato OpenAI e Gemini; modelos
  de linguagem Ollama (padrão `qwen2.5:14b`), formato OpenAI, Gemini, Anthropic e qualquer
  função; bancos Qdrant (padrão), Chroma e em memória; reindexação ao trocar de embedding;
  configuração em JSON.
- **API assíncrona** (`AsyncPiMemory`).
- **Linha de comando**, **servidor HTTP** (com página de administração local e token opcional) e
  **servidor MCP**, todos com o mesmo JSON da biblioteca.
- **Avaliação registrada** (`eval/`): memória 54/58 com `qwen2.5:14b` e 0 apagamentos indevidos;
  documentos com o trecho certo no top 3 em 96% (Qdrant); velocidade por banco.
- **Servidores protegidos contra outros sites e contra leitura de arquivos**: só
  `application/json`, `Host` local sem token, `documents.add` por caminho só com `--docs-dir`,
  token de no mínimo 16 caracteres (`tests/unit/test_security.py`).
- **Separação por dono testada**: `tests/contract/test_isolation.py` ataca as 22 operações a
  partir de outro dono, pela biblioteca, HTTP, MCP e linha de comando, nos três bancos.
- Guia completo (`docs/GUIA.md`), 7 notebooks executados e `llms.txt`.
- Pacotes (wheel e código-fonte) anexados a cada release do GitHub pela CI; instalação direto
  do repositório (`pip install "pi-memory[local] @ git+https://github.com/Pedro-Bianco/pi-memory"`).

### Limitações conhecidas

- Qdrant em modo local acima da meta de velocidade com 50 mil trechos (1,4 s p95).
- Chroma 1.5.x às vezes não consegue ler os vetores de volta ("Nothing found on disk"; visto
  com muitos clientes no mesmo processo): o grafo vem sem as ligações de parecidas e com um
  aviso, em vez de falhar. Busca e listas não leem vetores e não são afetadas.
- Sem OCR; sem .doc, .xls, .ppt nem imagens.
- Prompts e avaliação só em português.

[Não lançado]: https://github.com/Pedro-Bianco/pi-memory/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/Pedro-Bianco/pi-memory/releases/tag/v0.1.0
