# Handoff Protocol

Antes de trocar agente, gere checkpoint. O receptor deve executar `uv run python scripts/resume.py`, verificar o repositorio real e nao confiar apenas em resumo de chat.

Um handoff declara origem, destino, motivo, workstream, tarefa ativa, acoes permitidas, acoes proibidas, contexto requerido, commit atual, validacoes e proxima acao.

