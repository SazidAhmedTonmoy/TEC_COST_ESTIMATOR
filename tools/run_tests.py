"""Run every unittest module in isolated processes; fail if any module fails."""
import argparse,concurrent.futures,subprocess,sys,time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]

def run(path):
    start=time.monotonic()
    result=subprocess.run([sys.executable,'-m','unittest','discover','-s','tests','-p',path.name,'-v'],cwd=ROOT,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True)
    return path.name,result.returncode,result.stdout,time.monotonic()-start

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--workers',type=int,default=4);args=parser.parse_args()
    paths=sorted((ROOT/'tests').glob('test_*.py'))
    if not paths:raise SystemExit('No test modules found')
    start=time.monotonic();failed=[]
    with concurrent.futures.ThreadPoolExecutor(max_workers=max(1,min(args.workers,8))) as pool:
        for name,code,output,elapsed in pool.map(run,paths):
            print(f'\n{name} ({elapsed:.1f}s)\n{output}',flush=True)
            if code:failed.append(name)
    print(f'{len(paths)} modules completed in {time.monotonic()-start:.1f}s. Failed: {failed}',flush=True)
    return bool(failed)
if __name__=='__main__':sys.exit(main())
