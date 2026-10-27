"""El producto completo del router sobre el bench del voto y el control (X90).

Pregunta: ¿cuántos falsos directos tiene HOY la política de producción
(skills → reglas → router de Laya → voto 2-de-2, en enforce) en los casos
etiquetados del voto (`banco/voto_casos.jsonl` + `banco/voto_control.jsonl`)?

Dónde decide cada pieza (lección X82), declarado antes de correr:
- un skill o una regla deciden solo si disparan: ahí la ruta es herramientas;
- el router decide en el resto; si propone herramientas, termina ahí;
- el voto decide solo si el router propuso directo.
La VENTANA de riesgo son los casos esperado=herramientas sin skill ni regla:
ahí nada estructural frena un falso directo. Calculada sin Laya, hoy incluye
k13 y k15, los falsos directos del voto que ninguna regla cubre. Si la
ventana queda vacía, la medición no ejercita nada y no hay veredicto.

Decisión atada: 0 falsos directos → no hay agujero en producción (el router
los frena). Más de 0 → hallazgo abierto con sus ids y la capa que falló; la
discusión de cómo cerrarlo arranca de ese número, no de agregar verbos a una
lista.

Uso:
    python3 banco/probes/producto_router.py            # necesita Laya (LAYA_MODEL y LAYA_MODEL_VOTO)
    python3 banco/probes/producto_router.py --resumen
"""
import argparse
import json
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(RAIZ))
sys.path.insert(0, str(RAIZ / "banco" / "probes"))

from bench_voto import CASOS, CONTROL, cargar_casos  # noqa: E402
from h3g_reglas import politica, regla, router_y_voto  # noqa: E402

SALIDA = RAIZ / "salidas" / "evals" / "producto_router.jsonl"


def skill_de(pregunta):
    from utils.skills import disponibles, skill_para

    habilidad = skill_para(pregunta, disponibles())
    return habilidad.id if habilidad else ""


def casos():
    return cargar_casos(CASOS) + cargar_casos(CONTROL)


def en_ventana(caso, skill=skill_de):
    """Esperado herramientas y sin skill ni regla: lo frena el router o nadie."""
    return caso["esperado"] == "herramientas" and not skill(caso["pregunta"]) and not regla(caso["pregunta"])


def medir_caso(caso, router, voto, skill=skill_de):
    """La ruta de producción, capa por capa. `router(p)` -> propuesta;
    `voto(p)` -> (veredicto, llamo_al_arbitro); solo se consultan si hacen falta."""
    p = caso["pregunta"]
    hab, disparo = skill(p), regla(p)
    propuesta = veredicto = None
    if hab:
        final, capa = "herramientas", f"skill:{hab}"
    elif disparo:
        final, capa = "herramientas", f"regla:{disparo}"
    else:
        propuesta = router(p)
        if propuesta == "directo":
            veredicto, _arbitro = voto(p)
        final = politica("", propuesta, veredicto, con_reglas=True)
        capa = "voto" if propuesta == "directo" else "router"
    return {"id": caso["id"], "grupo": caso["grupo"], "esperado": caso["esperado"], "pregunta": p,
            "skill": hab, "regla": disparo, "propuesta": propuesta, "voto": veredicto,
            "final": final, "capa": capa, "ventana": en_ventana(caso, skill)}


def veredicto(filas):
    """PURA. Falsos directos de producción y dónde se decidieron."""
    ventana = [f for f in filas if f["ventana"]]
    falsos = [f for f in filas if f["esperado"] == "herramientas" and f["final"] == "directo"]
    completo = bool(ventana)
    return {
        "n": len(filas),
        "ventana": [f["id"] for f in ventana],
        "router_propuso_directo_en_ventana": [f["id"] for f in ventana if f["propuesta"] == "directo"],
        "falsos_directos": [f["id"] for f in falsos],
        "falsos_herramientas": [f["id"] for f in filas if f["esperado"] == "directo" and f["final"] == "herramientas"],
        "completo": completo,
        "decision": ("faltan datos: la ventana está vacía, la medición no ejercita nada" if not completo else
                     "no hay agujero: la política de producción frena todos los casos de la ventana"
                     if not falsos else
                     f"hallazgo abierto: {len(falsos)} falso(s) directo(s) en producción "
                     f"({', '.join(f['id'] for f in falsos)})"),
    }


def resumen(filas):
    v = veredicto(filas)
    L = ["# El producto completo del router sobre bench + control (X90)", "",
         f"Casos: {v['n']} · ventana (herramientas sin skill ni regla): {len(v['ventana'])} "
         f"({', '.join(v['ventana']) or '—'})", "",
         f"- el router propuso directo en la ventana: {', '.join(v['router_propuso_directo_en_ventana']) or 'ninguno'}",
         f"- falsos directos de producción: {', '.join(v['falsos_directos']) or 'ninguno'}",
         f"- falsos herramientas (costo): {', '.join(v['falsos_herramientas']) or 'ninguno'}", "",
         f"**Veredicto:** {v['decision']}", "",
         "| id | esperado | capa | propuesta | voto | final |", "|---|---|---|---|---|---|"]
    for f in filas:
        marca = " ⚠" if f["esperado"] == "herramientas" and f["final"] == "directo" else ""
        L.append(f"| {f['id']}{marca} | {f['esperado']} | {f['capa']} | {f['propuesta'] or '—'} "
                 f"| {f['voto'] or '—'} | {f['final']} |")
    return "\n".join(L) + "\n"


def main(argv=None):
    parser = argparse.ArgumentParser(prog="producto_router", description="X90: el router completo sobre bench + control")
    parser.add_argument("--resumen", action="store_true", help="solo rehace el resumen")
    args = parser.parse_args(argv)
    if not args.resumen:
        router, voto = router_y_voto()
        filas = [medir_caso(caso, router, voto) for caso in casos()]
        SALIDA.parent.mkdir(parents=True, exist_ok=True)
        SALIDA.write_text("".join(json.dumps(f, ensure_ascii=False) + "\n" for f in filas), encoding="utf-8")
    filas = [json.loads(ln) for ln in SALIDA.read_text(encoding="utf-8").splitlines() if ln.strip()] \
        if SALIDA.is_file() else []
    texto = resumen(filas)
    destino = SALIDA.with_name("producto_router-resumen.md")
    destino.write_text(texto, encoding="utf-8")
    print(texto)
    return 0


if __name__ == "__main__":
    sys.exit(main())
