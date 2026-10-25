"""Track actual artifact handoffs; does not run AI roles or grade semantic quality."""
import argparse
import hashlib
import json
from pathlib import Path


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def bounded(root, relative):
    path=(root/relative).resolve()
    if not path.is_relative_to(root.resolve()) or not path.is_file():
        raise ValueError(f'Missing or out-of-job artifact: {relative}')
    return path


def load(root):
    path=root/'handoffs.json'
    return json.loads(path.read_text(encoding='utf-8')) if path.exists() else {'version':1,'handoffs':[]}


def verify(root, records=None):
    root=Path(root).resolve()
    data=records if records is not None else load(root)
    errors=[]
    stale=set()
    seen={}
    superseded={entry['supersedes'] for entry in data['handoffs'] if entry.get('supersedes')}
    for entry in data['handoffs']:
        rid=entry['id']
        if rid in superseded:
            continue
        if rid in seen:
            errors.append(f'duplicate handoff {rid}')
        deps=entry.get('depends_on',[])
        if any(d not in seen for d in deps):
            errors.append(f'missing or unordered dependency {rid}')
            stale.add(rid)
        if any(d in stale for d in deps):
            errors.append(f'stale dependency {rid}')
            stale.add(rid)
        for kind in ('inputs','outputs'):
            for item in entry[kind]:
                try:
                    path=bounded(root,item['path'])
                    if digest(path)!=item['sha256']:
                        errors.append(f'{kind} changed: {rid}: {item["path"]}')
                        stale.add(rid)
                except ValueError as exc:
                    errors.append(str(exc)); stale.add(rid)
        for dependency in deps:
            if dependency in seen:
                parent=seen[dependency]
                if parent['product_key']!=entry['product_key'] and parent['product_key']!='agency':
                    errors.append(f'product mismatch: {dependency} -> {rid}')
                    stale.add(rid)
                consumed={(i['path'],i['sha256']) for i in entry['inputs']}
                produced={(i['path'],i['sha256']) for i in parent['outputs']}
                if not consumed.intersection(produced):
                    errors.append(f'no actual artifact consumed: {dependency} -> {rid}')
                    stale.add(rid)
        seen[rid]=entry
    return {'valid':not errors,'errors':errors,'stale_ids':sorted(stale),
            'handoff_count':len(data['handoffs']), 'active_handoff_count':len(seen),
            'semantic_quality_checked':False,'external_actions_verified':False}


def register(root, ident, role, product, inputs, outputs, dependencies=(), supersedes=None):
    root=Path(root).resolve()
    data=load(root)
    if any(r['id']==ident for r in data['handoffs']):
        raise ValueError('Handoff id already exists; record a new revision id')
    if not ident or not role or not product or not outputs:
        raise ValueError('id, role, product_key and outputs required')
    team=json.loads((Path(__file__).resolve().parents[1]/'knowledge/team.json').read_text(encoding='utf-8'))
    if role not in {member['id'] for member in team['members']}:
        raise ValueError('Unknown team role')
    if supersedes:
        previous=next((entry for entry in data['handoffs'] if entry['id']==supersedes),None)
        if not previous or previous['role']!=role or previous['product_key']!=product or any(entry.get('supersedes')==supersedes for entry in data['handoffs']):
            raise ValueError('Revision must replace one active handoff of the same role/product')
    record={'id':ident,'role':role,'product_key':product,'depends_on':list(dependencies),
            'inputs':[{'path':p,'sha256':digest(bounded(root,p))} for p in inputs],
            'outputs':[{'path':p,'sha256':digest(bounded(root,p))} for p in outputs],
            'status':'artifact_recorded','review_verdict':'unreviewed','supersedes':supersedes}
    proposed={'version':data['version'],'handoffs':data['handoffs']+[record]}
    check=verify(root,proposed)
    # Repairs can be recorded while older descendants remain stale. The new revision itself must be sound.
    if ident in check['stale_ids']:
        raise ValueError('; '.join(check['errors']))
    (root/'handoffs.json').write_text(json.dumps(proposed,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    return {**record,'job_valid_after_recording':check['valid']}


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('job_directory');p.add_argument('--register',dest='ident')
    p.add_argument('--role');p.add_argument('--product-key')
    p.add_argument('--input',action='append',default=[]);p.add_argument('--output',action='append',default=[])
    p.add_argument('--depends-on',action='append',default=[])
    p.add_argument('--supersedes')
    a=p.parse_args()
    try:
        root=Path(a.job_directory).resolve()
        repo=Path(__file__).resolve().parents[1]
        if not root.is_relative_to((repo/'private').resolve()):
            raise ValueError('Job directory must be inside private/')
        if a.ident:
            result=register(root,a.ident,a.role,a.product_key,a.input,a.output,a.depends_on,a.supersedes)
        else:
            result=verify(root)
        print(json.dumps(result,ensure_ascii=False))
        if result.get('valid') is False:raise SystemExit(1)
    except (ValueError,OSError,KeyError) as exc:p.exit(1,f'{exc}\n')
