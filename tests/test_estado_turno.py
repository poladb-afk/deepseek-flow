"""H2 PR 4a — la caja de la pregunta y el estado de sesión que sobrevive a resume.

Sin LLM. Clavan dos cosas que la auditoría de elegancia marcó (E5, F5):
- el estado de la pregunta vive en UNA caja (`shared["turno"]`) que
  GetQuestion reemplaza entera: no hay `pop` que olvidar;
- lo que vive fuera de `shared` (costo, aprobaciones, intención del juez de
  riesgo) viaja en el checkpoint y `resume` lo repone.
"""
import json

import nodes
import resume
from utils import aprobaciones, call_llm, estado_sesion
from utils.thread_store import cargar, cargar_sesion, checkpoint


def test_una_clave_nueva_de_la_pregunta_no_se_filtra_a_la_siguiente():
    """El bug que la caja hace imposible: cualquier cosa que un nodo guarde en
    la caja de la pregunta muere con ella, sin necesidad de un `pop`."""
    shared = {"messages": [{"role": "system", "content": "s"}]}
    nodes.GetQuestion().post(shared, None, "primera")
    shared["turno"]["algo_nuevo"] = "de la primera"
    shared["turno"]["rondas"] = 7
    nodes.GetQuestion().post(shared, None, "segunda")
    assert "algo_nuevo" not in shared["turno"]
    assert shared["turno"] == {**nodes.nuevo_turno(), "uso_inicio": shared["turno"]["uso_inicio"]}


def test_lo_de_la_sesion_queda_fuera_de_la_caja():
    """Compacción, respaldo y la tarea vigente NO son de la pregunta: un
    "seguí" conserva el objetivo; la compacción sigue contando."""
    shared = {"messages": [{"role": "system", "content": "s"}], "compacciones": 2}
    nodes.GetQuestion().post(shared, None, "auditá policy.py")
    nodes.GetQuestion().post(shared, None, "seguí")
    assert shared["_objetivo"] == "auditá policy.py"
    assert shared["compacciones"] == 2


def test_la_caja_es_json():
    shared = {"messages": []}
    nodes.GetQuestion().post(shared, None, "hola")
    nodes.actualizar_novedad(shared, [{"function": {"name": "read_file", "arguments": "{}"}}])
    assert json.loads(json.dumps(shared["turno"])) == shared["turno"]


def test_el_checkpoint_lleva_la_sesion_y_resume_la_repone(tmp_path, monkeypatch):
    """F5: tras resume, el costo de la sesión, /aprobaciones y la intención del
    juez de riesgo arrancaban de cero. Ahora viajan con el checkpoint."""
    monkeypatch.setattr(call_llm, "USO", {"llamadas": 4, "prompt": 900, "completion": 60})
    monkeypatch.setattr(call_llm, "USO_POR_MODELO", {"m": {"llamadas": 4, "prompt": 900, "completion": 60,
                                                          "cache_hit": 0, "cache_miss": 900}})
    aprobaciones.limpiar()
    aprobaciones.registrar("run_command", "echo hola", True, "auto")
    estado_sesion.recordar_usuario("borrá los cachés")
    checkpoint("t", "GetQuestion", "continue", {"messages": []}, ruta_dir=tmp_path)

    # "otro proceso": todo en cero
    monkeypatch.setattr(call_llm, "USO", {"llamadas": 0, "prompt": 0, "completion": 0})
    monkeypatch.setattr(call_llm, "USO_POR_MODELO", {})
    aprobaciones.limpiar()
    estado_sesion.recordar_usuario("")

    estado_sesion.restaurar(cargar_sesion("t", ruta_dir=tmp_path))
    assert call_llm.uso_de_sesion() == {"llamadas": 4, "prompt": 900, "completion": 60}
    assert call_llm.desglose_de_sesion()["m"]["prompt"] == 900
    assert [e["resumen"] for e in aprobaciones.eventos()] == ["echo hola"]
    assert estado_sesion.ultimo_usuario() == "borrá los cachés"
    aprobaciones.limpiar()


def test_un_checkpoint_viejo_se_migra_a_la_caja(tmp_path):
    """Los checkpoints escritos antes de la caja traen las claves sueltas:
    resume las migra y el chat sigue donde estaba."""
    viejo = {"messages": [{"role": "system", "content": "s"}], "tool_rounds": 3,
             "no_progress": 1, "_skill_activo": "revision", "_objetivo": "auditá"}
    checkpoint("v", "ExecuteTools", "default", viejo, ruta_dir=tmp_path)
    shared = resume.migrar(cargar("v", ruta_dir=tmp_path))
    assert shared["turno"]["rondas"] == 3 and shared["turno"]["sin_progreso"] == 1
    assert shared["turno"]["skill"] == "revision"
    assert "tool_rounds" not in shared and shared["_objetivo"] == "auditá"
    assert resume.migrar(shared) == shared  # idempotente
    assert cargar_sesion("v", ruta_dir=tmp_path) is not None


def test_restaurar_tolera_checkpoints_sin_sesion():
    antes = call_llm.uso_de_sesion()
    estado_sesion.restaurar(None)
    estado_sesion.restaurar({})
    assert call_llm.uso_de_sesion() == antes
