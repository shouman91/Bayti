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
    for skill in skills:
        assert (ROOT / skill['path']).is_file(), skill['path']
        assert set(skill['roles']) <= by_id.keys(), skill['name']
        covered.update(skill['roles'])
    assert covered == by_id.keys(), 'Uncovered role'
    agreement = json.loads((ROOT / 'knowledge/operating-agreement.json').read_text(encoding='utf-8'))
    assert agreement['monthly_agency_retainer']['amount'] == '450.00'
    assert agreement['monthly_agency_retainer']['currency'] == 'USD'
    assert agreement['automatic_billing'] is False
    assert 'private/' in (ROOT / '.gitignore').read_text(encoding='utf-8')
    return {'roles': len(members), 'skills': len(skills), 'finance_roles': 3, 'checks': 'passed', 'live_execution_tested': False}


if __name__ == '__main__':
    print(json.dumps(verify(), ensure_ascii=False))
