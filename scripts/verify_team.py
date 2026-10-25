"""Check role coverage, references, reporting lines and public package contents."""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def verify():
    team = json.loads((ROOT / 'knowledge/team.json').read_text(encoding='utf-8'))
    members = team['members']
    by_id = {member['id']: member for member in members}
    assert len(members) == team['total_roles'] == len(by_id) == 22, 'Role count/uniqueness'
    assert len({m['name'] for m in members}) == len(members), 'Duplicate display names'
    assert team['contact'] == 'manager', 'Default contact'
    assert {'finance-director', 'bookkeeper', 'receivables'} <= by_id.keys(), 'Finance coverage'
    for member in members:
        assert (ROOT / member['profile']).is_file(), member['profile']
        assert (ROOT / member['knowledge_path']).is_file(), member['id']+' knowledge missing'
        chain = set()
        current = member['id']
        while current:
            assert current in by_id, current
            assert current not in chain, f'Reporting cycle: {current}'
            chain.add(current)
            current = by_id[current]['reports_to']
        assert 'manager' in chain, f'No path to manager: {member["id"]}'
    covered = set()
    skills = json.loads((ROOT / 'knowledge/skills.json').read_text(encoding='utf-8'))['skills']
    names={skill['name']:skill for skill in skills}
    assert len(names)==len(skills)==28, 'Skill uniqueness/count'
    source_ids={source['id'] for source in json.loads((ROOT/'knowledge/source-library.json').read_text(encoding='utf-8'))['sources']}
    for skill in skills:
        assert (ROOT / skill['path']).is_file(), skill['path']
        assert set(skill['roles']) <= by_id.keys(), skill['name']
        for path in skill.get('knowledge',[]):
            assert (ROOT/path).is_file(), path
        assert set(skill.get('source_ids',[]))<=source_ids, skill['name']+' unknown source'
        covered.update(skill['roles'])
    for member in members:
        primary=names[member['primary_skill']]
        assert primary['roles']==[member['id']], 'Primary skill must be role-specific'
        assert primary['knowledge']==[member['knowledge_path']], 'Knowledge route mismatch'
    assert covered == by_id.keys(), 'Uncovered role'
    agreement = json.loads((ROOT / 'knowledge/operating-agreement.json').read_text(encoding='utf-8'))
    assert agreement['monthly_agency_retainer']['amount'] == '450.00'
    assert agreement['monthly_agency_retainer']['currency'] == 'USD'
    assert agreement['automatic_billing'] is False
    assert 'private/' in (ROOT / '.gitignore').read_text(encoding='utf-8')
    return {'roles': len(members), 'skills': len(skills), 'role_skills':22,'role_knowledge_files':22,
            'finance_roles': 3, 'checks': 'passed', 'live_execution_tested': False}


if __name__ == '__main__':
    print(json.dumps(verify(), ensure_ascii=False))
