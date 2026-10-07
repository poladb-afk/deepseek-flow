"""Sonda del Choose del supervisor con la lógica EXACTA de producción.

Corre el test a mano (bmo/train/tasks/supervisor_dispatch_test.jsonl)
contra uno o más checkpoints y reporta, por caso: elección cruda,
confianza, veredicto y la decisión final de ElegirSiguiente — con 'met'
la elección de Laya despacha local; cualquier otra cosa cae a la
votación. El valor real son DOS números: acierto crudo y cuántos pasos
despacha Laya sin gastar una llamada.

Con --votacion, la vía dudosa se mide COMPLETA (gasta API): dos votos
DeepSeek (directo y por eliminación) + el voto crudo de Laya → mayoría
2-de-3, igual que ElegirSiguiente en producción.

Uso:
    python3 sonda_supervisor.py [checkpoint ...]        # sin args: LAYA_MODEL_SUPERVISOR
    python3 sonda_supervisor.py --votacion [checkpoint] # mide también la mayoría
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from supervisor import PREGUNTA_DESPACHO, elegir_con_deepseek  # noqa: E402
from utils.call_llm import _setting  # noqa: E402

# El directorio de tests se resuelve por setting (default: la ruta histórica de
# esta máquina) para que la sonda no quede clavada a un path local.
_TAREAS = Path(_setting("BMO_TASKS_DIR", str(Path.home() / "Documentos" / "00_IA" / "bmo" / "train" / "tasks")))
TEST = _TAREAS / "supervisor_dispatch_test.jsonl"


def correr(agente, casos, votacion=False):
    from utils.call_llm import _setting
    from utils.laya import _confianza, veredicto
    from utils.votacion import mayoria

    alto = _setting("LAYA_UNSURE_HIGH_SUPERVISOR", "0.9")  # el umbral real de ElegirSiguiente
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
