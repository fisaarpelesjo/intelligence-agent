# Intelligence Agent Constitution

## Core Principles

### I. Governed Semantic Access

O runtime do agente nunca le camadas brutas do data warehouse nem executa SQL livre. Toda leitura de dado de negocio passa por um contrato de query estruturado (metrica, dimensao, operador e periodo aprovados) contra um unico dataset semantico curado, sob dry-run previo e tetos de bytes/linhas/tempo. Autorizacao e deny-by-default: ausencia de aprovacao explicita para uma metrica/dimensao/combinacao e sempre negacao, nunca permissao implicita.

### II. Deterministic First, Narrative Second

Todo numero, comparacao e deteccao de anomalia e calculado por codigo deterministico e testado. O LLM e usado exclusivamente para interpretar a pergunta do usuario e narrar um resultado ja calculado — nunca para produzir, ajustar ou aproximar um valor numerico. Nenhuma claim de causa e efeito e afirmada de forma autonoma; observacoes de anomalia ou correlacao sao sempre comunicadas como correlacao, associacao ou hipotese, com aviso explicito.

### III. Provenance or Abstention

Toda resposta do agente carrega proveniencia (fontes, data-as-of, cobertura, limitacoes conhecidas) ou, quando o dado for insuficiente para sustentar uma resposta confiavel, o sistema se abstem explicitamente com um motivo nomeado. Nunca ha um numero apresentado sem origem rastreavel. Comparacoes entre um periodo parcial e um periodo completo sao proibidas; comparacoes entre periodos parciais equivalentes sao permitidas.

### IV. Least Privilege

O acesso a dado de negocio e estritamente somente leitura. A unica escrita do agente e em suas proprias tabelas operacionais (outbox, dedupe, memoria de conversa, cooldown). O payload enviado a qualquer LLM provider contem somente evidencia agregada — nunca dado pessoal identificavel, credencial ou token de acesso. Identidade de canal (Telegram, WhatsApp ou equivalente) nunca e a identidade de autorizacao: todo remetente e resolvido para um identificador derivado antes de qualquer decisao de acesso.

### V. Idempotent, Auditable Delivery (NON-NEGOTIABLE)

Toda mensagem proativa passa por um outbox transacional e e publicada de forma idempotente, com dedupe por fingerprint — nenhuma mensagem chega duplicada a um destinatario. Toda mensagem so e originada quando o finding e priorizavel, o canal esta habilitado e o destinatario esta explicitamente na allow-list. Toda decisao de autorizacao e toda entrega carregam um correlation ID rastreavel ponta a ponta.

## Restricoes tecnologicas

Python >=3.12. Data warehouse (ex.: BigQuery) como unica fonte de leitura de dado de negocio, restrita ao dataset semantico. Postgres para estado operacional. LLM acessado somente via uma interface abstrata `LLMProvider` com suporte a fallback — nunca por SDK de fornecedor especifico no codigo de dominio. Fora de escopo do MVP: BI tradicional, SQL livre, sistema multi-agente, RAG sobre linhas de fato, LLM self-hosted, Kubernetes, Kafka.

Cada pacote do pipeline (catalogo semantico, execucao de query, interacao conversacional, integracao de canal, deteccao de anomalia, priorizacao de insights, distribuicao proativa, relatorio periodico, memoria de conversa) mantem uma fronteira de dependencia unidirecional, garantida por teste automatizado de analise estatica quando aplicavel (ex.: um pacote de deteccao nao pode importar scheduler/timer/thread).

## Fluxo de desenvolvimento

Este projeto segue o engineering-playbook: todo recorte de produto passa por PRD (`docs/requirements/project-requirements.md`) aprovado antes de `specify`, `plan`, `tasks` e `implement`. Todo workflow de CI e bloqueante — nenhum gate roda em modo advisory ou `continue-on-error`. Entregas Git seguem `engineering-playbook delivery`: `start -> prepare -> commit -> publish -> merge --auto -> status`, sem commit, push ou merge sem autorizacao explicita.

## Governance

Esta constitution tem precedencia sobre qualquer pratica de codigo em conflito. Emendas exigem atualizacao do PRD quando afetarem requisito de produto, documentacao da mudanca e justificativa. Toda spec e todo plano devem verificar conformidade com os 5 principios centrais antes de avancar para tasks. Complexidade que viole um principio central exige decisao humana explicita registrada como ADR.

**Version**: 0.1.0 | **Ratified**: 2026-09-07 | **Last Amended**: 2026-09-07
