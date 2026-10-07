"""Sonda del router con la lógica EXACTA de producción (compuerta incluida).

Corre el test a mano (bmo/train/tasks/router_flow_test.jsonl) contra uno o
más checkpoints y reporta, por caso: elección cruda, confianza, veredicto
(umbrales LAYA_UNSURE 0.7/0.3) y la decisión final del LayaRouter —
'directo' solo si eligió directo Y el veredicto es 'met'; cualquier otra
cosa cae a 'herramientas' (el lado seguro). Correcto = decisión == esperado.

El estado es {"pregunta": ...}: el contrato del fine-tune (task router_flow),
importado de nodes — una sola fuente; una copia local derivaría sin que
ningún test lo note (hallazgo medido en la revisión de consistencia).

Uso:
    python3 sonda_router.py [checkpoint ...]   # sin args: LAYA_MODEL del .env
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

# El directorio de tests se resuelve por setting (default: la ruta histórica de
# esta máquina) para que la sonda no quede clavada a un path local.
from utils.call_llm import _setting  # noqa: E402

_TAREAS = Path(_setting("BMO_TASKS_DIR", str(Path.home() / "Documentos" / "00_IA" / "bmo" / "train" / "tasks")))
TEST = _TAREAS / "router_flow_test.jsonl"
from nodes import PREGUNTA_ROUTER  # noqa: E402  (el contrato, sin copia)


def correr(agente, casos):
    from utils.laya import _confianza, veredicto

    filas, ok, crudo_ok = [], 0, 0
    for caso in casos:
        r = agente.system_one({"pregunta": caso["fields"]["pregunta"]}, PREGUNTA_ROUTER, lang="es")
        resp = r["answers"]["necesita_herramientas"]
        eleccion = resp.get("choice", resp.get("answer"))
        conf = _confianza(resp)
        esperado = caso["answers"]["necesita_herramientas"]
        decision = eleccion if (eleccion == "directo" and veredicto(conf) == "met") else "herramientas"
        ok += decision == esperado
        crudo_ok += eleccion == esperado
        filas.append((caso["id"], esperado, eleccion, conf, decision, "✓" if decision == esperado else "✗"))
    return filas, ok, crudo_ok


def main(paths):
    casos = [json.loads(linea) for linea in TEST.read_text(encoding="utf-8").splitlines() if linea.strip()]
    if not paths:
        from utils.laya import agente

        paths, agentes = [None], [agente()]
    else:
        import laya

        agentes = [laya.load(p, device="cpu") for p in paths]
    for nombre, agente in zip([p or "LAYA_MODEL (.env)" for p in paths], agentes, strict=True):
        filas, ok, crudo = correr(agente, casos)
        print(f"\n=== {nombre} ===")
        for id_, esperado, eleccion, conf, decision, marca in filas:
            print(f"  {marca} {id_:<22} esperado={esperado:<12} crudo={str(eleccion):<12} "
                  f"conf={conf:.2f} → decisión={decision}")
        print(f"con compuerta: {ok}/{len(casos)} · crudo: {crudo}/{len(casos)}")


if __name__ == "__main__":
    main(sys.argv[1:])
