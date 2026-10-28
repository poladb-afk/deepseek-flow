"""exp/52-A — la forma del loop: ¿cuántas rondas de tools se gastan de más?

**Pregunta.** El chat tiene un tope de rondas FIJO (`MAX_TOOL_ROUNDS`) y la
única podada es no-progreso por repetición idéntica. Las trazas `.runs` guardan
el NOMBRE de cada tool (`evento_tool` → `nodo=<tool>`, `acción=ok/error`) pero
no sus argumentos; alcanza para medir la FORMA del loop y una novedad
aproximada por nombre de tool: una ronda "no agrega novedad" si ninguna tool
que llamó es la primera vez que aparece en la pregunta.

**Criterio PRE-REGISTRADO para exp/52-B (antes de ver el artefacto):** una
regla de corte es candidata si recorta **≥20% de las rondas de la cola**
(ciclos con ≥5 rondas) **sin afectar los ciclos de ≤3 rondas**; la calidad de
la respuesta se valida después en replay offline y en el banco, jamás con esta
sonda. Si ningún cap ni regla estructural recorta eso, el presupuesto fijo no
es el problema y se documenta el negativo.

Código puro y determinista (sin LLM, sin red). Uso:
    python3 banco/probes/rondas.py [--dir .runs]
"""
import argparse
import json
import math
import statistics
import sys
from datetime import datetime
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent.parent


def leer_sesion(ruta):
    """Eventos de una traza; las líneas ilegibles se saltan."""
    eventos = []
    try:
        for linea in Path(ruta).read_text(encoding="utf-8").splitlines():
            if linea.strip():
                try:
                    eventos.append(json.loads(linea))
                except json.JSONDecodeError:
                    continue
    except OSError:
        pass
    return eventos


def _es_tool(nodo, accion):
    """Heurística de traza vieja: `evento_tool` usa nodo=<tool>, acción=ok/error
    y las tools son snake_case; los nodos de flujo, CamelCase."""
    return (isinstance(nodo, str) and nodo == nodo.lower()
            and accion in ("ok", "error") and nodo not in ("ok", "error"))


def rondas_sin_novedad(ciclo):
    """Cantidad de rondas que no estrenaron NINGUNA tool (novedad por nombre).

    Aproximación declarada: la traza no guarda argumentos, así que una segunda
    lectura del MISMO archivo cuenta como novedad (misma tool, args distintos).
    """
    vistas, sin_novedad = set(), 0
    for nombres in ciclo.get("tools_por_ronda", []):
        nuevos = [n for n in nombres if n not in vistas]
        if nombres and not nuevos:
            sin_novedad += 1
        vistas.update(nuevos)
    return sin_novedad


def simular_corte_novedad(ciclos_, k=2, min_rondas=3):
    """Counterfactual de la regla estructural: cortar tras `k` rondas
    consecutivas sin novedad (con un mínimo de rondas para no tocar cortos)."""
    recortadas = afectados = toca_cortos = 0
    for ciclo in ciclos_:
        if ciclo["rondas"] <= min_rondas:
            continue
        vistas = set()
        racha = 0
        corte_en = None
        for i, nombres in enumerate(ciclo.get("tools_por_ronda", [])):
            nuevos = [n for n in nombres if n not in vistas]
            vistas.update(nuevos)
            racha = 0 if nuevos else racha + 1
            if racha >= k:
                corte_en = i
                break
        if corte_en is None:
            continue
        afectados += 1
        recortadas += ciclo["rondas"] - (corte_en + 1)
    return {"k": k, "rondas_recortadas": recortadas, "ciclos_afectados": afectados,
            "toca_cortos": toca_cortos}


def es_sesion_chat(eventos):
    """La sesión contiene el flujo del chat (GetQuestion es su entrada)."""
    return any(evento.get("nodo") == "GetQuestion" for evento in eventos)


def ciclos(eventos):
    """Agrupa los eventos en CICLOS por pregunta (GetQuestion → answer/exit).

    Devuelve por ciclo: rondas de tools (AgentStep/accion=tool), si respondió,
    tiempo de agente (seg de AgentStep+ExecuteTools) y cantidad de eventos.
    Los flujos anidados (informe, debate…) corren dentro de una ronda y no
    abren ciclo propio: la pregunta del usuario sigue siendo la unidad.
    """
    salida = []
    actual = None
    for evento in eventos:
        nodo = evento.get("nodo")
        accion = evento.get("accion")
        if nodo == "GetQuestion":
            if actual is not None:
                salida.append(actual)
                actual = None
            if accion == "continue":
                actual = {"rondas": 0, "respondio": False, "seg_agente": 0.0,
                          "eventos": 0, "tools_por_ronda": []}
            continue
        if actual is None:
            continue
        actual["eventos"] += 1
        if nodo in ("AgentStep", "Cierre"):
            # X96: Cierre es la última llamada (la respuesta del turno que
            # agotó el presupuesto): sin esto quedaba como "sin responder"
            actual["seg_agente"] += float(evento.get("seg") or 0.0)
            if accion == "tool":
                actual["rondas"] += 1
                actual["tools_por_ronda"].append([])
            elif accion == "answer":
                actual["respondio"] = True
        elif nodo == "ExecuteTools":
            actual["seg_agente"] += float(evento.get("seg") or 0.0)
        elif _es_tool(nodo, accion) and actual["tools_por_ronda"]:
            actual["tools_por_ronda"][-1].append(nodo)
    if actual is not None:
        salida.append(actual)
    return salida


def resumen(ciclos_):
    """Estadísticas de la muestra (rondas por ciclo, cola larga, tiempo)."""
    rondas = [c["rondas"] for c in ciclos_]
    n = len(rondas)
    tiempos = [c["seg_agente"] for c in ciclos_]
    cola = [r for r in rondas if r >= 5]
    return {
        "ciclos": n,
        "con_tools": sum(1 for r in rondas if r > 0),
        "directos": sum(1 for r in rondas if r == 0),
        "rondas_totales": sum(rondas),
        "rondas_cola": sum(cola),
        "ciclos_cola": len(cola),
        "p50": statistics.median(rondas) if rondas else 0,
        "p90": sorted(rondas)[math.ceil(len(rondas) * 0.9) - 1] if rondas else 0,
        "max": max(rondas) if rondas else 0,
        "sin_responder": sum(1 for c in ciclos_ if not c["respondio"]),
        "seg_total": round(sum(tiempos), 1),
        "seg_cola": round(sum(c["seg_agente"] for c in ciclos_ if c["rondas"] >= 5), 1),
        "seg_mediana": round(statistics.median(tiempos), 2) if tiempos else 0.0,
        "ciclos_cap_8": sum(1 for r in rondas if r > 8),
    }


def simular_cap(ciclos_, cap):
    """Counterfactual: cuántas rondas y ciclos tocaría un tope fijo `cap`.

    Es un techo artificial: NO dice si la respuesta habría sido buena — solo
    el tamaño del recorte (la calidad se mide en exp/52-B con replay/banco).
    """
    recortadas = sum(max(0, c["rondas"] - cap) for c in ciclos_)
    afectados = sum(1 for c in ciclos_ if c["rondas"] > cap)
    toca_cortos = sum(1 for c in ciclos_ if c["rondas"] <= 3 and c["rondas"] > cap)
    return {
        "cap": cap,
        "rondas_recortadas": recortadas,
        "ciclos_afectados": afectados,
        "pct_ciclos": (afectados / len(ciclos_) * 100) if ciclos_ else 0.0,
        "toca_cortos": toca_cortos,
    }


def informe(ciclos_, caps=(2, 3, 4, 5, 6)):
    """El markdown de exp/52-A (determinista)."""
    r = resumen(ciclos_)
    lineas = [
        "# exp/52-A — la forma del loop del chat (offline, solo trazas)",
        "",
        f"**Muestra:** {r['ciclos']} ciclos de pregunta en `.runs` "
        f"({r['con_tools']} con tools, {r['directos']} directos/pre-fetch, "
        f"{r['sin_responder']} sin answer registrado).",
        "",
        "## Distribución de rondas por pregunta",
        f"- total de rondas de tools: **{r['rondas_totales']}**",
        f"- p50 **{r['p50']}** · p90 **{r['p90']}** · max **{r['max']}**",
        f"- cola larga (≥5 rondas): **{r['ciclos_cola']} ciclos** que gastan "
        f"**{r['rondas_cola']} rondas** "
        f"({(r['rondas_cola'] / r['rondas_totales'] * 100) if r['rondas_totales'] else 0:.0f}% del total)",
        f"- tiempo de agente: **{r['seg_total']} s** en total (mediana {r['seg_mediana']} s/pregunta)",
        f"- la cola se lleva **{r['seg_cola']} s** "
        f"({(r['seg_cola'] / r['seg_total'] * 100) if r['seg_total'] else 0:.0f}% del tiempo de agente)",
        "",
        "## Counterfactual de topes fijos (rondas, NO calidad)",
        "| cap | rondas recortadas | % de rondas | ciclos afectados | toca ciclos ≤3 |",
        "|---|---|---|---|---|",
    ]
    for cap in caps:
        s = simular_cap(ciclos_, cap)
        pct = (s["rondas_recortadas"] / r["rondas_totales"] * 100) if r["rondas_totales"] else 0.0
        lineas.append(
            f"| {cap} | {s['rondas_recortadas']} | {pct:.0f}% | "
            f"{s['ciclos_afectados']} ({s['pct_ciclos']:.0f}%) | {s['toca_cortos']} |"
        )
    sin_nov = [rondas_sin_novedad(c) for c in ciclos_]
    lineas += [
        "",
        "## Novedad por NOMBRE de tool (aproximación sin argumentos)",
        f"- rondas sin ninguna tool nueva: **{sum(sin_nov)}** "
        f"de {r['rondas_totales']} ({(sum(sin_nov) / r['rondas_totales'] * 100) if r['rondas_totales'] else 0:.0f}%)",
        f"- ciclos con al menos una ronda sin novedad: "
        f"**{sum(1 for x in sin_nov if x)}/{len(sin_nov)}**",
        "",
        "| regla (cortar tras k rondas sin novedad, mínimo 3) | rondas recortadas | ciclos | toca ≤3 |",
        "|---|---|---|---|",
    ]
    for k in (2, 3):
        sim = simular_corte_novedad(ciclos_, k=k)
        pct = (sim["rondas_recortadas"] / r["rondas_totales"] * 100) if r["rondas_totales"] else 0.0
        lineas.append(f"| k={k} | {sim['rondas_recortadas']} ({pct:.0f}%) | "
                      f"{sim['ciclos_afectados']} | {sim['toca_cortos']} |")
    lineas += [
        "",
        "## Criterio pre-registrado para exp/52-B",
        "Una regla de corte es **candidata** si recorta **≥20% de las rondas de",
        "la cola** (ciclos ≥5) **sin afectar ciclos de ≤3**. El cap fijo es solo",
        "una cota superior: la regla real tiene que ser estructural (p. ej. dejar",
        "de pedir tools cuando la última ronda no agregó información), y su",
        "calidad se valida con replay offline + banco (turnos OK), nunca acá.",
        "",
        f"**Sesgo declarado:** {r['ciclos_cap_8']} ciclos superan las 8 rondas: no son",
        "tráfico normal del chat (el tope default es 8) — vienen de escenarios del",
        "banco que corren con `MAX_TOOL_ROUNDS=25` y de versiones viejas. La cola",
        "está inflada por ellos; el criterio se lee sobre la FORMA, no como costo",
        "de producción.",
        "",
        "**Límite honesto:** la traza no guarda nombres ni argumentos de tools:",
        "no se puede ver repetición de la MISMA tool ni qué ronda agregó datos.",
        "Esa señal exige instrumentar la traza (exp/52-B) o rejugar el contenido.",
    ]
    return "\n".join(lineas) + "\n"


def main(argv=None):
    parser = argparse.ArgumentParser(prog="rondas", description="exp/52-A: forma del loop del chat")
    parser.add_argument("--dir", default=str(RAIZ / ".runs"), help="directorio de trazas")
    parser.add_argument("--salida", default=None, help="markdown de salida")
    args = parser.parse_args(argv)
    todos = []
    sesiones_chat = 0
    for ruta in sorted(Path(args.dir).glob("*.jsonl")):
        eventos = leer_sesion(ruta)
        if not es_sesion_chat(eventos):
            continue
        sesiones_chat += 1
        todos.extend(ciclos(eventos))
    if not todos:
        print("sin ciclos de chat en", args.dir)
        return 1
    texto = informe(todos)
    destino = Path(args.salida or (RAIZ / "salidas" / "evals" /
                                   f"exp52_rondas_{datetime.now():%Y%m%d}.md"))
    destino.parent.mkdir(parents=True, exist_ok=True)
    destino.write_text(texto, encoding="utf-8")
    print(f"sesiones de chat: {sesiones_chat} · ciclos: {len(todos)}")
    print(texto)
    print(f"artefacto: {destino.relative_to(RAIZ)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
