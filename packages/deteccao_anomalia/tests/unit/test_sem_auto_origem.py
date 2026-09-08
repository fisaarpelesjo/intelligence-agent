import ast
from pathlib import Path

PROIBIDOS = {"threading", "sched", "time"}
SRC_DIR = Path(__file__).resolve().parents[2] / "src" / "deteccao_anomalia"


def _modulos_importados(arquivo: Path) -> set[str]:
    arvore = ast.parse(arquivo.read_text(encoding="utf-8"))
    modulos: set[str] = set()
    for node in ast.walk(arvore):
        if isinstance(node, ast.Import):
            modulos.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            modulos.add(node.module.split(".")[0])
    return modulos


def test_nenhum_modulo_de_scheduling_timer_ou_thread_e_importado() -> None:
    encontrados: dict[str, set[str]] = {}
    for arquivo in SRC_DIR.rglob("*.py"):
        proibidos_no_arquivo = _modulos_importados(arquivo) & PROIBIDOS
        if proibidos_no_arquivo:
            encontrados[str(arquivo)] = proibidos_no_arquivo

    assert not encontrados, f"imports proibidos encontrados: {encontrados}"
