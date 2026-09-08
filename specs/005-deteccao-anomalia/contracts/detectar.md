# Contrato: funcao de deteccao

## `detectar(rule, catalogo, data_source, reference_today, max_bytes, max_rows) -> DetectionOutcome`

1. Se `rule.window_days < 1` -> `reason_code="janela_invalida"`, `triggered=False`.
2. `observed_date = reference_today - 1 dia` (ultimo dia completo).
3. Executar a metrica em `observed_date` (mesmo helper de `relatorio_periodico`). Se indisponivel -> `reason_code="observado_indisponivel"`.
4. Para cada um dos `window_days` dias imediatamente anteriores a `observed_date` (`observed_date - 1`, `observed_date - 2`, ..., `observed_date - window_days`): executar a metrica. Se qualquer um indisponivel -> `reason_code="baseline_incompleta"`, parar imediatamente (nao executa os dias restantes da janela desnecessariamente apos a primeira falha nao e obrigatorio, mas todas devem ser tentadas ou a primeira falha ja decide — implementacao pode parar cedo).
5. `baseline_value = media aritmetica dos window_days valores`. Se `baseline_value == 0` -> `reason_code="baseline_zero"`.
6. `deviation_pct = (observed_value - baseline_value) / baseline_value * 100`.
7. Se `abs(deviation_pct) > rule.threshold_pct` -> `triggered=True`, `finding` preenchido (`direction="increase"` se `deviation_pct > 0` senao `"decrease"`).
8. Senao -> `triggered=False`, `finding=None`, `reason_code=None`.

Nenhuma excecao de `catalogo_semantico`/`execucao_query` propaga — ja retornam recusa nomeada.
