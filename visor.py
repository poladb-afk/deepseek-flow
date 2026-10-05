"""Visor del trace: `.runs/*.jsonl` convertido en HTML inspeccionable.

Cada corrida del harness deja un evento por nodo ({ts, nodo, accion, seg}
— utils/tracing.py); esta pieza los lee y escribe al lado del jsonl un
HTML autocontenido (sin CDN, sin dependencias): cronología con barras de
duración, resumen por nodo y el recorrido con las vueltas de bucle
(cada `ElegirSiguiente→EjecutarPaso` del supervisor es una vuelta).

Código puro: el mismo jsonl siempre produce el mismo HTML.

Uso:
    python3 main.py visor [trace.jsonl ...]   # sin args: el más reciente
"""
import argparse
import html
import json
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path

RUNS = Path(__file__).resolve().parent / ".runs"
COLORES = ["#7aa2f7", "#9ece6a", "#e0af68", "#f7768e", "#bb9af7", "#7dcfff",
           "#ff9e64", "#73daca"]


def leer_eventos(ruta):
    eventos = []
    with open(ruta, encoding="utf-8") as f:
        for linea in f:
            if linea.strip():
                eventos.append(json.loads(linea))
    return eventos


def mas_reciente():
    if not RUNS.is_dir():
        raise SystemExit(f"ERROR: no hay carpeta {RUNS}")
    # de más nuevo a más viejo, saltando vacíos (main.py abre el propio
    # antes de despachar el subcomando: esa corrida siempre queda en 0)
    for traza in sorted(RUNS.glob("*.jsonl"), reverse=True):
        if traza.stat().st_size > 0:
            return traza
    raise SystemExit(f"ERROR: sin trazas con contenido en {RUNS}")


def generar(ruta):
    eventos = leer_eventos(ruta)
    if not eventos:
        raise SystemExit(f"ERROR: trace vacío: {ruta}")
    t0 = eventos[0]["ts"]
    total = eventos[-1]["ts"] - t0 + eventos[-1].get("seg", 0)
    color_de = defaultdict(lambda: COLORES[len(color_de) % len(COLORES)])

    por_nodo = Counter()
    seg_por_nodo = defaultdict(float)
    for e in eventos:
        por_nodo[e["nodo"]] += 1
        seg_por_nodo[e["nodo"]] += e.get("seg", 0)

    filas = []
    for e in eventos:
        rel = e["ts"] - t0
        seg = e.get("seg", 0)
        ancho = max(1, round(seg / total * 100)) if total else 1
        filas.append(f"""
<tr>
  <td class="num">{rel:8.2f}s</td>
  <td><span class="chip" style="background:{color_de[e['nodo']]}">{html.escape(e['nodo'])}</span></td>
  <td class="accion">{html.escape(str(e['accion']))}</td>
  <td class="num">{seg:6.2f}s</td>
  <td><div class="barra" style="width:{ancho}%"></div></td>
</tr>""")

    seg_total = sum(seg_por_nodo.values()) or 1.0
    resumen = "".join(f"""
<tr>
  <td><span class="chip" style="background:{color_de[n]}">{html.escape(n)}</span></td>
  <td class="num">{veces}</td>
  <td class="num">{seg_por_nodo[n]:.2f}s</td>
  <td class="num">{seg_por_nodo[n] / seg_total * 100:.0f}%</td>
</tr>""" for n, veces in por_nodo.most_common())

    chips = []
    for e in eventos:
        chips.append(f'<span class="chip" style="background:{color_de[e["nodo"]]}">{html.escape(e["nodo"])}</span>')
    recorrido = '<span class="flecha">→</span>'.join(chips)

    fecha = datetime.fromtimestamp(t0).strftime("%Y-%m-%d %H:%M:%S")
    destino = ruta.with_suffix(".html")
    destino.write_text(f"""<!doctype html>
<html lang="es"><head><meta charset="utf-8">
<title>trace — {ruta.name}</title>
<style>
 body {{ font-family: ui-monospace, monospace; background: #1a1b26; color: #c0caf5; margin: 2rem; }}
 h1 {{ font-size: 1.1rem; color: #7aa2f7; }}
 .meta {{ color: #565f89; margin-bottom: 1.5rem; }}
 table {{ border-collapse: collapse; width: 100%; margin-bottom: 2rem; }}
 td, th {{ padding: 3px 10px; text-align: left; border-bottom: 1px solid #292e42; font-size: 0.85rem; }}
 .num {{ text-align: right; color: #9aa5ce; white-space: nowrap; }}
 .chip {{ display: inline-block; padding: 1px 8px; border-radius: 9px; color: #1a1b26; font-size: 0.78rem; white-space: nowrap; }}
 .flecha {{ color: #565f89; margin: 0 2px; }}
 .accion {{ color: #9ece6a; }}
 .barra {{ height: 10px; background: #7aa2f7; border-radius: 4px; min-width: 2px; }}
 .recorrido {{ line-height: 2.4; margin-bottom: 2rem; }}
 h2 {{ font-size: 0.95rem; color: #e0af68; }}
</style></head><body>
<h1>trace — {html.escape(ruta.name)}</h1>
<p class="meta">{fecha} · {len(eventos)} eventos · {total:.1f}s en total ·
{len(por_nodo)} nodos distintos</p>
<h2>Recorrido (las vueltas del bucle, en orden)</h2>
<div class="recorrido">{recorrido}</div>
<h2>Resumen por nodo</h2>
<table><tr><th>nodo</th><th>veces</th><th>tiempo</th><th>%</th></tr>{resumen}</table>
<h2>Cronología</h2>
<table><tr><th>t</th><th>nodo</th><th>acción</th><th>duró</th><th style="width:30%"></th></tr>{"".join(filas)}</table>
</body></html>""", encoding="utf-8")
    return destino


def main(argv=None):
    parser = argparse.ArgumentParser(prog="visor", description="HTML inspeccionable de un trace .runs/*.jsonl")
    parser.add_argument("trazas", nargs="*", help="traces a visualizar (default: el más reciente de .runs/)")
    args = parser.parse_args(argv)
    rutas = [Path(t) for t in args.trazas] or [mas_reciente()]
    for ruta in rutas:
        if not ruta.is_file():
            raise SystemExit(f"ERROR: no existe: {ruta}")
        destino = generar(ruta)
        print(f"✓ {destino}")


if __name__ == "__main__":
    main()
