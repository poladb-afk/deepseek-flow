"""exp/53 — bench permanente de decisiones del VOTO (Mesa 1, ítem 7).

El dataset `banco/voto_casos.jsonl` fija los casos que importan de la cascada:

- `correccion`: donde Laya-router dice directo y DEBE corregirse a herramientas
  (imperativos/capacidades; los falso-directo medidos el 2026-10-05 y exp/46).
- `directo`: control inverso — conocimiento o creatividad que NO debe pedir
  tools ("escribime un haiku", la trampa inversa del router).
- `herramientas`: casos claros con tools, para que el voto no pierda recall.

Mide DOS capas, en este orden (exp/54 añadió la segunda):

1. **capa voto** (sin reglas): voto local LAYA_MODEL_VOTO decide si es
   confiable; la banda incierta la arbitra DeepSeek con el prompt de
   `nodes.PROMPT_ARBITRO_VOTO`.
2. **capa producto** (con las reglas duras del `LayaRouter` en enforce):
   `regla_temporal` (exp/46) y `regla_imperativo_capacidad` (exp/54) mandan a
   herramientas ANTES del modelo.

Reporta por grupo: aciertos, falsos directos de producto, cobertura local
(llamadas al árbitro ahorradas) y latencia. Es instrumento de SEÑAL, no gate.
Texto sintético del repo (sin datos de usuario): el dataset se versiona y el
bench es reproducible. Uso:
    python3 banco/probes/bench_voto.py [--casos ruta] [--sin-reglas]
"""
import argparse
import hashlib
import json
import statistics
import sys
import time
from datetime import datetime
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(RAIZ))  # los imports del harness (nodes, utils) viven en la raíz

from utils.laya_routing import regla_imperativo_capacidad, regla_temporal  # noqa: E402

CASOS = RAIZ / "banco" / "voto_casos.jsonl"
CONTROL = RAIZ / "banco" / "voto_control.jsonl"
CONTROL_BASELINE = RAIZ / "banco" / "voto_control_baseline.json"
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


def regla_dura(pregunta):
    """La regla dura del `LayaRouter` en enforce (misma fuente que producción)."""
    if regla_temporal(pregunta):
        return "regla:temporal"
    if regla_imperativo_capacidad(pregunta):
        return "regla:imperativo"
    return ""


def medir(casos, voto_local, arbitro, regla=regla_dura):
    """Mide las dos capas. `voto_local(pregunta)` devuelve (resp, conf,
    confiable, causa) o None; `arbitro(pregunta)` y `regla(pregunta)` son
    callables para que los tests sean puros (sin Laya ni red)."""
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
            final_voto, origen_voto = local, "voto"
        else:
            final_voto, origen_voto = arbitro(caso["pregunta"]), "arbitro"
        regla_aplicada = regla(caso["pregunta"]) if regla else ""
        if regla_aplicada:
            final, origen_decision = "herramientas", regla_aplicada
        else:
            final, origen_decision = final_voto, origen_voto
        falso_directo = caso["esperado"] == "herramientas" and final == "directo"
        falso_directo_voto = caso["esperado"] == "herramientas" and final_voto == "directo"
        filas.append({
            "id": caso["id"],
            "grupo": caso["grupo"],
            "esperado": caso["esperado"],
            "local": local,
            "conf": None if conf is None else round(float(conf), 4),
            "confiable": bool(confiable),
            "causa": causa,
            "final_voto": final_voto,
            "origen_voto": origen_voto,
            "regla": regla_aplicada,
            "final": final,
            "origen_decision": origen_decision,
            "acierto": final == caso["esperado"],
            "acierto_voto": final_voto == caso["esperado"],
            "falso_directo": falso_directo,
            "falso_directo_voto": falso_directo_voto,
            "cubierto_por": caso.get("cubierto_por", ""),
            "cubierto_por_regla": falso_directo_voto and not falso_directo,
            "seg": round(time.perf_counter() - inicio, 3),
        })
    return filas


def _por_grupo(filas, clave_acierto):
    salida = {}
    for grupo in GRUPOS:
        del_grupo = [f for f in filas if f["grupo"] == grupo]
        if del_grupo:
            salida[grupo] = {
                "aciertos": sum(1 for f in del_grupo if f[clave_acierto]),
                "casos": len(del_grupo),
            }
    return salida


def resumen(filas):
    """Métricas de las dos capas: producto (final) y voto (sin reglas)."""
    return {
        "casos": len(filas),
        "aciertos": sum(1 for f in filas if f["acierto"]),
        "por_grupo": _por_grupo(filas, "acierto"),
        "aciertos_voto": sum(1 for f in filas if f["acierto_voto"]),
        "por_grupo_voto": _por_grupo(filas, "acierto_voto"),
        "falsos_directos": [f["id"] for f in filas if f["falso_directo"]],
        "falsos_directos_voto": [f["id"] for f in filas if f["falso_directo_voto"]],
        "cubiertos_por_regla": [f["id"] for f in filas if f["cubierto_por_regla"]],
        "reglas_disparadas": sum(1 for f in filas if f["regla"]),
        "cobertura_local": sum(1 for f in filas if f["origen_voto"] == "voto"),
        "arbitro": sum(1 for f in filas if f["origen_voto"] == "arbitro"),
        "errores": [{"id": f["id"], "esperado": f["esperado"], "final": f["final"]}
                    for f in filas if not f["acierto"]],
        "seg_mediana": round(statistics.median([f["seg"] for f in filas]), 3) if filas else 0.0,
        "seg_total": round(sum(f["seg"] for f in filas), 1),
    }


DIRECTOS_MIN_H3G2 = 6  # exp/53: el voto acertó 6/6 en el grupo directo


def veredicto_h3g2(filas, voto_local_disponible):
    """El criterio de banco/specs/h3g2_voto_solo.md, sin retoques. PURA.

    Mide al voto donde DECIDE: cada fila del bench es el caso "Laya propuso
    directo" (la cascada corre siempre), así que la capa voto es la única red.
    Las reglas se pueden borrar si (1) corrió el checkpoint real, (2) el voto
    no da NINGÚN falso directo y (3) no lo logra diciendo siempre herramientas
    (el grupo directo sigue como en exp/53)."""
    directos = [f for f in filas if f["grupo"] == "directo"]
    condiciones = {
        "checkpoint": bool(voto_local_disponible),
        "seguridad": not any(f["falso_directo_voto"] for f in filas),
        "ahorro": sum(1 for f in directos if f["acierto_voto"]) >= DIRECTOS_MIN_H3G2,
    }
    gana = bool(filas) and all(condiciones.values())
    return {"condiciones": condiciones, "gana": gana,
            "falsos_directos_voto": [f["id"] for f in filas if f["falso_directo_voto"]],
            "decision": "el voto solo alcanza: se pueden borrar las reglas (aplicar h3g_borrar_reglas.patch)"
            if gana else "las reglas se quedan"}


CONTROL_HERRAMIENTAS_MIN = 10  # imperativos + recencia, escritos antes de entrenar
CONTROL_DIRECTOS_MIN = 4       # trampas inversas nuevas ("escribime un haiku")


def huella(ruta):
    """sha256 del archivo: ata el baseline a ESTE control, byte a byte."""
    return hashlib.sha256(Path(ruta).read_bytes()).hexdigest()


def baseline_control(filas_control, huella_control, checkpoint):
    """Lo que el voto de PRODUCCIÓN falla en el control, registrado antes de
    entrenar (enmienda del 2026-10-27). PURA."""
    return {
        "control_sha256": huella_control,
        "checkpoint": checkpoint,
        "n": len(filas_control),
        "falsos_directos": [f["id"] for f in filas_control if f["falso_directo_voto"]],
        "trampas_mal": [f["id"] for f in filas_control
                        if f["esperado"] == "directo" and not f["acierto_voto"]],
    }


def veredicto_reentreno(filas, filas_control, n_fugas, voto_local_disponible,
                        baseline=None, huella_control=None):
    """El criterio de banco/specs/voto_reentreno.md, sin retoques. PURA.

    Un checkpoint nuevo de router_voto se promueve si pasa H3-G2 en el bench
    Y lo mismo fuera de muestra (el control), con el entrenamiento limpio de
    fugas, y si el control DISCRIMINA: el voto de producción, medido antes de
    entrenar sobre este mismo control (misma huella), daba al menos un falso
    directo. Un control que el voto viejo ya pasaba no distingue aprender de
    memorizar. Sin anti-fuga o sin baseline, no hay veredicto."""
    h3g2 = veredicto_h3g2(filas, voto_local_disponible)
    herramientas = [f for f in filas_control if f["esperado"] == "herramientas"]
    directos = [f for f in filas_control if f["esperado"] == "directo"]
    tamano = len(herramientas) >= CONTROL_HERRAMIENTAS_MIN and len(directos) >= CONTROL_DIRECTOS_MIN
    condiciones = {
        "h3g2": h3g2["gana"],
        "control_tamano": tamano,
        "control_seguridad": tamano and not any(f["falso_directo_voto"] for f in filas_control),
        "control_ahorro": tamano and all(f["acierto_voto"] for f in directos),
        "antifuga": n_fugas == 0,
        "control_discrimina": baseline is not None and baseline.get("control_sha256") == huella_control
        and len(baseline.get("falsos_directos") or []) >= 1,
    }
    completo = n_fugas is not None and baseline is not None
    gana = completo and all(condiciones.values())
    if completo:
        decision = ("se promueve el checkpoint y H3-G2 queda ganado (aplicar el borrado aparcado)"
                    if gana else "no se promueve: el checkpoint de producción sigue igual")
    elif baseline is None:
        decision = "falta el baseline del control (--registrar-baseline con el voto de producción, ANTES de entrenar)"
    else:
        decision = "falta correr el anti-fuga sobre el entrenamiento (--entrenamiento)"
    return {"condiciones": condiciones, "completo": completo, "gana": gana,
            "falsos_directos_control": [f["id"] for f in filas_control if f["falso_directo_voto"]],
            "decision": decision}


def leer_baseline(ruta=CONTROL_BASELINE):
    ruta = Path(ruta)
    return json.loads(ruta.read_text(encoding="utf-8")) if ruta.is_file() else None


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
    lineas.append("  capa voto (sin reglas):")
    for grupo, datos in metricas["por_grupo_voto"].items():
        lineas.append(f"    {grupo:12}: {datos['aciertos']}/{datos['casos']}")
    lineas.append(
        f"    local resolvió {metricas['cobertura_local']}/{metricas['casos']} "
        f"(árbitro {metricas['arbitro']}) · mediana {metricas['seg_mediana']} s/caso"
    )
    lineas.append("  capa producto (con reglas del router):")
    for grupo, datos in metricas["por_grupo"].items():
        lineas.append(f"    {grupo:12}: {datos['aciertos']}/{datos['casos']}")
    lineas.append(f"    reglas disparadas: {metricas['reglas_disparadas']}/{metricas['casos']}")
    if metricas["falsos_directos"]:
        lineas.append(f"  ❌ falsos directos de PRODUCTO: {metricas['falsos_directos']}")
    if metricas["cubiertos_por_regla"]:
        lineas.append(f"  ⚠ el voto solo fallaba acá; la regla lo cubre: "
                      f"{metricas['cubiertos_por_regla']}")
    for error in metricas["errores"]:
        marca = "⚠" if error["id"] in metricas["cubiertos_por_regla"] else "❌"
        lineas.append(f"  {marca} {error['id']}: esperado {error['esperado']}, "
                      f"final {error['final']}")
    for fila in filas:
        marca = "✓" if fila["acierto"] else "❌"
        lineas.append(
            f"    {marca} {fila['id']:4} {fila['grupo']:12} final={fila['final']:12} "
            f"({fila['origen_decision']}, {fila['seg']:.2f}s) "
            f"[voto {fila['final_voto']}] {fila['causa']}"
        )
    return "\n".join(lineas)


def main(argv=None):
    parser = argparse.ArgumentParser(prog="bench_voto", description="exp/53: bench del voto")
    parser.add_argument("--casos", default=str(CASOS), help="dataset JSONL de casos")
    parser.add_argument("--sin-reglas", action="store_true",
                        help="mide solo la capa voto (sin reglas duras del router)")
    parser.add_argument("--sin-voto-local", action="store_true",
                        help="todo lo arbitra DeepSeek (H3-G2 no da veredicto así)")
    parser.add_argument("--control", default=str(CONTROL), help="casos fuera de muestra")
    parser.add_argument("--entrenamiento", default=None,
                        help="JSONL con el que se entrenó el checkpoint (anti-fuga del reentreno)")
    parser.add_argument("--registrar-baseline", action="store_true",
                        help="registra lo que el voto de PRODUCCIÓN falla en el control (antes de entrenar)")
    parser.add_argument("--salida", default=None, help="JSON de resultados")
    args = parser.parse_args(argv)
    casos = cargar_casos(args.casos)
    voto_local = None if args.sin_voto_local else _voto_local_real()
    checkpoint = voto_local is not None
    if voto_local is None:
        print("[bench] LAYA_MODEL_VOTO no disponible: todo lo arbitra DeepSeek")
        voto_local = lambda _p: None  # noqa: E731
    filas = medir(casos, voto_local, _arbitro_real(),
                  regla=None if args.sin_reglas else regla_dura)
    metricas = resumen(filas)
    h3g2 = veredicto_h3g2(filas, checkpoint)
    print(informe_texto(filas, metricas))
    print(f"  H3-G2 (voto solo, banco/specs/h3g2_voto_solo.md): {'GANA' if h3g2['gana'] else 'NO GANA'} "
          f"{h3g2['condiciones']} → {h3g2['decision']}")
    reentreno = None
    control = cargar_casos(args.control) if Path(args.control).is_file() else []
    if args.registrar_baseline:
        if not checkpoint or not control:
            raise SystemExit("ERROR: el baseline necesita el checkpoint de producción (LAYA_MODEL_VOTO) y el control")
        from utils.call_llm import _setting

        filas_control = medir(control, voto_local, _arbitro_real(), regla=None)
        base = baseline_control(filas_control, huella(args.control), _setting("LAYA_MODEL_VOTO", ""))
        CONTROL_BASELINE.write_text(json.dumps(base, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
        print(f"[bench] baseline del control → {CONTROL_BASELINE.relative_to(RAIZ)}: "
              f"falsos directos {base['falsos_directos']}, trampas mal {base['trampas_mal']}")
        if not base["falsos_directos"]:
            print("[bench] ⚠ el control NO discrimina: el voto de producción no falla ninguno. "
                  "Ampliá las familias de c01/c02 antes de entrenar (banco/specs/voto_reentreno.md).")
        return 0
    if control or args.entrenamiento:
        from voto_antifuga import fugas, leer, protegidos

        filas_control = medir(control, voto_local, _arbitro_real(), regla=None)
        n_fugas = len(fugas(leer(args.entrenamiento), protegidos())) if args.entrenamiento else None
        reentreno = veredicto_reentreno(filas, filas_control, n_fugas, checkpoint,
                                        leer_baseline(), huella(args.control) if control else None)
        print(f"  reentreno (banco/specs/voto_reentreno.md): {'GANA' if reentreno['gana'] else 'NO GANA'} "
              f"{reentreno['condiciones']} → {reentreno['decision']}")
    destino = Path(args.salida or (RAIZ / "salidas" / "evals" /
                                   f"bench_voto_{datetime.now():%Y%m%d}.json"))
    destino.parent.mkdir(parents=True, exist_ok=True)
    destino.write_text(json.dumps({
        "fecha": datetime.now().isoformat(timespec="seconds"),
        "dataset": str(Path(args.casos).relative_to(RAIZ)),
        "reglas": not args.sin_reglas,
        "metricas": metricas,
        "h3g2": h3g2,
        "reentreno": reentreno,
        "filas": filas,
    }, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"artefacto: {destino.relative_to(RAIZ)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
