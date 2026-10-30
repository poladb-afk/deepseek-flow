"""Los comandos reales de `run_command` (pre-registro de la fase 5a).

READ-ONLY, sin LLM ni red. La traza (`.runs`) no guarda argumentos; los dos
lectores honestos son:

- los checkpoints de thread (`salidas/**/threads/*.jsonl`): guardan el
  `shared` completo, así que los `tool_calls` de `run_command` traen el
  comando — incluidos los `auto`, que no pasan por el HITL;
- el log de riesgo (`salidas/riesgo.jsonl`): cada HITL de comando con su
  `origen`. Trunca a 200 caracteres: un comando de exactamente 200 se
  descarta (no se sabe si está entero).

Cada comando único se clasifica con la política de HOY (`utils.policy`):
`clasificar` y `explicar`. Eso es la FOTO contra la que la 5a tiene que dar
0 diferencias.

Privacidad: la raíz del repo pasa a `{RAIZ}` y el home a `{HOME}` (los
placeholders del banco); `/home/<usuario>` y `/Users/<usuario>` ajenos, a
`{HOME}`. Un comando que parezca llevar un secreto se descarta y se cuenta.
La salida por default va a `salidas/` (ignorado); `--fixture` escribe la foto
que se versiona, para revisarla a mano ANTES de commitear.

Uso:
    python3 banco/probes/comandos_reales.py [--salidas salidas] [--fixture]
"""
import argparse
import json
import re
import sys
from collections import Counter
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(RAIZ))

from utils import policy  # noqa: E402

HOME = Path.home()
FIXTURE = RAIZ / "banco" / "fixtures" / "policy_comandos.jsonl"
LARGO_MAX = 500
TRUNCADO_RIESGO = 200
_SECRETO = re.compile(r"(?i)sk-[a-z0-9]{8}|api[_-]?key|token\s*=|passw(or)?d|secret|bearer\s")
_HOME_AJENO = re.compile(r"/(?:home|Users)/[^/\s'\"]+")


def anonimizar(comando, raiz=RAIZ, home=HOME):
    """Las rutas personales a placeholders. PURA."""
    texto = str(comando).replace(str(raiz), "{RAIZ}").replace(str(home), "{HOME}")
    return _HOME_AJENO.sub("{HOME}", texto)


def de_threads(lineas):
    """Los comandos de `run_command` en checkpoints ya parseados. PURA."""
    for linea in lineas:
        for m in (linea.get("shared") or {}).get("messages") or []:
            for tc in m.get("tool_calls") or [] if isinstance(m, dict) else []:
                funcion = tc.get("function") or {}
                if funcion.get("name") != "run_command":
                    continue
                try:
                    comando = json.loads(funcion.get("arguments") or "{}").get("command")
                except (json.JSONDecodeError, AttributeError):
                    continue
                if isinstance(comando, str) and comando.strip():
                    yield comando


def de_riesgo(lineas):
    """Los comandos del log de riesgo, sin los que pueden estar truncados. PURA."""
    for fila in lineas:
        comando = fila.get("comando")
        if isinstance(comando, str) and comando.strip() and len(comando) < TRUNCADO_RIESGO:
            yield comando


def _jsonl(ruta):
    try:
        texto = Path(ruta).read_text(encoding="utf-8")
    except OSError:
        return []
    filas = []
    for cruda in texto.splitlines():
        try:
            filas.append(json.loads(cruda))
        except json.JSONDecodeError:
            continue
    return [f for f in filas if isinstance(f, dict)]


def foto(comandos, raiz=RAIZ, home=HOME):
    """[{comando, nivel, explicacion, veces}] ordenado, y lo descartado. PURA
    salvo la política (determinista)."""
    veces, descartes = Counter(), Counter()
    for crudo in comandos:
        if _SECRETO.search(crudo):
            descartes["posible_secreto"] += 1
            continue
        if len(crudo) > LARGO_MAX:
            descartes["largo"] += 1
            continue
        veces[anonimizar(crudo.strip(), raiz, home)] += 1
    filas = [{"comando": c, "nivel": policy.clasificar(c), "explicacion": policy.explicar(c), "veces": n}
             for c, n in sorted(veces.items())]
    return filas, dict(descartes)


def resumen(filas, descartes):
    por_nivel = Counter(f["nivel"] for f in filas)
    primeros = Counter((f["comando"].split() or ["?"])[0] for f in filas)
    lineas = [f"comandos únicos: {len(filas)} (usos: {sum(f['veces'] for f in filas)})",
              "por nivel: " + ", ".join(f"{k} {v}" for k, v in sorted(por_nivel.items())),
              "primer token: " + ", ".join(f"{k} {v}" for k, v in primeros.most_common(15)),
              "descartados: " + (", ".join(f"{k} {v}" for k, v in descartes.items()) or "ninguno")]
    return "\n".join(lineas)


def main(argv=None):
    parser = argparse.ArgumentParser(prog="comandos_reales", description="fase 5a: la foto de la política")
    parser.add_argument("--salidas", default=str(RAIZ / "salidas"))
    parser.add_argument("--fixture", action="store_true", help=f"escribe la foto versionable en {FIXTURE}")
    args = parser.parse_args(argv)
    salidas = Path(args.salidas)
    comandos = []
    for ruta in sorted(salidas.rglob("*.jsonl")):
        if ruta.parent.name == "threads":
            comandos += list(de_threads(_jsonl(ruta)))
    comandos += list(de_riesgo(_jsonl(salidas / "riesgo.jsonl")))
    filas, descartes = foto(comandos)
    destino = FIXTURE if args.fixture else salidas / "evals" / "comandos_reales.jsonl"
    destino.parent.mkdir(parents=True, exist_ok=True)
    campos = ("comando", "nivel", "explicacion") if args.fixture else ("comando", "nivel", "explicacion", "veces")
    destino.write_text("".join(json.dumps({k: f[k] for k in campos}, ensure_ascii=False) + "\n" for f in filas),
                       encoding="utf-8")
    print(resumen(filas, descartes))
    print(f"→ {destino}" + ("  (revisalo a mano antes de commitear)" if args.fixture else ""))
    return 0


if __name__ == "__main__":
    sys.exit(main())
