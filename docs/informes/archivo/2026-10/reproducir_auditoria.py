import ast, collections, contextlib, importlib, importlib.abc, importlib.util, inspect, io, json, linecache, math, os, pkgutil, socket, sqlite3, subprocess, sys, types, warnings, zipfile
from pathlib import Path
from types import SimpleNamespace as NS
from unittest.mock import patch
from pyfakefs.fake_filesystem_unittest import Patcher
import numpy, openai, pocketflow, requests, yaml

sys.dont_write_bytecode=True
os.environ.update({'DEEPSEEK_API_KEY':'AUDIT_NO_REAL_KEY','PREGUNTAS_LOG':'0','LAYA_LOG_DECISIONES':'0','HF_HUB_OFFLINE':'1','TRANSFORMERS_OFFLINE':'1','AGENT_ALLOWED_DIRS':'/mnt/data','MEMORIA_PREFILTRO':'0','RAG_PREFILTRO':'0','CHAT_STREAM':'0','HITL_AUTO':'1','HITL_WEB':'0','USE_VOTACION':'1','LAYA_UNSURE_HIGH':'0.85','LAYA_MODO':'enforce','LAYA_CALIBRACION_ROUTER':''})
os.chdir('/mnt/data')
with zipfile.ZipFile('/mnt/data/deepseek-flow-10-15-main.zip') as z:
    sources={i.filename.split('/',1)[1]:z.read(i).decode('utf-8') for i in z.infolist() if not i.is_dir()}
class ZipSource(importlib.abc.MetaPathFinder,importlib.abc.Loader):
    def find_spec(self,fullname,path=None,target=None):
        stem=fullname.replace('.','/')
        for rel,pkg in [(stem+'.py',False),(stem+'/__init__.py',True)]:
            if rel in sources:
                spec=importlib.util.spec_from_loader(fullname,self,is_package=pkg)
                spec.loader_state=rel;spec.origin='/mnt/data/'+rel
                return spec
        if fullname in {'banco','banco.probes'}:
            spec=importlib.util.spec_from_loader(fullname,self,is_package=True);spec.loader_state=None;return spec
    def create_module(self,spec):return None
    def exec_module(self,module):
        rel=module.__spec__.loader_state
        if rel is None:module.__path__=['/mnt/data/'+module.__name__.replace('.','/')];return
        filename='/mnt/data/'+rel;module.__file__=filename
        if module.__spec__.submodule_search_locations is not None:module.__path__=[str(Path(filename).parent)]
        linecache.cache[filename]=(len(sources[rel]),None,sources[rel].splitlines(True),filename)
        exec(compile(sources[rel],filename,'exec'),module.__dict__)
sys.meta_path.insert(0,ZipSource())
original_iter=pkgutil.iter_modules
def zip_iter(path=None,prefix=''):
    if path and '/mnt/data/modules' in list(path):
        for n in sorted(sources):
            if n.startswith('modules/') and n.endswith('.py') and n!='modules/__init__.py':
                yield pkgutil.ModuleInfo(None,prefix+Path(n).stem,False)
    else: yield from original_iter(path,prefix)
pkgutil.iter_modules=zip_iter

def blocked(*a,**k):raise RuntimeError('AUDIT: external action deliberately blocked')
socket.create_connection=blocked;socket.socket.connect=blocked;socket.socket.connect_ex=blocked
subprocess.run=blocked
# The real Laya release is inspected statically by the parent; inference is impossible here.
sys.modules['laya']=NS(load=blocked)
import nodes, flow, supervisor, evals, effective_n, bench_juez, juez, research, debate, informe, rag, heartbeat
from utils import policy, fs_tools, call_llm, laya, laya_routing, contexto, compaccion, hitl_web, conformal
from modules import coding, memoria
mod_evals=importlib.import_module('modules.evals')

findings=[]
def probe(id,title,severity,where,fix):
    def deco(fn):
        out=io.StringIO()
        try:
            with contextlib.redirect_stdout(out), contextlib.redirect_stderr(out): evidence=fn()
            findings.append(dict(id=id,titulo=title,prioridad=severity,ubicacion=where,estado='reproducido',evidencia=evidence,correccion=fix,log=out.getvalue()[:1800]))
        except BaseException as exc:
            findings.append(dict(id=id,titulo=title,prioridad=severity,ubicacion=where,estado='prueba_inconclusa',error=type(exc).__name__+': '+str(exc),log=out.getvalue()[:1800],correccion=fix))
        return fn
    return deco

@probe('A01','HITL auto acepta comandos que escriben o ejecutan código','P0','utils/policy.py:51-71,115-183; modules/coding.py:162-207','Desactivar AUTO por defecto; usar argv sin shell y validar opciones por herramienta. pytest requiere confianza explícita o aislamiento.')
def _():
    cmds=['find . -delete','sort -o audit_marker.txt entrada.txt','echo hola\ntouch audit_marker.txt','echo hola & touch audit_marker.txt','pytest -p plugin_local']
    decisions={c:policy.clasificar(c) for c in cmds}
    assert all(v=='auto' for v in decisions.values())
    calls=[]
    with patch.object(coding,'_approve',side_effect=AssertionError('No debe pedir aprobación en la reproducción')),patch.object(coding.subprocess,'run',side_effect=lambda *a,**k:(calls.append({'shell':k.get('shell'),'command':a[0]}) or NS(returncode=0,stdout='',stderr=''))):
        out=coding.run_command(cmds[2])
    assert calls and calls[0]['shell'] is True
    return {'clasificaciones':decisions,'subproceso_simulado':calls,'resultado':out,'comandos_reales_ejecutados':0}

@probe('A02','Un stream cancelado conserva tool calls ejecutables','P1','utils/call_llm.py:171-229; nodes.py:335-338','Transportar estado de finalización; al cancelar o fallar descartar llamadas pendientes y no despacharlas. Cerrar siempre el stream con finally.')
def _():
    class FakeStream:
        def __iter__(self):
            yield NS(choices=[NS(delta=NS(content=None,tool_calls=[NS(index=0,id='c1',function=NS(name='write_file',arguments='{"path":"audit_marker.txt","content":"demo"}'))]))])
            raise KeyboardInterrupt()
        def close(self):pass
    client=NS(chat=NS(completions=NS(create=lambda **k:FakeStream())))
    with patch.object(call_llm,'_client',return_value=client):msg=call_llm.call_llm_agent_stream([{'role':'user','content':'demo'}],nodes.TOOLS)
    shared={'messages':[]};action=nodes.AgentStep().post(shared,None,msg)
    assert action=='tool' and msg.tool_calls
    return {'interrupcion':'KeyboardInterrupt','accion_posterior':action,'tool_conservada':msg.tool_calls[0].function.name,'archivos_escritos':0}

@probe('A03','El presupuesto retira esquemas pero no bloquea tool calls nativas','P1','nodes.py:279-338,348-365; flow.py:23-30','Comprobar presupuesto y capacidades en la frontera de despacho, no solo al construir la petición al modelo; rechazar llamadas si tools=None.')
def _():
    tc=NS(id='c1',function=NS(name='read_file',arguments='{"path":"demo.txt"}'))
    fake=NS(content=None,tool_calls=[tc]);messages=[{'role':'system','content':'s'},{'role':'user','content':'q'}]
    shared={'messages':messages,'tool_rounds':8,'max_tool_rounds':8}
    n=nodes.AgentStep();inp=n.prep(shared);assert inp[1] is None
    with patch.object(nodes,'call_llm_agent',return_value=fake):result=n.exec(inp)
    action=n.post(shared,inp,result)
    assert action=='tool'
    return {'presupuesto_agotado':True,'tools_ofrecidas':None,'respuesta_simulada':'tool_call nativa','accion':action,'alcance':'Prueba de defensa de frontera; no demuestra que DeepSeek emita esta respuesta en producción.'}

@probe('A04','El log aplicada se escribe antes del veto del segundo voto','P1','nodes.py:506-535','Registrar la ruta FINAL después del voto, incluyendo causa y resultado del veto; conservar por separado la propuesta.')
def _():
    events=[];received=[];config=laya_routing.RouterConfig(modo='enforce',umbral=.85)
    detail={'choice':'directo','probabilities':{'directo':.99,'herramientas':.01}}
    with patch.object(laya_routing,'config_router',return_value=config),patch.object(laya_routing,'registrar_decision',side_effect=lambda event,**k:events.append(event.copy())),patch.object(nodes,'voto_confirmacion_router',side_effect=lambda arg:(received.append(arg) or 'herramientas')):
        action=nodes.LayaRouter().post({}, {'pregunta':'hola'},detail)
    assert events[0]['aplicada']=='directo' and action=='herramientas'
    return {'aplicada_en_log':events[0]['aplicada'],'accion_real':action,'argumento_recibido_por_voto':received[0]}

@probe('A05','El voto recibe un dict y vuelve a envolverlo como pregunta textual','P2','nodes.py:429-465,528','Pasar prep_res["pregunta"] al voto, o compartir una función de construcción del estado sin doble serialización.')
def _():
    seen=[]
    def fake(state,*a,**k):seen.append(state);return {'confirma_herramientas':('directo',.99)}
    with patch.object(laya,'disponible',return_value=True),patch.object(laya,'preguntar',side_effect=fake):nodes.voto_confirmacion_router({'pregunta':'hola'})
    assert seen[0]['pregunta']=="{'pregunta': 'hola'}"
    return {'esperado':{'pregunta':'hola'},'enviado_al_checkpoint':seen[0],'efecto_en_precision':'No medido; incompatibilidad de entrada demostrada.'}

@probe('A06','Sin Laya el prefiltro recorta y memoria anuncia que filtró con Laya','P1','utils/contexto.py:65-81; modules/memoria.py:100-120','Ante ausencia/fallo devolver todas las unidades. Separar un límite determinista independiente del filtro aprendido.')
def _():
    units=list(range(12))
    with patch.object(contexto,'_puntuar',return_value=None):
        result=contexto.elegir_por_laya('q',units,8)
        with patch.dict(os.environ,{'MEMORIA_PREFILTRO':'1','MEMORIA_PREFILTRO_N':'8'}):selected,used=memoria._prefiltrar('q',units)
    assert result==units[:8] and used is True
    return {'entrada':12,'salida_sin_modelo':len(result),'memoria_marca_prefiltro_activo':used}

@probe('A07','El prefiltro de memoria puntúa rutas, no contenido de notas','P1','modules/memoria.py:42-46,115; utils/contexto.py:95-105','Construir candidatos con id/ruta y contenido acotado; pasar el contenido al modelo y recuperar objetos originales por id.')
def _():
    captured=[]
    def fake(states,*a,**k):captured.extend(states);return [{'aporta_contexto':('si',.9)} for _ in states]
    with patch.object(laya,'disponible',return_value=True),patch.object(laya,'preguntar_lote',side_effect=fake):scores=contexto._puntuar('decisión de arquitectura',[Path('/mnt/data/nota.md')],'LAYA_MODEL_PREFILTRO')
    assert captured[0]['bloque']=='/mnt/data/nota.md'
    return {'estado_enviado':captured[0],'contenido_de_la_nota_enviado':False}

@probe('A08','El lector de memoria sigue symlinks fuera de su raíz','P1','modules/memoria.py:42-46,70-78','Aplicar contención y política de enlaces también a memoria, tanto al enumerar como al abrir cada nota.')
def _():
    with Patcher() as p:
        p.fs.create_dir('/mnt/data/allowed/mem')
        p.fs.create_file('/mnt/data/outside/privado.md',contents='MARCADOR_PRIVADO_AUDITORIA')
        p.fs.create_symlink('/mnt/data/allowed/mem/enlace.md','/mnt/data/outside/privado.md')
        with patch.dict(os.environ,{'AGENT_ALLOWED_DIRS':'/mnt/data/allowed','MEMORIA_DIR':'/mnt/data/allowed/mem','MEMORIA_PREFILTRO':'0'}):
            normal=fs_tools.read_file('/mnt/data/outside/privado.md');memory=memoria.memory_search('MARCADOR')
        assert normal.startswith('ERROR') and 'MARCADOR_PRIVADO_AUDITORIA' in memory
    return {'read_file_bloquea':True,'memory_search_revela_marcador_externo':True,'filesystem':'simulado en RAM; ningún archivo privado real leído'}

@probe('A09','La tool evals acepta salida fuera de AGENT_ALLOWED_DIRS','P1','modules/evals.py:22-31; evals.py:572-576','Validar salida antes de ejecutar el bench y escribir mediante escribir_salida o un directorio de artefactos autorizado.')
def _():
    with Patcher() as p:
        p.fs.create_dir('/mnt/data/allowed/runs')
        with patch.dict(os.environ,{'AGENT_ALLOWED_DIRS':'/mnt/data/allowed'}),patch.object(evals,'_git_sha',return_value='audit'),patch.object(evals,'correr_bench',return_value=({'estado':'ok','score':1.0},None)),patch.object(evals,'comparar_baseline',return_value={}),patch.object(evals,'linter_runs',return_value={}),patch.object(evals,'costos_runs',return_value=[]),patch.object(evals,'informe_markdown',return_value='# AUDIT'):
            result=mod_evals.evals('/mnt/data/allowed/runs','/mnt/data/outside')
        files=list(Path('/mnt/data/outside').glob('*.md'))
        assert files and files[0].read_text()=='# AUDIT'
    return {'escritura_externa_a_raices':True,'resultado':result,'filesystem':'simulado en RAM'}

@probe('A10','El bench del router no aplica la política actual de producción','P1','evals.py:63-67,103-145; utils/laya_routing.py:113-146; nodes.py:495-535','Reutilizar el mismo evaluador de política y la misma construcción de estado; medir voto, shadow/off y conformal por separado.')
def _():
    detail={'choice':'directo','probabilities':{'directo':.99,'herramientas':.01}}
    bench=evals._decision('directo',.99,lambda c:'met')
    config=laya_routing.RouterConfig(modo='shadow',umbral=.85)
    proposed,_,_=laya_routing.decide(detail,config);production=laya_routing.ruta_aplicada(proposed,config)
    assert bench=='directo' and production=='herramientas'
    return {'bench':bench,'produccion_shadow':production,'otras_diferencias_estaticas':['no segundo voto','no q conformal','entrada del bench sin truncamiento de 1000 caracteres']}

@probe('A11','Evals degradado falla si ya existe un baseline válido','P1','evals.py:160-182,564-565','No restar métricas None; retornar estado no evaluable conservando el baseline cuando no hubo bench.')
def _():
    baseline=NS(is_file=lambda:True,read_text=lambda **k:json.dumps({'score':.9,'ece':.1}))
    try:evals.comparar_baseline(evals._placeholder_bench('sin modelo'),baseline)
    except TypeError as exc:return {'error':str(exc),'condicion':'sin modelo/test + baseline previo con score numérico'}
    raise AssertionError('No reprodujo')

@probe('A12','Fallo de inferencia Laya aborta el supervisor en vez de usar fallback','P1','supervisor.py:182-206; utils/laya.py:103-112','Capturar fallos de inferencia/contrato en la frontera local del supervisor y continuar por elegir_con_deepseek; no confundir carga disponible con inferencia fiable.')
def _():
    with patch.object(laya,'disponible',return_value=True),patch.object(laya,'preguntar',side_effect=RuntimeError('inferencia simulada falló')) as infer,patch.object(supervisor,'elegir_con_deepseek',return_value='finish') as fallback:
        try:supervisor.ElegirSiguiente(max_retries=2,wait=0).run({'tarea':'demo'})
        except RuntimeError as exc:
            assert infer.call_count==2 and fallback.call_count==0
            return {'inferencias':infer.call_count,'fallback_llamadas':fallback.call_count,'error':str(exc)}
    raise AssertionError('No reprodujo')

@probe('A13','NaN en el umbral acepta directo por comparación no válida','P1','utils/laya_routing.py:65-68,139-141; utils/call_llm.py:66-72','Validar math.isfinite y rango del umbral; configuración inválida debe fallar al iniciar o abstenerse.')
def _():
    with patch.dict(os.environ,{'LAYA_UNSURE_HIGH':'nan'}):config=laya_routing.config_router()
    response={'choice':'directo','probabilities':{'directo':.51,'herramientas':.49}}
    action,reason,_=laya_routing.decide(response,config)
    assert math.isnan(config.umbral) and action=='directo'
    return {'umbral':'NaN','p_directo':.51,'propuesta':action,'causa':reason,'nota':'El segundo voto aún podría vetar; se demuestra bypass de la primera compuerta.'}

@probe('A14','LIMIT SQL no es un tope real y fetchall puede cargar todo','P1','modules/db.py:16-24,90-114','Conectar mode=ro, usar fetchmany(MAX_FILAS+1), truncar celdas y aplicar deadline/progress_handler independiente del busy timeout.')
def _():
    outputs={}
    for query in ['SELECT x FROM t LIMIT -1','SELECT x FROM t -- limit']:
        con=sqlite3.connect(':memory:');con.row_factory=sqlite3.Row;con.execute('CREATE TABLE t(x INTEGER)');con.executemany('INSERT INTO t VALUES (?)',[(i,) for i in range(200)])
        with patch.object(importlib.import_module('modules.db'),'_con',return_value=con):out=importlib.import_module('modules.db').sql(query)
        outputs[query]=len(out.splitlines())-2
    assert all(n==200 for n in outputs.values())
    return {'MAX_FILAS_declarado':50,'filas_devueltas':outputs,'base':'SQLite :memory:'}

@probe('A15','El esquema declara memory_search sin argumentos pero Python exige query','P2','modules/memoria.py:49,181-186','Definir memory_search(query="") y añadir prueba automática de compatibilidad esquema/firma para todos los módulos.')
def _():
    bad=[]
    impls={'list_files':fs_tools.list_files,'read_file':fs_tools.read_file,'search_files':fs_tools.search_files,**nodes.MODULE_IMPLS}
    for tool in nodes.TOOLS:
        f=tool['function'];fn=impls[f['name']];required=set(f.get('parameters',{}).get('required',[]))
        mandatory={n for n,p in inspect.signature(fn).parameters.items() if p.default is inspect.Parameter.empty and p.kind in (p.POSITIONAL_OR_KEYWORD,p.KEYWORD_ONLY)}
        if mandatory-required:bad.append({'tool':f['name'],'Python_requiere_pero_esquema_no':sorted(mandatory-required)})
    result=fs_tools.run_tool_call({'id':'m1','function':{'name':'memory_search','arguments':'{}'}},nodes.MODULE_IMPLS)
    assert 'missing 1 required' in result['content'] and bad
    return {'tools':len(nodes.TOOLS),'incompatibilidades':bad,'resultado':result['content']}

@probe('A16','ExecuteTools registra exit no cero y rechazo como éxito','P2','nodes.py:362-364; modules/coding.py:183-195,214','Retornar ToolResult estructurado con status/error/exit_code; no inferir éxito por prefijo de texto.')
def _():
    events=[]
    calls=[{'id':'c1','function':{'name':'run_command','arguments':'{}'}}]
    for content in ['exit 1\nprueba fallida','RECHAZADO por el usuario']:
        with patch.object(nodes,'run_tool_call',return_value={'role':'tool','tool_call_id':'c1','content':content}),patch.object(nodes,'evento_tool',side_effect=lambda name,ok,sec:events.append({'content':content,'ok':ok})):
            nodes.ExecuteTools().exec(calls)
    assert all(e['ok'] for e in events)
    return events

@probe('A17','La compacción puede borrar la tarea activa sin guardar un resumen','P1','utils/compaccion.py:146-157,165-201; nodes.py:258-274','Preservar la petición activa y el estado de trabajo; guardar un resumen real o snapshot antes de eliminar. No afirmar que los hechos están en memoria si no se persistieron.')
def _():
    messages=[{'role':'system','content':'s'},{'role':'user','content':'OBJETIVO_UNICO_ACTIVO'}]
    for i in range(10):
        messages.extend([{'role':'assistant','content':None,'tool_calls':[{'id':str(i),'type':'function','function':{'name':'read_file','arguments':'{}'}}]},{'role':'tool','tool_call_id':str(i),'content':'X'*1000}])
    out=compaccion.compactar(messages,4000)
    assert 'OBJETIVO_UNICO_ACTIVO' not in compaccion.serializar(out)
    return {'mensajes_antes':len(messages),'despues':len(out),'objetivo_activo_conservado':False,'texto_insertado':out[1]['content']}

@probe('A18','Effective N no tolera JSON válido de forma inválida','P2','effective_n.py:88-111; informe.py:leer_registro','Reutilizar leer_registro y distinguir JSON inválido de estructura inválida en los conteos.')
def _():
    outcomes={}
    with Patcher() as p:
        p.fs.create_dir('/mnt/data')
        for i,obj in enumerate([[],None,{'fields':None,'answers':{}}]):
            f=Path('/mnt/data')/('case'+str(i)+'.jsonl');p.fs.create_file(f,contents=json.dumps(obj)+'\n')
            try:effective_n.HashFile().exec(f)
            except Exception as exc:outcomes[json.dumps(obj)]=type(exc).__name__
    assert len(outcomes)==3
    return outcomes

@probe('A19','Reutilizar un flow Effective N conserva los params de la primera ejecución','P2','effective_n.py:277-304','Eliminar monkeypatch de instancia/cierre; implementar Flow.prep o un subflujo que reciba parámetros explícitos por ejecución.')
def _():
    calls=[]
    with patch.object(effective_n,'collect_files',side_effect=lambda *args:(calls.append(args[0]) or [])):
        f=effective_n.create_effective_n_flow()
        f.run({'folder':'primera','salida':None})
        f.run({'folder':'segunda','salida':None})
    assert calls==['primera','primera']
    return {'carpetas_solicitadas':['primera','segunda'],'carpetas_procesadas':calls,'alcance':'API de reutilización del mismo objeto; wrappers actuales suelen crear un flow nuevo.'}

@probe('A20','Un pre-hook de seguridad que lanza se ignora y la tool ejecuta','P1','utils/fs_tools.py:391-405','Distinguir hooks de seguridad obligatorios de observabilidad best-effort; fallo del control obligatorio debe vetar.')
def _():
    ran=[]
    with patch.dict(fs_tools.HOOKS_PRE,{'audit_dummy':[lambda tc:(_ for _ in ()).throw(RuntimeError('control roto'))]}):
        out=fs_tools.run_tool_call({'id':'a','function':{'name':'audit_dummy','arguments':'{}'}},{'audit_dummy':lambda:(ran.append(True) or 'ok')})
    assert ran and out['content']=='ok'
    return {'hook':'RuntimeError','implementacion_ejecutada':True,'efecto':'dummy sin efectos externos','nota':'Diseño fail-open demostrado; no implica que el denylist actual lance normalmente.'}

@probe('A21','Cancelación HITL web deja el pedido pendiente sin limpiar','P2','utils/hitl_web.py:200-228','Limpiar _pendiente en finally y manejar cancelación como rechazo o propagarla después de limpiar.')
def _():
    with patch.object(hitl_web,'_arrancar',return_value=8765),patch.object(hitl_web.threading.Event,'wait',side_effect=KeyboardInterrupt()):
        try:hitl_web.aprobar('demo','sin efectos')
        except KeyboardInterrupt:pass
        remained=hitl_web._pendiente is not None
        hitl_web._pendiente=None
    assert remained
    return {'KeyboardInterrupt_propagado':True,'pedido_pendiente_tras_interrupcion':remained,'servidor_real_iniciado':False}

@probe('A22','Las duraciones anidadas se suman como si fueran tiempo total','P2','evals.py:415-426; nodes.py:357-364; utils/tracing.py:55-94','Separar wall time, tiempo inclusivo/exclusivo por span y uso real del proveedor; no llamar coste económico a segundos acumulados.')
def _():
    events=[{'nodo':'run_command','accion':'ok','seg':10},{'nodo':'ExecuteTools','accion':'default','seg':10}]
    out=evals.costo_traza(events)
    assert out['total']==20
    return {'ejemplo':'Una tool de 10 s incluida en ExecuteTools de 10 s','total_reportado':out['total'],'tiempo_transcurrido_del_ejemplo':10}

@probe('A23','Un tamaño de batch Laya sin límite pasa todos los estados al forward','P2','utils/laya.py:126-134; utils/contexto.py:95-101; laya/agent.py:711-731 (paquete)','Exponer batch_size y límites de candidatos/tokens; medir pico de memoria, no solo número de checkpoints retenidos.')
def _():
    calls=[]
    class Fake:
        def predict_batch(self,states,questions,**kw):calls.append({'n':len(states),'kwargs':kw});return [{'answers':{}} for _ in states]
    with patch.object(laya,'agente',return_value=Fake()):result=laya.preguntar_lote(['x']*1000,{})
    assert calls[0]['n']==1000 and 'batch_size' not in calls[0]['kwargs']
    return {'llamada_simulada':calls[0],'nota':'No se midió OOM; se comprueba ausencia del límite que ofrece la dependencia.'}

@probe('A24','El tope de checkpoints se aplica después de cargar uno adicional','P2','utils/laya.py:37-78','Gestionar presupuesto de carga antes del nuevo modelo o aislar en proceso; gc.collect no garantiza devolución de RSS/VRAM al SO.')
def _():
    observed=[]
    def load(key):observed.append({'nuevo':key,'ya_retenidos':len(laya._agentes)});return object()
    with patch.object(laya,'_agentes',{}),patch.object(laya,'_errores',{}),patch.object(laya,'_uso',{}),patch.object(laya,'MAX_EN_PROCESO',2),patch.object(laya,'_setting',side_effect=lambda name,default=None:name),patch.dict(sys.modules,{'laya':NS(load=load)}):
        for key in ['audit_a','audit_b','audit_c']:laya.agente(key)
        retained=len(laya._agentes)
    assert observed[-1]['ya_retenidos']==2 and retained==2
    return {'carga_tercer_modelo':observed[-1],'retenidos_al_final':retained,'pico_bytes':'No medido; la política permite solapar 3 cargas/objetos con tope de caché 2.'}

@probe('A25','El log de preguntas guarda texto por defecto aunque el log de routing sea opt-in','P2','nodes.py:20-42,213; .env.example:32-37,111-114','Unificar configuración de privacidad, documentar cada sink, minimizar/redactar datos y definir retención y permisos.')
def _():
    with Patcher() as p:
        p.fs.create_dir('/mnt/data')
        env=dict(os.environ);env.pop('PREGUNTAS_LOG',None)
        with patch.dict(os.environ,env,clear=True):nodes.registrar_pregunta('MARCADOR_TEXTO_USUARIO','/mnt/data/questions.jsonl')
        text=Path('/mnt/data/questions.jsonl').read_text();assert 'MARCADOR_TEXTO_USUARIO' in text
    return {'PREGUNTAS_LOG_no_definido':'se guarda texto','LAYA_LOG_PREGUNTA_default':0,'filesystem':'RAM; no datos del usuario'}

@probe('A26','Guardado del resumen de sesión sigue un symlink colgante','P1','modules/memoria.py:145-165','Usar creación exclusiva y contención del destino resuelto también en guardar_resumen_sesion; compartir escritor seguro con memory_save.')
def _():
    with Patcher() as p:
        p.fs.create_dir('/mnt/data/allowed/mem');p.fs.create_dir('/mnt/data/outside')
        target='/mnt/data/outside/created.md'
        link='/mnt/data/allowed/mem/sesion_'+memoria.date.today().isoformat()+'.md'
        p.fs.create_symlink(link,target)
        with patch.dict(os.environ,{'MEMORIA_DIR':'/mnt/data/allowed/mem'}):memoria.guardar_resumen_sesion('MARCADOR_RESUMEN')
        exists=Path(target).is_file()
        assert exists
    return {'destino_externo_creado_via_symlink_colgante':exists,'condicion':'enlace preexistente dentro de memoria','filesystem':'simulado en RAM'}

@probe('A27','El dispatcher no contiene tool calls con envoltura incompleta','P2','utils/fs_tools.py:379-415; nodes.py:356-362','Validar envelope, id, function y argumentos antes de hooks; producir resultado de error o cancelar lote de forma explícita.')
def _():
    errors=[]
    for tc in [{},{'function':{}},{'function':{'name':'unknown','arguments':'{}'}}]:
        try:fs_tools.run_tool_call(tc)
        except Exception as exc:errors.append(type(exc).__name__+': '+str(exc))
    assert len(errors)==3
    return {'entradas_incompletas':3,'excepciones_escapan':errors}

@probe('A28','El bench del juez excluye de cita_ok casos que lanzan excepciones','P2','bench_juez.py:183-198,218-225','Contar fallo de cita cuando el caso exigía cita y no produjo respuesta; distinguir no aplicable de no evaluable y de fallo.')
def _():
    cases=[{'id':'ok','pregunta':'ok','cita_archivo':'demo.py'},{'id':'broken','pregunta':'broken','cita_archivo':'demo.py'}]
    def respond(q):
        if q=='broken':raise RuntimeError('fallo simulado')
        return 'respuesta',None
    with patch.object(bench_juez,'cita_ok',return_value=True),patch.object(bench_juez,'detalle_fallo',return_value=[]):out=bench_juez.correr(cases,respond)
    assert out['n_con_cita']==1 and out['cita_ok']==1.0
    return {'casos_que_exigen_cita':2,'casos_con_respuesta':1,'denominador_cita_ok':out['n_con_cita'],'cita_ok_reportado':out['cita_ok'],'respuesta_ok_reportado':out['respuesta_ok']}

# Non-executing validation across every source file.
syntax=[];asserts=[]
for name,text in sources.items():
    if not name.endswith('.py'):continue
    try:tree=ast.parse(text,filename=name)
    except SyntaxError as exc:syntax.append({'file':name,'error':str(exc)});continue
    if not name.startswith('tests/'):
        for node in ast.walk(tree):
            if isinstance(node,ast.Assert):asserts.append({'file':name,'line':node.lineno,'test':ast.unparse(node.test)})
calib=[json.loads(l) for l in sources['banco/calibracion_router_2026-10-08.jsonl'].splitlines() if l.strip()]
result={'scope':{'files':len(sources),'python_files':sum(n.endswith('.py') for n in sources),'python_lines':sum(len(t.splitlines()) for n,t in sources.items() if n.endswith('.py')),'syntax_failures':syntax,'framework':'PocketFlow 0.0.3','execution':'isolated reproductions, NOT the original full pytest suite','external_model_calls':0,'real_shell_commands_from_harness':0,'filesystem_probes':'pyfakefs in-memory only'},'findings':findings,'runtime_asserts':asserts,'calibration':{'rows':len(calib),'labels':dict(collections.Counter(str(c.get('etiqueta')) for c in calib)),'correct':sum(c.get('correcto') is True for c in calib),'source_labels':dict(collections.Counter(str(c.get('fuente')) for c in calib))}}
print('AUDIT_JSON_BEGIN')
print(json.dumps(result,ensure_ascii=False))
