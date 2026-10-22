"""Run every unittest module in isolated processes; fail if any module fails."""
import argparse,concurrent.futures,os,subprocess,sys,tempfile,time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]

def run(path):
    start=time.monotonic()
    # Keep the account fallback private for the subprocess lifetime. Clear any
    # inherited Tender override so it follows a fixture's current account path;
    # a test may still set its own explicit Tender path when needed.
    with tempfile.TemporaryDirectory(prefix='conest-test-module-') as folder:
        environment=os.environ.copy()
        environment.update({
            'CONEST_DB_PATH':str(Path(folder)/'catalog.db'),
            'CONEST_TENDERS_DB_PATH':'',
        })
        result=subprocess.run([sys.executable,'-m','unittest','discover','-s','tests','-p',path.name,'-v'],cwd=ROOT,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True,env=environment)
    return path.name,result.returncode,result.stdout,time.monotonic()-start

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--workers',type=int,default=4);args=parser.parse_args()
    paths=sorted((ROOT/'tests').glob('test_*.py'))
    if not paths:raise SystemExit('No test modules found')
    start=time.monotonic();failed=[];failure_outputs=[]
    with concurrent.futures.ThreadPoolExecutor(max_workers=max(1,min(args.workers,8))) as pool:
        for name,code,output,elapsed in pool.map(run,paths):
            print(f'\n{name} ({elapsed:.1f}s)\n{output}',flush=True)
            if code:
                failed.append(name)
                failure_outputs.append((name,output))
    print(f'{len(paths)} modules completed in {time.monotonic()-start:.1f}s. Failed: {failed}',flush=True)
    # Make failing assertions visible at the bottom of GitHub Actions logs.
    for name,output in failure_outputs:
        print(f'\n::group::Failure details: {name}\n{output}\n::endgroup::',flush=True)
        print(f'::error title=TEC ConEst tests::{name} failed; expand failure details above',flush=True)
    return bool(failed)
if __name__=='__main__':sys.exit(main())
