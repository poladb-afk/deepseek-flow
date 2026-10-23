"""F11 · Disparar el agente desde cualquier lado. Todo el estado vive en la base de DBOS.

POST /tasks             {"task": str, "callback": url?}  → 202 {"id"}
POST /tasks/<id>/reply  {"answer": str}                  → 202 | 409
GET  /tasks/<id>                                         → {"id", "status", "pending" | "result" | "error"}
GET  /catalog                                            → estado de cada pieza
Si existe AGENT_TOKEN, se exige "Authorization: Bearer <token>" y los webhooks van firmados (X-Signature).
"""
import asyncio, hmac, json, os, re, sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import fractal_agent as fa


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        if not self.authorized():
            return
        if self.path == "/catalog":
            tk = fa.default_toolkit().restore(asyncio.run(fa.load_outcomes()))
            return self.reply(200, {n: {"kind": p.kind, "status": p.status, "wins": p.wins, "trials": p.trials}
                                    for n, p in tk.items()})
        match = re.fullmatch(r"/tasks/(\w+)", self.path)
        status = match and fa.summary(match[1])
        self.reply(200, status) if status else self.reply(404, {"error": "no existe"})

    def do_POST(self):
        if not self.authorized():
            return
        body = json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0))) or "{}")
        if self.path == "/tasks":
            return self.reply(202, {"id": fa.launch(body["task"], body.get("callback"))})
        if match := re.fullmatch(r"/tasks/(\w+)/reply", self.path):
            if fa.reply(match[1], body["answer"]):
                return self.reply(202, {"id": match[1]})
            return self.reply(409, {"error": "la tarea no está esperando una respuesta"})
        self.reply(404, {"error": "no existe"})

    def authorized(self):
        key = os.getenv("AGENT_TOKEN")
        if not key or hmac.compare_digest(self.headers.get("Authorization", ""), f"Bearer {key}"):
            return True
        self.reply(401, {"error": "token inválido"})

    def reply(self, code, body):
        data = json.dumps(body, ensure_ascii=False).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, *args):
        pass


if __name__ == "__main__":
    fa.start()  # al arrancar retoma lo que quedó a medias, con sus webhooks
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8000
    print(f"escuchando en :{port}", flush=True)
    ThreadingHTTPServer(("", port), Handler).serve_forever()
