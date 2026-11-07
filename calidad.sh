#!/usr/bin/env bash
# Base de calidad de deepseek-flow: higiene (ruff) + complejidad de las
# fronteras + ratchet (métricas vs baseline) + funcional (pytest) + cobertura
# por archivo + tipos del producto (Pyright, X184).
#
# El gate determinista — sin LLM, mismo comando ⇒ mismo resultado:
#   ./calidad.sh          → corre las seis palancas, exit 0 si TODO verde
#   (usarlo antes de commit; y como paso de CI: .github/workflows/calidad.yml)
set -u
cd "$(dirname "$0")"

fallo=0

echo "═══ 1/6 higiene — ruff check ═══"
if ruff check .; then
    echo "✅ higiene verde"
else
    echo "❌ higiene roja"
    fallo=1
fi

echo
echo "═══ 2/6 complejidad — C901 ≤ 12 en las fronteras de seguridad ═══"
# Las dos fronteras del PR 6 se exigen al instante (ruff). El resto del harness
# NO queda libre: la etapa 3 mide C901 repo-wide (mismo umbral, conteo exacto
# de ruff) y anidación de control > 3 como métricas del ratchet con la deuda
# actual sembrada (9 y 21). Esta etapa se mantiene porque es la que protege las
# fronteras de seguridad con el mismo gate determinista de siempre.
if ruff check --select C901 --config 'lint.mccabe.max-complexity=12' modules/coding.py utils/fs_tools.py; then
    echo "✅ complejidad verde (fronteras; repo-wide en el ratchet)"
else
    echo "❌ complejidad roja: una frontera volvió a crecer"
    fallo=1
fi

echo
echo "═══ 3/6 ratchet — las métricas no empeoran (baseline versionado) ═══"
# Mecanismo de git-agent-ratchet: helpers privados duplicados (baja = mejora) y
# tests definidos (sube = mejora) contra ratchets/baseline.json. La métrica puede
# mejorar o quedar igual; empeorar exige que el operador humano corra --actualizar.
if python3 ratchet.py; then
    echo "✅ ratchet verde"
else
    echo "❌ ratchet rojo: una métrica empeoró (o el baseline es un bypass)"
    fallo=1
fi

echo
echo "═══ 4/6 funcional — pytest (midiendo cobertura) ═══"
# X175: la suite corre UNA vez entera. La cobertura se mide con los tests que
# no dependen del entorno; los marcados (red, datos, laya, git) corren aparte y
# sin medir, porque cubren distinto según la máquina (medido: con ddgs
# instalado, utils/websearch.py suma 6 líneas cubiertas). `cobertura`: los tests
# que abren un colector anidado apagan el externo (medido, X175), así que
# también corren en la segunda pasada.
# La pasada medida corre como el CI, SIN .env: el .env local mueve la cobertura
# por archivo (call_llm 10→11, citas 13→12; medido) aunque no el total, y la
# sección del baseline quedaría a merced de si el archivo está. Se aparta y se
# restaura pase lo que pase (la segunda pasada, la no medida, corre con .env).
rm -rf .cobertura
ENTORNO="red or datos or laya or git or cobertura"
apartado=""
restaurar_env() {
    [ -n "$apartado" ] && mv "$apartado/.env" .env && rmdir "$apartado"
}
if [ -f .env ]; then
    apartado="$(mktemp -d)"
    mv .env "$apartado/.env"
    trap restaurar_env EXIT
    trap 'restaurar_env; exit 130' INT TERM
fi
medida=1
python3 -m coverage run -m pytest tests/ -q -m "not ($ENTORNO)" || medida=0
if [ -n "$apartado" ]; then
    restaurar_env
    apartado=""
    trap - EXIT INT TERM
fi
funcional=0
if [ "$medida" -eq 1 ] && python3 -m pytest tests/ -q -m "$ENTORNO"; then
    echo "✅ funcional verde"
else
    echo "❌ funcional roja"
    fallo=1
    funcional=1
fi

echo
echo "═══ 5/6 cobertura — ningún archivo suma líneas sin test (baseline versionado) ═══"
# X185: la cobertura solo vale sobre una suite que pasó. Si la etapa 4 falló, se
# mide SOLO como diagnóstico y con --no-escribir: una corrida inválida movió el
# baseline 1017→1016 sin clave (PATH relativo → el subproceso del test no
# encontraba `sys.executable` → suite roja → la etapa 5 veía "mejora" y
# reescribía). Un gate no acepta una mejora que no midió sobre una suite válida.
if [ "$funcional" -ne 0 ]; then
    echo "⏭️  cobertura en diagnóstico: la suite no pasó; el baseline NO se toca"
    python3 ratchet.py --cobertura --no-escribir
else
    if python3 ratchet.py --cobertura; then
        echo "✅ cobertura verde"
    else
        echo "❌ cobertura roja: hay código nuevo sin test"
        fallo=1
    fi
fi

echo
echo "═══ 6/6 tipos — pyright (producto, baseline versionado) ═══"
# X184: la etapa solo junta el JSON (`--outputjson`; exit 1 = hay diagnósticos,
# esperado mientras el baseline los contemple). `ratchet.py --pyright` lo
# compara por archivo:regla: solo baja, y sin un JSON válido es ROJO. Pyright
# está pinneado en requirements-dev.txt; el target fijo vive en [tool.pyright].
mkdir -p .pyright
python3 -m pyright --outputjson > .pyright/datos.json
if python3 ratchet.py --pyright; then
    echo "✅ tipos verde"
else
    echo "❌ tipos roja: un error de tipo nuevo (o el baseline no es de esta versión)"
    fallo=1
fi

echo
if [ "$fallo" -eq 0 ]; then
    echo "✅ BASE DE CALIDAD VERDE"
else
    echo "❌ BASE DE CALIDAD ROJA"
fi
exit "$fallo"
