"""Fase 5a: la política como datos no cambia NINGUNA decisión.

Las dos fotos se congelaron con la política de ANTES de la migración
(`banco/specs/fase5a.md`): la real (`policy_comandos.jsonl`, comandos de
`run_command` de los threads del operador) y la sintética
(`policy_casos_entrada.jsonl`, casos por entrada de las listas).
Criterio pre-registrado: 0 diferencias en nivel y en texto.
"""
import json
from pathlib import Path

import pytest

from utils import policy

FIXTURES = Path(__file__).resolve().parents[1] / "banco" / "fixtures"


def _foto(nombre):
    ruta = FIXTURES / nombre
    if not ruta.exists():
        pytest.skip(f"falta la foto {nombre}")
    return [json.loads(linea) for linea in ruta.read_text(encoding="utf-8").splitlines() if linea.strip()]


@pytest.mark.parametrize("nombre", ["policy_comandos.jsonl", "policy_casos_entrada.jsonl"])
def test_cero_diferencias_contra_la_foto(nombre):
    filas = _foto(nombre)
    diferencias = [(f["comando"], f["nivel"], policy.clasificar(f["comando"]))
                   for f in filas if policy.clasificar(f["comando"]) != f["nivel"]]
    diferencias += [(f["comando"], f["explicacion"], policy.explicar(f["comando"]))
                    for f in filas if policy.explicar(f["comando"]) != f["explicacion"]]
    assert diferencias == [], f"{len(diferencias)} diferencias de {len(filas)}: {diferencias[:5]}"


def _escribir(tmp_path, datos):
    ruta = tmp_path / "p.json"
    ruta.write_text(datos if isinstance(datos, str) else json.dumps(datos), encoding="utf-8")
    return ruta


@pytest.mark.parametrize("contenido", [None, "{roto", "[]"], ids=["ausente", "json_roto", "no_objeto"])
def test_falla_cerrada_si_el_archivo_falta_o_no_es_json(tmp_path, contenido):
    ruta = tmp_path / "no_existe.json" if contenido is None else _escribir(tmp_path, contenido)
    with pytest.raises(ValueError):
        policy._leer_politica(ruta)


@pytest.mark.parametrize("rotura", ["nivel_desconocido", "repetido", "tapado", "sin_negra_doble",
                                    "sin_explicacion", "token_con_espacio", "sin_clave", "flag_sin_guion"])
def test_falla_cerrada_si_los_datos_no_validan(tmp_path, rotura):
    datos = json.loads(policy._ARCHIVO.read_text(encoding="utf-8"))
    prefijos = datos["prefijos"]
    if rotura == "nivel_desconocido":
        prefijos[0]["nivel"] = "a_veces"
    elif rotura == "repetido":
        prefijos.append(dict(prefijos[0]))
    elif rotura == "tapado":
        prefijos[:] = [{"tokens": ["rm"], "nivel": "preguntar", "explicacion": "x"}] + \
            [p for p in prefijos if p["tokens"] != ["rm"]]
    elif rotura == "sin_negra_doble":
        prefijos[:] = [p for p in prefijos if p.get("nivel") != "confirmar_doble"]
    elif rotura == "sin_explicacion":
        prefijos[0]["explicacion"] = " "
    elif rotura == "token_con_espacio":
        prefijos[0]["tokens"] = ["git push"]
    elif rotura == "sin_clave":
        del datos["envoltorios"]
    else:
        datos["flags_peligrosos"]["find"]["flags"].append("delete")
    with pytest.raises(ValueError):
        policy._leer_politica(_escribir(tmp_path, datos))


def test_el_archivo_versionado_valida_y_es_el_que_se_usa():
    assert policy._leer_politica() == policy._POLITICA
    assert policy.IRREVERSIBLES == ("git push", "rm -rf", "rm -fr")
