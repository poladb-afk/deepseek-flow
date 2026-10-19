"""exp/53 — bench permanente de decisiones del VOTO (Mesa 1, ítem 7).

El dataset `banco/voto_casos.jsonl` fija los casos que importan de la cascada:

- `correccion`: donde Laya-router dice directo y DEBE corregirse a herramientas
  (imperativos/capacidades; los falso-directo medidos el 2026-10-05 y exp/46).
- `directo`: control inverso — conocimiento o creatividad que NO debe pedir
  tools ("escribime un haiku", la trampa inversa del router).
- `herramientas`: casos claros con tools, para que el voto no pierda recall.

Mide la cascada REAL de producción (voto local LAYA_MODEL_VOTO decide si es
confiable; la banda incierta la arbitra DeepSeek con el MISMO prompt de
`nodes.PROMPT_ARBITRO_VOTO`) y reporta por grupo: aciertos, falsos directos
(riesgo de responder sin leer) y cobertura local (llamadas al árbitro
ahorradas). Es instrumento de SEÑAL, no gate: un fallo en `correccion` se
reporta como ❌, no rompe el proceso.

Texto sintético del repo (sin datos de usuario): por eso el dataset se
versiona y el bench es reproducible. Uso:
    python3 banco/probes/bench_voto.py [--casos ruta] [--salida ruta.json]
"""
import argparse
import json
import statistics
import sys
import time
from datetime import datetime
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(RAIZ))  # los imports del harness (nodes, utils) viven en la raíz

CASOS = RAIZ / "banco" / "voto_casos.jsonl"
GRUPOS = ("correccion", "directo", "herramientas")
ESPERADOS = ("herramientas", "directo")


def cargar_casos(ruta=CASOS):
    """JSONL del dataset; valida lo que el bench necesita para no mentir."""
    casos = []
    for numero, linea in enumerate(Path(ruta).read_text(encoding="utf-8").splitlines(), 1):
        if not linea.strip():
            continue
        caso = json.loads(linea)
        for campo in ("id", "grupo", "esperado", "pregunta"):
            if not caso.get(campo):
                raise ValueError(f"{ruta}:{numero}: falta {campo}")
        if caso["grupo"] not in GRUPOS:
            raise ValueError(f"{ruta}:{numero}: grupo inválido {caso['grupo']!r}")
        if caso["esperado"] not in ESPERADOS:
            raise ValueError(f"{ruta}:{numero}: esperado inválido {caso['esperado']!r}")
        casos.append(caso)
    ids = [caso["id"] for caso in casos]
    if len(ids) != len(set(ids)):
        raise ValueError(f"{ruta}: ids repetidos")
    return casos


def medir(casos, voto_local, arbitro):
    """Cascada de producción: el voto local cierra si es confiable; si duda,
    arbitra. `voto_local(pregunta)` devuelve (resp, conf, confiable, causa) o
    None si no hay checkpoint; `arbitro(pregunta)` devuelve herramientas|directo.
    Acepta callables para que los tests sean puros (sin Laya ni red)."""
    filas = []
    for caso in casos:
        inicio = time.perf_counter()
        local = conf = None
        confiable, causa = False, "sin voto local"
        try:
            resultado = voto_local(caso["pregunta"])
            if resultado is not None:
                local, conf, confiable, causa = resultado
        except Exception as e:  # noqa: BLE001 (el bench mide degradación, no revienta)
            causa = f"voto local falló ({type(e).__name__})"
        if confiable:
            final, origen_decision = local, "voto"
        else:
            final, origen_decision = arbitro(caso["pregunta"]), "arbitro"
        filas.append({
            "id": caso["id"],
            "grupo": caso["grupo"],
            "esperado": caso["esperado"],
            "local": local,
            "conf": None if conf is None else round(float(conf), 4),
            "confiable": bool(confiable),
            "causa": causa,
            "final": final,
            "origen_decision": origen_decision,
            "cubierto_por": caso.get("cubierto_por", ""),
            "acierto": final == caso["esperado"],
            "falso_directo": caso["esperado"] == "herramientas" and final == "directo",
            "seg": round(time.perf_counter() - inicio, 3),
        })
    return filas


def resumen(filas):
    """Métricas del bench: acierto por grupo, seguridad, ahorro y latencia."""
    por_grupo = {}
    for grupo in GRUPOS:
        del_grupo = [f for f in filas if f["grupo"] == grupo]
        if del_grupo:
            por_grupo[grupo] = {
                "aciertos": sum(1 for f in del_grupo if f["acierto"]),
                "casos": len(del_grupo),
            }
    return {
        "casos": len(filas),
        "aciertos": sum(1 for f in filas if f["acierto"]),
        "por_grupo": por_grupo,
        "cobertura_local": sum(1 for f in filas if f["origen_decision"] == "voto"),
        "arbitro": sum(1 for f in filas if f["origen_decision"] == "arbitro"),
        "falsos_directos": [f["id"] for f in filas if f["falso_directo"]],
        "falsos_directos_producto": [f["id"] for f in filas
                                     if f["falso_directo"] and not f["cubierto_por"]],
        "cubiertos_por_regla": [f["id"] for f in filas
                                if f["falso_directo"] and f["cubierto_por"]],
        "errores": [{"id": f["id"], "esperado": f["esperado"], "final": f["final"]}
                    for f in filas if not f["acierto"]],
        "seg_mediana": round(statistics.median([f["seg"] for f in filas]), 3) if filas else 0.0,
        "seg_total": round(sum(f["seg"] for f in filas), 1),
    }


def _voto_local_real():
    """El voto local de producción (checkpoint LAYA_MODEL_VOTO), o None."""
    import nodes
    from utils.laya import disponible, preguntar
    from utils.laya_routing import config_voto, decide_voto

    if not disponible("LAYA_MODEL_VOTO"):
        return None
    config = config_voto()

    def voto_local(pregunta):
        resp, conf = preguntar(
            {"pregunta": str(pregunta)[:1000]}, nodes.PREGUNTA_VOTO,
            setting="LAYA_MODEL_VOTO",
        )["confirma_herramientas"]
        confiable, causa = decide_voto(resp, conf, config)
        return resp, conf, confiable, causa

    return voto_local


def _arbitro_real():
    """El árbitro DeepSeek con el MISMO prompt que producción."""
    import nodes
    from utils.call_llm import call_llm
    from utils.estructura import extraer_yaml

    def arbitro(pregunta):
        crudo = call_llm(nodes.PROMPT_ARBITRO_VOTO.format(pregunta=pregunta))
        return extraer_yaml(crudo).get("veredicto", "herramientas")

    return arbitro


def informe_texto(filas, metricas):
    lineas = [f"== exp/53 bench del voto: {metricas['casos']} casos =="]
    for grupo, datos in metricas["por_grupo"].items():
        lineas.append(f"  {grupo:12}: {datos['aciertos']}/{datos['casos']}")
    lineas.append(
        f"  voto local resolvió {metricas['cobertura_local']}/{metricas['casos']} "
        f"(árbitro {metricas['arbitro']}) · mediana {metricas['seg_mediana']} s/caso"
    )
    if metricas["falsos_directos_producto"]:
        lineas.append(f"  ❌ falsos directos de PRODUCTO: {metricas['falsos_directos_producto']}")
    if metricas["cubiertos_por_regla"]:
        lineas.append(f"  ⚠ voto falla pero lo cubre una regla del router: "
                      f"{metricas['cubiertos_por_regla']}")
    for error in metricas["errores"]:
        marca_error = "⚠" if error["id"] in metricas["cubiertos_por_regla"] else "❌"
        lineas.append(f"  {marca_error} {error['id']}: esperado {error['esperado']}, "
                      f"final {error['final']}")
    for fila in filas:
        marca = "✓" if fila["acierto"] else "❌"
        lineas.append(
            f"    {marca} {fila['id']:4} {fila['grupo']:12} final={fila['final']:12} "
            f"({fila['origen_decision']}, {fila['seg']:.2f}s) {fila['causa']}"
        )
    return "\n".join(lineas)


def main(argv=None):
    parser = argparse.ArgumentParser(prog="bench_voto", description="exp/53: bench del voto")
    parser.add_argument("--casos", default=str(CASOS), help="dataset JSONL de casos")
    parser.add_argument("--salida", default=None, help="JSON de resultados")
    args = parser.parse_args(argv)
    casos = cargar_casos(args.casos)
    voto_local = _voto_local_real()
    if voto_local is None:
        print("[bench] LAYA_MODEL_VOTO no disponible: todo lo arbitra DeepSeek")
        voto_local = lambda _p: None  # noqa: E731
    filas = medir(casos, voto_local, _arbitro_real())
    metricas = resumen(filas)
    print(informe_texto(filas, metricas))
    destino = Path(args.salida or (RAIZ / "salidas" / "evals" /
                                   f"bench_voto_{datetime.now():%Y%m%d}.json"))
    destino.parent.mkdir(parents=True, exist_ok=True)
    destino.write_text(json.dumps({
        "fecha": datetime.now().isoformat(timespec="seconds"),
        "dataset": str(Path(args.casos).relative_to(RAIZ)),
        "metricas": metricas,
        "filas": filas,
    }, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"artefacto: {destino.relative_to(RAIZ)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
