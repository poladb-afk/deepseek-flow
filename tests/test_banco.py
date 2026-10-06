"""El banco de conversación: escenarios válidos y marcadores que matchean.

El banco corre contra el chat REAL (LLM incluido), así que acá solo se
fija lo determinista: todo escenario que haya en banco/escenarios/ parsea,
tiene ids únicos y políticas HITL conocidas; y los marcadores que el banco
cuenta matchean las líneas que el chat imprime de verdad (el formato de
esas líneas es el contrato — si cambia, el banco queda ciego y este test
es el que lo avisa)."""
import re
from pathlib import Path

from banco.banco import MARCADORES, cargar_escenario, contar_marcadores, limpiar

ESCENARIOS = Path(__file__).resolve().parent.parent / "banco" / "escenarios"


def test_los_escenarios_del_banco_son_validos():
    yamls = list(ESCENARIOS.glob("*.yaml"))
    assert yamls, "banco/escenarios/ vacío: sin escenarios no hay banco"
    for ruta in yamls:
        esc = cargar_escenario(ruta)  # levanta ValueError si algo no cierra
        assert esc["id"] == ruta.stem, f"{ruta}: el id debería ser el nombre del archivo"
        for turno in esc["turnos"]:
            assert "linea" in turno, f"{ruta}: turno sin línea"
            assert turno.get("hitl", "none") in ("none", "s", "n"), f"{ruta}: hitl inválido"
            assert int(turno.get("timeout", 120)) > 0


def test_los_marcadores_matchean_las_lineas_reales_del_chat():
    muestras = {
        "laya": "  [laya] herramientas (conf 0.99)",
        "voto": "  [voto] deepseek dice herramientas → herramientas",
        "hitl_prompt": "¿Escribir? → /x/hola.txt (s/n): ",
        "compaccion": "[compacción] zona fría: 30 mensajes → resumen; ventana caliente: 11",
        "sintaxis": "contenido\n⚠ SINTAXIS: invalid syntax (roto.py, line 1)",
        "veto": "comando PROHIBIDO por la denylist dura",
        "recuperacion": "  [recuperación] tool calls llegaron como texto (DSML) → ejecutando",
        "sanitizado": "  [sanitizado] la respuesta descarriló a un prompt ajeno: cortada",
        "ronda": "  ⚙ ronda 3/8",
        "auto_lectura": "── run_command [auto: solo-lectura] ──",
        "interrumpido": "[interrumpido] generación cortada por el usuario",
    }
    for nombre, patron in MARCADORES.items():
        assert re.search(patron, muestras[nombre]), f"marcador {nombre} no matchea su línea real"
    conteo = contar_marcadores("\n".join(muestras.values()))
    assert conteo["laya"] == 1 and conteo["ronda"] == 1 and conteo["veto"] == 1


def test_limpiar_quita_ansi_y_crlf():
    assert limpiar("\x1b[32mok\x1b[0m\r\n") == "ok\n"
