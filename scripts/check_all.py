"""Run repeatable local checks; does not repeat behavioral model trials or live actions."""
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import subprocess
import sys


def run():
    root=Path(__file__).resolve().parents[1]
    commands=[
        [sys.executable,'-X','utf8','scripts/verify_team.py'],
        [sys.executable,'-X','utf8','-m','unittest','discover','-s','tests','-v'],
    ]
    checks=[]
    for command in commands:
        result=subprocess.run(command,cwd=root,capture_output=True,text=True,encoding='utf-8')
        checks.append({'command':command[3:],'exit_code':result.returncode,
                       'stdout':result.stdout,'stderr':result.stderr})
    return {'checked_at_utc':datetime.now(timezone.utc).isoformat(),
            'passed':all(not c['exit_code'] for c in checks),
            'checks':checks,'behavioral_trials_replayed':False,'live_platform_tested':False}


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--report',default='private/evaluation/automated-checks.json')
    args=parser.parse_args()
    root=Path(__file__).resolve().parents[1]
    target=(root/args.report).resolve()
    if not target.is_relative_to(root):parser.error('Report must be inside repository')
    report=run()
    target.parent.mkdir(parents=True,exist_ok=True)
    target.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({'passed':report['passed'],'report':str(target)}))
    raise SystemExit(0 if report['passed'] else 1)
