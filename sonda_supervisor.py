"""Sonda del Choose del supervisor con la lógica EXACTA de producción.

Corre el test a mano (bmo/train/tasks/supervisor_dispatch_test.jsonl)
contra uno o más checkpoints y reporta, por caso: elección cruda,
confianza, veredicto y la decisión final — con 'met' la elección de Laya
despacha local; cualquier otra cosa cae a la votación. El valor real son
DOS números: acierto crudo y cuántos pasos despacha Laya sin gastar una
llamada.

Esta sonda es la CASA del contrato del fine-tune supervisor_dispatch:
PREGUNTA_DESPACHO y elegir_con_deepseek VIVEN acá desde que el Supervisor v2
jubiló el Choose (el checkpoint quedó como evidencia histórica — el
instrumento de medida sobrevive al mecanismo que medía). El congelamiento
del contrato se testea ALLÍ, en esta sonda.

Con --votacion, la vía dudosa se mide COMPLETA (gasta API): dos votos
DeepSeek (directo y por eliminación) + el voto crudo de Laya → mayoría
2-de-3.

Uso:
    python3 sonda_supervisor.py [checkpoint ...]        # sin args: LAYA_MODEL_SUPERVISOR
    python3 sonda_supervisor.py --votacion [checkpoint] # mide también la mayoría
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from supervisor import MAX_FALLOS_POR_HERRAMIENTA, REGISTRO, catalogo  # noqa: E402
from utils.call_llm import call_llm  # noqa: E402
from utils.estructura import extraer_yaml  # noqa: E402
from utils.rutas import tasks_dir  # noqa: E402

# El directorio de tests se resuelve por setting (default: la ruta histórica de
# esta máquina) para que la sonda no quede clavada a un path local.
_TAREAS = tasks_dir()
TEST = _TAREAS / "supervisor_dispatch_test.jsonl"


# Congelada: task supervisor_dispatch (bmo/train/tasks/supervisor_dispatch.yaml).
# Las 18 opciones en este orden exacto; entrenamiento y producción leen igual.
PREGUNTA_DESPACHO = {
    "elegir_proxima": {
        "type": "choice",
        "instructions": "Which tool runs the next step of this task, given what already ran?",
        "criteria": {
            "list_files": "see which files a folder holds",
            "read_file": "read the exact content of one file",
            "search_files": "find files by name or contained text",
            "write_file": "create or replace a file (needs approval)",
            "run_informe": "summarize one folder of traces",
            "run_auditoria": "compare several folders of traces",
            "answer_verified": "answer with citations checked against files",
            "rag_search": "semantic search over the local index",
            "rag_index": "(re)index a folder for semantic search",
            "debate": "run a proponent-vs-critic debate",
            "mcp_tools": "list the tools of external MCP servers",
            "mcp_call": "call a tool on an external MCP server",
            "search_web": "quick web search: titles, URLs, snippets",
            "deep_research": "multi-round web research with a report",
            "sql": "one SELECT query over the traces db",
            "db_schema": "schema of the traces database",
            "run_effective_n": "exact dedup of trace datasets",
            "finish": "done or blocked: synthesize now",
        },
    }
}
OPCIONES = list(PREGUNTA_DESPACHO["elegir_proxima"]["criteria"])

INSTRUCCION_ELECCION = {
    # voto A — el clásico
    "directo": "Elige UNA herramienta para el siguiente paso (o finish). "
               "El siguiente paso sigue de lo que FALTA, no de lo ya hecho.",
    # voto B — independiente por construcción: razona al revés
    "eliminacion": "Primero ELIMINA: nombra las herramientas que ya cumplieron "
                   "su parte según los hechos (o están prohibidas) y quedan descartadas. "
                   "Luego elige UNA de las restantes para el siguiente paso (o finish "
                   "si no queda nada que aporte).",
}


def elegir_con_deepseek(tarea, hechos, fuera, estilo="directo"):
    """Un voto de DeepSeek sobre el catálogo, con el framing del estilo."""
    veto_txt = (
        f"\nPROHIBIDO elegir (ya fallaron {MAX_FALLOS_POR_HERRAMIENTA} veces): "
        + ", ".join(sorted(fuera)) + ".\n" if fuera else ""
    )
    plan = extraer_yaml(call_llm(
        f"Tarea del usuario: {tarea}\n\n"
        f"Ya ejecutado:\n" + ("\n".join(hechos) or "(nada)") + "\n\n"
        f"Herramientas disponibles (nombre: descripción):\n{catalogo()}\n"
        f"{veto_txt}"
        f"finish: la tarea está cubierta o bloqueada; sintetizar ya.\n\n"
        f"{INSTRUCCION_ELECCION[estilo]}\n\n"
        "Responde SOLO yaml:\n```yaml\nherramienta: nombre\n```"
    ))
    eleccion = plan["herramienta"]
    assert eleccion in REGISTRO or eleccion == "finish", f"herramienta desconocida: {eleccion}"
    return eleccion


def correr(agente, casos, votacion=False):
    from utils.call_llm import _setting
    from utils.laya import _confianza, veredicto
    from utils.votacion import mayoria

    alto = _setting("LAYA_UNSURE_HIGH_SUPERVISOR", "0.9")  # el umbral histórico del Choose
    filas, crudo_ok, local_ok, locales, final_ok = [], 0, 0, 0, 0
    for caso in casos:
        r = agente.system_one(
            {"tarea": caso["fields"]["tarea"], "hechos": caso["fields"].get("hechos", "")},
            PREGUNTA_DESPACHO,
            lang="es",
        )
        resp = r["answers"]["elegir_proxima"]
        eleccion = resp.get("choice", resp.get("answer"))
        conf = _confianza(resp)
        esperado = caso["answers"]["elegir_proxima"]
        crudo_ok += eleccion == esperado
        if veredicto(conf, alto=alto) == "met":
            decision, detalle = eleccion, f"laya {conf:.2f}"
            locales += 1
            local_ok += eleccion == esperado
        elif votacion:
            tarea, hechos = caso["fields"]["tarea"], caso["fields"].get("hechos", "").splitlines()
            a = elegir_con_deepseek(tarea, hechos, set(), "directo")
            b = elegir_con_deepseek(tarea, hechos, set(), "eliminacion")
            votos = [a, b] + ([eleccion] if eleccion else [])
            decision = mayoria(votos, desempate=a, minimo=2)
            detalle = f"votos {votos}"
        else:
            decision, detalle = "(votación)", "—"
        final_ok += decision == esperado
        filas.append((caso["id"], esperado, eleccion, conf, decision, detalle, "✓" if decision == esperado else "✗"))
    return filas, crudo_ok, local_ok, locales, final_ok


def main(args):
    votacion = "--votacion" in args
    paths = [a for a in args if not a.startswith("--")]
    casos = [json.loads(linea) for linea in TEST.read_text(encoding="utf-8").splitlines() if linea.strip()]
    if not paths:
        from utils.call_llm import _setting

        setting = _setting("LAYA_MODEL_SUPERVISOR", "")
        if not setting:
            print("sin LAYA_MODEL_SUPERVISOR: pasá checkpoints como argumentos")
            return
        import laya

        paths, agentes = [setting], [laya.load(setting, device="cpu")]
    else:
        import laya

        agentes = [laya.load(p, device="cpu") for p in paths]
    for nombre, agente in zip(paths, agentes, strict=True):
        filas, crudo, local_ok, locales, final = correr(agente, casos, votacion)
        print(f"\n=== {nombre}{' (con votación 2-de-3)' if votacion else ''} ===")
        for id_, esperado, eleccion, conf, decision, detalle, marca in filas:
            print(f"  {marca} {id_:<26} esperado={esperado:<16} crudo={str(eleccion):<16} "
                  f"conf={conf:.2f} → {decision} · {detalle}")
        extra = f" · sistema (laya+mayoría): {final}/{len(casos)}" if votacion else ""
        print(f"crudo: {crudo}/{len(casos)} · despachos locales de Laya: {locales}/{len(casos)} "
              f"· correctos entre los locales: {local_ok}/{locales or 1}{extra}")


if __name__ == "__main__":
    main(sys.argv[1:])
