"""Contratos congelados (sha1): lo que no puede cambiar sin querer (PR 4)."""


def test_pregunta_despacho_congelada():
    # El contrato del despacho se mudó con la sonda (supervisor v2): su casa
    # es sonda_supervisor.py. REGISTRO sigue viviendo en supervisor.py.
    from sonda_supervisor import OPCIONES
    from supervisor import REGISTRO

    # El contrato del fine-tune supervisor_dispatch (bmo): las 18 opciones,
    # en este orden. Cambiar esto desincroniza entrenamiento y producción.
    esperadas = [
        "list_files", "read_file", "search_files", "write_file", "run_informe",
        "run_auditoria", "answer_verified", "rag_search", "rag_index", "debate",
        "mcp_tools", "mcp_call", "search_web", "deep_research", "sql", "db_schema",
        "run_effective_n", "finish",
    ]
    assert esperadas == OPCIONES, f"contrato roto: {OPCIONES}"
    assert "run_supervisor" not in OPCIONES  # L1: anti-recursión
    assert all(o in REGISTRO or o == "finish" for o in OPCIONES)

def test_contratos_laya_congelados_sha1():
    """El contrato con el fine-tune es byte-a-byte: cambiar UNA palabra de
    instructions/criteria desincroniza entrenamiento y producción. El test
    de claves no alcanza (hallazgo de la revisión de consistencia)."""
    import hashlib
    import json

    from sonda_supervisor import PREGUNTA_DESPACHO  # su casa desde supervisor v2

    canon = lambda p: hashlib.sha1(  # noqa: E731
        json.dumps(p, sort_keys=True, ensure_ascii=False).encode()
    ).hexdigest()
    assert canon(PREGUNTA_DESPACHO) == "de43614ad2f939048fb76ef7f9058bdbb0ef212e"


def test_sonda_supervisor_es_la_casa_del_contrato():
    """Con el supervisor v2 el contrato del despacho (PREGUNTA_DESPACHO y
    elegir_con_deepseek) VIVE en sonda_supervisor.py: supervisor ya no lo
    expone (se jubiló el Choose). La sonda lo mide como evidencia histórica."""
    import sonda_supervisor
    import supervisor

    assert not hasattr(supervisor, "PREGUNTA_DESPACHO")
    assert isinstance(sonda_supervisor.PREGUNTA_DESPACHO, dict)
    assert "elegir_proxima" in sonda_supervisor.PREGUNTA_DESPACHO
    assert callable(sonda_supervisor.elegir_con_deepseek)


def test_contrato_prefiltro_congelado_sha1():
    """El contrato del pre-filtro (exp/13): entrenamiento y producción leen
    la misma pregunta byte a byte — cambiar una palabra desincroniza el
    fine-tune router_prefiltro sin que nada lo note, como los demás
    contratos congelados."""
    import hashlib
    import json

    from utils.contexto import PREGUNTA_PREFILTRO

    sha = hashlib.sha1(json.dumps(PREGUNTA_PREFILTRO, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
    assert sha == "b40267534690ca6a787ebf8b40903b8dac8b3521", f"contrato del prefiltro derivado: {sha}"
