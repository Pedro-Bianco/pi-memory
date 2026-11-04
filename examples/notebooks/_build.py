"""Builds the example notebooks from the cells below and runs them with real engines, so every
output shown is a real execution.

    python examples/notebooks/_build.py            # build and run all
    python examples/notebooks/_build.py 03 04      # only these

Needs: pip install -e ".[local,chroma,dev]" nbformat nbclient ipykernel; Ollama open with
qwen2.5:14b and nomic-embed-text; GEMINI_API_KEY optional (notebook 05 skips that part without it).
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

import nbformat
from nbclient import NotebookClient

HERE = Path(__file__).resolve().parent
md, code = nbformat.v4.new_markdown_cell, nbformat.v4.new_code_cell

SETUP = code('''import json
import shutil
import warnings
from pathlib import Path

warnings.filterwarnings("ignore", message="IProgress not found")  # aviso do tqdm no Jupyter

def mostrar(obj, limite=1500):
    """JSON legível (o mesmo formato da biblioteca, do HTTP e do MCP)."""
    texto = json.dumps(obj, ensure_ascii=False, indent=2)
    print(texto if len(texto) <= limite else texto[:limite] + "\\n…")

def pasta_limpa(nome):
    """Cada notebook começa do zero: apaga a pasta de dados da execução anterior."""
    shutil.rmtree(nome, ignore_errors=True)
    return nome''')

INSTALL = md('''> **Instalação** (uma vez):
> ```bash
> pip install "pi-memory[local]"
> ollama pull qwen2.5:14b
> ```
> Todos os dados deste notebook são fictícios. As saídas abaixo vêm de uma execução real.''')

NOTEBOOKS: dict[str, tuple[str, list]] = {}

# ── 01 ───────────────────────────────────────────────────────────────────────────────────────
NOTEBOOKS["01_memoria_basica"] = ("Memória de longo prazo: o básico", [
    md('''# 01 · Memória de longo prazo: o básico

O que este notebook mostra:

1. criar um `PiMemory` com os motores locais (FastEmbed + Ollama + Qdrant numa pasta);
2. entregar conversas e ver **cada decisão** (guardar, substituir, apagar, ignorar);
3. buscar, listar, editar e apagar memórias à mão;
4. a separação por **dono** (`owner`).'''),
    INSTALL, SETUP,
    md('''## Criar o objeto

Tudo parte de um objeto que você cria: não há estado global. `path` é a pasta do banco local
(Qdrant embutido). O modelo de linguagem padrão já é o `qwen2.5:14b`, o que passou na avaliação
registrada (veja o README); aqui ele é passado explicitamente só para ficar visível.'''),
    code('''from pi_memory import PiMemory
from pi_memory.llms import OllamaLLM

pm = PiMemory(path=pasta_limpa("dados_01"), llm=OllamaLLM("qwen2.5:14b", timeout=180))
print(pm.embedder.name, "|", pm.embedder.dimension, "dimensões")'''),
    md('''## Guardar a partir de uma conversa

`memories.add` recebe uma conversa (lista de mensagens `user`/`assistant`, ou um texto solto
como mensagem do usuário). O modelo extrai os fatos sobre o usuário e, para cada um, decide o
que fazer comparando com as 3 memórias mais parecidas do mesmo dono. O retorno lista as
decisões.'''),
    code('''r = pm.memories.add("Oi! Meu nome é Ana Exemplo, moro em Curitiba e trabalho como enfermeira.",
                    owner="ana")
mostrar(r)'''),
    md('''## Substituir: um fato novo sobre o mesmo assunto

"Me mudei" deve **substituir** a cidade antiga (evento `update`, com `previous_text`), não criar
uma segunda memória.'''),
    code('''mostrar(pm.memories.add("Novidade: me mudei para Recife semana passada.", owner="ana"))'''),
    md('''## Apagar: algo deixou de ser verdade

Pedir para esquecer, ou contar que algo acabou, gera `delete`. Na dúvida a biblioteca **guarda**
e nunca apaga por palpite (o campo `reason` aparece quando isso acontece).'''),
    code('''pm.memories.remember("O usuário tem um carro", owner="ana")      # fato direto, sem modelo
mostrar(pm.memories.add("Vendi meu carro, agora só ando de bicicleta.", owner="ana"))'''),
    md('''## Ignorar: nada novo, ou nada sobre o usuário'''),
    code('''mostrar(pm.memories.add("Como eu disse, sou enfermeira.", owner="ana"))
mostrar(pm.memories.add("Qual a capital da Austrália?", owner="ana"))'''),
    md('''## Conversa com o assistente como contexto

As falas do assistente servem só de contexto (para entender um "sim"); nada que **só** o
assistente disse vira memória.'''),
    code('''mostrar(pm.memories.add([
    {"role": "assistant", "content": "Você ainda faz plantão noturno?"},
    {"role": "user", "content": "sim, às quartas e sextas"},
], owner="ana"))'''),
    md('''## Buscar

Busca híbrida: significado + palavra exata. Devolve as memórias mais próximas com pontuação;
use as 3 primeiras como contexto, não só a primeira.'''),
    code('''for r in pm.memories.search("onde a Ana mora?", owner="ana")["results"]:
    print(f"{r['score']:.3f}  [{r['memory']['topic']}]  {r['text']}")'''),
    md('''## Listar, editar e apagar à mão'''),
    code('''lista = pm.memories.list(owner="ana")
print("total:", lista["total"])
for m in lista["memories"]:
    print(f"- [{m['topic']}] {m['text']}")'''),
    code('''primeira = lista["memories"][0]
editada = pm.memories.update(primeira["id"], owner="ana", text=primeira["text"] + " (confirmado)")
print(editada["text"])
print(pm.memories.delete(primeira["id"], owner="ana"))'''),
    md('''## Donos separados

Cada operação recebe `owner`. As memórias de um dono não aparecem para outro, e um `id` de
outro dono é tratado como inexistente.'''),
    code('''pm.memories.remember("O usuário joga xadrez", owner="bruno")
print("ana:", [r["text"] for r in pm.memories.search("xadrez", owner="ana")["results"][:1]])
print("bruno:", [r["text"] for r in pm.memories.search("xadrez", owner="bruno")["results"][:1]])

from pi_memory import NotFoundError
try:
    pm.memories.get(lista["memories"][1]["id"], owner="bruno")
except NotFoundError as e:
    print("NotFoundError:", e.message)'''),
    md('''## Erros claros, em português

Toda exceção da biblioteca tem `code` e `message`; `to_dict()` dá o mesmo JSON de erro que o
HTTP e o MCP vão devolver.'''),
    code('''from pi_memory import PiMemoryError
try:
    pm.memories.add("oi", owner="")
except PiMemoryError as e:
    mostrar(e.to_dict())'''),
    code('''pm.close()'''),
])

# ── 02 ───────────────────────────────────────────────────────────────────────────────────────
NOTEBOOKS["02_documentos"] = ("Base de documentos com citação", [
    md('''# 02 · Base de documentos com citação

O que este notebook mostra:

1. adicionar PDF, Word, planilha, apresentação e texto;
2. buscar por **significado** e por **palavra exata** (códigos como `NF-4521`);
3. cada resultado com a **citação** de onde veio (arquivo + página, slide, aba ou seção);
4. o que acontece ao adicionar o mesmo arquivo de novo, uma versão nova, ou um PDF escaneado.

Os documentos são fictícios e ficam em `eval/fixtures/` (gerados por `make_fixtures.py`).'''),
    INSTALL, SETUP,
    code('''from pi_memory import PiMemory

FIXTURES = Path("../../eval/fixtures")
# Só documentos: o modelo de linguagem não é usado aqui, então qualquer função serve.
pm = PiMemory(path=pasta_limpa("dados_02"), llm=lambda prompt: "")'''),
    md('''## Adicionar documentos'''),
    code('''for nome in ["contrato_exemplo.pdf", "relatorio.docx", "vendas.xlsx", "apresentacao.pptx",
             "notas.md", "manual.txt", "estoque.csv"]:
    r = pm.documents.add(FIXTURES / nome, owner="empresa")
    d = r["document"]
    print(f"{r['status']:<9} {d['source']:<22} {d['format']:<5} {d['chunks']:>3} trechos")'''),
    md('''## Perguntar com outras palavras

A pergunta não precisa repetir as palavras do texto. A citação (`citation.label`) diz exatamente
de onde veio cada trecho.'''),
    code('''def perguntar(pergunta, limite=3):
    print("?", pergunta)
    for r in pm.documents.search(pergunta, owner="empresa", limit=limite)["results"]:
        print(f"  {r['score']:.3f}  {r['citation']['label']:<38} {r['text'][:70]}")

perguntar("Qual o prazo para entregar os relatórios depois da visita?")
perguntar("Qual a penalidade por pagar a parcela com atraso?")
perguntar("Quantos clientes novos o apresentador quer conquistar até dezembro?")'''),
    md('''## Palavra exata: códigos, números, nomes

O vetor de significado empata códigos parecidos (`NF-4521` × `NF-4522`); a parte de palavra
exata os separa. O código aparece em dois documentos, e os dois vêm na frente.'''),
    code('''perguntar("NF-4521")
perguntar("Arruela 10mm")'''),
    md('''## Filtros

`filters` aceita igualdade em campos do trecho (`format`, `doc_id`) e em `metadata.<chave>`.'''),
    code('''r = pm.documents.search("multa por atraso", owner="empresa", filters={"format": "docx"})
print([x["citation"]["label"] for x in r["results"]])'''),
    md('''## Mesmo arquivo de novo, versão nova, remoção'''),
    code('''print(pm.documents.add(FIXTURES / "notas.md", owner="empresa")["status"])   # unchanged

nova = Path("dados_02/notas.md")
nova.write_text("# Notas\\n\\nA reunião mudou para a sala Verde.", encoding="utf-8")
r = pm.documents.add(nova, owner="empresa")
print(r["status"], r["document"]["chunks"], "trecho")                         # replaced
perguntar("em que sala é a reunião agora?", limite=2)'''),
    code('''doc = next(d for d in pm.documents.list(owner="empresa")["documents"] if d["source"] == "manual.txt")
print(pm.documents.remove(doc["id"], owner="empresa"))
print([d["source"] for d in pm.documents.list(owner="empresa")["documents"]])'''),
    md('''## PDF escaneado e formato não suportado

Um PDF só de imagens não tem texto: a biblioteca recusa com explicação e não indexa nada.
OCR não é feito nesta versão; um leitor próprio com OCR pode ser passado em
`PiMemory(readers=[...])`.'''),
    code('''from pi_memory import PiMemoryError
for nome, dados in [("escaneado.pdf", (FIXTURES / "escaneado.pdf").read_bytes()),
                    ("foto.heic", b"...")]:
    try:
        pm.documents.add_bytes(nome, dados, owner="empresa")
    except PiMemoryError as e:
        print(f"{e.code}: {e.message}")'''),
    code('''pm.close()'''),
])

# ── 03 ───────────────────────────────────────────────────────────────────────────────────────
NOTEBOOKS["03_agente_com_memoria"] = ("Agente real com memória", [
    md('''# 03 · Um agente real com memória

Um assistente de conversa (Ollama, `qwen2.5:14b`) que, a cada mensagem:

1. **lembra**: busca as memórias do usuário e os trechos de documentos ligados à mensagem;
2. **responde** com esse contexto no prompt de sistema, citando documentos;
3. **aprende**: entrega a troca (pergunta + resposta) ao `memories.add`, que decide o que guardar.

Depois o programa é "fechado" (o objeto é descartado) e aberto de novo numa **segunda sessão**:
o assistente continua sabendo quem é o usuário, porque a memória está na pasta.

Este é o padrão "memória como contexto": simples, previsível, uma busca por mensagem. O
notebook 04 mostra o padrão "memória como ferramenta", em que o próprio modelo decide.'''),
    INSTALL, SETUP,
    code('''import httpx
from pi_memory import PiMemory
from pi_memory.llms import OllamaLLM

OLLAMA, MODELO = "http://localhost:11434", "qwen2.5:14b"
PASTA = pasta_limpa("dados_03")
FIXTURES = Path("../../eval/fixtures")'''),
    md('''## O agente

`conversar()` é o agente inteiro. O histórico da sessão fica em memória do programa; o que deve
durar entre sessões vai para o pi-memory.'''),
    code('''SISTEMA = """Você é um assistente pessoal, em português do Brasil. Responda curto.
Use as memórias e os trechos abaixo só quando ajudarem. Ao usar um trecho, cite a fonte entre
colchetes, como [contrato.pdf, página 3]. Se não souber, diga que não sabe.

Memórias sobre o usuário:
{memorias}

Trechos de documentos:
{trechos}"""


def contexto(pm, dono, mensagem):
    memorias = pm.memories.search(mensagem, owner=dono, limit=3)["results"]
    trechos = pm.documents.search(mensagem, owner=dono, limit=3)["results"]
    return SISTEMA.format(
        memorias="\\n".join(f"- {m['text']}" for m in memorias) or "(nenhuma)",
        trechos="\\n".join(f"[{t['citation']['label']}] {t['text']}" for t in trechos) or "(nenhum)")


def conversar(pm, dono, historico, mensagem, mostrar_aprendizado=True):
    historico.append({"role": "user", "content": mensagem})
    mensagens = [{"role": "system", "content": contexto(pm, dono, mensagem)}, *historico[-10:]]
    resposta = httpx.post(f"{OLLAMA}/api/chat", timeout=180, json={
        "model": MODELO, "messages": mensagens, "stream": False,
        "options": {"temperature": 0}}).json()["message"]["content"]
    historico.append({"role": "assistant", "content": resposta})
    print(f"🧑 {mensagem}\\n🤖 {resposta}")
    # aprender com a troca: o pi-memory extrai fatos e decide guardar/substituir/apagar/ignorar
    decisoes = pm.memories.add(historico[-2:], owner=dono)["decisions"]
    if mostrar_aprendizado:
        for d in decisoes:
            antes = f"  (antes: {d['previous_text']})" if d["previous_text"] else ""
            print(f"   💾 {d['event']}: {d['text']}{antes}")
    print()'''),
    md('''## Sessão 1'''),
    code('''pm = PiMemory(path=PASTA, llm=OllamaLLM(MODELO, timeout=180))
pm.documents.add(FIXTURES / "contrato_exemplo.pdf", owner="ana")   # um contrato da Ana
historico = []

conversar(pm, "ana", historico, "Oi! Sou a Ana, trabalho como enfermeira e moro em Curitiba.")
conversar(pm, "ana", historico, "Tenho uma gata chamada Mel e prefiro respostas bem curtas.")
conversar(pm, "ana", historico, "No meu contrato, qual o prazo de entrega dos relatórios?")
pm.close()   # "fecha o programa": o histórico da sessão se perde, a memória fica na pasta'''),
    md('''## Sessão 2: outro dia, programa aberto de novo

Histórico vazio. O que o assistente sabe vem só da memória.'''),
    code('''pm = PiMemory(path=PASTA, llm=OllamaLLM(MODELO, timeout=180))
historico = []

conversar(pm, "ana", historico, "Bom dia! Você lembra qual é a minha profissão e o nome da minha gata?")
conversar(pm, "ana", historico, "Novidade: me mudei para Recife.")
conversar(pm, "ana", historico, "Em que cidade eu moro agora?")'''),
    md('''## O que ficou guardado'''),
    code('''for m in pm.memories.list(owner="ana")["memories"]:
    print(f"- [{m['topic']}] {m['text']}")
pm.close()'''),
    md('''## Variações comuns

- **Guardar de tempos em tempos** em vez de a cada troca: acumule as mensagens e chame
  `memories.add(ultimas_16_mensagens, owner)` a cada N trocas (menos chamadas ao modelo; o
  extrator entende melhor respostas curtas como "sim" com mais contexto).
- **Guardar em segundo plano**: `memories.add` pode rodar numa thread depois de responder, para
  o usuário não esperar a extração.
- **Modelos diferentes**: o modelo que conversa e o que extrai memórias podem ser diferentes
  (`PiMemory(llm=...)` é só o extrator).'''),
])

# ── 04 ───────────────────────────────────────────────────────────────────────────────────────
NOTEBOOKS["04_agente_com_ferramentas"] = ("Agente com ferramentas de memória", [
    md('''# 04 · Agente que usa a memória como ferramenta

Aqui o **modelo decide** quando consultar a memória, quando pesquisar nos documentos e quando
guardar um fato, chamando ferramentas (function calling do Ollama). Útil quando o agente já tem
outras ferramentas e você não quer buscar contexto a cada mensagem.

As ferramentas são funções Python comuns sobre a API do pi-memory; o mesmo desenho vale para
qualquer framework de agentes (o servidor MCP previsto expõe essas operações direto).'''),
    INSTALL, SETUP,
    code('''import httpx
from pi_memory import PiMemory
from pi_memory.llms import OllamaLLM

OLLAMA, MODELO, DONO = "http://localhost:11434", "qwen2.5:14b", "ana"
pm = PiMemory(path=pasta_limpa("dados_04"), llm=OllamaLLM(MODELO, timeout=180))
pm.documents.add(Path("../../eval/fixtures/vendas.xlsx"), owner=DONO)
pm.memories.remember("O usuário prefere respostas curtas", owner=DONO, topic="perfil")'''),
    md('''## As ferramentas'''),
    code('''def buscar_memorias(consulta: str) -> dict:
    r = pm.memories.search(consulta, owner=DONO, limit=3)["results"]
    return {"memorias": [m["text"] for m in r]}

def buscar_documentos(consulta: str) -> dict:
    r = pm.documents.search(consulta, owner=DONO, limit=3)["results"]
    return {"trechos": [{"fonte": t["citation"]["label"], "texto": t["text"]} for t in r]}

def guardar_fato(fato: str) -> dict:
    m = pm.memories.remember(fato, owner=DONO)
    return {"guardado": m["text"]}

FERRAMENTAS = {f.__name__: f for f in (buscar_memorias, buscar_documentos, guardar_fato)}

def esquema(nome, descricao, parametro):
    return {"type": "function", "function": {
        "name": nome, "description": descricao,
        "parameters": {"type": "object", "required": [parametro],
                       "properties": {parametro: {"type": "string"}}}}}

TOOLS = [
    esquema("buscar_memorias", "Busca o que já se sabe sobre o usuário (preferências, família, trabalho).", "consulta"),
    esquema("buscar_documentos", "Pesquisa nos documentos do usuário; devolve trechos com a fonte.", "consulta"),
    esquema("guardar_fato", "Guarda um fato duradouro sobre o usuário, escrito como 'O usuário ...'.", "fato"),
]'''),
    md('''## O laço do agente

Enquanto o modelo pedir ferramentas, executa e devolve o resultado; quando ele responder com
texto, termina.'''),
    code('''SISTEMA = ("Você é um assistente em português do Brasil. Você tem ferramentas e deve usá-las:\\n"
           "- buscar_documentos: SEMPRE que a pergunta for sobre vendas, notas, clientes, contratos "
           "ou outros dados do usuário, antes de dizer que não sabe; cite a fonte;\\n"
           "- buscar_memorias: quando precisar de algo que o usuário contou antes;\\n"
           "- guardar_fato: quando o usuário contar um fato novo e duradouro sobre si.")

def agente(mensagem, historico):
    historico.append({"role": "user", "content": mensagem})
    print(f"🧑 {mensagem}")
    for _ in range(6):
        msg = httpx.post(f"{OLLAMA}/api/chat", timeout=180, json={
            "model": MODELO, "stream": False, "tools": TOOLS, "options": {"temperature": 0},
            "messages": [{"role": "system", "content": SISTEMA}, *historico]}).json()["message"]
        historico.append(msg)
        chamadas = msg.get("tool_calls") or []
        if not chamadas:
            print(f"🤖 {msg['content']}\\n")
            return
        for chamada in chamadas:
            nome, args = chamada["function"]["name"], chamada["function"]["arguments"]
            resultado = FERRAMENTAS[nome](**args)
            print(f"   🔧 {nome}({json.dumps(args, ensure_ascii=False)}) → "
                  f"{json.dumps(resultado, ensure_ascii=False)[:160]}")
            historico.append({"role": "tool", "content": json.dumps(resultado, ensure_ascii=False)})

historico = []
agente("Oi! Comecei hoje num emprego novo: sou analista de dados na Livraria Exemplo.", historico)
agente("Quanto vendemos para a Padaria Imaginária e qual foi a nota?", historico)
agente("Você lembra onde eu trabalho e como prefiro as respostas?", []) # histórico vazio'''),
    code('''for m in pm.memories.list(owner=DONO)["memories"]:
    print(f"- [{m['topic']}] {m['text']}")'''),
    md('''## O ponto fraco: guardar depende do modelo

Veja a primeira mensagem acima: o usuário contou do emprego novo e o modelo pode **não** chamar
`guardar_fato`; se isso acontece, na terceira pergunta (histórico vazio) o agente não sabe onde o
usuário trabalha. Buscar pela ferramenta funciona bem (ele consultou a planilha e citou a nota),
mas confiar ao modelo a decisão de **guardar** é frágil.

## Variante robusta: ferramentas para buscar, aprendizado automático

As ferramentas continuam para **buscar**; depois de cada troca, o seu código entrega a conversa
ao `memories.add`, que extrai e decide sozinho (como no notebook 03). Mesmas três mensagens,
memória limpa:'''),
    code('''pm.memories.delete_all(owner=DONO)
pm.memories.remember("O usuário prefere respostas curtas", owner=DONO, topic="perfil")

def agente_que_aprende(mensagem, historico):
    agente(mensagem, historico)
    troca = [{"role": "user", "content": mensagem},
             {"role": "assistant", "content": historico[-1].get("content", "")}]
    for d in pm.memories.add(troca, owner=DONO)["decisions"]:
        print(f"   💾 {d['event']}: {d['text']}")
    print()

historico = []
agente_que_aprende("Oi! Comecei hoje num emprego novo: sou analista de dados na Livraria Exemplo.", historico)
agente_que_aprende("Quanto vendemos para a Padaria Imaginária e qual foi a nota?", historico)
agente_que_aprende("Você lembra onde eu trabalho e como prefiro as respostas?", [])'''),
    code('''for m in pm.memories.list(owner=DONO)["memories"]:
    print(f"- [{m['topic']}] {m['text']}")
pm.close()'''),
    md('''## Contexto × ferramenta: quando usar cada um

| | Memória como contexto (notebook 03) | Memória como ferramenta (este) |
|---|---|---|
| Quem decide buscar | o seu código, toda mensagem | o modelo |
| Previsibilidade | alta | depende do modelo seguir as ferramentas |
| Custo | 1 busca por mensagem | só quando o modelo pede |
| Guardar | `memories.add` com decisão completa | depende de o modelo chamar a ferramenta; a variante robusta usa `memories.add` automático |
| Bom para | assistentes pessoais | agentes com muitas ferramentas |'''),
])

# ── 05 ───────────────────────────────────────────────────────────────────────────────────────
NOTEBOOKS["05_motores_e_configuracao"] = ("Trocar motores, configurar por JSON, reindexar", [
    md('''# 05 · Trocar motores, configurar por JSON, reindexar

Cada peça é trocada só na criação do objeto; o resto do código não muda.

| Peça | Opções incluídas |
|---|---|
| Embedding | FastEmbed (padrão), Ollama, formato OpenAI, Gemini |
| Modelo de linguagem | Ollama (padrão), formato OpenAI, Gemini, Anthropic, qualquer função `str -> str` |
| Banco vetorial | Qdrant (padrão), Chroma, em memória |'''),
    INSTALL, SETUP,
    code('''import os
from pi_memory import PiMemory
from pi_memory.embedders import OllamaEmbedder, OpenAIEmbedder
from pi_memory.stores import ChromaStore, MemoryStore

def demonstrar(pm, rotulo):
    pm.memories.remember("O usuário tem uma gata chamada Mel", owner="ana")
    pm.memories.remember("O usuário trabalha como enfermeira", owner="ana")
    melhor = pm.memories.search("qual o nome do animal de estimação?", owner="ana")["results"][0]
    print(f"{rotulo:<34} {pm.embedder.name:<42} → {melhor['text']}")
    pm.close()'''),
    md('''## Embeddings e bancos diferentes, mesmo código'''),
    code('''demonstrar(PiMemory(path=pasta_limpa("dados_05_qdrant"), llm=lambda p: ""), "FastEmbed + Qdrant (padrão)")
demonstrar(PiMemory(embedder=OllamaEmbedder("nomic-embed-text"),
                    store=ChromaStore(path=pasta_limpa("dados_05_chroma")), llm=lambda p: ""),
           "Ollama + Chroma")
demonstrar(PiMemory(embedder=OpenAIEmbedder("nomic-embed-text", base_url="http://localhost:11434/v1"),
                    store=MemoryStore(), llm=lambda p: ""),
           "formato OpenAI (via Ollama) + memória")'''),
    md('''## Gemini (faixa gratuita), se houver chave

A chave vem da variável de ambiente `GEMINI_API_KEY` e nunca aparece em mensagens. Os nomes
dos modelos de conversa mudam rápido, por isso `GeminiLLM` exige o nome.'''),
    code('''if os.environ.get("GEMINI_API_KEY"):
    from pi_memory.embedders import GeminiEmbedder
    from pi_memory.llms import GeminiLLM
    demonstrar(PiMemory(embedder=GeminiEmbedder(), store=MemoryStore(), llm=lambda p: ""),
               "Gemini embedding + memória")
    pm = PiMemory(embedder=OllamaEmbedder("nomic-embed-text"), store=MemoryStore(),
                  llm=GeminiLLM("gemini-3.5-flash", timeout=120))
    mostrar(pm.memories.add("Sou o Bruno e moro em Vila Exemplo.", owner="bruno"))
    pm.close()
else:
    print("GEMINI_API_KEY não definida: parte do Gemini pulada")'''),
    md('''## Qualquer função como modelo de linguagem

Útil para usar o SDK que você já tem, um modelo remoto próprio, ou para testes.'''),
    code('''def meu_llm(prompt: str) -> str:
    # aqui entraria a chamada ao seu provedor; esta resposta fixa só mostra o formato
    return "FATO: O usuário gosta de jazz" if "Abaixo está um trecho" in prompt else "1. lazer"

pm = PiMemory(embedder=OllamaEmbedder("nomic-embed-text"), store=MemoryStore(), llm=meu_llm)
mostrar(pm.memories.add("adoro jazz", owner="ana"))
pm.close()'''),
    md('''## Configuração em JSON

O mesmo dicionário serve para a linha de comando (`--config arquivo.json`) e para os servidores.
Chaves de API **não** entram no arquivo.'''),
    code('''config = {
    "path": pasta_limpa("dados_05_config"),
    "embedder": {"type": "ollama", "model": "nomic-embed-text"},
    "llm": {"type": "ollama", "model": "qwen2.5:14b", "timeout": 180},
    "store": {"type": "chroma", "path": "dados_05_config/chroma"},
    "topics": ["trabalho", "família", "saúde", "lazer", "outros"],
}
pm = PiMemory.from_config(config)
print(type(pm.embedder).__name__, type(pm.llm).__name__, type(pm.store).__name__, pm.topics)
pm.close()

from pi_memory import PiMemoryError
try:
    PiMemory.from_config({"llm": {"type": "openai", "model": "x", "api_key": "sk-..."}})
except PiMemoryError as e:
    print(e.code, "→", e.message)'''),
    md('''## Trocar de embedding numa memória existente

Vetores de modelos diferentes não se misturam: abrir com outro modelo é recusado com
explicação. Para migrar, abra com o modelo antigo e chame `reindex`.'''),
    code('''pasta = pasta_limpa("dados_05_reindex")
pm = PiMemory(path=pasta, llm=lambda p: "")
pm.memories.remember("O usuário tem uma gata chamada Mel", owner="ana")
pm.close()

try:
    PiMemory(path=pasta, embedder=OllamaEmbedder("nomic-embed-text"), llm=lambda p: "")
except PiMemoryError as e:
    print(e.code, "→", e.message, "\\n")

pm = PiMemory(path=pasta, llm=lambda p: "")
mostrar(pm.reindex(OllamaEmbedder("nomic-embed-text")))
pm.close()

pm = PiMemory(path=pasta, embedder=OllamaEmbedder("nomic-embed-text"), llm=lambda p: "")
print(pm.memories.search("gato", owner="ana")["results"][0]["text"])
pm.close()'''),
])

# ── 06 ───────────────────────────────────────────────────────────────────────────────────────
NOTEBOOKS["06_grafo"] = ("Grafo da memória por assunto", [
    md('''# 06 · Grafo da memória por assunto

`graph.data(owner)` devolve o grafo em JSON (assuntos, memórias, ligações) e
`graph.html(owner, path)` gera uma página única e interativa que abre sem internet: arrastar,
aproximar (roda do mouse ou dois dedos), filtrar por assunto, buscar texto e clicar numa
memória para ver o texto e a mais parecida.'''),
    INSTALL, SETUP,
    code('''from pi_memory import PiMemory
pm = PiMemory(path=pasta_limpa("dados_06"), llm=lambda p: "")
for texto, assunto in [
    ("O usuário trabalha como enfermeira", "trabalho"),
    ("O usuário faz plantão noturno às quartas", "trabalho"),
    ("O usuário lidera a equipe de triagem", "trabalho"),
    ("O usuário tem uma filha chamada Lia", "família"),
    ("O usuário tem um filho chamado Davi", "família"),
    ("O usuário corre 5 km toda manhã", "saúde"),
    ("O usuário é alérgico a camarão", "saúde"),
    ("O usuário gosta de jazz", "lazer"),
]:
    pm.memories.remember(texto, owner="ana", topic=assunto)'''),
    md('''## Os dados'''),
    code('''grafo = pm.graph.data("ana")
print(len(grafo["nodes"]), "nós,", len(grafo["edges"]), "ligações")
mostrar(grafo["nodes"][:3])
mostrar([e for e in grafo["edges"] if e["kind"] == "similar"][:3])'''),
    md('''## A página'''),
    code('''print(pm.graph.html("ana", path="dados_06/grafo.html"))
pm.close()
# Abra o arquivo no navegador. Num Jupyter local também dá para ver aqui:
# from IPython.display import IFrame; IFrame("dados_06/grafo.html", width="100%", height=500)'''),
    md('''Pela linha de comando:

```bash
pi-memory --path dados_06 graph html --owner ana --out grafo.html
```

![Grafo com 40 memórias fictícias](grafo_exemplo.png)'''),
])


# ── 07 ───────────────────────────────────────────────────────────────────────────────────────
NOTEBOOKS["07_administracao"] = ("Administração da memória e da base de conhecimento", [
    md("""# 07 · Administração: coleções, documentos, trechos

Tudo o que está guardado pode ser visto e controlado: **coleções** (bases de conhecimento com
nome), **documentos**, **trechos** e **memórias**. Este notebook usa a biblioteca; o mesmo vale
pela linha de comando, pelo HTTP, pelo MCP e pela página de administração local
(`pi-memory serve-http` → `http://127.0.0.1:8765/`)."""),
    INSTALL, SETUP,
    code("""from pi_memory import PiMemory

FIXTURES = Path("../../eval/fixtures")
PASTA = pasta_limpa("dados_07")
pm = PiMemory(path=PASTA, llm=lambda prompt: "")      # só administração: sem modelo de linguagem"""),
    md("""## Documentos em coleções

Cada documento entra numa coleção (padrão `geral`). Também dá para criar um documento digitando
o texto."""),
    code("""pm.documents.add(FIXTURES / "contrato_exemplo.pdf", owner="empresa", collection="contratos")
pm.documents.add(FIXTURES / "vendas.xlsx", owner="empresa", collection="financeiro")
pm.documents.add(FIXTURES / "relatorio.docx", owner="empresa", collection="financeiro")
r = pm.documents.add_text("Procedimento de backup",
                          "O backup roda toda sexta às 22h. A cópia fica no servidor Exemplo.",
                          owner="empresa", collection="ti")
print(r["status"], r["document"]["source"], "→", r["document"]["collection"])
mostrar(pm.documents.collections("empresa"))"""),
    md("""## Visão geral do dono"""),
    code("""pm.memories.remember("O usuário é o responsável pelo financeiro", owner="empresa", topic="trabalho")
s = pm.stats("empresa")
print(s["memories"], "| documentos:", s["documents"], "| trechos:", s["chunks"])"""),
    md("""## Um documento e seus trechos; apagar um trecho"""),
    code("""contrato = pm.documents.list("empresa", collection="contratos")["documents"][0]
doc = pm.documents.get(contrato["id"], "empresa")
print(doc["document"]["source"], "-", doc["document"]["chunks"], "trechos")
for c in doc["chunks"][:3]:
    print(f"  #{c['index']} {c['location']}: {c['text'][:60]}")

print(pm.documents.delete_chunk(doc["chunks"][0]["id"], "empresa"))
print("agora:", pm.documents.list("empresa", collection="contratos")["documents"][0]["chunks"], "trechos")"""),
    md("""## Busca restrita a uma coleção e exclusão de uma coleção inteira"""),
    code("""for hit in pm.documents.search("quando roda o backup?", "empresa", collection="ti")["results"]:
    print(hit["citation"]["label"], "→", hit["text"][:70])

print(pm.documents.delete_collection("financeiro", "empresa"))
print([c["name"] for c in pm.documents.collections("empresa")["collections"]])
pm.close()"""),
    md("""## O mesmo pela linha de comando

Cada operação vira um comando; `--format text` mostra uma saída legível."""),
    code("""import subprocess, sys

def pi_memory(*args):
    saida = subprocess.run([sys.executable, "-m", "pi_memory.cli", "--path", PASTA, "--format", "text", *args],
                           capture_output=True, text=True, encoding="utf-8")
    print(saida.stdout.strip() or saida.stderr.strip())

pi_memory("collections", "list", "--owner", "empresa")
pi_memory("documents", "list", "--owner", "empresa", "--collection", "ti")"""),
    md("""## O mesmo pelo servidor HTTP

O servidor serve a página de administração em `/` e as operações em `/v1/<operação>`. Aqui ele
sobe numa porta livre, só nesta máquina, e é chamado como qualquer outro programa chamaria."""),
    code("""import threading, urllib.request
from pi_memory.servers.http import make_server

pm = PiMemory(path=PASTA, llm=lambda prompt: "")
servidor = make_server(pm, port=0)
threading.Thread(target=servidor.serve_forever, daemon=True).start()
url = f"http://127.0.0.1:{servidor.server_address[1]}"

pedido = urllib.request.Request(url + "/v1/stats", data=json.dumps({"owner": "empresa"}).encode(),
                                headers={"Content-Type": "application/json"})
with urllib.request.urlopen(pedido) as resposta:
    mostrar(json.loads(resposta.read())["collections"])
with urllib.request.urlopen(url + "/") as resposta:
    pagina = resposta.read().decode()
print("página de administração:", len(pagina), "bytes;", "título:", pagina.split("<title>")[1].split("<")[0])

servidor.shutdown(); servidor.server_close(); pm.close()"""),
    md("""![Administração local: base de conhecimento](../../docs/img/admin-base-de-conhecimento.png)"""),
])


def build(name: str, title: str, cells: list) -> None:
    nb = nbformat.v4.new_notebook(cells=cells, metadata={
        "kernelspec": {"name": "python3", "display_name": "Python 3", "language": "python"},
        "language_info": {"name": "python"}, "title": title})
    started = time.perf_counter()
    NotebookClient(nb, timeout=900, kernel_name="python3",
                   resources={"metadata": {"path": str(HERE)}}).execute()
    path = HERE / f"{name}.ipynb"
    nbformat.write(nb, path)
    print(f"{path.name}: {time.perf_counter() - started:.0f} s")


if __name__ == "__main__":
    wanted = sys.argv[1:]
    for name, (title, cells) in NOTEBOOKS.items():
        if not wanted or name[:2] in wanted:
            build(name, title, cells)
