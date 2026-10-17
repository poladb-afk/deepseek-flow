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

from utils.policy import PREGUNTAR

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
        # Traza compacta para el tablero: tipo/nivel/decisión/segundos, SIN
        # resumen (F4: la tasa real de rechazo HITL no era medible).
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


def pedir_aprobacion(prompt, cuerpo=""):
    """El s/n del HITL: por navegador con HITL_WEB=1, si no por terminal.

    Unificada acá (PR 3 del plan de orden): modules/coding.py y
    modules/escritura.py tenían el MISMO cuerpo copiado. cuerpo es el contexto
    que viaja al HITL web. Nunca lanza: EOF o Ctrl+C es RECHAZO."""
    from utils import hitl_web
    from utils.call_llm import _setting

    if _setting("HITL_WEB", "0") == "1":
        return hitl_web.aprobar(prompt, cuerpo)
    try:
        answer = input(f"{prompt} (s/n): ").strip().lower()
    except (EOFError, KeyboardInterrupt):
        print()
        return False
    return answer in YES
