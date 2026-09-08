import dataclasses
import inspect

import relatorio_periodico
from relatorio_periodico import AlertBundle, DailyReport


def test_daily_report_e_alert_bundle_nao_compartilham_campo() -> None:
    campos_relatorio = {f.name for f in dataclasses.fields(DailyReport)}
    campos_alerta = {f.name for f in dataclasses.fields(AlertBundle)}

    assert campos_relatorio.isdisjoint(campos_alerta)


def test_nenhuma_funcao_publica_retorna_os_dois_tipos_combinados() -> None:
    for name in relatorio_periodico.__all__:
        obj = getattr(relatorio_periodico, name)
        if not inspect.isfunction(obj):
            continue
        signature = inspect.signature(obj)
        return_annotation = signature.return_annotation
        assert return_annotation is not tuple[DailyReport, AlertBundle]
