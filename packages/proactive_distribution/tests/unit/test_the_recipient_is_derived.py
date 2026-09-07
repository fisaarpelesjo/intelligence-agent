"""The recipient is derived, and a correct literal must fail this file — T706, T707.

`FR-201` is about the **shape of the derivation**, not about whether one id is right
today. **A literal that happens to be correct passes every test that checks the
answer** — it fails only a test that checks the derivation, and this is that test.

## How it checks the derivation rather than the answer

By deriving twice, from two different environments, and requiring **two different**
answers. A literal returns the same both times, however right it looked, and that is
the failure this file exists to produce.

## And nothing here reads the value

`FR-202`: no node asserts about the **value** of a secret-bearing key — only about the
key. The two ids below are this file's own strings, chosen to differ from each other
and nothing else; neither is anybody's chat and neither is compared against one.
"""

from __future__ import annotations

import pytest

from proactive_distribution.distribute import (
    RECIPIENT_KEY,
    NoAcceptedRecipient,
    recipients_from,
)

pytestmark = pytest.mark.unit

#: Two values this file invented, differing from each other. Their content means nothing
#: and is never compared to a real id.
FIRST = "first-environment"
SECOND = "second-environment"


def test_two_environments_give_two_recipients() -> None:
    """**This is the node a correct literal fails.**

    An implementation returning a hardcoded id — even the right one — answers the same
    for both environments, and the assertion below is what notices.
    """
    first = recipients_from({RECIPIENT_KEY: FIRST})
    second = recipients_from({RECIPIENT_KEY: SECOND})
    assert first != second, (
        "the same recipient came back from two different environments, so the value is not "
        "being derived from the key; a literal answers this way even when it is correct"
    )


def test_each_environment_gives_back_what_it_declared() -> None:
    """Derived AND faithful: not merely different, but the thing the key held.

    OD-105 (2026-09-03): a resposta e PLURAL — a lista declarada, na ordem, sem
    duplicatas. O molde e o recipients_from da 008 (o consertado de 30/08).
    """
    assert recipients_from({RECIPIENT_KEY: FIRST}) == (FIRST,)
    assert recipients_from({RECIPIENT_KEY: SECOND}) == (SECOND,)
    assert recipients_from({RECIPIENT_KEY: "111, 222 333;222"}) == ("111", "222", "333")


def test_an_absent_key_refuses_rather_than_defaulting() -> None:
    """A default recipient is a message sent to somebody nobody authorized."""
    with pytest.raises(NoAcceptedRecipient):
        recipients_from({})


def test_an_empty_key_refuses_too() -> None:
    """Present and empty is not present. A blank variable authorizes nobody."""
    with pytest.raises(NoAcceptedRecipient):
        recipients_from({RECIPIENT_KEY: "   "})


def test_the_refusal_names_the_key_and_never_a_value() -> None:
    """**The one place a chat id would leak without anybody deciding to.**

    A refusal that quoted what it found would put the value in a log the first time the
    variable held something unexpected.
    """
    with pytest.raises(NoAcceptedRecipient) as caught:
        recipients_from({RECIPIENT_KEY: ""})
    message = str(caught.value)
    assert RECIPIENT_KEY in message
    assert FIRST not in message and SECOND not in message


def test_the_key_is_named_once_and_read_from_the_module() -> None:
    """The key's name is the contract, and it is imported rather than retyped here.

    A test spelling the variable name itself would keep passing after somebody renamed
    it in the module, which is the `F136` shape in the smallest possible form.
    """
    # OD-105 (2026-09-03): a chave que responde "para onde um envio VAI" — a mesma do
    # relatorio (OD-28). A allowlist de quem FALA com o bot nao autoriza destino.
    assert RECIPIENT_KEY == "TELEGRAM_REPORT_CHAT_ID"
