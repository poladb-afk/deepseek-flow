"""El banco de conversación: escenarios válidos y marcadores que matchean.

El banco corre contra el chat REAL (LLM incluido), así que acá solo se
fija lo determinista: todo escenario que haya en banco/escenarios/ parsea,
tiene ids únicos y políticas HITL conocidas; y los marcadores que el banco
cuenta matchean las líneas que el chat imprime de verdad (el formato de
esas líneas es el contrato — si cambia, el banco queda ciego y este test
es el que lo avisa)."""
import re
from pathlib import Path

from banco.banco import DENYLIST_DURA, MARCADORES, cargar_escenario, contar_marcadores, decision_hitl, limpiar

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


# --- scope HITL por path (exp/11) -------------------------------------------
# Fixtures REALES (líneas textuales de transcripts de sesiones anteriores).
PROMPT_ESCRITURA_DENTRO = "¿Escribir? → /tmp/prueba_banco/hola.txt (s/n): "
PROMPT_ESCRITURA_FUERA = "¿Escribir? → /otro/lado/ajeno.txt (s/n): "
PROMPT_ENV = "¿Escribir? → /proy/prueba_scope/.env (s/n): "
PROMPT_COMANDO = "¿Ejecutar? (s/n): "
BUFFER_COMANDO = (
    "── run_command ──\n"
    "↳ correr la suite de tests del banco\n"
    "cd /x && python3 -m pytest tests/test_banco.py\n"
    "¿Ejecutar? (s/n): "
)
BUFFER_COMANDO_PUSH = (
    "── run_command ──\n"
    "↳ subir los cambios\n"
    "git push origin main\n"
    "¿Ejecutar? (s/n): "
)


def test_escritura_dentro_del_scope():
    d = decision_hitl(PROMPT_ESCRITURA_DENTRO, "",
                      permitir=["/tmp/prueba", "/proy/prueba_scope"])
    assert d["tipo"] == "escritura"
    assert d["objetivo"] == "/tmp/prueba_banco/hola.txt"
    assert d["dentro"] is True


def test_escritura_fuera_del_scope():
    d = decision_hitl(PROMPT_ESCRITURA_FUERA, "",
                      permitir=["/tmp/prueba", "/proy/prueba_scope"])
    assert d["tipo"] == "escritura"
    assert d["dentro"] is False
    assert d["motivo"] == "fuera-de-scope"


def test_env_fuera_aunque_el_scope_lo_permita():
    # el prefijo del permitir CONTIENE el directorio del .env: aun así la
    # denylist dura del conductor manda por encima.
    d = decision_hitl(PROMPT_ENV, "", permitir=["/proy/prueba_scope"])
    assert d["dentro"] is False
    assert d["motivo"] == "denylist"


def test_comando_dentro_de_permitir_comandos():
    d = decision_hitl(PROMPT_COMANDO, BUFFER_COMANDO,
                      permitir_comandos=["cd"])
    assert d["tipo"] == "comando"
    assert d["objetivo"] == "cd /x && python3 -m pytest tests/test_banco.py"
    assert d["dentro"] is True


def test_comando_git_push_es_denylist():
    d = decision_hitl(PROMPT_COMANDO, BUFFER_COMANDO_PUSH,
                      permitir_comandos=["git"])
    assert d["tipo"] == "comando"
    assert d["objetivo"] == "git push origin main"
    assert d["dentro"] is False
    assert d["motivo"] == "denylist"


def test_extraccion_del_comando_ignora_banner_y_explicacion():
    buffer = (
        "texto anterior del turno\n"
        "── run_command ──\n"
        "↳ explicación que NO es el comando\n"
        "python3 -m pytest -q\n"
        "¿Ejecutar? (s/n): "
    )
    d = decision_hitl(PROMPT_COMANDO, buffer)
    assert d["objetivo"] == "python3 -m pytest -q"
    assert d["dentro"] is True


def test_prompt_no_parseable_sigue_el_flujo():
    d = decision_hitl("¿Querés seguir? [y/n]: ", "")
    assert d["tipo"] == "desconocido"
    assert d["objetivo"] is None
    assert d["dentro"] is True
    assert d["motivo"] == "no-parseable"


def test_denylist_dura_es_la_declarada():
    assert ".env" in DENYLIST_DURA["rutas"]
    assert ".git/" in DENYLIST_DURA["rutas"]
    assert "memoria/" in DENYLIST_DURA["rutas"]
    assert "git push" in DENYLIST_DURA["comandos"]
    assert "rm -rf" in DENYLIST_DURA["comandos"]
    assert "rm -fr" in DENYLIST_DURA["comandos"]


def test_escenario_sin_scope_sigue_siendo_valido():
    # las claves nuevas son OPCIONALES: los escenarios existentes no las traen
    yamls = list(ESCENARIOS.glob("*.yaml"))
    assert yamls
    for ruta in yamls:
        esc = cargar_escenario(ruta)
        assert "permitir" not in esc or isinstance(esc["permitir"], list)
        assert "permitir_comandos" not in esc or isinstance(esc["permitir_comandos"], list)


def test_escenario_con_env_lo_expone_y_sin_env_sigue_valido(tmp_path):
    """exp/4: `env:` por escenario (p. ej. MAX_TOOL_ROUNDS=40 para sesiones
    de aplicación); sin la clave, compatibilidad total."""
    from banco.banco import cargar_escenario

    esc = cargar_escenario(ESCENARIOS / "exp4-amplio.yaml")
    assert esc["env"] == {"MAX_TOOL_ROUNDS": "40"}
    for ruta in ("smoke.yaml", "exp4-bajo.yaml"):
        cargar_escenario(ESCENARIOS / ruta)  # sin env o con env: ambas válidas
