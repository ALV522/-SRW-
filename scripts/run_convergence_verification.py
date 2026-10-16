from __future__ import annotations
import compileall, json, subprocess, sys, unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
BACKEND=ROOT/'backend'

def main()->int:
    sys.path.insert(0,str(BACKEND))
    ok_compile=compileall.compile_dir(str(BACKEND/'srw'),quiet=1)
    suite=unittest.defaultTestLoader.discover(str(ROOT/'convergence_tests'),pattern='test_*.py')
    result=unittest.TextTestRunner(verbosity=2).run(suite)
    js=[]
    for path in sorted((ROOT/'frontend/dist').glob('*.js')):
        proc=subprocess.run(['node','--check',str(path)],capture_output=True,text=True) if shutil_which('node') else None
        js.append({'file':path.name,'status':'PASS' if proc and proc.returncode==0 else ('SKIPPED_NO_NODE' if proc is None else 'FAIL')})
    release=json.loads((BACKEND/'srw/release_state.json').read_text(encoding='utf-8'))
    payload={'compile':'PASS' if ok_compile else 'FAIL','unittest_count':result.testsRun,'unittest':'PASS' if result.wasSuccessful() else 'FAIL','javascript':js,'release':release}
    print(json.dumps(payload,ensure_ascii=False,indent=2))
    return 0 if ok_compile and result.wasSuccessful() and all(x['status']!='FAIL' for x in js) else 1

def shutil_which(name):
    import shutil
    return shutil.which(name)
if __name__=='__main__':raise SystemExit(main())
