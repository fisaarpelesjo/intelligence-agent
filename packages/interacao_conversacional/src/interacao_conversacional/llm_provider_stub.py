from __future__ import annotations

from .modelos import ClaimClass, ClaimSentence, NarrationPayload


class LLMProviderStub:
    """Narra um NarrationPayload em texto template, deterministico, sem chamada externa.

    Nunca calcula nada (ADR-0005) — todo numero ja vem pronto no payload.
    """

    def narrar(self, payload: NarrationPayload) -> list[ClaimSentence]:
        sentences = [
            ClaimSentence(
                text=(
                    f"{payload.metric_id} foi {payload.value} {payload.unit} "
                    f"em {payload.period_label} (fonte: {payload.source_view})."
                ),
                claim_class=ClaimClass.FACTUAL_RESULT,
            )
        ]
        if payload.comparison is not None:
            sentences.append(
                ClaimSentence(
                    text=(
                        f"Variacao de {payload.comparison.percentage_change:.1f}% "
                        "em relacao ao periodo anterior."
                    ),
                    claim_class=ClaimClass.CALCULATED_COMPARISON,
                )
            )
        sentences.append(
            ClaimSentence(
                text="Numero reflete apenas o periodo e a fonte indicados; nao implica causa.",
                claim_class=ClaimClass.LIMITATION,
            )
        )
        return sentences
