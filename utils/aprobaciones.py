"""Historial de aprobaciones HITL de la sesión (mesa 8, UX).

Registro EN MEMORIA (buffer de UX) de cada aprobación humana que el chat
pidió: qué se pedía (write/edit/run), si se aprobó y con qué nivel de riesgo.
Además emite una TRAZA COMPACTA (tipo/nivel/decisión, SIN contenido) vía
utils.tracing cuando el tracing está activo: eso alimenta el tablero de
fricción. Sirve para dos cosas:

- Que el usuario pueda ver, en cualquier momento, qué se aprobó en la
  sesión (`resumen()`), sin depender de scrollear el historial del chat.
- Dejar señal barata para auditar la fricción (cuántas aprobaciones, cuántas
  rechazadas) sin leer trazas.

Contrato: solo registra; nunca decide, nunca pide input, nunca rompe. Si algo
falla al registrar, se ignora (es UX, no contención)."""

import json
import time
from pathlib import Path
from typing import NamedTuple

from utils.policy import IRREVERSIBLES, PREGUNTAR, irreversible, opaco, segmentos

_MAX = 200  # tope del buffer circular: una sesión larga no crece sin techo
_eventos = []  # lista de dicts: {tipo, resumen, nivel, decision}


def registrar(tipo, resumen, decision, nivel=PREGUNTAR):
    """Registra UNA aprobación. `tipo` ∈ {write_file, edit_file, run_command};
    `decision` booleana (aprobado/rechazado); `nivel` el de policy (auto/
    preguntar/confirmar_doble). Best-effort: nunca lanza."""
    try:
        _eventos.append({
            "tipo": str(tipo),
            "resumen": " ".join(str(resumen).split())[:200],  # una línea, acotado
            "decision": bool(decision),
            "nivel": str(nivel),
        })
        if len(_eventos) > _MAX:
            del _eventos[0]
        # Traza compacta para el tablero: tipo/nivel/decisión (seg queda 0:
        # registrar no mide duración), SIN resumen (F4: la tasa real de
        # rechazo HITL no era medible).
        from utils import tracing

        tracing.evento_hitl(str(tipo), str(nivel), bool(decision))
    except Exception:  # noqa: BLE001  (UX: un fallo acá jamás corta la acción)
        pass


def resumen():
    """Texto de las aprobaciones de la sesión, en orden cronológico. Lista
    vacía → mensaje claro. Determinista sobre el buffer actual."""
    if not _eventos:
        return "No hay aprobaciones en esta sesión."
    aprobadas = sum(1 for e in _eventos if e["decision"])
    lineas = [f"Aprobaciones HITL de la sesión: {len(_eventos)} "
              f"({aprobadas} aprobadas, {len(_eventos) - aprobadas} rechazadas)"]
    for e in _eventos:
        marca = "✓" if e["decision"] else "✗"
        nivel = "" if e["nivel"] == PREGUNTAR else f" [{e['nivel']}]"
        lineas.append(f"  {marca}{nivel} {e['tipo']}: {e['resumen']}")
    return "\n".join(lineas)


def eventos():
    """Copia de los eventos registrados (para tests e inspección)."""
    return [dict(e) for e in _eventos]


def limpiar():
    """Vacía el buffer (arranque de sesión o tests)."""
    _eventos.clear()


YES = {"s", "si", "sí", "y", "yes"}
NO = {"n", "no"}


class Decision(NamedTuple):
    """La respuesta del HITL: `ok` decide, `motivo` es lo que el humano
    explicó después del n. Verdadera solo si `ok` (contrato bool de siempre)."""

    ok: bool
    motivo: str = ""

    def __bool__(self):
        return self.ok


class Pedido(NamedTuple):
    """Lo que se pide aprobar, como DATO. Quien aprueba decide sobre los
    campos, no releyendo el prompt: el conductor de exp/99 lo reconstruía de
    la pantalla y aprobaba `git push` sin ver la doble confirmación (auditoría
    2026-10-26, S1). `prompt` y `cuerpo` son para el humano."""

    prompt: str
    cuerpo: str = ""
    tipo: str = ""       # escritura | comando | delegar
    objetivo: str = ""   # ruta resuelta o comando completo
    nivel: str = PREGUNTAR


# Lo que ningún scope aprueba. Las rutas se comparan por COMPONENTE y sin
# mayúsculas (el substring dejaba pasar `/repo/.ENV`); un nombre con punto
# también cuenta como sufijo (`prod.env`, `x.git`), uno sin punto no
# (`no_memoria` es otra carpeta). Los comandos son la misma lista doble de la
# policy, normalizada (sudo, /bin/rm, git -C).
RUTAS_PROHIBIDAS = (".env", ".git", "memoria")
COMANDOS_PROHIBIDOS = IRREVERSIBLES


def ruta_prohibida(ruta):
    partes = [p.lower() for p in Path(ruta).parts]
    return any(p == n or p.startswith(n + ".") or (n.startswith(".") and p.endswith(n))
               for p in partes for n in RUTAS_PROHIBIDAS)


def dentro_de_scope(tipo, objetivo, rutas=None, comandos=None):
    """(dentro, motivo) de un pedido contra un scope. PURA.

    `None` = sin restricción salvo las prohibiciones. Las rutas se comparan
    por contención real (`/repo/docs` no cubre `/repo/docs_evil`); un comando
    entra solo si CADA segmento empieza con un prefijo permitido y el shell no
    lo transforma (`pytest; curl x | sh` no es `pytest`). Un tipo que no es
    escritura ni comando no se aprueba: lo que no se sabe leer, no pasa."""
    if tipo == "escritura":
        if ruta_prohibida(objetivo):
            return False, "denylist"
        destino = Path(objetivo).resolve()
        if rutas is not None and not any(destino.is_relative_to(Path(r).resolve()) for r in rutas):
            return False, "fuera-de-scope"
        return True, "ok"
    if tipo != "comando":
        return False, "tipo-desconocido"
    if irreversible(objetivo):
        return False, "denylist"
    if comandos is None:
        return True, "ok"
    # "cd {RAIZ} &&" de un escenario es el prefijo de UN segmento: `cd {RAIZ}`
    prefijos = [segmentos(p)[0].split() for p in comandos if segmentos(p)]
    cubierto = all(any(s.split()[:len(p)] == p for p in prefijos) for s in segmentos(objetivo))
    if opaco(objetivo) or not cubierto:
        return False, "fuera-de-scope"
    return True, "ok"


def por_scope(pedido, ruta_scope):
    """El aprobador sin humano (banco, conductor): decide por los DATOS del
    pedido contra el scope del archivo y deja cada decisión en su JSONL. El
    archivo se relee en cada pedido: el driver cambia la política por turno
    reescribiéndolo. El tope se cuenta en el JSONL, así sobrevive a un resume."""
    ruta_scope = Path(ruta_scope)
    scope = json.loads(ruta_scope.read_text(encoding="utf-8"))
    eventos = Path(scope.get("eventos") or ruta_scope.with_suffix(".jsonl"))
    previas = len(eventos.read_text(encoding="utf-8").splitlines()) if eventos.exists() else 0
    if not scope.get("aprobar", True):
        ok, motivo = False, "el-escenario-rechaza"
    elif previas >= int(scope.get("max", 12)):
        ok, motivo = False, "tope"
    else:
        ok, motivo = dentro_de_scope(pedido.tipo, pedido.objetivo,
                                     scope.get("rutas"), scope.get("comandos"))
    eventos.parent.mkdir(parents=True, exist_ok=True)
    with eventos.open("a", encoding="utf-8") as f:
        f.write(json.dumps({"ts": round(time.time(), 3), "tipo": pedido.tipo,
                            "objetivo": pedido.objetivo[:300], "nivel": pedido.nivel,
                            "ok": ok, "motivo": motivo}, ensure_ascii=False) + "\n")
    # misma forma que la terminal (el transcript y el marcador hitl_prompt la
    # cuentan), con la respuesta ya puesta: no queda un (s/n) pendiente
    print(f"{pedido.prompt} (s/n): {'s' if ok else 'n ' + motivo} [scope]", flush=True)
    return Decision(ok, "" if ok else motivo)


def pedir_aprobacion(pedido):
    """La Decision de un Pedido: contra el scope con HITL_SCOPE (banco y
    conductor), por navegador con HITL_WEB=1, si no por terminal.

    En la terminal `n <motivo>` viaja como motivo; s/si/y ignoran el resto.
    Nunca lanza: EOF, Ctrl+C o un HITL_SCOPE ilegible son RECHAZO. El HITL
    web devuelve SU Decision (exp/102: también puede traer motivo)."""
    from utils import hitl_web
    from utils.call_llm import _setting

    scope = _setting("HITL_SCOPE", "")
    if scope:
        try:
            return por_scope(pedido, scope)
        except (OSError, ValueError, TypeError):
            return Decision(False, "scope-invalido")
    if _setting("HITL_WEB", "0") == "1":
        return hitl_web.aprobar(pedido.prompt, pedido.cuerpo)
    try:
        answer = input(f"{pedido.prompt} (s/n): ").strip()
    except (EOFError, KeyboardInterrupt):
        print()
        return Decision(False)
    # la MINÚSCULA es solo para la primera palabra: el motivo viaja con su
    # casing original (un "no toques Policy.py" no llega como "policy.py")
    primera, _, resto = answer.partition(" ")
    if primera.lower() in YES:
        return Decision(True)
    if primera.lower() in NO:
        return Decision(False, resto.strip())
    return Decision(False)
