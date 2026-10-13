"""Run the finite request roster with an exclusive lock and verified imports."""
import csv
import json
from pathlib import Path
import subprocess
import sys
import time

ROOT=Path('data/request_recovery')
STATE=ROOT/'normalized-state.json'

def finished(state_path=STATE, total=601):
    if not state_path.exists():
        return False
    data=json.loads(state_path.read_text())
    rosters=data.get('rosters',{})
    return bool(rosters) and all(int(roster.get('cursor_index',0)) >= total for roster in rosters.values())

def main():
    import fcntl
    ROOT.mkdir(parents=True,exist_ok=True)
    with (ROOT/'normalized.csv').open(newline='',encoding='utf-8') as stream:
        total=sum(1 for _ in csv.DictReader(stream))
    with (ROOT/'runner.lock').open('a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        for cycle in range(70):
            if finished(total=total):
                print('Request roster traversal complete; held profiles remain for review.',flush=True)
                return
            stamp=time.strftime('%Y%m%dT%H%M%SZ',time.gmtime())
            command=[sys.executable,'-u','-m','battlebot.harvest.auto_profile_harvester',
                '--input',str(ROOT/'normalized.csv'),'--output','profiles/request_recovery_v2/generated',
                '--needs-review','profiles/request_recovery_v2/needs_review',
                '--state-file',str(STATE),'--queue-mode','--max-per-cycle','10',
                '--skip-needs-review-existing','--quiet-skips']
            with (ROOT/f'harvest-{stamp}.log').open('w') as log:
                subprocess.run(command,stdout=log,stderr=subprocess.STDOUT,timeout=1800,check=True)
            subprocess.run([sys.executable,str(ROOT/'tools/import-request-recovery.py'),
                '--apply','--report',str(ROOT/f'import-{stamp}.json')],timeout=300,check=True)
            print(json.dumps({'cycle':cycle,'log':f'harvest-{stamp}.log'}),flush=True)
            time.sleep(60)
        raise RuntimeError('Bounded traversal did not complete; inspect state before rerunning')

if __name__=='__main__':
    main()
