"""Sonda del Choose del supervisor con la lógica EXACTA de producción.

Corre el test a mano (bmo/train/tasks/supervisor_dispatch_test.jsonl)
contra uno o más checkpoints y reporta, por caso: elección cruda,
confianza, veredicto (0.7/0.3) y la decisión final de ElegirSiguiente —
con 'met' la elección de Laya despacha local; cualquier otra cosa cae a
DeepSeek (el lado seguro). El valor real son DOS números: acierto crudo
y cuántos pasos despacha Laya sin gastar una llamada.

Uso:
    python3 sonda_supervisor.py [checkpoint ...]   # sin args: LAYA_MODEL_SUPERVISOR
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

TEST = Path("/home/roquedb/Documentos/00_IA/bmo/train/tasks/supervisor_dispatch_test.jsonl")
from supervisor import PREGUNTA_DESPACHO  # noqa: E402


def correr(agente, casos):
    from utils.call_llm import _setting
    from utils.laya import _confianza, veredicto

    alto = _setting("LAYA_UNSURE_HIGH_SUPERVISOR", "0.9")  # el umbral real de ElegirSiguiente
    filas, crudo_ok, local_ok, locales = [], 0, 0, 0
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
        despacha_local = veredicto(conf, alto=alto) == "met"
        locales += despacha_local
        decision = eleccion if despacha_local else "(deepseek)"
        crudo_ok += eleccion == esperado
        local_ok += despacha_local and eleccion == esperado
        filas.append((caso["id"], esperado, eleccion, conf, decision, "✓" if eleccion == esperado else "✗"))
    return filas, crudo_ok, local_ok, locales


def main(paths):
    casos = [json.loads(l) for l in TEST.read_text(encoding="utf-8").splitlines() if l.strip()]
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
    for nombre, agente in zip(paths, agentes):
        filas, crudo, local_ok, locales = correr(agente, casos)
        print(f"\n=== {nombre} ===")
        for id_, esperado, eleccion, conf, decision, marca in filas:
            print(f"  {marca} {id_:<26} esperado={esperado:<16} crudo={str(eleccion):<16} "
                  f"conf={conf:.2f} → {decision}")
        print(f"crudo: {crudo}/{len(casos)} · despachos locales de Laya: {locales}/{len(casos)} "
              f"· correctos entre los locales: {local_ok}/{locales or 1}")


if __name__ == "__main__":
    main(sys.argv[1:])
