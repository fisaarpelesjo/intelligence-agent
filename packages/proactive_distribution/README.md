# `proactive_distribution`

**Saying it to the person who needs it, without being asked.**

The seventh package of the governed stack, and **the first that originates anything**.
That is its whole novelty and its whole risk.

## The authority, and it is narrow on purpose

`FR-062` of `004` says the system MUST originate no message on its own initiative.
**That requirement is not amended** — `004`'s specification is untouched. An ADR
supersedes it for **one case**, and the case is three conditions that must all hold:

1. the finding is **prioritisable** — `006` placed it;
2. the channel is **already enabled** — this package enables nothing;
3. the recipient **has accepted** — one, derived from `TELEGRAM_ALLOWED_CHAT_ID`.

An exception that said *the system may originate messages* would have cost the property
`FR-062` buys. Three checkable conditions is what keeps the exception from becoming the
rule, and each one refuses with **its own code** so a caller knows which stopped it.

## What it emits: five labelled fields, and never a sentence

The owner chose the shape on 2026-08-27 over three alternatives — one that put
everything in a sentence, one that split the causality caveat away from the number, and
one that repeated the number in two places that can disagree.

**Label and value, one line per field, five fields: metric, period, figure, direction,
caveat.**

**Where there is no prose, there is no sentence that claims more than was measured.** The
form cannot commit that defect *by construction* rather than avoiding it by discipline —
and the causality caveat is a field like the others, which changes where it lives and not
whether it may change: its value is compared against `005`'s own constant and refused one
character apart.

## What it answers today: a refusal, and that is the package working

**Nothing can be sent, for two independent reasons.**

* **No finding is prioritisable.** Both of `006`'s component readers answer `None`.
* **No label is approved.** The five words are the owner's and he has not written them.

The two have **separate codes**, deliberately: *nothing was worth sending* is a fact
about the warehouse, and *there is no approved way to say it* is a fact about a decision
nobody has taken. A reader who sees one must know which of the two stopped them.

## What it will not do

**It writes no label**, under any name — not `EXAMPLE_`, not `DRAFT_`, not a fixture. A
plausible label is a word this repository wrote that a reader would attribute to him,
which is fabricating an approval.

**It composes no prose**, asserted by walking the syntax tree rather than promised.

**It originates nothing on its own** — no scheduler, no timer, no thread, no event loop.
A run is called and receives what it needs as parameters.

**It enables no channel and declares no production readiness.**

**It writes no recipient.** The id is derived from the declared key, and the node proving
it derives twice from two environments and requires two answers — because a literal that
happens to be correct passes every test that checks the answer and only fails one that
checks the derivation.

See `specs/007-proactive-distribution/` for the governing specification.
