"""H3-G — ¿el router necesita reglas de palabras clave? (pre-registro: banco/specs/h3g_reglas.md)

Diseño pareado: por cada caso se consulta UNA vez el router de Laya y, si
propone directo, el voto de confirmación; con esos mismos resultados se arman
el brazo CON reglas (producción) y el brazo SIN reglas. El criterio
pre-registrado se aplica con una función pura, sin retoques.

Uso:
    python3 banco/probes/h3g_reglas.py            # necesita Laya (LAYA_MODEL) y DeepSeek para el árbitro
    python3 banco/probes/h3g_reglas.py --resumen  # rehace el resumen con lo ya medido

INVÁLIDO POR DISEÑO (X82): corrido, dio "gana" con cobertura efectiva 0. Una
regla solo cambia la ruta si dispara Y Laya propuso directo; el criterio
contaba disparos. Se conserva como registro; la pregunta se mide en H3-G2.
"""
import argparse
import dataclasses
import json
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(RAIZ))

from utils.laya_routing import regla_imperativo_capacidad, regla_temporal  # noqa: E402

CASOS_HUMANOS = RAIZ / "banco" / "voto_casos.jsonl"
CASOS_ARBITRO = RAIZ / "banco" / "calibracion_router_2026-10-08.jsonl"
SALIDA = RAIZ / "salidas" / "evals" / "h3g_reglas.jsonl"
COBERTURA_MIN = 20


def regla(pregunta):
    """La regla dura de producción (misma fuente que LayaRouter.exec)."""
    if regla_temporal(pregunta):
        return "temporal"
    if regla_imperativo_capacidad(pregunta):
        return "imperativo"
    return ""


def politica(regla_disparada, propuesta, voto, con_reglas):
    """La ruta final de LayaRouter en enforce. PURA. Orden de producción:
    regla → herramientas; si no, la propuesta del router; un directo necesita
    que el voto confirme (2-de-2)."""
    if con_reglas and regla_disparada:
        return "herramientas"
    if propuesta != "directo":
        return "herramientas"
    return "directo" if voto == "directo" else "herramientas"


def _normal(texto):
    return " ".join(str(texto).lower().split())


def cargar_casos(humanos=CASOS_HUMANOS, arbitro=CASOS_ARBITRO):
    """Los casos etiquetados, sin repetidos (la etiqueta humana gana)."""
    casos = {}
    for ruta, fuente, clave in ((arbitro, "arbitro", "etiqueta"), (humanos, "humana", "esperado")):
        if not Path(ruta).is_file():
            continue
        for linea in Path(ruta).read_text(encoding="utf-8").splitlines():
            if not linea.strip():
                continue
            fila = json.loads(linea)
            if fila.get("pregunta") and fila.get(clave) in ("directo", "herramientas"):
                casos[_normal(fila["pregunta"])] = {"pregunta": fila["pregunta"], "esperado": fila[clave],
                                                    "fuente": fuente, "id": fila.get("id", "")}
    return list(casos.values())


def medir_caso(caso, router, voto):
    """Consulta router y voto UNA vez y arma los dos brazos. `router(p)` ->
    propuesta; `voto(p)` -> (veredicto, llamo_al_arbitro). El voto solo corre
    si el router propone directo (como en producción)."""
    p = caso["pregunta"]
    disparo = regla(p)
    propuesta = router(p)
    veredicto, arbitro = voto(p) if propuesta == "directo" else (None, False)
    fila = {**caso, "regla": disparo, "propuesta": propuesta, "voto": veredicto}
    for brazo, con in (("con", True), ("sin", False)):
        final = politica(disparo, propuesta, veredicto, con)
        fila[f"final_{brazo}"] = final
        # el árbitro solo se paga en el brazo donde el voto efectivamente corre
        fila[f"arbitro_{brazo}"] = bool(arbitro) and not (con and disparo)
    return fila


def veredicto(filas):
    """El criterio de banco/specs/h3g_reglas.md, sin retoques. PURA."""
    def cuenta(brazo, esperado, final):
        return sum(1 for f in filas if f["esperado"] == esperado and f[f"final_{brazo}"] == final)

    medidas = {brazo: {"falso_directo": cuenta(brazo, "herramientas", "directo"),
                       "falso_herramientas": cuenta(brazo, "directo", "herramientas"),
                       "arbitro": sum(1 for f in filas if f[f"arbitro_{brazo}"])}
               for brazo in ("con", "sin")}
    cobertura = sum(1 for f in filas if f["regla"])
    salvados = [f for f in filas if f["esperado"] == "herramientas"
                and f["final_con"] == "herramientas" and f["final_sin"] == "directo"]
    condiciones = {"cobertura": cobertura >= COBERTURA_MIN,
                   "seguridad": medidas["sin"]["falso_directo"] == medidas["con"]["falso_directo"]}
    completo = bool(filas)
    gana = completo and all(condiciones.values())
    return {"n": len(filas), "medidas": medidas, "cobertura": cobertura, "salvados": salvados,
            "condiciones": condiciones, "gana": gana,
            "decision": ("sin reglas gana: se borran regla_temporal y regla_imperativo_capacidad" if gana else
                         "las reglas se quedan (salvan casos o no se ejercitaron)") if completo
            else "faltan datos: no hay veredicto"}


def cobertura_efectiva(filas):
    """Casos donde la regla podía DECIDIR: dispara y Laya propuso directo
    (X82). La `cobertura` del criterio contaba disparos, incluidos los casos
    que Laya ya mandaba a herramientas, donde la regla no tenía nada que
    salvar. Se reporta al lado; el criterio pre-registrado no se toca."""
    return sum(1 for f in filas if f["regla"] and f["propuesta"] == "directo")


def resumen(filas):
    v = veredicto(filas)
    L = ["# H3-G — ¿el router necesita reglas de palabras clave?", "",
         "Criterio pre-registrado: banco/specs/h3g_reglas.md.", "",
         f"Casos: {v['n']} ({sum(1 for f in filas if f['fuente'] == 'humana')} con etiqueta humana) · "
         f"las reglas disparan en {v['cobertura']}.", "",
         "| brazo | falso directo | falso herramientas | llamadas al árbitro |", "|---|---|---|---|"]
    for brazo, nombre in (("con", "con reglas (hoy)"), ("sin", "sin reglas")):
        m = v["medidas"][brazo]
        L.append(f"| {nombre} | {m['falso_directo']} | {m['falso_herramientas']} | {m['arbitro']} |")
    L += [""] + [f"- {c}: {'✅' if ok else '❌'}" for c, ok in v["condiciones"].items()]
    L += ["", f"**Veredicto:** {'GANA' if v['gana'] else 'NO GANA'} → {v['decision']}", ""]
    efectiva = cobertura_efectiva(filas)
    L += [f"**Corrección X82:** cobertura efectiva (regla dispara y Laya propuso directo) = {efectiva}. "
          + ("Las reglas nunca estuvieron en posición de decidir: el veredicto de arriba no las "
             "ejercitó y no autoriza el borrado. El criterio válido es H3-G2 "
             "(banco/specs/h3g2_voto_solo.md)." if efectiva < COBERTURA_MIN else
             "Alcanza el mínimo pre-registrado."), ""]
    if v["salvados"]:
        L += ["## Casos que las reglas salvan (falso directo sin ellas)", ""]
        L += [f"- [{f['fuente']}] ({f['regla']}) {f['pregunta'][:140]}" for f in v["salvados"]]
    return "\n".join(L) + "\n"


def _router_y_voto():
    """Los componentes REALES de producción, en modo enforce."""
    import nodes
    from utils import call_llm
    from utils.laya import disponible, preguntar_detalle
    from utils.laya_routing import config_router, decide

    if not disponible():
        raise SystemExit("ERROR: Laya no está disponible (LAYA_MODEL): sin router no hay experimento")
    config = dataclasses.replace(config_router(), modo="enforce")

    def router(pregunta):
        detalle = preguntar_detalle({"pregunta": pregunta[:1000]}, nodes.PREGUNTA_ROUTER)
        return decide(detalle.get("necesita_herramientas"), config)[0]

    def voto(pregunta):
        original, llamadas = call_llm.call_llm, []

        def contado(*a, **k):
            llamadas.append(1)
            return original(*a, **k)

        call_llm.call_llm = contado
        try:
            return nodes.voto_confirmacion_router(pregunta), bool(llamadas)
        finally:
            call_llm.call_llm = original

    return router, voto


def main(argv=None):
    parser = argparse.ArgumentParser(prog="h3g_reglas", description="H3-G: router con y sin reglas de palabras clave")
    parser.add_argument("--resumen", action="store_true", help="solo rehace el resumen")
    args = parser.parse_args(argv)
    if not args.resumen:
        router, voto = _router_y_voto()
        SALIDA.parent.mkdir(parents=True, exist_ok=True)
        filas = []
        for k, caso in enumerate(cargar_casos(), 1):
            fila = medir_caso(caso, router, voto)
            filas.append(fila)
            print(f"[h3g] {k} {fila['fuente']:7s} esperado={fila['esperado']:12s} regla={fila['regla'] or '-':10s} "
                  f"con={fila['final_con']:12s} sin={fila['final_sin']}", flush=True)
        SALIDA.write_text("".join(json.dumps(f, ensure_ascii=False) + "\n" for f in filas), encoding="utf-8")
    filas = [json.loads(ln) for ln in SALIDA.read_text(encoding="utf-8").splitlines() if ln.strip()] \
        if SALIDA.is_file() else []
    texto = resumen(filas)
    destino = SALIDA.with_name("h3g_reglas-resumen.md")
    destino.write_text(texto, encoding="utf-8")
    print(texto)
    print(f"[h3g] resumen → {destino}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
