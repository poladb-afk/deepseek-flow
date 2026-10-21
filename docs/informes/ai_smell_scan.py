#!/usr/bin/env python3
"""ai_smell_scan.py - detecta patrones típicos de código generado por IA en proyectos Python.

Uso:  python ai_smell_scan.py ruta/al/proyecto  [--md reporte.md]
Solo usa la librería estándar. Es heurístico: cada hallazgo es una pista para revisar, no una condena.
"""
import ast, sys, re, pathlib, collections

REGLAS = {
    "PARAM_SIN_USO":   "Parámetro declarado pero nunca usado (boilerplate típico de IA)",
    "EXCEPT_AMPLIO":   "except Exception / except: genérico que puede ocultar bugs",
    "EXCEPT_SILENCIO": "except que solo hace pass/log/return sin re-lanzar (traga errores)",
    "RETURN_DEFAULT_EN_ERROR": "Devuelve 0/None/''/[]/{} dentro de un except (falla silenciosa)",
    "SQL_FSTRING":     "SQL armado con f-string/format/% -> posible inyección SQL",
    "FLOAT_DINERO":    "float() aplicado a algo que parece dinero (usar Decimal)",
    "SECRETO_HARDCODE":"Posible secreto/credencial en el código",
    "COMENTARIO_OBVIO":"Comentario que repite lo que hace el código (el 'qué', no el 'por qué')",
    "DOCSTRING_PLANTILLA":"Docstring de plantilla (Args/Returns que solo repiten nombres)",
    "MUERTO_TODO":     "Placeholder/TODO/NotImplemented que la IA dejó a medio hacer",
    "PRINT_DEBUG":     "print() en código de librería (en vez de logging o nada)",
    "EVAL_EXEC":       "Uso de eval/exec/pickle.loads/subprocess shell=True",
    "IMPORT_SIN_USO":  "Import que no se usa",
    "FUNC_DUPLICADA":  "Funciones con cuerpo casi idéntico (copy-paste generado)",
}

DINERO = re.compile(r"(monto|precio|price|amount|total|importe|saldo|balance|cost|costo)", re.I)
SECRETO = re.compile(r"(api[_-]?key|secret|password|passwd|token)\s*=\s*['\"][^'\"]{6,}['\"]", re.I)
SQL = re.compile(r"\b(SELECT|INSERT|UPDATE|DELETE)\b.+\b(FROM|INTO|SET|WHERE)\b", re.I)
OBVIO = re.compile(r"#\s*(initialize|inicializ|increment|incrementa|return|retorna|devuelve|loop|itera|import|create|crea|set |define|call|llama)\b", re.I)

class Scanner(ast.NodeVisitor):
    def __init__(self, path, src):
        self.path, self.src, self.lines = path, src, src.splitlines()
        self.hallazgos = []
        self.cuerpos = collections.defaultdict(list)
    def add(self, regla, node_or_line, detalle=""):
        linea = node_or_line if isinstance(node_or_line, int) else node_or_line.lineno
        self.hallazgos.append((str(self.path), linea, regla, detalle))

    def visit_FunctionDef(self, node):
        nombres = {n.id for n in ast.walk(node) if isinstance(n, ast.Name)}
        args = node.args.args + node.args.kwonlyargs
        decorada = bool(node.decorator_list)
        es_abstracta = len(node.body) == 1 and isinstance(node.body[0], (ast.Pass, ast.Raise)) or \
            (len(node.body) <= 2 and isinstance(node.body[0], ast.Expr) and isinstance(getattr(node.body[0], "value", None), ast.Constant) and len(node.body)==1)
        if not decorada and not es_abstracta:
            for a in args:
                if a.arg in ("self", "cls") or a.arg.startswith("_"):
                    continue
                if a.arg not in nombres:
                    self.add("PARAM_SIN_USO", node, f"{node.name}({a.arg})")
        doc = ast.get_docstring(node)
        if doc and re.search(r"^\s*(Args|Parameters|Returns):", doc, re.M):
            pares = re.findall(r"^\s+(\w+)\s*(?:\(.*?\))?:\s*(.+)$", doc, re.M)
            obvios = sum(1 for n, d in pares if n.lower().replace("_", " ") in d.lower().replace("_", " "))
            if pares and obvios / len(pares) >= 0.5:
                self.add("DOCSTRING_PLANTILLA", node, node.name)
        cuerpo = node.body[1:] if doc else node.body
        if cuerpo:
            firma = ast.dump(ast.Module(body=cuerpo, type_ignores=[]), annotate_fields=False)
            if len(firma) > 300:
                self.cuerpos[firma].append((node.name, node.lineno))
        for n in ast.walk(node):
            if isinstance(n, ast.Raise) and n.exc is not None:
                t = n.exc.func if isinstance(n.exc, ast.Call) else n.exc
                if isinstance(t, ast.Name) and t.id == "NotImplementedError":
                    self.add("MUERTO_TODO", n, f"NotImplementedError en {node.name}")
        self.generic_visit(node)
    visit_AsyncFunctionDef = visit_FunctionDef

    def visit_ExceptHandler(self, node):
        if node.type is None or (isinstance(node.type, ast.Name) and node.type.id in ("Exception", "BaseException")):
            self.add("EXCEPT_AMPLIO", node)
        relanza = any(isinstance(n, ast.Raise) for n in ast.walk(node))
        if not relanza:
            self.add("EXCEPT_SILENCIO", node)
            for n in node.body:
                if isinstance(n, ast.Return):
                    v = n.value
                    if v is None or (isinstance(v, ast.Constant) and v.value in (0, 0.0, None, "", False)) or \
                       (isinstance(v, (ast.List, ast.Dict, ast.Tuple)) and not getattr(v, "elts", getattr(v, "keys", [1]))):
                        self.add("RETURN_DEFAULT_EN_ERROR", n)
        self.generic_visit(node)

    def visit_Call(self, node):
        f = node.func
        nombre = f.id if isinstance(f, ast.Name) else (f.attr if isinstance(f, ast.Attribute) else "")
        if nombre in ("execute", "executemany", "raw", "text", "read_sql") and node.args:
            a = node.args[0]
            if isinstance(a, ast.JoinedStr) or (isinstance(a, ast.BinOp) and isinstance(a.op, (ast.Mod, ast.Add))) or \
               (isinstance(a, ast.Call) and isinstance(a.func, ast.Attribute) and a.func.attr == "format"):
                self.add("SQL_FSTRING", node)
        if nombre == "float" and node.args:
            seg = ast.get_source_segment(self.src, node.args[0]) or ""
            if DINERO.search(seg):
                self.add("FLOAT_DINERO", node, seg[:60])
        if nombre in ("eval", "exec") and isinstance(f, ast.Name):
            self.add("EVAL_EXEC", node, nombre)
        if nombre == "loads" and isinstance(f, ast.Attribute) and isinstance(f.value, ast.Name) and f.value.id == "pickle":
            self.add("EVAL_EXEC", node, "pickle.loads")
        for kw in node.keywords:
            if kw.arg == "shell" and isinstance(kw.value, ast.Constant) and kw.value.value is True:
                self.add("EVAL_EXEC", node, "shell=True")
        if nombre == "print" and isinstance(f, ast.Name) and not self.path.name.startswith(("test_", "cli", "__main__", "main")):
            self.add("PRINT_DEBUG", node)
        self.generic_visit(node)

    def visit_JoinedStr(self, node):
        seg = ast.get_source_segment(self.src, node) or ""
        if SQL.search(seg):
            self.add("SQL_FSTRING", node, seg[:60])
        self.generic_visit(node)

    def fin(self, tree):
        importados = {}
        for n in ast.walk(tree):
            if isinstance(n, (ast.Import, ast.ImportFrom)):
                for a in n.names:
                    nom = (a.asname or a.name).split(".")[0]
                    importados[nom] = n.lineno
        usados = {n.id for n in ast.walk(tree) if isinstance(n, ast.Name)} | \
                 {n.value.id for n in ast.walk(tree) if isinstance(n, ast.Attribute) and isinstance(n.value, ast.Name)}
        if self.path.name != "__init__.py":
            for nom, ln in importados.items():
                if nom not in usados and nom != "*" and nom not in self.src.split("__all__")[-1][:0]:
                    if not re.search(rf"['\"]{nom}['\"]", self.src):
                        self.add("IMPORT_SIN_USO", ln, nom)
        for i, l in enumerate(self.lines, 1):
            if SECRETO.search(l):
                self.add("SECRETO_HARDCODE", i, l.strip()[:60])
            if OBVIO.match(l.strip()):
                self.add("COMENTARIO_OBVIO", i, l.strip()[:60])
            if re.search(r"#\s*(TODO|FIXME|XXX)\b", l) or re.search(r"your[_ ]code[_ ]here|implement (this|logic)", l, re.I):
                self.add("MUERTO_TODO", i, l.strip()[:60])
        for firma, fs in self.cuerpos.items():
            if len(fs) > 1:
                self.add("FUNC_DUPLICADA", fs[0][1], ", ".join(f"{n}@{ln}" for n, ln in fs))

def escanear(raiz):
    raiz = pathlib.Path(raiz)
    todos = []
    ignorar = {".venv", "venv", "node_modules", ".git", "site-packages", "__pycache__", "build", "dist"}
    archivos = [raiz] if raiz.is_file() else [p for p in raiz.rglob("*.py") if not ignorar & set(p.parts)]
    for p in archivos:
        try:
            src = p.read_text(encoding="utf-8", errors="replace")
            tree = ast.parse(src)
        except SyntaxError as e:
            todos.append((str(p), e.lineno or 0, "SYNTAX", str(e))); continue
        s = Scanner(p, src); s.visit(tree); s.fin(tree)
        todos += s.hallazgos
    return sorted(set(todos)), len(archivos)

def reporte(hallazgos, n):
    cnt = collections.Counter(h[2] for h in hallazgos)
    out = [f"# Reporte de 'olores' de código IA\n", f"Archivos analizados: {n} | Hallazgos: {len(hallazgos)}\n",
           "## Resumen\n", "| Regla | Cantidad | Qué significa |", "|---|---|---|"]
    for r, c in cnt.most_common():
        out.append(f"| {r} | {c} | {REGLAS.get(r, r)} |")
    out.append("\n## Detalle\n")
    for f, l, r, d in hallazgos:
        out.append(f"- `{f}:{l}` **{r}** {d}")
    return "\n".join(out)

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(__doc__); sys.exit(1)
    h, n = escanear(sys.argv[1])
    txt = reporte(h, n)
    print(txt)
    if "--md" in sys.argv:
        pathlib.Path(sys.argv[sys.argv.index("--md") + 1]).write_text(txt, encoding="utf-8")
