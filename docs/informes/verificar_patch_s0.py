"""Sondas S0; no sustituyen calidad.sh ni la suite pytest del repositorio.
Uso: python verificar_patch_s0.py ORIGINAL.zip CANDIDATO.zip --workdir CARPETA
Requiere pytest instalado para un subprocess sintético. No instala paquetes ni
extrae proyectos. Crea archivos planos de prueba y los elimina al finalizar.
"""
import argparse
import ast
import builtins
import contextlib
import copy
import io
import json
import os
from pathlib import Path
import subprocess
import sys
from types import ModuleType, SimpleNamespace
from unittest.mock import patch
import uuid
import zipfile


def leer(path):
    with zipfile.ZipFile(path) as z:
        names=[n for n in z.namelist() if n.endswith('/utils/citas.py')]
        if len(names)!=1:raise ValueError('ZIP sin implementación única de citas')
        prefix=names[0][:-len('utils/citas.py')]
        return {n:z.read(prefix+n).decode() for n in ('utils/citas.py','utils/fs_tools.py',
                'utils/policy.py','utils/politica_comandos.json','modules/coding.py')}


def politica(files):
    mod=ModuleType('policy_observada');mod.__file__='/__snapshot__/utils/policy.py'
    def read(path,*a,**k):
        if str(path)=='/__snapshot__/utils/politica_comandos.json':return files['utils/politica_comandos.json']
        raise RuntimeError('Lectura no autorizada por la sonda')
    with patch.object(Path,'read_text',read):exec(compile(files['utils/policy.py'],'utils/policy.py','exec'),mod.__dict__)
    return mod


def funciones(source,names,env):
    nodes=[copy.deepcopy(n) for n in ast.parse(source).body if isinstance(n,ast.FunctionDef) and n.name in names]
    if {n.name for n in nodes}!=set(names):raise ValueError('Faltan funciones esperadas')
    exec(compile(ast.Module(body=nodes,type_ignores=[]),'funciones_originales','exec'),env)


def cargar_citas(files,roots):
    fs=ModuleType('utils.fs_tools');fs.__dict__.update(Path=Path,allowed_roots=lambda:roots)
    funciones(files['utils/fs_tools.py'],{'_raiz_que_contiene','_resolve'},fs.__dict__)
    normal=builtins.__import__
    def importar(name,globals=None,locals=None,fromlist=(),level=0):
        if name=='utils.fs_tools':return fs
        return normal(name,globals,locals,fromlist,level)
    env={'__name__':'citas_observadas','__builtins__':{**vars(builtins),'__import__':importar}}
    exec(compile(files['utils/citas.py'],'utils/citas.py','exec'),env)
    return env


def observar_citas(files,workdir):
    name='__s0_'+uuid.uuid4().hex
    fixture=workdir/(name+'.py');alias=workdir/(name+'_alias.py')
    root=Path(sys.base_prefix).resolve()
    if workdir.is_relative_to(root):raise ValueError('workdir debe estar fuera de sys.base_prefix')
    denied=cargar_citas(files,[root]);allowed=cargar_citas(files,[workdir])
    created=[];real_read=Path.read_text;real_glob=Path.rglob
    def observar(env,ref):
        reads=[];scans=[]
        def read(path,*a,**k):
            if path.resolve()!=fixture.resolve():raise RuntimeError('La sonda no lee archivos ajenos')
            reads.append(path.name);return real_read(path,*a,**k)
        def glob(path,*a,**k):
            scans.append(str(path));return real_glob(path,*a,**k)
        with patch.object(Path,'read_text',read),patch.object(Path,'rglob',glob):
            result=env['verificar_citas'](ref+':1')
        return result,reads,scans
    try:
        absent,_,_=observar(denied,fixture.name)
        fixture.write_text('DATO_SINTETICO = 1\n');created.append(fixture)
        alias.symlink_to(fixture);created.append(alias)
        present,reads,scans=observar(denied,fixture.name)
        linked,alias_reads,alias_scans=observar(denied,alias.name)
        positive,positive_reads,_=observar(allowed,str(fixture))
        # Dos controles positivos con candidatos inyectados y lectura real.
        allowed['_RAICES_DE_CITAS']=('fuentes_controladas',)
        with patch.object(Path,'rglob',lambda *a,**k:iter([fixture])):
            fallback=allowed['verificar_citas'](name+'_missing.py:1')
        with patch.object(Path,'rglob',lambda *a,**k:iter([fixture,alias])):
            ambiguous=allowed['verificar_citas'](name+'_missing.py:1')
        return {'externa_no_lee':not reads and present['ok']==0,
                'existencia_externa_no_cambia_resultado':present==absent,
                'no_recorre_bases_externas':not scans,
                'alias_externo_no_lee':not alias_reads and linked['ok']==0,
                'lectura_autorizada':positive['ok']==1 and len(positive_reads)==1,
                'fallback_autorizado':fallback['ok']==1,'ambiguedad_conservada':ambiguous['ok']==0,
                'lecturas_externas':len(reads)+len(alias_reads),'recorridos_externos':len(scans)+len(alias_scans),
                'alcance':'citas completo, resolución original, roots controladas; dos casos con candidatos inyectados'}
    finally:
        for p in reversed(created):p.unlink(missing_ok=True)


def ejecutar(files,workdir,approve):
    pol=politica(files);asked=[];name='__s0_'+uuid.uuid4().hex
    testfile=workdir/(name+'_test.py');effect=workdir/(name+'_efecto.txt')
    command='python3 -m pytest '+testfile.name+' -q'
    ns={'__name__':'coding_observado','Path':Path,'subprocess':subprocess,
        'TIMEOUT_S':30,'SALIDA_MAX':4000,'clasificar':pol.clasificar,'explicar':pol.explicar,
        '_setting':lambda n,d:d,'_sale_de_raices':lambda c:False,'_configuracion_editada':lambda c:False,
        'RECHAZO':'RECHAZADO','RECHAZO_DOBLE':'RECHAZADO','Pedido':lambda *a:SimpleNamespace(args=a),
        '_approve':lambda p:asked.append(p) or approve,'registrar_aprobacion':lambda *a,**k:None,
        '_registrar_riesgo':lambda *a,**k:None,'recortar_chars':lambda s,n,*a:s[:n]}
    funciones(files['modules/coding.py'],{'_nivel','_aprobar','_ejecutar','run_command'},ns)
    testfile.write_text('from pathlib import Path\ndef test_controlado():\n'+
                       f'    Path({str(effect)!r}).write_text("efecto sintético")\n')
    clean={'PATH':os.environ.get('PATH','/usr/bin:/bin'),'PYTEST_DISABLE_PLUGIN_AUTOLOAD':'1',
           'PYTHONDONTWRITEBYTECODE':'1','PYTHONIOENCODING':'utf-8',
           'PYTEST_ADDOPTS':'-p no:cacheprovider --noconftest -c /dev/null'}
    try:
        stdout=io.StringIO()
        with patch.dict(os.environ,clean,clear=True),contextlib.redirect_stdout(stdout):
            result=ns['run_command'](command)
        return {'aprobador':approve,'pedidos':len(asked),'efecto':effect.exists(),
                'nivel':pol.clasificar(command),'resultado':result,
                'alcance':'funciones originales; roots/historial/telemetría controlados; subprocess real sobre test sintético'}
    finally:
        testfile.unlink(missing_ok=True);effect.unlink(missing_ok=True)


def comparar(original,candidate,workdir):
    workdir=Path(workdir).resolve()
    if not workdir.is_dir():raise ValueError('workdir debe existir')
    old=leer(original);new=leer(candidate);prev=Path.cwd()
    try:
        os.chdir(workdir)
        before=observar_citas(old,workdir);after=observar_citas(new,workdir)
        before_run=ejecutar(old,workdir,False);denied=ejecutar(new,workdir,False);approved=ejecutar(new,workdir,True)
    finally:os.chdir(prev)
    passed=(before['lecturas_externas']>0 and all(v for v in after.values() if isinstance(v,bool))
            and before_run['efecto'] and before_run['pedidos']==0
            and not denied['efecto'] and denied['pedidos']==1
            and approved['efecto'] and approved['pedidos']==1)
    return {'aceptacion_focal':passed,'citas_antes':before,'citas_despues':after,
            'pytest_antes_rechazo':before_run,'pytest_despues_rechazo':denied,
            'pytest_despues_aprobacion':approved,'suite_pytest_repo':'NO EJECUTADA','gate':'NO EJECUTADO'}


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('original',type=Path);p.add_argument('candidate',type=Path)
    p.add_argument('--workdir',type=Path,default=Path(__file__).resolve().parent)
    a=p.parse_args();result=comparar(a.original,a.candidate,a.workdir)
    print(json.dumps(result,ensure_ascii=False,indent=2))
    raise SystemExit(0 if result['aceptacion_focal'] else 1)
