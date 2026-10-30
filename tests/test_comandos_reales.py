"""Fase 5a, pre-registro: la sonda que arma la foto de la política (sin red)."""
import json
from pathlib import Path

from banco.probes import comandos_reales as cr


def _checkpoint(*comandos):
    calls = [{"id": str(i), "type": "function",
              "function": {"name": "run_command", "arguments": json.dumps({"command": c})}}
             for i, c in enumerate(comandos)]
    calls.append({"id": "x", "type": "function", "function": {"name": "read_file", "arguments": "{}"}})
    return {"shared": {"messages": [{"role": "user", "content": "hola"},
                                    {"role": "assistant", "content": None, "tool_calls": calls}]}}


def test_lee_los_comandos_de_los_checkpoints_y_no_otras_tools():
    lineas = [_checkpoint("ls -la", "git status"), {"shared": {"messages": "roto"}}, {}]
    assert list(cr.de_threads(lineas)) == ["ls -la", "git status"]


def test_el_log_de_riesgo_descarta_los_que_pueden_estar_truncados():
    filas = [{"comando": "rm x"}, {"comando": "a" * cr.TRUNCADO_RIESGO}, {"comando": ""}]
    assert list(cr.de_riesgo(filas)) == ["rm x"]


def test_anonimiza_raiz_home_y_homes_ajenos():
    raiz, home = Path("/home/yo/repo"), Path("/home/yo")
    assert cr.anonimizar("cat /home/yo/repo/a.py /home/yo/.bashrc /home/otro/x", raiz, home) == \
        "cat {RAIZ}/a.py {HOME}/.bashrc {HOME}/x"


def test_la_foto_es_la_politica_de_hoy_dedup_y_sin_secretos():
    filas, descartes = cr.foto(["ls", "ls", "rm -rf build", "curl -H 'Bearer abc' x",
                                "x" * (cr.LARGO_MAX + 1)], raiz=Path("/r"), home=Path("/h"))
    assert [(f["comando"], f["nivel"], f["veces"]) for f in filas] == [
        ("ls", "auto", 2), ("rm -rf build", "confirmar_doble", 1)]
    assert descartes == {"posible_secreto": 1, "largo": 1}
    assert all(f["explicacion"] for f in filas)
