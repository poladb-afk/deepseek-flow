"""Smoke tests de lo estable — sin red, sin LLM, sin modelo (PR 4)."""


def test_action_space_completo():
    from nodes import TOOLS

    nombres = {t["function"]["name"] for t in TOOLS}
    esperadas = {
        "list_files", "read_file", "search_files",  # CORE
        "run_informe", "write_file", "answer_verified", "run_auditoria",
        "rag_search", "rag_index", "debate",  # módulos
        "mcp_tools", "mcp_call", "search_web", "deep_research", "run_supervisor",
        "sql", "db_schema", "run_effective_n", "evals", "request_human_input",
    }
    assert esperadas <= nombres, f"faltan: {esperadas - nombres}"

def test_imports_batchflow_exactos():
    """Cobertura de abstracciones: las piezas nuevas importan exactamente
    pocketflow.BatchFlow (effective_n) y pocketflow.AsyncParallelBatchFlow
    (juez_lote)."""
    import inspect

    import effective_n
    import juez_lote

    assert "BatchFlow" in inspect.getsource(effective_n)
    assert "AsyncParallelBatchFlow" in inspect.getsource(juez_lote)
    # y las usa como clase base / instancia real
    from pocketflow import AsyncParallelBatchFlow, BatchFlow

    assert issubclass(effective_n.EffectiveNMulti, BatchFlow)
    assert issubclass(juez_lote.JuezLoteFlow, AsyncParallelBatchFlow)

def test_action_space_suma_coding():
    from nodes import TOOLS

    nombres = {t["function"]["name"] for t in TOOLS}
    assert {"run_command", "edit_file"} <= nombres

def test_action_space_suma_memoria():
    from nodes import TOOLS

    nombres = {t["function"]["name"] for t in TOOLS}
    assert {"memory_search", "memory_save"} <= nombres

def test_action_space_suma_vision_y_a2a():
    from nodes import TOOLS

    nombres = {t["function"]["name"] for t in TOOLS}
    assert {"ver_imagen", "ver_pdf", "agentes_remotos", "a2a_tarea"} <= nombres
