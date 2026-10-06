#!/usr/bin/env bash
# Base de calidad de deepseek-flow: higiene (ruff) + funcional (pytest).
#
# El gate determinista — sin LLM, mismo comando ⇒ mismo resultado:
#   ./calidad.sh          → corre ambas palancas, exit 0 si TODO verde
#   (usarlo antes de commit; o como paso de CI cuando exista)
set -u
cd "$(dirname "$0")"

fallo=0

echo "═══ 1/2 higiene — ruff check ═══"
if ruff check .; then
    echo "✅ higiene verde"
else
    echo "❌ higiene roja"
    fallo=1
fi

echo
echo "═══ 2/2 funcional — pytest ═══"
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
