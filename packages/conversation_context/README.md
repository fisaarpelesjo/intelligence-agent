# conversation-context

Memoria de conversa ENTRE mensagens, com dono, escopo e expiracao — spec `011`.

- O dono e DERIVADO da identidade que o `004` resolve; nunca um chat id escrito.
- Um turno e a FORMA ESTRUTURADA de uma pergunta governada — nunca texto cru
  (`003:FR-082` vale em avanco).
- A memoria dura UM DIA (`OD-67`) e lembra uma JANELA DE TURNOS (`OD-68`).
- Arquivo local hoje, Postgres quando a VM chegar, pela costura do `003:FR-081`.
- Inbound continua desligado (`OD-20`): este pacote prepara memoria, nao recebe mensagem.
