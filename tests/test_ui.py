"""UX de terminal: color, progreso y diff resaltado (PR 4)."""

import modules.memoria as mem

# Pulido de terminal (mesa 8): colores por tipo de evento + progreso de rondas


def test_colorear_sin_tty_no_pinta(monkeypatch):
    """Sin tty (tests, pipes) el color NO aparece: los textos quedan
    intactos. Es lo que garantiza que nada cambie en CI ni en logs."""
    import utils.terminal as t

    monkeypatch.setattr(t.sys.stdout, "isatty", lambda: False, raising=False)
    assert t.colorear("hola", "tool") == "hola"
    assert t.colorear("hola", "error") == "hola"

def test_colorear_con_tty_pinta_y_respeta_apagados(monkeypatch):
    """Con tty sí pinta (códigos ANSI + reset); NO_COLOR y COLOR=0 mandan
    sobre un tty real."""
    import utils.terminal as t

    monkeypatch.setattr(t.sys.stdout, "isatty", lambda: True, raising=False)
    monkeypatch.delenv("NO_COLOR", raising=False)
    monkeypatch.delenv("COLOR", raising=False)
    pintado = t.colorear("hola", "error")
    assert pintado != "hola" and "\033[" in pintado and pintado.endswith("\033[0m")
    assert "hola" in pintado

    # NO_COLOR (estándar) apaga aun con tty
    monkeypatch.setenv("NO_COLOR", "1")
    assert t.colorear("hola", "error") == "hola"

    # COLOR=0 (escape hatch propio) también apaga
    monkeypatch.delenv("NO_COLOR")
    monkeypatch.setenv("COLOR", "0")
    assert t.colorear("hola", "error") == "hola"

def test_colorear_tipo_desconocido_no_altera(monkeypatch):
    import utils.terminal as t

    monkeypatch.setattr(t.sys.stdout, "isatty", lambda: True, raising=False)
    monkeypatch.delenv("NO_COLOR", raising=False)
    monkeypatch.delenv("COLOR", raising=False)
    assert t.colorear("hola", "inexistente") == "hola"

def test_progreso_ronda():
    from utils.terminal import progreso_ronda

    assert progreso_ronda(2, 8) == "⚙ ronda 2/8"
    assert progreso_ronda(1, 1) == "⚙ ronda 1/1"
    assert progreso_ronda(3) == "⚙ ronda 3"  # sin tope conocido

# HITL UX (mesa 8): highlight, explicación y historial de aprobaciones

def test_highlight_diff(monkeypatch):
    """El diff se colorea por tipo de línea; sin color, queda intacto."""
    import utils.terminal as term

    diff = "@@ -1 +1 @@\n-a = 1\n+a = 2\n c"
    # sin tty/color: intacto (lo que ven tests, pipes y logs)
    monkeypatch.setattr(term, "_quiere_color", lambda: False)
    assert term.highlight_diff(diff) == diff
    # con color: adiciones verdes, supresiones rojas, cabeceras coloreadas
    monkeypatch.setattr(term, "_quiere_color", lambda: True)
    h = term.highlight_diff(diff)
    assert "\033[32m+a = 2\033[0m" in h  # verde
    assert "\033[31m-a = 1\033[0m" in h  # rojo
    assert "\033[36m@@ -1 +1 @@\033[0m" in h  # cian
    # las cabeceras +++/--- van en gris, no verde/rojo (no confundir el nombre)
    assert "\033[90m--- a (actual)\033[0m" in term.highlight_diff("--- a (actual)\n+++ a (nuevo)")


def test_catalogo_memoria_muestra_nombres_y_respeta_memoria_0(tmp_path, monkeypatch, capsys):
    """Mesa 8: al arrancar se lista la biblioteca (solo nombres, SIN inyectar
    contexto); con MEMORIA=0 no imprime nada."""

    monkeypatch.delenv("MEMORIA", raising=False)
    monkeypatch.setenv("MEMORIA_DIR", str(tmp_path))
    (tmp_path / "nota_uno.md").write_text("cuerpo uno\n", encoding="utf-8")
    (tmp_path / "nota_dos.md").write_text("cuerpo dos\n", encoding="utf-8")
    mem.catalogo()
    salida = capsys.readouterr().out
    assert "biblioteca: 2 notas" in salida and "nota_uno.md" in salida

    monkeypatch.setenv("MEMORIA", "0")
    mem.catalogo()
    assert capsys.readouterr().out == ""
