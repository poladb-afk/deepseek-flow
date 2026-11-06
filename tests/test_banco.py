"""El banco de conversación: escenarios válidos y marcadores que matchean.

El banco corre contra el chat REAL (LLM incluido), así que acá solo se
fija lo determinista: todo escenario que haya en banco/escenarios/ parsea,
tiene ids únicos y políticas HITL conocidas; y los marcadores que el banco
cuenta matchean las líneas que el chat imprime de verdad (el formato de
esas líneas es el contrato — si cambia, el banco queda ciego y este test
es el que lo avisa)."""
import re
from pathlib import Path

import pytest

from banco.banco import MARCADORES, cargar_escenario, contar_marcadores
from utils.aprobaciones import COMANDOS_PROHIBIDOS, RUTAS_PROHIBIDAS, Pedido, dentro_de_scope, por_scope
from utils.conductor import escribir_scope, leer_decisiones, limpiar

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
        "skill": "  [skill] revision activo — revisión de código",
        "hitl_prompt": "¿Escribir? → /x/hola.txt (s/n): ",
        "compaccion": "[compacción] zona fría: 30 mensajes → resumen; ventana caliente: 11",
        "sintaxis": "contenido\n⚠ SINTAXIS: invalid syntax (roto.py, line 1)",
        "veto_l8": "  [laya] search_files está vetada (dos fallos) → elige DeepSeek",
        "veto_denylist": ("  [denylist] comando vetado (daño irreversible): "
                          "no se ejecutó ni se pidió aprobación"),
        "recuperacion": "  [recuperación] tool calls llegaron como texto (DSML) → ejecutando",
        "sanitizado": "  [sanitizado] la respuesta descarriló a un prompt ajeno: cortada",
        "ronda": "  ⚙ ronda 3/8",
        "auto_lectura": "── run_command [auto: solo-lectura] ──",
        "interrumpido": "[interrumpido] generación cortada por el usuario",
        "dsml_ignorado": "  [DSML] tool calls como texto: IGNORADOS (presupuesto agotado)",
        "prefetch": "  [pre-fetch] /tmp/proyecto/flow.py",
    }
    for nombre, patron in MARCADORES.items():
        assert re.search(patron, muestras[nombre]), f"marcador {nombre} no matchea su línea real"
    conteo = contar_marcadores("\n".join(muestras.values()))
    assert conteo["ronda"] == 1
    assert conteo["veto_l8"] == 1 and conteo["veto_denylist"] == 1
    # la segunda línea real de veto L8 (formato `[L8] X vetada`) es positiva
    assert re.search(MARCADORES["veto_l8"], "  [L8] db_schema vetada y elegida igual → finish")
    # Fixtures NEGATIVOS reales: las dos líneas contaminantes medidas hoy NO
    # matchean ninguna clave de veto (el viejo `PROHIBID|[Vv]etad` sí lo hacía).
    contaminantes = (
        "+        if PROHIBIDOS.search(limpia):",
        "vetado por la denylist del driver; lo documenta la auditoría)",
    )
    for linea in contaminantes:
        c = contar_marcadores(linea)
        assert not c.get("veto_l8") and not c.get("veto_denylist"), f"falso positivo en {linea!r}"
    # Fixture NEGATIVO del skill: el TEMPLATE del código fuente (con
    # {exec_res.id}) lo cita la prosa de un agente que lee nodes.py y NO cuenta.
    template = '  [skill] {exec_res.id} activo — {exec_res.descripcion}'
    assert not re.search(MARCADORES["skill"], template), \
        "el template del código fuente no debe matchear (prosa ecoada)"


def test_limpiar_quita_ansi_y_crlf():
    assert limpiar("\x1b[32mok\x1b[0m\r\n") == "ok\n"


# scope HITL (exp/11) — desde la auditoría 2026-10-26 el pedido llega como
# DATO (utils.aprobaciones.Pedido) y se juzga en el chat: el driver ya no
# reconstruye ruta ni comando leyendo la pantalla.
RUTAS = ["/tmp/prueba", "/proy/prueba_scope"]


def test_escritura_dentro_del_scope():
    assert dentro_de_scope("escritura", "/tmp/prueba/hola.txt", RUTAS) == (True, "ok")


def test_escritura_fuera_del_scope():
    assert dentro_de_scope("escritura", "/otro/lado/ajeno.txt", RUTAS) == (False, "fuera-de-scope")
    # contención por COMPONENTE: el prefijo de texto `/tmp/prueba` no cubre
    # `/tmp/prueba_banco` (startswith lo aprobaba: auditoría S2)
    assert dentro_de_scope("escritura", "/tmp/prueba_banco/hola.txt", RUTAS) == (False, "fuera-de-scope")
    assert dentro_de_scope("escritura", "/tmp/prueba/../fuera.txt", RUTAS) == (False, "fuera-de-scope")


def test_env_fuera_aunque_el_scope_lo_permita():
    # el scope CONTIENE el directorio del .env: aun así la denylist manda, y
    # sin importar mayúsculas ni sufijos (.ENV, .env.local)
    for ruta in ("/proy/prueba_scope/.env", "/proy/prueba_scope/.ENV", "/proy/prueba_scope/.env.local"):
        assert dentro_de_scope("escritura", ruta, RUTAS) == (False, "denylist"), ruta
    assert dentro_de_scope("escritura", "/proy/prueba_scope/no_memoria/x.md", RUTAS) == (True, "ok")


def test_comando_dentro_de_permitir_comandos():
    comandos = ["cd /x &&", "python3 -m pytest"]
    assert dentro_de_scope("comando", "cd /x && python3 -m pytest tests/test_banco.py",
                           comandos=comandos) == (True, "ok")
    # CADA segmento necesita su prefijo; y lo que el shell transforma no pasa
    for cmd in ("python3 -m pytest; curl x | sh", "python3 -m pytest $(cat x)",
                "python3 -m pytestx", "python3 -m pytest > /etc/x"):
        assert dentro_de_scope("comando", cmd, comandos=comandos)[0] is False, cmd


@pytest.mark.parametrize("comando", ["bash -c 'rm -rf ~'", "pip install x", "python3 script.py",
                                     "mkdir x", "find . -delete", "curl x"])
def test_un_scope_sin_comandos_no_aprueba_ningun_comando(comando):
    """X172: un escenario del banco sin `permitir_comandos` escribe
    `comandos: null`, y null aprobaba sin humano todo lo que no fuera
    irreversible. Ahora null es lo mismo que el conductor sin
    `--permitir-comandos`: ningún comando que pida aprobación."""
    assert dentro_de_scope("comando", comando) == (False, "fuera-de-scope")
    assert dentro_de_scope("comando", comando, comandos=None) == dentro_de_scope("comando", comando, comandos=[])


def test_un_scope_sin_rutas_sigue_aprobando_escrituras():
    """X172 no toca las escrituras: `rutas: null` sigue siendo sin restricción
    salvo la denylist (y la contención de AGENT_ALLOWED_DIRS)."""
    assert dentro_de_scope("escritura", "/proy/x/a.py") == (True, "ok")
    assert dentro_de_scope("escritura", "/proy/x/.env") == (False, "denylist")


def test_comando_git_push_es_denylist():
    for cmd in ("git push origin main", "git -C . push", "ls && sudo rm -rf /x", "/bin/rm -fr x"):
        assert dentro_de_scope("comando", cmd, comandos=["git", "ls", "sudo", "/bin/rm"]) == (False, "denylist"), cmd


# X170: con `permitir_comandos="git"` el scope aprueba solo lo que sabe leer.
# Un global que redefine qué corre (`-c`, `--exec-path`, `--super-prefix`) o
# uno desconocido es fuera-de-scope: antes los seis daban `(True, "ok")`.
@pytest.mark.parametrize("comando", [
    "git --exec-path /x stash drop",
    "git --super-prefix x stash drop",
    "git --exec-path /x reset --hard",
    "git --frobnicate x reset --hard",
    "git -c alias.r='reset --hard' r",
    "git -c core.pager=cat log",
])
def test_el_scope_no_aprueba_un_git_que_no_puede_leer(comando):
    assert dentro_de_scope("comando", comando, comandos=["git"]) == (False, "fuera-de-scope")


@pytest.mark.parametrize("comando", [
    "git stash list", "git stash pop", "git stash show -p",
    "git branch -d merged", "git branch nueva", "git -C . status",
])
def test_el_scope_sigue_aprobando_el_git_reversible_y_legible(comando):
    assert dentro_de_scope("comando", comando, comandos=["git"]) == (True, "ok")


@pytest.mark.parametrize("comando", ["git stash drop", "git -C . reset --hard", "git branch -D vieja"])
def test_lo_destructivo_legible_sigue_en_la_denylist_del_scope(comando):
    assert dentro_de_scope("comando", comando, comandos=["git"]) == (False, "denylist")


# X171: en un scope con prefijos, un segmento se aprueba solo si su base está
# declarada y sus opciones están en la lista blanca. Las siete medidas del
# roadmapper daban `(True, "ok")` sobre `9dabed2`; el chat no cambia.
@pytest.mark.parametrize("base, comando", [
    ("bash", "bash -c 'rm -rf ~'"),
    ("find", "find . -delete"),
    ("pytest", "pytest -p evil"),
    ("sort", "sort --compress-program=./payload.sh x"),
    ("ruff", "ruff check --fix ."),
    ("tail", "tail -f log.txt"),
    ("sed", "sed -i s/a/b/ x.py"),  # base sin lista, no solo una opción rara
])
def test_el_scope_no_aprueba_bases_ni_opciones_no_declaradas(base, comando):
    assert dentro_de_scope("comando", comando, comandos=[base]) == (False, "fuera-de-scope")


@pytest.mark.parametrize("base, comando", [
    ("cd", "cd /tmp"),
    ("python3", "python3 salidas/x/run.py hola"),
    ("python3 -m pytest", "python3 -m pytest -q tests/test_banco.py"),
    ("pytest", "pytest -q tests/"),
    ("ruff", "ruff check ."),
    ("python3 -m ruff", "python3 -m ruff check ."),
    ("git", "git status"),
    ("git", "git stash show -p"),
    ("git", "git branch -d merged"),
    ("git", "git branch -a"),
    ("git", "git -C . status"),
    ("git", "git restore --staged a.py"),
    ("ls", "ls -la"),
    ("cat", "cat x.py"),
    ("mkdir", "mkdir -p salida"),
    ("rm", "rm -r .ruff_cache"),
])
def test_el_scope_sigue_aprobando_lo_declarado(base, comando):
    assert dentro_de_scope("comando", comando, comandos=[base]) == (True, "ok")


def test_el_chat_no_cambia_con_la_lista_blanca_del_scope():
    """X171 es solo para el scope sin humano: el humano ve la misma fricción."""
    from utils.policy import clasificar

    for comando in ("ls -la", "git log --oneline", "find . -name '*.py'", "pytest -q",
                    "ruff check .", "cat x.py"):
        assert clasificar(comando) == "auto", comando
    for comando in ("bash -c 'rm -rf ~'", "find . -delete", "pytest -p evil", "tail -f log.txt",
                    "ruff check --fix .", "rm -r x", "git branch -a"):
        assert clasificar(comando) == "preguntar", comando


def test_extraccion_del_comando_ignora_banner_y_explicacion(tmp_path):
    """Ya no hay extracción: el aprobador decide sobre `objetivo`, nunca sobre
    el prompt que lee el humano. Un prompt inocente no lava un push."""
    scope = escribir_scope(tmp_path / "s.json", comandos=["git"], eventos=tmp_path / "e.jsonl")
    d = por_scope(Pedido("¿Ejecutar?", "↳ explicación", "comando", "git push origin main",
                         "confirmar_doble"), scope)
    assert d.ok is False and d.motivo == "denylist"
    assert leer_decisiones(tmp_path / "e.jsonl")[0]["objetivo"] == "git push origin main"


def test_prompt_no_parseable_sigue_el_flujo(tmp_path):
    """Un pedido de tipo desconocido NO se aprueba (antes: dentro=True), pero
    el flujo sigue: el rechazo vuelve como Decision y queda registrado."""
    assert dentro_de_scope("desconocido", "x") == (False, "tipo-desconocido")
    scope = escribir_scope(tmp_path / "s.json", eventos=tmp_path / "e.jsonl")
    assert por_scope(Pedido("¿Querés seguir?"), scope).ok is False
    assert len(leer_decisiones(tmp_path / "e.jsonl")) == 1


def test_denylist_dura_es_la_declarada():
    assert {".env", ".git", "memoria"} <= set(RUTAS_PROHIBIDAS)
    assert {"git push", "rm -rf", "rm -fr"} <= set(COMANDOS_PROHIBIDOS)


def test_el_scope_cubre_el_prompt_de_edit_file_de_exp98(tmp_path, monkeypatch):
    """El hueco de exp/99 era de PARSEO (el sufijo `(2 hunks, …)` no matcheaba):
    ahora edit_file entrega la ruta resuelta como dato y el scope la juzga."""
    import modules.coding as coding

    (tmp_path / "src").mkdir()
    archivo = tmp_path / "src" / "main.py"
    archivo.write_text("a = 1\n", encoding="utf-8")
    monkeypatch.setenv("AGENT_ALLOWED_DIRS", str(tmp_path))
    eventos = tmp_path / "e.jsonl"
    for permitido, ok in ((tmp_path / "docs", False), (tmp_path / "src", True)):
        monkeypatch.setenv("HITL_SCOPE", str(escribir_scope(tmp_path / "s.json", [str(permitido)],
                                                             eventos=eventos)))
        coding.edit_file(str(archivo), "a = 1", "a = 2")
        fila = leer_decisiones(eventos)[-1]
        assert fila["tipo"] == "escritura" and fila["objetivo"] == str(archivo)
        assert fila["ok"] is ok
    assert archivo.read_text(encoding="utf-8") == "a = 2\n"


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


def test_max_hitl_por_turno_se_valida_y_llega_al_dict(tmp_path):
    """Fix 11: knob declarativo `max_hitl` por turno. Un entero válido pasa
    y queda en el dict del escenario; los inválidos levantan ValueError."""
    import yaml as _yaml

    def _cargar(max_hitl):
        ruta = tmp_path / "esc.yaml"
        turno = {"id": "t1", "linea": "hola", "timeout": 5}
        if max_hitl is not None:
            turno["max_hitl"] = max_hitl
        ruta.write_text(_yaml.safe_dump(
            {"id": "esc", "turnos": [turno]}, allow_unicode=True), encoding="utf-8")
        return cargar_escenario(ruta)

    esc = _cargar(3)
    assert esc["turnos"][0]["max_hitl"] == 3
    for malo in ("0", "x", -1):
        try:
            _cargar(malo)
        except ValueError:
            pass
        else:
            raise AssertionError(f"max_hitl={malo!r} debería levantar ValueError")


def test_env_del_chat_aisla_la_memoria_y_marca_procedencia(monkeypatch):
    """exp/71: una corrida de banco no puede tocar la biblioteca curada del
    usuario (antes, con MEMORIA=0, el respaldo de compacción igual escribía
    `memoria/`). La memoria del banco va a `salidas/banco/memoria` y sus
    logs (preguntas, riesgo) a `salidas/banco/`: el tráfico
    sintético no cae en los de producción (X93)."""
    from banco.banco import RAIZ, _env_del_chat

    monkeypatch.delenv("MEMORIA", raising=False)
    monkeypatch.delenv("MEMORIA_DIR", raising=False)
    env = _env_del_chat({"MAX_TOOL_ROUNDS": "3"})
    assert env["PREGUNTAS_ARCHIVO"] == str(RAIZ / "salidas" / "banco" / "preguntas.jsonl")
    assert env["RIESGO_ARCHIVO"] == str(RAIZ / "salidas" / "banco" / "riesgo.jsonl")
    assert env["MEMORIA"] == "0"
    assert env["MAX_TOOL_ROUNDS"] == "3"  # el env del escenario sigue mandando
    assert env["MEMORIA_DIR"] == str(RAIZ / "salidas" / "banco" / "memoria")

    # exp/71b: heredar el entorno del operador NO devuelve la biblioteca a
    # producción; solo el `env:` del escenario puede pisar el default.
    monkeypatch.setenv("MEMORIA", "1")
    monkeypatch.setenv("MEMORIA_DIR", str(RAIZ / "memoria"))
    env = _env_del_chat()
    assert env["MEMORIA"] == "0"
    assert env["MEMORIA_DIR"] == str(RAIZ / "salidas" / "banco" / "memoria")


# tarea hecha que no se cumple sin trabajar (cierre de H1, 2026-10-26) ----------

def test_ningun_escenario_se_pasa_sin_hacer_nada():
    """banco-1 y banco-3 daban OK aunque el modelo no hiciera nada (sus fixes
    ya estaban aplicados y `verificar: pytest` pasaba igual). Los chequeos de
    transcript/salida de cada turno tienen que FALLAR con un turno vacío."""
    from banco.banco import verificar_turno

    for ruta in ESCENARIOS.glob("*.yaml"):
        for turno in cargar_escenario(ruta)["turnos"]:
            chequeos = [c for c in turno.get("verificar") or () if next(iter(c)) in ("transcript", "salida")]
            if chequeos:
                assert verificar_turno(chequeos, ""), f"{ruta.name}:{turno['id']} pasa con un turno vacío"


def test_un_verificar_que_no_mide_trabajo_invalida_el_escenario(tmp_path):
    import yaml

    ruta = tmp_path / "e.yaml"
    ruta.write_text(yaml.safe_dump({"id": "e", "turnos": [
        {"id": "t", "linea": "x", "verificar": [{"comando": "true"}, {"no_existe": "y"}]}]}),
        encoding="utf-8")
    try:
        cargar_escenario(ruta)
    except ValueError as e:
        assert "sin hacer nada" in str(e)
    else:
        raise AssertionError("un verificar sin chequeo de trabajo debería ser inválido")


def test_salida_compara_contra_el_repo_vivo(tmp_path, monkeypatch):
    """`salida` calcula la respuesta con un comando: el escenario no guarda
    números que envejezcan, y la respuesta tiene que venir marcada."""
    import banco.banco as bb

    monkeypatch.setattr(bb, "RAIZ", tmp_path)
    (tmp_path / "a.txt").write_text("1\n2\n3\n", encoding="utf-8")
    chequeo = [{"salida": "wc -l < a.txt"}]
    assert bb.verificar_turno(chequeo, "listo.\nRESPUESTA: **3**") == []
    assert bb.verificar_turno(chequeo, "RESPUESTA: 33")              # otro número
    assert bb.verificar_turno(chequeo, "son 3 líneas")               # sin marca
    assert bb.verificar_turno([{"salida": "false"}], "RESPUESTA: 3")  # el comando no corre


def test_friccion_auto_tiene_respuestas_calculables():
    """Cada turno de friccion-auto calcula su respuesta contra el repo vivo:
    si un archivo se mueve, el escenario se rompe acá y no en la corrida."""
    from banco.banco import _respuesta_esperada

    esc = cargar_escenario(ESCENARIOS / "friccion-auto.yaml")
    turnos = [t for t in esc["turnos"] if t.get("verificar")]
    assert len(turnos) >= 5
    for turno in turnos:
        (tipo, comando), = turno["verificar"][0].items()
        assert tipo == "salida" and _respuesta_esperada(comando), turno["id"]


def test_ningun_escenario_setea_un_env_que_el_harness_no_lee():
    """X112: un `env:` que nadie lee no mide nada y nadie se entera (los brazos
    de PROMPT_FABLE y PROMPT_FORMA quedaron así). Cada clave tiene que leerla
    algún código del repo, con los mismos lectores que el ratchet."""
    from conftest import RAIZ

    import ratchet

    leidos = set()
    for ruta in RAIZ.rglob("*.py"):
        rel = ruta.relative_to(RAIZ).as_posix()
        if rel.startswith(("tests/", "docs/", "salidas/", ".", "banco/fable/escenarios/")):
            continue
        texto = ruta.read_text(encoding="utf-8", errors="replace")
        for patron in ratchet.LECTORES_SETTINGS:
            leidos |= set(re.findall(patron, texto))
    inertes = {}
    for ruta in sorted((RAIZ / "banco" / "escenarios").glob("*.yaml")):
        for clave in cargar_escenario(ruta).get("env") or {}:
            if clave not in leidos:
                inertes.setdefault(clave, []).append(ruta.name)
    assert not inertes, f"escenarios con env que ningún código lee: {inertes}"
