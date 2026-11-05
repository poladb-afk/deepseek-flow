"""S9b A′ — compatibilidad del vocabulario viejo del chat.

El refactor borró `AgentStep`/`ExecuteTools`/`Cierre`, pero las trazas, los
`.runs` y los checkpoints anteriores son del chat: `replay.NODOS_HISTORICOS` y
`ACCIONES_HISTORICAS` los traducen al vocabulario del loop actual. Estos tests
son el candado de ese mapa —sin él, la primera traza vieja auditada parecería
de otro producto— con un `.jsonl` real del emisor (copiado de `.runs`) y un
checkpoint con la forma previa a la caja `turno`.
"""
import json

from conftest import RAIZ

FIXTURES = RAIZ / "tests" / "fixtures"


def test_una_traza_vieja_real_del_chat_pasa_el_replay_por_el_mapa():
    import replay
    from instrumentos import leer_eventos

    eventos = leer_eventos(FIXTURES / "chat_viejo_s9b.jsonl")
    assert eventos, "el fixture de traza vieja se perdió"
    clases, aristas = replay._grafos_vivos()
    assert replay.nivel_a(eventos, clases) == []
    assert replay.nivel_a_desconocidos(eventos, clases, replay._herramientas_vivas()) == []
    assert replay.nivel_b_chat(eventos, clases, aristas) == []


def test_el_mapa_de_nombres_historicos_apunta_a_clases_vivas():
    import replay

    clases, _ = replay._grafos_vivos()
    assert set(replay.NODOS_HISTORICOS) == {"AgentStep", "ExecuteTools", "Cierre"}
    for viejo, nuevo in replay.NODOS_HISTORICOS.items():
        assert nuevo in clases, nuevo
        assert viejo not in clases, viejo  # los viejos ya no existen: solo se mapean


def test_un_checkpoint_viejo_migra_y_el_resume_lo_lee():
    from resume import migrar
    from utils.thread_store import cargar

    shared = cargar("chat_previo", ruta_dir=FIXTURES)
    assert shared and "turno" not in shared  # el fixture es del formato anterior
    assert shared["tool_rounds"] == 3
    migrar(shared)
    assert shared["turno"]["rondas"] == 3
    assert "tool_rounds" not in shared
    assert json.dumps(shared)  # sigue siendo JSON para el próximo checkpoint
