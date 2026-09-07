# catalogo_semantico

Decide se uma pergunta sobre uma metrica de negocio e autorizada — sem ler nenhum dado real. Ve `specs/001-catalogo-semantico/spec.md` no repositorio para a especificacao completa.

## Uso

```python
from datetime import date
from catalogo_semantico import carregar_catalogo, decidir

catalogo = carregar_catalogo("packages/catalogo_semantico/catalog")
eventos_de_auditoria = []

decisao = decidir(
    catalogo,
    metric_id="signups",
    dimension_id="country",
    period_start=date(2026, 3, 1),
    period_end=date(2026, 3, 31),
    audit_sink=eventos_de_auditoria,
)

if decisao.allowed:
    print(decisao.resolved_metric_version.label)
else:
    print(f"negado: {decisao.reason_code}")
```

## Garantias

- `decidir()` nunca faz chamada de rede ou banco de dados (Constitution Principio I).
- Autorizacao e deny-by-default: metrica ou dimensao nao aprovada e sempre negada.
- Uma versao de metrica descontinuada continua resolvivel para o periodo historico em que esteve vigente.
- Toda chamada de `decidir()` emite exatamente um evento em `audit_sink`.

## Testes

```bash
uv run pytest packages/catalogo_semantico
```
