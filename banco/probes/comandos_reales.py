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

`--casos` escribe la otra mitad del instrumento de la 5a: UN caso sintético
por entrada de la política (cada prefijo, cada flag peligroso con cada
prefijo de su base, cada envoltorio con cada opción, cada opción global de
git), derivado mecánicamente de las listas, con el nivel y el texto de la
política del árbol donde se corre. Así ninguna entrada queda sin ejercitar
aunque el tráfico real no la use.

Uso:
    python3 banco/probes/comandos_reales.py [--salidas salidas] [--fixture | --casos]
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
CASOS = RAIZ / "banco" / "fixtures" / "policy_casos_entrada.jsonl"
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


def _base_efectiva(prefijo):
    return policy._BASES_MODULO.get(tuple(prefijo[:3]), prefijo[0])


def casos_por_entrada():
    """Los comandos sintéticos, uno o más por entrada de la política (lee
    los nombres internos de `utils.policy`, que la 5a conserva). Ordenados
    y sin repetidos: mismo árbol ⇒ mismo archivo, byte a byte."""
    auto = list(policy._WHITELIST_PREFIJOS)
    todos = auto + list(policy._NEGRA_PREGUNTAR) + list(policy._NEGRA_DOBLE) \
        + [p for p, _ in policy._EXPLICACIONES]
    casos = set()
    for prefijo in todos:
        texto = " ".join(prefijo)
        casos |= {texto, f"{texto} x", f"sudo {texto} x", f"ls && {texto} x", f"/bin/{texto} x"}
    for base, flags in policy._FLAGS_PELIGROSOS.items():
        for prefijo in (p for p in auto if _base_efectiva(p) == base):
            texto = " ".join(prefijo)
            for flag in flags:
                casos |= {f"{texto} {flag} x", f"{texto} {flag}=x"}
                if len(flag) == 2:
                    casos.add(f"{texto} -q{flag[1]} x")
    for envoltorio in sorted(policy._ENVOLTORIOS):
        casos |= {f"{envoltorio} rm -rf x", f"{envoltorio} ls"}
        for opcion in policy._OPCIONES_CON_VALOR.get(envoltorio, ()):
            casos |= {f"{envoltorio} {opcion} v rm -rf x", f"{envoltorio} {opcion} v ls"}
    for opcion in sorted(policy._GIT_GLOBAL_CON_VALOR):
        casos |= {f"git {opcion} v push", f"git {opcion} v status"}
    return [{"comando": c, "nivel": policy.clasificar(c), "explicacion": policy.explicar(c)}
            for c in sorted(casos)]


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
    modo = parser.add_mutually_exclusive_group()
    modo.add_argument("--fixture", action="store_true", help=f"escribe la foto versionable en {FIXTURE}")
    modo.add_argument("--casos", action="store_true", help=f"escribe un caso por entrada en {CASOS}")
    args = parser.parse_args(argv)
    if args.casos:
        casos = casos_por_entrada()
        CASOS.write_text("".join(json.dumps(c, ensure_ascii=False) + "\n" for c in casos), encoding="utf-8")
        print(f"casos por entrada: {len(casos)} → {CASOS}")
        return 0
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
