# Segurança

## Como relatar uma vulnerabilidade

**Não abra uma issue pública.** Use o relato privado do GitHub: aba **Security** do repositório →
**Report a vulnerability**. Descreva o problema, como reproduzir e o impacto. A resposta vem em
até 7 dias, com o plano de correção; o crédito é seu na nota da versão, se quiser.

## Versões cobertas

| Versão | Correções de segurança |
|---|---|
| 0.1.x | sim |

## O que esperar do pi-memory

- **Local por padrão, sem telemetria.** Com os motores padrão nada sai da máquina; motores de
  nuvem só recebem dados quando você os configura.
- **Chaves de API** só por parâmetro ou variável de ambiente; nunca são gravadas, nunca entram no
  arquivo de configuração (é recusado) e aparecem mascaradas em mensagens de erro.
- **Servidor HTTP**: ouve em `127.0.0.1` por padrão; com `PI_MEMORY_TOKEN` (ou `--token`) exige
  `Authorization: Bearer <token>` em todas as operações; token com menos de 16 caracteres é
  recusado; a linha de comando recusa ouvir fora da máquina sem token. Não há HTTPS embutido:
  para expor em rede, use um proxy com HTTPS na frente. O servidor não registra o conteúdo das
  requisições.
- **Outros sites abertos no navegador** não conseguem usar o servidor local: as operações só
  aceitam `Content-Type: application/json` (bloqueia o envio entre sites, CSRF) e, sem token, só
  pedidos endereçados a `127.0.0.1`/`localhost`/`[::1]` (bloqueia DNS rebinding).
- **Arquivos da máquina**: pelo HTTP e pelo MCP, `documents.add` não lê arquivos pelo caminho,
  salvo dentro da pasta indicada em `--docs-dir`; assim nem um cliente remoto nem um agente
  induzido por texto malicioso puxa arquivos privados. Testes em `tests/unit/test_security.py`.
- **Página de administração e grafo**: arquivos locais sem recursos da internet, com política de
  segurança de conteúdo que bloqueia o resto; textos das memórias são escapados.
- **Separação por dono** (`owner`): toda operação exige um dono e só alcança os dados dele; um
  registro de outro dono, pedido pelo id, responde `not_found`. O teste
  `tests/contract/test_isolation.py` tenta ler, editar e apagar dados de outro dono pelas 22
  operações, em todos os transportes e bancos. A separação é lógica, não criptografia: quem
  acessa a pasta ou o banco acessa tudo. Proteja a pasta de dados como qualquer dado pessoal.
- **O pi-memory não autentica usuários**: ele confia no `owner` recebido. Num sistema com vários
  clientes, o seu servidor descobre o dono pelo login e o repassa; o servidor HTTP/MCP embutido
  tem um único token, que libera todos os donos, e serve para uso local ou atrás do seu servidor,
  nunca exposto direto a clientes finais. Detalhes no guia, seção 11.5.
- **Documentos** são lidos pela biblioteca padrão (Office) e pelo `pypdf`; arquivos maliciosos
  podem consumir memória ou tempo: limite o tamanho do que você aceita de terceiros (o servidor
  HTTP limita o corpo a 50 MB).
