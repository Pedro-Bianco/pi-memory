## O que muda e por quê

<!-- Descreva a mudança e o problema que ela resolve. Feche a issue relacionada, se houver
(ex.: "Fecha #12"). -->

## Como foi verificado

- [ ] `ruff check` sem erros
- [ ] `pytest` passa (testes rápidos, sem rede e sem modelos)
- [ ] Teste novo cobrindo a mudança
- [ ] Se afeta qualidade ou velocidade: medição de antes e depois com `eval/run.py`, e tabelas
      do README atualizadas com `python eval/report.py --write`
- [ ] Operação nova ou alterada: `operations.py`, `schemas.json` (com descrição de cada campo)
      e teste de paridade
- [ ] Só dados fictícios em código, testes e exemplos
- [ ] `CHANGELOG.md` atualizado (seção "Não lançado")
