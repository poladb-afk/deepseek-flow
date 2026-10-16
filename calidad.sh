#!/usr/bin/env bash
# Base de calidad de deepseek-flow: higiene (ruff) + complejidad de las
# fronteras + funcional (pytest).
#
# El gate determinista — sin LLM, mismo comando ⇒ mismo resultado:
#   ./calidad.sh          → corre las tres palancas, exit 0 si TODO verde
#   (usarlo antes de commit; y como paso de CI: .github/workflows/calidad.yml)
set -u
cd "$(dirname "$0")"

fallo=0

echo "═══ 1/3 higiene — ruff check ═══"
if ruff check .; then
    echo "✅ higiene verde"
else
    echo "❌ higiene roja"
    fallo=1
fi

echo
echo "═══ 2/3 complejidad — C901 ≤ 12 en las fronteras de seguridad ═══"
# Solo las dos fronteras del PR 6 (shell y lectura de archivos): el resto del
# repo tiene funciones largas a propósito (evals.linter_traza, banco.correr…).
if ruff check --select C901 --config 'lint.mccabe.max-complexity=12' modules/coding.py utils/fs_tools.py; then
    echo "✅ complejidad verde"
else
    echo "❌ complejidad roja: una frontera volvió a crecer"
    fallo=1
fi

echo
echo "═══ 3/3 funcional — pytest ═══"
if python3 -m pytest tests/ -q; then
    echo "✅ funcional verde"
else
    echo "❌ funcional roja"
    fallo=1
fi

echo
if [ "$fallo" -eq 0 ]; then
    echo "✅ BASE DE CALIDAD VERDE"
else
    echo "❌ BASE DE CALIDAD ROJA"
fi
exit "$fallo"
