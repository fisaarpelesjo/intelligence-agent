# Delivery Pipeline

`scripts/delivery.py` automatiza uma esteira segura de entrega Git em etapas separadas:

`start -> prepare -> commit -> publish -> merge --auto -> status`.

Operacoes remotas exigem comando explicito e `--yes-remote`. O script nunca usa force push, nunca publica em `main`, nunca faz amend implicitamente, nunca cria tag ou release e nunca executa merge dentro de `publish`.

## Comandos

```bash
uv run python scripts/delivery.py start --type feat --number 019 --slug safe-delivery
uv run python scripts/delivery.py prepare --title "feat(delivery): add safe git delivery pipeline"
git add <files>
uv run python scripts/delivery.py commit
uv run python scripts/delivery.py publish --yes-remote --remote origin --base main
uv run python scripts/delivery.py status
uv run python scripts/delivery.py merge --auto --yes-remote
```

## Gates

- `start` valida nome da branch e recusa arvore suja sem `--allow-dirty`.
- `prepare` exige branch diferente de `main`, executa verificacoes locais, revisao somente leitura, checkpoint e gera `.project/delivery/prepare.yml` mais `.project/delivery/pr.md`.
- `commit` exige prepare aprovado e atual, staged files, Conventional Commit, scan basico de secrets e ownership.
- `publish` exige commit local valido, branch diferente de `main`, checkpoint antes de remoto, push sem force e PR via GitHub CLI.
- `merge --auto` exige PR e CI configurada, habilita squash auto-merge e respeita branch protection.
- `status` e somente leitura e nao consulta remoto.

## Recuperacao

Depois de falha de rede ou interrupcao, execute:

```bash
uv run python scripts/delivery.py status
uv run python scripts/resume.py
uv run python scripts/reconcile.py
```

Reexecute `publish` depois que a rede voltar. A etapa e idempotente: se o PR da branch ja existir, ele e atualizado em vez de recriado.

