"""Fase 5a: la política como datos no cambia NINGUNA decisión.

Las dos fotos se congelaron con la política de ANTES de la migración
(`banco/specs/fase5a.md`): la real (`policy_comandos.jsonl`, comandos de
`run_command` de los threads del operador) y la sintética
(`policy_casos_entrada.jsonl`, casos por entrada de las listas).
Criterio original: 0 diferencias. S0-CITAS-EJECUCION retira auto de pytest y
actualiza sus explicaciones por delta explícito; las fotos no se reescriben.
"""
import hashlib
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
    """Foto inmutable y delta explícito de S0-CITAS-EJECUCION, sin omitir filas."""
    filas = _foto(nombre)
    ruta = Path(__file__).with_name("fixtures") / "policy_pytest_autorizacion.json"
    deltas = json.loads(ruta.read_text(encoding="utf-8"))[nombre]
    vistos = set()
    diferencias = []
    for fila in filas:
        clave = hashlib.sha256(fila["comando"].encode()).hexdigest()
        esperado = {"nivel": fila["nivel"], "explicacion": fila["explicacion"]}
        if clave in deltas:
            cambio = deltas[clave]
            assert cambio["antes"] == esperado
            assert (cambio["antes"]["nivel"], cambio["despues"]["nivel"]) in {
                ("auto", "preguntar"), ("preguntar", "preguntar"),
            }
            esperado = cambio["despues"]
            vistos.add(clave)
        actual = {"nivel": policy.clasificar(fila["comando"]), "explicacion": policy.explicar(fila["comando"])}
        if actual != esperado:
            diferencias.append((fila["comando"], esperado, actual))
    assert vistos == set(deltas), "hay deltas sin comando histórico correspondiente"
    assert diferencias == [], f"{len(diferencias)} diferencias no autorizadas: {diferencias[:5]}"


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
                                    "sin_explicacion", "token_con_espacio", "sin_clave", "flag_sin_guion",
                                    "opcion_sin_guion", "sin_subcomandos_git", "subcomando_con_espacio",
                                    "git_clave_desconocida", "git_viejo_suelto"])
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
    elif rotura == "flag_sin_guion":
        datos["flags_peligrosos"]["find"]["flags"].append("delete")
    elif rotura == "sin_subcomandos_git":
        del datos["git"]["subcomandos_de_scope"]
    elif rotura == "subcomando_con_espacio":
        datos["git"]["subcomandos_de_scope"].append("config core.pager")
    elif rotura == "git_clave_desconocida":
        datos["git"]["subcomandos_permitidos"] = ["status"]  # X177: un typo no amplía nada en silencio
    elif rotura == "git_viejo_suelto":
        datos["git_subcomandos_de_scope"] = datos.pop("git")["subcomandos_de_scope"]
    else:
        datos["opciones_permitidas"]["pytest"]["opciones"].append("q")
    with pytest.raises(ValueError):
        policy._leer_politica(_escribir(tmp_path, datos))


def test_el_archivo_versionado_valida_y_es_el_que_se_usa():
    assert policy._leer_politica() == policy._POLITICA
    assert policy.IRREVERSIBLES == ("git push", "rm -rf", "rm -fr", "git reset --hard", "git clean -f",
                                    "git checkout --", "git restore --worktree", "git switch -f",
                                    "git stash drop", "git stash clear", "git branch -D")
