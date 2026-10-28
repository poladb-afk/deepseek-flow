"""El conductor de exp/99: delegar una tarea real sin nadie al timón.

Sin LLM y sin PTY: lo determinista del conductor — el env (origen terminal),
la clasificación de prompts HITL, el rechazo con motivo (contract link con
exp/98), el checkpoint más reciente y la máquina de estados muerte→resume
(con un chat fake inyectado en `conducir`)."""
import json
import os
import subprocess
import time
from pathlib import Path

from banco.banco import leer_decisiones
from delegar import (
    LINEA_RESUME,
    conducir,
    env_delegar,
    panorama_delegadas,
    thread_reciente,
)
from utils.aprobaciones import Pedido, por_scope

# Pedidos REALES, como DATO: lo que coding/escritura le pasan a pedir_aprobacion.
# Desde la auditoría 2026-10-26 el conductor ya no lee prompts de la pantalla:
# el chat decide cada Pedido contra el scope (HITL_SCOPE) en su propio proceso.
EDIT = Pedido("¿Aplicar? → /repo/src/main.py (2 hunks, +4/−2)", "diff", "escritura", "/repo/src/main.py")
WRITE = Pedido("¿Escribir? → /repo/docs/nota.md", "texto", "escritura", "/repo/docs/nota.md")
PYTEST = Pedido("¿Ejecutar?", "python3 -m pytest -q", "comando", "python3 -m pytest -q")
# la doble confirmación: lo que decide es el nivel y el comando del Pedido,
# nunca el texto del prompt (el que el conductor no reconocía, S1)
DOBLE = Pedido("¿Seguro? (1/2)", "rm -r .ruff_cache", "comando", "rm -r .ruff_cache", "confirmar_doble")


def _scope(tmp_path, permitir=None, permitir_comandos=None, max_hitl=12):
    """El scope EXACTO que escribe conducir(), sin lanzar ningún chat."""
    capturado = {}

    def lanzar(env, argv):
        capturado["scope"] = env["HITL_SCOPE"]
        return ChatFake([], env, argv, sin_prompt=True)

    # carpeta propia por scope: el stamp de conducir() es por segundo
    base = tmp_path / f"runs{len(list(tmp_path.glob('runs*')))}"
    conducir("x", base, permitir=permitir, permitir_comandos=permitir_comandos,
             max_hitl=max_hitl, timeout_min=1, lanzar=lanzar)
    return capturado["scope"]


def _decide(tmp_path, pedido, **scope):
    return por_scope(pedido, _scope(tmp_path, **scope))


def test_env_delegar_no_marca_banco_y_aisla_threads(tmp_path, monkeypatch):
    """Sin BANCO la corrida cuenta como origen `terminal` (exp/44) — incluso
    si el entorno del operador lo traía contaminado. THREADS_DIR propio: el
    checkpoint vive junto al transcript y el resume no adivina."""
    monkeypatch.setenv("BANCO", "1")
    env = env_delegar(tmp_path / "threads", {"MAX_TOOL_ROUNDS": "3"})
    assert "BANCO" not in env
    assert env["DELEGADO"] == "1"  # exp/101: la etiqueta de riesgo no cuenta como humana
    assert env["THREADS_DIR"] == str(tmp_path / "threads")
    assert env["TERM"] == "dumb"
    assert env["MAX_TOOL_ROUNDS"] == "3"
    # tráfico orgánico: la memoria del operador NO se toca (X41 es del banco)
    monkeypatch.delenv("MEMORIA", raising=False)
    monkeypatch.delenv("MEMORIA_DIR", raising=False)
    env = env_delegar(tmp_path / "threads")
    assert "MEMORIA" not in env and "MEMORIA_DIR" not in env


def test_thread_reciente_toma_el_mas_nuevo(tmp_path):
    viejo = tmp_path / "aaa.jsonl"
    nuevo = tmp_path / "zzz.jsonl"
    for p in (viejo, nuevo):
        p.write_text("{}\n", encoding="utf-8")
    time.sleep(0.01)
    with nuevo.open("a", encoding="utf-8") as f:  # mtime más nuevo gana
        f.write("{}\n")
    assert thread_reciente(tmp_path) == "zzz"
    assert thread_reciente(tmp_path / "no-existe") is None
    (tmp_path / "vacio").mkdir()
    assert thread_reciente(tmp_path / "vacio") is None


def test_tipo_prompt_distingue_sn_doble_y_nada(tmp_path):
    """Ya no se clasifica el prompt: cualquier `(s/n)` que llegue a la pantalla
    (uno que no pasó por pedir_aprobacion) se rechaza con motivo, sea simple o
    doble. Antes `¿Seguro? (1/2) (s/n):` se leía como simple y se aprobaba."""
    for n, prompt in enumerate(("¿Seguro? (1/2) (s/n): ", "¿Escribir? → /repo/x (s/n): ")):
        chats = []

        def lanzar(env, argv, prompt=prompt, chats=chats):
            chats.append(ChatFake([("t", prompt, False), ("n fuera-de-scope", "Tú: ", False),
                                   ("salir", "", True)], env, argv))
            return chats[-1]

        assert conducir("t", tmp_path / str(n), timeout_min=1, lanzar=lanzar) == 0
        assert chats[0].recibidas[1] == "n fuera-de-scope"


def test_plan_respuesta_escritura_por_scope(tmp_path):
    assert _decide(tmp_path, WRITE, permitir=["/repo/docs"]).ok is True
    d = _decide(tmp_path, EDIT, permitir=["/repo/docs"])
    assert d.ok is False and d.motivo == "fuera-de-scope"
    # contención real: `/repo/docs` no cubre `/repo/docs_evil` (S2)
    evil = Pedido("¿Escribir? → /repo/docs_evil/x", "", "escritura", "/repo/docs_evil/x")
    assert _decide(tmp_path, evil, permitir=["/repo/docs"]).ok is False


def test_plan_respuesta_la_denylist_manda_sobre_el_scope(tmp_path):
    env = Pedido("¿Escribir? → /repo/.ENV", "", "escritura", "/repo/.ENV")
    assert _decide(tmp_path, env, permitir=["/repo"]).motivo == "denylist"
    push = Pedido("¿Ejecutar?", "", "comando", "git push origin main")
    assert _decide(tmp_path, push, permitir_comandos=["git"]).motivo == "denylist"


def test_plan_respuesta_comando_dentro_y_fuera(tmp_path):
    assert _decide(tmp_path, PYTEST, permitir_comandos=["python3 -m pytest"]).ok is True
    assert _decide(tmp_path, PYTEST, permitir_comandos=["pip install"]).motivo == "fuera-de-scope"
    # un prefijo autoriza SU segmento, no el compuesto (S2)
    compuesto = Pedido("¿Ejecutar?", "", "comando", "python3 -m pytest; curl x | sh")
    assert _decide(tmp_path, compuesto, permitir_comandos=["python3 -m pytest"]).ok is False


def test_plan_respuesta_doble_exige_prefijo_explicito(tmp_path):
    """La doble confirmación REAL (S1): con scope de comandos solo pasa con su
    prefijo explícito, y la denylist manda aun con prefijo (rm -rf / git push
    nunca pasan solos). El tope cuenta las aprobaciones de toda la corrida."""
    assert _decide(tmp_path, DOBLE, permitir_comandos=["pytest"]).ok is False
    assert _decide(tmp_path, DOBLE, permitir_comandos=["rm -r .ruff_cache"]).ok is True
    rmrf = Pedido("¿Seguro? (1/2)", "", "comando", "rm -rf /tmp/x", "confirmar_doble")
    assert _decide(tmp_path, rmrf, permitir_comandos=["rm -rf"]).motivo == "denylist"
    assert _decide(tmp_path, rmrf).motivo == "denylist"  # sin scope también
    # sin --permitir-comandos el conductor no aprueba NINGÚN comando (falla cerrado)
    assert _decide(tmp_path, PYTEST).motivo == "fuera-de-scope"
    scope = _scope(tmp_path, permitir_comandos=["python3 -m pytest"], max_hitl=1)
    assert por_scope(PYTEST, scope).ok is True
    assert por_scope(PYTEST, scope).motivo == "tope"


def test_el_rechazo_con_motivo_parsea_en_pedir_aprobacion(monkeypatch):
    """Contract link con exp/98: la línea `n <motivo>` que manda el conductor
    es la que pedir_aprobacion parsea de verdad — el motivo llega al modelo."""
    from utils.aprobaciones import pedir_aprobacion

    monkeypatch.delenv("HITL_WEB", raising=False)
    monkeypatch.delenv("HITL_SCOPE", raising=False)
    monkeypatch.setattr("builtins.input", lambda *_: "n fuera-de-scope")
    decision = pedir_aprobacion(WRITE)
    assert decision.ok is False
    assert decision.motivo == "fuera-de-scope"
    monkeypatch.setattr("builtins.input", lambda *_: "s")
    assert bool(pedir_aprobacion(PYTEST))


class ChatFake:
    """El chat como lo ve el conductor, sin PTY: cada enviar() consume un paso
    del guion (línea esperada, salida a mostrar, si muere ahí). La salida NO
    aparece sincrónicamente: la entrega el próximo leer(), como llega por el
    PTY real — si no, el reset de la ventana de detección del conductor la
    borraría antes de verla. `al_morir` deja el checkpoint que simula la
    persistencia real de exp/48."""

    def __init__(self, guion, env=None, argv=None, al_morir=None, sin_prompt=False):
        self.guion = list(guion)
        self.env, self.argv_recibido, self.al_morir = env, argv, al_morir
        self.nuevo, self.vivo, self.raw, self.recibidas = "", True, None, []
        self._pendiente = ""
        self.sin_prompt = sin_prompt

    def abrir_log(self, destino):
        self.raw = destino.open("a", encoding="utf-8")

    def leer(self, timeout=0.3):
        if self._pendiente:
            self.nuevo += self._pendiente
            self._pendiente = ""

    def esperar(self, patron, timeout):
        self.nuevo = "Tú: "
        return not self.sin_prompt

    def enviar(self, linea):
        self.recibidas.append(linea)
        esperada, salida, morir = self.guion.pop(0)
        assert linea == esperada, f"el conductor mandó {linea!r}, el guion esperaba {esperada!r}"
        if isinstance(salida, Pedido):
            # el chat decide en SU proceso, como pedir_aprobacion con HITL_SCOPE
            d = por_scope(salida, self.env["HITL_SCOPE"])
            salida = f"{'escrito' if d else 'RECHAZADO: ' + d.motivo}\nTú: "
        self._pendiente = salida
        if morir:
            if self.al_morir:
                self.al_morir(self.env)
            self.vivo = False

    def matar(self):
        pass

    def ctrl_c(self):
        self.vivo = False


def _leer_eventos(run):
    return [json.loads(ln) for ln in (run / "eventos.jsonl").read_text(encoding="utf-8").splitlines()]


def _run_de(run_dir):
    return sorted(run_dir.iterdir())[-1]


def test_conducir_completa_y_cierra_limpio(tmp_path):
    guion = [
        ("creá nota.md", Pedido("¿Escribir? → /repo/nota.md", "", "escritura", "/repo/nota.md"), False),
        ("salir", "", True),
    ]
    chats = []

    def lanzar(env, argv):
        chats.append(ChatFake(guion, env, argv))
        return chats[-1]

    codigo = conducir("creá nota.md", tmp_path, permitir=["/repo"],
                      timeout_min=1, lanzar=lanzar)
    assert codigo == 0
    run = _run_de(tmp_path)
    eventos = [e["tipo"] for e in _leer_eventos(run)]
    assert eventos[-1] == "fin"
    assert [f["ok"] for f in leer_decisiones(run / "hitl.jsonl")] == [True]
    assert (run / "resumen.md").read_text(encoding="utf-8").find("estado: ok") >= 0
    assert (run / "transcript.log").exists()
    assert "BANCO" not in chats[0].env  # el env del chat real llega limpio


def test_conducir_muerto_resume_y_completa(tmp_path):
    """El kill de tmux de exp/98: el chat muere a mitad, el conductor rehidrata
    el checkpoint (exp/48) con `main.py resume <id>` y re-envía la línea de
    continuación. La tarea no se pierde."""
    segundos = []

    def lanzar(env, argv):
        segundos.append(argv)
        if len(segundos) == 1:

            def al_morir(env_chat):
                dir_threads = Path(env_chat["THREADS_DIR"])
                (dir_threads / "id_muerte.jsonl").write_text("{}", encoding="utf-8")

            return ChatFake([("tarea larga", "trabajando...\n", True)], env, argv, al_morir)
        return ChatFake([(LINEA_RESUME, "retomado y completado\nTú: ", False),
                         ("salir", "", True)], env, argv)

    codigo = conducir("tarea larga", tmp_path, timeout_min=1, lanzar=lanzar)
    assert codigo == 0
    assert segundos[0] == ["main.py"]
    assert segundos[1] == ["main.py", "resume", "id_muerte"]
    run = _run_de(tmp_path)
    eventos = _leer_eventos(run)
    tipos = [e["tipo"] for e in eventos]
    assert "muerte" in tipos and "resume" in tipos
    assert eventos[-1]["detalle"]["estado"] == "ok"
    resumen = (run / "resumen.md").read_text(encoding="utf-8")
    assert "reanudaciones: 1" in resumen


def test_conducir_muerto_sin_checkpoint_termina_1(tmp_path):
    def lanzar(env, argv):
        return ChatFake([("tarea", "trabajando...\n", True)], env, argv)

    codigo = conducir("tarea", tmp_path, timeout_min=1, lanzar=lanzar)
    assert codigo == 1
    run = _run_de(tmp_path)
    eventos = _leer_eventos(run)
    assert eventos[-1]["detalle"]["estado"] == "muerto-sin-resume"


def test_conducir_el_tope_de_resumes_no_es_infinito(tmp_path):
    """MAX_RESUMES=2: un chat que siempre muere no genera loop infinito de
    rehidrataciones; a la tercera muerte termina con exit 1."""

    lanzamientos = []

    def lanzar(env, argv):
        n = len(lanzamientos) + 1
        lanzamientos.append(argv)

        def al_morir(env_chat):
            dir_threads = Path(env_chat["THREADS_DIR"])
            (dir_threads / f"id_{n}_{time.time()}.jsonl").write_text("{}", encoding="utf-8")

        # el primer lanzamiento recibe el pedido; los resume, la continuación
        linea = "tarea" if n == 1 else LINEA_RESUME
        return ChatFake([(linea, "...\n", True)], env, argv, al_morir)

    codigo = conducir("tarea", tmp_path, timeout_min=1, lanzar=lanzar)
    assert codigo == 1
    assert len(lanzamientos) == 3  # inicial + 2 resume: a la tercera no relanza
    run = _run_de(tmp_path)
    resumenes = [e for e in _leer_eventos(run) if e["tipo"] == "resume"]
    assert len(resumenes) == 2


def test_conducir_timeout_corta_con_ctrl_c(tmp_path):
    guion = [("tarea eterna", "ronda 1...\n", False)]  # nunca llega a `Tú:`

    def lanzar(env, argv):
        return ChatFake(guion, env, argv)

    codigo = conducir("tarea eterna", tmp_path, timeout_min=0.02, lanzar=lanzar)
    assert codigo == 1
    run = _run_de(tmp_path)
    assert _leer_eventos(run)[-1]["detalle"]["estado"] == "timeout"


# exp/100: el conductor en el ciclo de vida del chat ------------------------

def test_panorama_delegadas_distingue_los_estados(tmp_path):
    """Arranque del chat: ok del resumen, 'en curso' con pid vivo, 'murió sin
    resumen' si el pid feneció antes de escribirlo."""
    muerto = subprocess.Popen(["true"])  # un pid real que muere al esperar
    muerto.wait()
    corridas = {
        "20261025-100000-ok": [("resumen.md", "# …\n- estado: ok\n")],
        "20261025-100100-curso": [("conductor.pid", str(os.getpid()))],
        "20261025-100200-muerto": [("conductor.pid", str(muerto.pid))],
    }
    for nombre, archivos in corridas.items():
        run = tmp_path / nombre
        run.mkdir()
        for nombre_archivo, contenido in archivos:
            (run / nombre_archivo).write_text(contenido, encoding="utf-8")
    lineas = panorama_delegadas(tmp_path)
    assert lineas == [
        "20261025-100200-muerto: murió sin resumen",
        "20261025-100100-curso: en curso",
        "20261025-100000-ok: ok",
    ]
    assert panorama_delegadas(tmp_path, maximo=2) == lineas[:2]
    assert panorama_delegadas(tmp_path / "no-existe") == []


def test_corridas_activas_solo_las_vivas_sin_resumen(tmp_path):
    from delegar import corridas_activas

    for nombre, archivos in {
        "a-terminada": [("resumen.md", "- estado: ok"), ("conductor.pid", "1")],
        "b-curso": [("conductor.pid", str(os.getpid()))],
        "c-sin-pid": [],
    }.items():
        run = tmp_path / nombre
        run.mkdir()
        for nombre_archivo, contenido in archivos:
            (run / nombre_archivo).write_text(contenido, encoding="utf-8")
    activas = corridas_activas(tmp_path)
    assert [d.name for d in activas] == ["b-curso"]


def test_el_modulo_expone_la_tool_con_su_impl():
    """El contrato de modules/: TOOLS declara `delegar_tarea` e IMPL tiene
    la implementación bajo el MISMO nombre (el action space arma el par)."""
    from modules.delegar import IMPL, TOOLS

    nombres = [t["function"]["name"] for t in TOOLS]
    assert nombres == ["delegar_tarea"]
    assert set(IMPL) == set(nombres) and callable(IMPL["delegar_tarea"])


def test_delegar_tarea_rechazada_no_lanza_nada(monkeypatch, capsys):
    """El rechazo del lanzamiento (exp/98, con motivo) no spawnea proceso y
    el motivo le vuelve al modelo."""
    import modules.delegar as mod
    from utils.aprobaciones import Decision

    def lanzar_si_me_dejan(*a, **k):
        raise AssertionError("un rechazo no debe lanzar el conductor")

    monkeypatch.setattr(mod.subprocess, "Popen", lanzar_si_me_dejan)
    monkeypatch.setattr(mod, "pedir_aprobacion",
                        lambda prompt, cuerpo="": Decision(False, "apretado de tiempo"))
    salida = mod.delegar_tarea("creá el informe X", permitir="/repo/salidas")
    assert "RECHAZADO" in salida and "apretado de tiempo" in salida
    assert "no se lanzó" in salida
    # el operador vio el pedido y el scope ANTES del s/n (patrón run_command)
    impreso = capsys.readouterr().out
    assert "creá el informe X" in impreso and "/repo/salidas" in impreso


def test_delegar_tarea_lanza_el_conductor_detached(monkeypatch):
    import modules.delegar as mod

    lanzamientos = []

    def popen_falso(argv, **kwargs):
        lanzamientos.append((argv, kwargs))

    monkeypatch.setattr(mod.subprocess, "Popen", popen_falso)
    monkeypatch.setattr(mod, "pedir_aprobacion", lambda prompt, cuerpo="": True)
    salida = mod.delegar_tarea("creá X y verificalo", permitir="/repo/a, /repo/b",
                               permitir_comandos="python3 -m pytest", timeout_min="45")
    argv, kwargs = lanzamientos[0]
    assert argv[1:5] == ["main.py", "delegar", "creá X y verificalo", "--permitir"]
    assert argv[5:8] == ["/repo/a", "--permitir", "/repo/b"]
    assert "python3 -m pytest" in argv and "--timeout-min" in argv
    assert kwargs["start_new_session"] is True  # sobrevive al cierre del chat
    assert kwargs["cwd"] == mod.RAIZ
    assert kwargs["stdin"] is subprocess.DEVNULL
    assert "salidas/delegar" in salida


def test_delegar_tarea_valida_sus_entradas(monkeypatch):
    import modules.delegar as mod

    monkeypatch.setattr(mod.subprocess, "Popen", lambda *a, **k: None)
    assert mod.delegar_tarea("   ") .startswith("ERROR")
    assert mod.delegar_tarea("tarea", timeout_min="cero").startswith("ERROR")
    assert mod.delegar_tarea("tarea", timeout_min="0").startswith("ERROR")


def test_delegar_tarea_shadow_fuerza_el_modo(monkeypatch):
    import modules.delegar as mod

    lanzamientos = []

    def popen_falso(argv, env=None, **kwargs):
        lanzamientos.append(env)

    monkeypatch.setattr(mod.subprocess, "Popen", popen_falso)
    monkeypatch.setattr(mod, "pedir_aprobacion", lambda prompt, cuerpo="": True)
    mod.delegar_tarea("tarea", shadow="1")
    assert lanzamientos[0]["LAYA_MODO"] == "shadow"


def test_el_arranque_y_cierre_del_chat_reportan_delegadas(monkeypatch, capsys):
    """Los ganchos del módulo delegar: el arranque imprime el panorama; el
    aviso de cierre solo sale cuando hay corridas activas (exp/100)."""
    import delegar
    import modules.delegar as delegar_mod

    monkeypatch.setattr(delegar, "panorama_delegadas",
                        lambda: ["20261025-101000: ok", "20261025-100900: en curso"])
    delegar_mod.estado_delegadas()
    out = capsys.readouterr().out
    assert "[delegar]" in out and "20261025-101000: ok" in out

    monkeypatch.setattr(delegar, "corridas_activas", lambda: [])
    delegar_mod.aviso_delegadas_al_cerrar()
    assert capsys.readouterr().out == ""

    from pathlib import Path as _Path

    monkeypatch.setattr(delegar, "corridas_activas", lambda: [_Path("20261025-101500")])
    delegar_mod.aviso_delegadas_al_cerrar()
    assert "siguen corriendo" in capsys.readouterr().out
