# Requirements Documentation

`templates/project/requirements.md` e o modelo canonico do Project Requirements Document — PRD. Ele deve ser preenchido pelo proprietario do projeto antes do GitHub Spec Kit transformar recortes aprovados em `specification -> plan -> tasks -> implementation -> validation -> convergence`.

O PRD e a fonte mestre de requisitos do produto. Specs do Spec Kit devem referenciar IDs do PRD, como `FR-001`, `NFR-001`, `BR-001`, `CON-001`, `SC-001` e `AC-001`, em vez de copiar silenciosamente o mesmo requisito. Quando houver conflito, prevalecem nesta ordem: PRD aprovado, ADRs aprovados, specs aprovadas, plano, tarefas, implementacao e resumos de agente.

## Como usar

1. Copie o template para `docs/requirements/project-requirements.md` usando `uv run python scripts/bootstrap.py` ou manualmente.
2. Preencha secoes aplicaveis. Para secoes nao aplicaveis, escreva `N/A - nao aplicavel, porque: <justificativa>`.
3. Mantenha lacunas como `TODO`, `ASSUMPTION` ou `QUESTION`; agentes nao devem inventar stakeholders, prazos, metricas, regras, limites, requisitos legais, arquitetura ou aprovacoes.
4. Revise contradicoes, ambiguidades materiais e requisitos sem verificacao.
5. Somente uma aprovacao humana pode mudar `status` para `approved`, preencher `approvers` e `approval_date`.
6. Use recortes aprovados para executar o fluxo do Spec Kit.

## Mudancas

O ciclo de requisitos e: elicitar -> analisar -> especificar -> revisar -> aprovar -> decompor em specs -> implementar -> verificar -> validar em uso -> manter.

Mudancas em requisitos aceitos devem registrar impacto sobre specs, planos, tarefas, testes, benchmarks, ADRs, documentacao, releases, compatibilidade e migracao. Nao altere silenciosamente requisito aprovado para coincidir com a implementacao existente.

## Validacao

`uv run python scripts/verify.py` valida existencia do template e guia, secoes obrigatorias, front matter, IDs dos exemplos, requisitos duplicados, criterios de aceitacao ausentes, placeholders em requisitos aceitos e aprovacao invalida. Qualidade semantica continua sendo responsabilidade de revisao humana.
