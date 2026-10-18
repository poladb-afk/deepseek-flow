"""Candados del HITL graduado y la frontera del shell: clasificación, hooks, denylist y raíces (PR 4)."""
import pytest
from conftest import tc as _tc


def test_run_command_hitl_y_rieles(monkeypatch):
    import modules.coding as coding

    # HITL_AUTO=0 fuerza el camino clásico (todo pregunta), que es lo que
    # este test ejercita: aprobación, rechazo, timeout y truncado. La
    # clasificación graduada tiene sus propios tests.
    monkeypatch.setenv("HITL_AUTO", "0")

    # aprobado: ejecuta y reporta exit + salida
    monkeypatch.setattr(coding, "_approve", lambda p: True)
    r = coding.run_command("echo hola-coding")
    assert r.startswith("exit 0") and "hola-coding" in r

    # rechazado: no ejecuta, el rechazo es texto para el modelo
    monkeypatch.setattr(coding, "_approve", lambda p: False)
    r = coding.run_command("echo no-deberia")
    assert r.startswith("RECHAZADO") and "no-deberia" not in r

    # timeout: el riel mecánico corta el comando colgado
    monkeypatch.setattr(coding, "_approve", lambda p: True)
    monkeypatch.setattr(coding, "TIMEOUT_S", 1)
    assert "timeout" in coding.run_command("sleep 5")

    # truncado: la salida larga no intoxica el historial
    monkeypatch.setattr(coding, "TIMEOUT_S", 120)
    r = coding.run_command("python3 -c \"print('x' * 20000)\"")
    assert "salida truncada" in r and len(r) < 6000

def test_policy_clasifica_los_tres_niveles():
    from utils.policy import clasificar

    # AUTO: whitelist de solo-lectura
    for c in ("pytest -q", "python3 -m pytest tests/", "grep -r x .", "ls -la",
              "cat x.py", "head -5 x", "tail -f x", "wc -l x", "find . -name x",
              "file x", "echo hola", "git status", "git log --oneline",
              "git diff", "git show HEAD", "git blame x.py"):
        assert clasificar(c) == "auto", c

    # PREGUNTAR: lo no reconocido y la negra de un solo s/n
    for c in ("mkdir nueva", "curl http://x", "rm -f x", "git commit -m x",
              "git checkout .", "git reset --hard", "pip install x"):
        assert clasificar(c) == "preguntar", c

    # CONFIRMAR_DOBLE
    assert clasificar("git push") == "confirmar_doble"
    assert clasificar("git push origin main") == "confirmar_doble"
    assert clasificar("") == "preguntar"
    assert clasificar(None) == "preguntar"

def test_policy_semicolon_y_cd_neutro():
    """Lecciones medidas en el test exhaustivo del 2026-10-06 (35 turnos vs
    DeepSeek real): (1) el modelo prefijó `cd <dir> &&` en 5/5 run_command y
    el compuesto degradaba a preguntar aunque el fondo fuera pytest auto;
    (2) el `;` NO se partía como && y |: `ls ; rm -rf /tmp/x` clasificaba
    auto y el rm corría sin aprobación (hueco real: shell=True)."""
    from utils.policy import clasificar

    # cd neutro: solo cambia el cwd del subshell de este comando
    assert clasificar("cd /algun/lado && python3 -m pytest tests/ -q") == "auto"
    assert clasificar("cd . && ls") == "auto"

    # ... pero no relaja nada: el segmento peligroso sigue mandando
    assert clasificar("cd /tmp && rm -f x") == "preguntar"
    assert clasificar("cd /algo && python3 main.py evals") == "preguntar"
    assert clasificar("cd /algo && git push") == "confirmar_doble"

    # sort a la whitelist (medido: find | sort | head era el conteo natural)
    assert clasificar("find . -name '*.py' | sort -rn | head -5") == "auto"

    # el ; parte como && y |: TODOS los segmentos deben ser auto (y la
    # negra doble gana sobre todo — rm -rf paga las DOS confirmaciones)
    assert clasificar("ls ; rm -rf /tmp/x") == "confirmar_doble"
    assert clasificar("git status ; rm algo") == "preguntar"
    assert clasificar("ls ; grep x y") == "auto"

def test_policy_reglas_de_composicion():
    from utils.policy import clasificar

    # compuesto todo-seguro = auto
    assert clasificar("ls && grep x y") == "auto"
    assert clasificar("cat a.py | grep def") == "auto"
    assert clasificar("git status && git diff") == "auto"

    # compuesto mixto = preguntar (basta UN segmento no auto)
    assert clasificar("ls && rm -f x") == "preguntar"
    assert clasificar("git status | python3 -c 'print(1)'") == "preguntar"
    assert clasificar("pytest -q && pip install x") == "preguntar"

    # redirección / sustitución / xargs = preguntar (incluso con whitelist)
    for c in ("cat x > y", "echo hi > f", "grep x < f", "ls >> log",
              "ls $(pwd)", "echo `date`", "ls | xargs rm", "cat x | xargs grep y"):
        assert clasificar(c) == "preguntar", c

    # python3 -c SIEMPRE pregunta (código arbitrario)
    assert clasificar("python3 -c \"print(1)\"") == "preguntar"
    assert clasificar("python -c \"print(1)\"") == "preguntar"

    # doble confirmación gana sobre todo lo demás en el compuesto
    assert clasificar("git push && ls") == "confirmar_doble"
    assert clasificar("ls && git push") == "confirmar_doble"
    assert clasificar("git push origin main && rm -rf /") == "confirmar_doble"

def test_policy_2_amp_1_es_lectura():
    """Fix 12 (spec banco_robusto_2026-10-07): `2>&1` duplica stderr al
    stdout ya capturado — es LECTURA de descriptor, no redirección que
    escribe. Se descarta antes del escaneo, pero toda redirección REAL
    conserva su carácter cazable: la matriz de abajo demuestra que ninguna
    escritura se escapa."""
    from utils.policy import clasificar

    # AUTO: `2>&1` solo, con pipe, y en comandos de solo-lectura whitelisted
    assert clasificar("python3 -m pytest tests/ -q 2>&1") == "auto"
    assert clasificar("python3 -m pytest tests/ -q 2>&1 | tail -20") == "auto"
    assert clasificar("grep algo archivo 2>&1") == "auto"
    assert clasificar("cat x | head -3 2>&1") == "auto"

    # PREGUNTAR: redirecciones reales (el strip no oculta ninguna)
    assert clasificar("echo hola > f") == "preguntar"
    assert clasificar("echo hola > f 2>&1") == "preguntar"  # `> f` sobrevive
    assert clasificar("comando 2> err.txt") == "preguntar"  # fd a archivo, no `2>&1`
    assert clasificar("comando 2>&1 > f") == "preguntar"  # orden importa: queda `> f`

def test_run_command_auto_no_pide_input(monkeypatch):
    import modules.coding as coding

    # con HITL_AUTO=1 (default), un comando seguro NO debe llamar a input:
    # si lo llamara, este monkeypatch explotaría.
    def explota(prompt):
        raise AssertionError(f"no debía preguntar: {prompt!r}")

    monkeypatch.delenv("HITL_AUTO", raising=False)
    monkeypatch.setattr("builtins.input", explota)
    r = coding.run_command("echo auto-sin-input")
    assert r.startswith("exit 0") and "auto-sin-input" in r

def test_run_command_no_seguro_pide_input(monkeypatch):
    import modules.coding as coding

    llamados = []

    def falso_input(prompt):
        llamados.append(prompt)
        return "s"

    monkeypatch.delenv("HITL_AUTO", raising=False)
    monkeypatch.setattr("builtins.input", falso_input)
    r = coding.run_command("echo no-seguro")  # echo SÍ es auto; forzamos no-auto
    # (echo es auto → para probar el camino 'preguntar' usamos algo no whitelisted)
    assert llamados == []  # echo se ejecutó auto, sin input
    assert r.startswith("exit 0")

    # un comando no-seguro SÍ pide (rm... no lo ejecutamos realmente: no está
    # en whitelist así que pregunta; lo rechazamos para no tocar nada)
    monkeypatch.setattr("builtins.input", lambda p: (llamados.append(p), "n")[1])
    r2 = coding.run_command("mkdir no_se_debe_crear")
    assert llamados and llamados[-1].startswith("¿Ejecutar?")
    assert r2.startswith("RECHAZADO")

def test_run_command_hitl_auto_cero_compatibilidad(monkeypatch):
    import modules.coding as coding

    # Con HITL_AUTO=0 hasta un comando seguro pregunta (comportamiento de hoy).
    llamados = []
    monkeypatch.setenv("HITL_AUTO", "0")
    monkeypatch.setattr("builtins.input", lambda p: (llamados.append(p), "s")[1])
    r = coding.run_command("echo compat")
    assert llamados  # preguntó pese a ser whitelisted
    assert r.startswith("exit 0") and "compat" in r
    monkeypatch.delenv("HITL_AUTO", raising=False)

def test_run_command_doble_confirmacion_aborta(monkeypatch):
    import modules.coding as coding

    # git push pide dos s/n; si la segunda es 'n', aborta (sin ejecutar).
    respuestas = iter(["s", "n"])
    monkeypatch.delenv("HITL_AUTO", raising=False)
    monkeypatch.setattr("builtins.input", lambda p: next(respuestas))
    r = coding.run_command("git push")  # no llega a ejecutar: aborta en la 2ª
    assert r.startswith("RECHAZADO")

    # si la primera es 'n', también aborta
    monkeypatch.setattr("builtins.input", lambda p: "n")
    r = coding.run_command("git push --dry-run")
    assert r.startswith("RECHAZADO")

def test_hook_py_compile_tras_edit_y_write(tmp_path, monkeypatch, capsys):
    import modules.coding as coding
    import modules.escritura
    from utils.fs_tools import run_tool_call

    # run_tool_call real: registra las implementaciones de los módulos (en
    # el agente lo hace nodes.py; acá lo armamos igual).
    extra = {**coding.IMPL, **modules.escritura.IMPL}
    monkeypatch.setenv("AGENT_ALLOWED_DIRS", str(tmp_path))
    monkeypatch.setattr(coding, "_approve", lambda p: True)
    monkeypatch.setattr(modules.escritura, "_approve", lambda p: True)

    # edit_file de un .py con sintaxis rota: el hook agrega ⚠ SINTAXIS
    roto = tmp_path / "roto.py"
    roto.write_text("def f(:\n    pass\n", encoding="utf-8")
    res = run_tool_call(_tc("edit_file", {
        "path": str(roto), "old_string": "def f(:", "new_string": "def g(:"}), extra)
    assert "⚠ SINTAXIS" in res["content"]
    # el aviso también llega a la terminal (no solo al modelo)
    assert "[hook] ⚠ SINTAXIS" in capsys.readouterr().out

    # write_file de un .py roto también
    res = run_tool_call(_tc("write_file", {
        "path": str(tmp_path / "nuevo.py"), "content": "x = (\n"}), extra)
    assert "⚠ SINTAXIS" in res["content"]
    assert "[hook] ⚠ SINTAXIS" in capsys.readouterr().out

    # un .py correcto NO agrega nada
    res = run_tool_call(_tc("write_file", {
        "path": str(tmp_path / "bueno.py"), "content": "def ok():\n    return 1\n"}), extra)
    assert "⚠ SINTAXIS" not in res["content"]
    assert res["content"].startswith("Escrito")
    # compila bien: el hook NO imprime nada en terminal
    assert "[hook] ⚠ SINTAXIS" not in capsys.readouterr().out

    # un .txt no dispara py_compile (no aplica)
    res = run_tool_call(_tc("write_file", {
        "path": str(tmp_path / "notas.txt"), "content": "esto no es python(\n"}), extra)
    assert "⚠ SINTAXIS" not in res["content"]

    # edit_file que corrige el .py roto: sin aviso
    res = run_tool_call(_tc("edit_file", {
        "path": str(roto), "old_string": "def g(:", "new_string": "def g():"}), extra)
    assert "⚠ SINTAXIS" not in res["content"]

def test_hook_no_rompe_la_ejecucion(tmp_path, monkeypatch):
    # Un hook que lanza NO rompe el resultado (contrato de hierro).
    from utils import fs_tools

    def hook_malo(tool_call, resultado):
        raise ValueError("boom")

    fs_tools.HOOKS_POST.setdefault("read_file", []).append(hook_malo)
    try:
        res = fs_tools.run_tool_call(_tc("read_file", {
            "path": str(tmp_path / "x.txt")}))  # no existe → ERROR
        assert res["content"].startswith("ERROR")
    finally:
        fs_tools.HOOKS_POST["read_file"].remove(hook_malo)

def test_hook_pre_denylist_veta_antes_de_ejecutar(tmp_path, monkeypatch, capsys):
    """Mesa 2 (residual): el denylist de run_command corre ANTES de la
    implementación (hook PRE). Un comando prohibido se veta sin ejecutarse
    NI aprobarse (input explota si se llamara). El hook imprime un aviso
    [denylist] antes de devolver el veto (paridad con _hook_py_compile)."""
    import subprocess

    import modules.coding as coding
    from utils import fs_tools

    # el denylist quedó registrado al importar el módulo
    assert fs_tools.HOOKS_PRE.get("run_command")

    def explota(*a, **k):
        raise AssertionError("el comando prohibido llegó a ejecutarse")

    # input y subprocess explotan: si el denylist fallara, el test lo delata.
    # Guardamos el subprocess.run ORIGINAL antes de parchear (restaurarlo con
    # coding.subprocess.run devolvería el parcheado).
    run_original = subprocess.run
    monkeypatch.setattr("builtins.input", explota)
    monkeypatch.setattr(coding.subprocess, "run", explota)

    res = fs_tools.run_tool_call(
        _tc("run_command", {"command": "rm -rf /"}),
        coding.IMPL,
    )
    assert res["content"].startswith("ERROR") and "denylist" in res["content"]
    salida = capsys.readouterr().out
    # Fix 10a: el ancla es la línea impresa VERBATIM de la spec, y el comando
    # que eligió el modelo NO viaja adentro de ella.
    assert "  [denylist] comando vetado (daño irreversible): no se ejecutó ni se pidió aprobación" in salida
    assert "rm -rf /" not in salida

    res = fs_tools.run_tool_call(
        _tc("run_command", {"command": ":(){ :|:& };:"}),
        coding.IMPL,
    )
    assert res["content"].startswith("ERROR") and "denylist" in res["content"]
    salida = capsys.readouterr().out
    assert "  [denylist] comando vetado (daño irreversible): no se ejecutó ni se pidió aprobación" in salida
    assert ":(){ :|:& };:" not in salida

    # un comando normal NO es vetado: restauramos el run real y verificamos
    # que llega a la implementación (echo inofensivo, HITL_AUTO lo corre auto).
    monkeypatch.delenv("HITL_AUTO", raising=False)
    monkeypatch.setattr(coding.subprocess, "run", run_original)
    res = fs_tools.run_tool_call(
        _tc("run_command", {"command": "echo denylist-ok"}),
        coding.IMPL,
    )
    assert res["content"].startswith("exit 0") and "denylist-ok" in res["content"]

def test_hook_pre_que_lanza_falla_cerrado(tmp_path):
    """Un hook PRE que lanza VETA (fail-closed): es una guarda de seguridad y
    'no pude decidir' no puede significar 'adelante'. El chat no se rompe: el
    veto vuelve como texto de tool."""
    from utils import fs_tools

    def hook_malo(tool_call):
        raise ValueError("boom")

    corrio = []
    fs_tools.HOOKS_PRE.setdefault("zz_guarda", []).append(hook_malo)
    try:
        res = fs_tools.run_tool_call(_tc("zz_guarda", {}),
                                     {"zz_guarda": lambda: corrio.append(1) or "corrió"})
        assert not corrio, "la implementación NO debe correr si la guarda lanzó"
        assert res["content"].startswith("ERROR: la guarda previa de zz_guarda falló (ValueError)")
    finally:
        fs_tools.HOOKS_PRE.pop("zz_guarda", None)

def test_policy_rm_rf_paga_doble():
    """Desviación de spec encontrada en auditoría: rm -rf debía ser
    confirmar_doble (doble fricción) y había quedado en preguntar."""
    from utils.policy import clasificar

    assert clasificar("rm -rf /tmp/x") == "confirmar_doble"
    assert clasificar("rm -fr /tmp/x") == "confirmar_doble"
    assert clasificar("rm archivo.txt") == "preguntar"
    assert clasificar("ls && rm -rf /") == "confirmar_doble"  # compuesto: el piso lo fija el peor

def test_explicar_comando():
    """Explicación corta y determinista por comando (mesa 8)."""
    from utils.policy import explicar

    assert "borrado recursivo" in explicar("rm -rf /tmp/x")
    assert "borra archivos" in explicar("rm archivo.txt")
    assert "publica commits" in explicar("git push origin main")
    assert "solo lee" in explicar("grep -r foo src/")
    assert "código Python arbitrario" in explicar('python3 -c "print(1)"')
    # no reconocido: describe el default preguntar
    assert "pide aprobación" in explicar("comando_raro --x")
    # vacío: default seguro
    assert "inválido" in explicar("   ")

def test_ningun_flujo_escribe_fuera_de_las_raices(tmp_path, monkeypatch):
    """exp/26 (C01 P0 de la auditoría externa): los flujos escribían con
    Path.write_text() una ruta de salida elegida por el modelo. Medido: con
    las raíces acotadas, write_file RECHAZABA la ruta externa y los flujos la
    escribían igual. Ahora todos pasan por utils.fs_tools.escribir_salida."""
    import auditoria
    import effective_n
    import informe
    import research
    import supervisor

    allowed = tmp_path / "allowed"
    allowed.mkdir()
    monkeypatch.setenv("AGENT_ALLOWED_DIRS", str(allowed))
    fuera = tmp_path / "FUERA.md"

    casos = [
        (informe.WriteReport(), {"salida": str(fuera)}, "# informe"),
        (auditoria.ReduceGlobal(), {"salida": str(fuera)}, "# auditoria"),
        (research.Synthesizer(), {"salida": str(fuera)},
         {"action": "finalize", "content": "# research"}),
        (supervisor.Sintetizar(),
         {"salida": str(fuera), "tarea": "t", "hechos": []}, "cierre"),
        (effective_n.WriteReport(), {"salida": str(fuera)},
         {"markdown": "# effective", "total": 2, "efectivo": 1}),
    ]
    for nodo, shared, exec_res in casos:
        with pytest.raises(ValueError, match="fuera de los directorios permitidos"):
            nodo.post(shared, None, exec_res)
    assert not fuera.exists()

    # el camino legítimo (dentro de las raíces) sigue escribiendo igual
    dentro = allowed / "informe.md"
    informe.WriteReport().post({"salida": str(dentro)}, None, "# ok")
    assert dentro.read_text(encoding="utf-8") == "# ok"

def test_supervisor_no_puede_saltear_el_denylist(monkeypatch):
    """exp/36 (barrida): EjecutarPaso llamaba REGISTRO[tool](**args) directo,
    salteando HOOKS_PRE — y el denylist duro de run_command solo corre por
    run_tool_call. Medido: el mismo 'rm -rf /' que el chat veta, por el
    supervisor se ejecutaba."""
    import json as _json

    import supervisor as sup
    from utils.fs_tools import HOOKS_PRE

    visto = {}

    def veto(tool_call):
        visto["comando"] = _json.loads(tool_call["function"]["arguments"])["command"]
        return "ERROR: comando prohibido por la denylist (test)"

    monkeypatch.setitem(HOOKS_PRE, "run_command", [veto])

    # El flujo v2 despacha por run_tool_call dentro de Ejecutar.exec: el hook
    # de la denylist corre igual que en el chat (no hay camino que lo saltee).
    snap = {
        "tool_calls": [{
            "id": "c1", "type": "function",
            "function": {"name": "run_command", "arguments": '{"command": "rm -rf /"}'},
        }],
        "fallos": {}, "exitosas": [], "previas": {}, "base": 0,
    }
    salidas = sup.Ejecutar().exec(snap)
    assert salidas[0]["resultado"].startswith("ERROR: comando prohibido")
    assert visto["comando"] == "rm -rf /"


def test_policy_flags_peligrosos_en_forma_pegada():
    """Flags peligrosos de una letra en forma pegada (-o/ruta, -pVALOR)
    degradan el segmento; el flag exacto y la forma --flag=valor ya estaban
    cubiertos. Evidencia: mutantes de _tiene_flag_peligroso sobrevivían
    (Fase 1, M1; informe f1_mutation.md)."""
    from utils.policy import clasificar

    assert clasificar("sort -o/tmp/x") == "preguntar"
    assert clasificar("sort -o /tmp/x") == "preguntar"
    assert clasificar("pytest -pno:cacheprovider") == "preguntar"
    assert clasificar("pytest -p no:cacheprovider") == "preguntar"
    # control: sin flag peligroso sigue auto
    assert clasificar("sort archivo.txt") == "auto"


def test_policy_descarta_2and1_y_conserva_redirecciones_reales():
    """La excepción semántica documentada: 2>&1 es lectura de descriptor y
    se descarta ANTES del escaneo; una redirección real sigue degradando.
    Evidencia: mutantes del stripping de 2>&1 sobrevivían (Fase 1, M2)."""
    from utils.policy import clasificar

    assert clasificar("ls 2>&1") == "auto"
    assert clasificar("ls 2>&1 | grep x") == "auto"
    assert clasificar("pytest -q 2>&1") == "auto"
    assert clasificar("ls 2>&1 > out.txt") == "preguntar"
    assert clasificar("ls > out.txt 2>&1") == "preguntar"


def test_aprobar_doble_confirmacion_y_motivos(monkeypatch, capsys):
    """El flujo real de _aprobar: orden de las dos preguntas, motivo del
    rechazo y línea de transparencia del modo auto. Los tests del flujo
    monkeypatchean _approve entero; acá se simulan las respuestas humanas.
    Evidencia: 42 mutantes de _aprobar sobrevivían (Fase 1, M8)."""
    import modules.coding as coding
    from modules.coding import RECHAZO, RECHAZO_DOBLE

    def no_preguntar(_p):
        raise AssertionError("auto no debe pedir aprobación")

    monkeypatch.setattr(coding, "registrar_aprobacion", lambda *a, **k: None)

    respuestas = iter([True, True])
    monkeypatch.setattr(coding, "_approve", lambda _p: next(respuestas))
    aprobado, motivo = coding._aprobar("echo hola", "confirmar_doble", None)
    assert aprobado is True and motivo == ""
    salida = capsys.readouterr().out
    assert "doble confirmación" in salida and "echo hola" in salida

    respuestas = iter([True, False])
    monkeypatch.setattr(coding, "_approve", lambda _p: next(respuestas))
    aprobado, motivo = coding._aprobar("echo hola", "confirmar_doble", None)
    assert aprobado is False and motivo == RECHAZO_DOBLE

    respuestas = iter([False])
    monkeypatch.setattr(coding, "_approve", lambda _p: next(respuestas))
    aprobado, motivo = coding._aprobar("echo hola", "preguntar", None)
    assert aprobado is False and motivo == RECHAZO

    monkeypatch.setattr(coding, "_approve", no_preguntar)
    aprobado, motivo = coding._aprobar("cat x", "auto", None)
    assert aprobado is True and motivo == ""
    assert "auto: solo-lectura" in capsys.readouterr().out


def test_policy_traversal_por_recorrido_de_symlinks_degrada():
    """`find -L` y `grep -R` siguen symlinks al recorrer: con un enlace
    dentro de las raíces pueden leer fuera de ellas, así que no son auto.
    Evidencia: auditoría F2 (symlink escape vía recorrido)."""
    from utils.policy import clasificar

    assert clasificar("grep -R secreto .") == "preguntar"
    assert clasificar("grep --dereference-recursive secreto .") == "preguntar"
    assert clasificar("find . -L -name x") == "preguntar"
    # control: la versión que NO sigue symlinks sigue siendo solo-lectura
    assert clasificar("grep -r secreto .") == "auto"


def test_explicar_pytest_admite_que_ejecuta_codigo():
    """A45: la whitelist no puede rotular pytest como solo-lectura estricta;
    ejecuta conftest/plugins del repo y escribe cachés. La decisión es
    aceptarlo (con HITL_AUTO=0 como modo estricto), pero la explicación
    tiene que decirlo."""
    from utils.policy import explicar

    texto = explicar("pytest -q")
    assert "conftest" in texto and "cach" in texto
    assert "solo lee" not in texto


def test_policy_2and1_se_descarta_como_token_no_substring():
    """A44: el doc dice que se descarta el TOKEN 2>&1; antes se borraba la
    substring en cualquier posición (incluso dentro de un argumento). Ahora
    solo se quita el token exacto y un > escondido en un argumento degrada."""
    from utils.policy import clasificar

    assert clasificar("ls 2>&1") == "auto"
    assert clasificar("ls 2>&1 | grep x") == "auto"
    assert clasificar("grep 'x2>&1y' README.md") == "preguntar"
