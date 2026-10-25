"""Deterministic operations math. Data inputs do not authorize live changes."""
import argparse
from datetime import date
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
import json
from pathlib import Path


def number(value):
    if value is None or isinstance(value, bool):
        raise ValueError('Numeric value required')
    try:
        result = Decimal(str(value))
    except InvalidOperation as exc:
        raise ValueError('Invalid number') from exc
    if not result.is_finite() or result < 0:
        raise ValueError('Finite nonnegative value required')
    return result


def amount(value):
    return str(value.quantize(Decimal('.01'), rounding=ROUND_HALF_UP))


def ratio(numerator, denominator):
    return amount(numerator / denominator) if denominator else None


def campaign_report(rows):
    seen = set()
    results = []
    for row in rows:
        if not row.get('id') or row['id'] in seen:
            raise ValueError('Missing or duplicate campaign row id')
        seen.add(row['id'])
        for key in ('currency', 'period_start', 'period_end', 'source', 'attribution', 'result_type', 'product_key'):
            if not isinstance(row.get(key), str) or not row[key].strip():
                raise ValueError(f'Missing context: {key}')
        start, end = date.fromisoformat(row['period_start']), date.fromisoformat(row['period_end'])
        if end < start:
            raise ValueError('Invalid campaign period')
        source_timezone=row.get('source_timezone')
        if source_timezone is not None and (not isinstance(source_timezone,str) or not source_timezone.strip()):
            raise ValueError('source_timezone must be a named timezone or null')
        spend = number(row['spend'])
        counts = {}
        for key in ('conversations', 'qualified_leads', 'confirmed_results'):
            value = number(row[key]) if row.get(key) is not None else None
            if value is not None and value != value.to_integral_value():
                raise ValueError('Result counts must be integers')
            counts[key] = value
        revenue = number(row['attributed_revenue']) if row.get('attributed_revenue') is not None else None
        costs = number(row['variable_costs']) if row.get('variable_costs') is not None else None
        results.append({
            **{key: row[key] for key in ('id', 'product_key', 'result_type', 'currency', 'period_start', 'period_end', 'source', 'attribution')},
            'source_timezone':source_timezone,
            'comparison_limitations':[] if source_timezone else ['source_timezone_unknown'],
            'spend': amount(spend),
            'cost_per_conversation': ratio(spend, counts['conversations']) if counts['conversations'] is not None else None,
            'cost_per_qualified_lead': ratio(spend, counts['qualified_leads']) if counts['qualified_leads'] is not None else None,
            'cost_per_confirmed_result': ratio(spend, counts['confirmed_results']) if counts['confirmed_results'] is not None else None,
            'reported_roas': ratio(revenue, spend) if revenue is not None else None,
            'contribution_after_ads': amount(revenue-costs-spend) if revenue is not None and costs is not None else None,
            'not_net_profit': True,
            'confirmed_result_count': int(counts['confirmed_results']) if counts['confirmed_results'] is not None else None,
        })
    # No grand aggregate: period overlap, currencies, and result types are intentionally kept separate.
    return results


def clean_crm(rows):
    leads, order_owners, conflicts = {}, {}, []
    allowed = {'inquiry', 'qualified', 'quoted', 'confirmed', 'delivered', 'lost', 'cancelled'}
    duplicates = 0
    for row in rows:
        key = row.get('lead_id')
        if not key or row.get('stage') not in allowed or not row.get('product_key') or not isinstance(row.get('opt_out'), bool):
            raise ValueError('Invalid CRM row')
        if row['stage'] in ('confirmed', 'delivered') and not row.get('order_id'):
            raise ValueError('Confirmed lead requires order/booking evidence reference')
        if key in leads:
            if leads[key] == row:
                duplicates += 1
                continue
            conflicts.append(key)
            # No timestamps in this contract: never invent the latest state.
            continue
        leads[key] = dict(row)
        if row.get('order_id'):
            order = row['order_id']
            if order in order_owners and order_owners[order] != key:
                raise ValueError('Order assigned to multiple leads; resolve before counting')
            order_owners[order] = key
    if conflicts:
        raise ValueError('Conflicting lead versions require dated resolution: '+', '.join(sorted(set(conflicts))))
    confirmed=[r for r in leads.values() if r['stage'] in ('confirmed','delivered')]
    product_orders={r['order_id'] for r in confirmed if not r['product_key'].startswith('service:')}
    measurement_bookings={r['order_id'] for r in confirmed if r['product_key']=='service:measurement'}
    other_service_results={r['order_id'] for r in confirmed if r['product_key'].startswith('service:') and r['product_key']!='service:measurement'}
    return {'leads': list(leads.values()), 'duplicates_removed': duplicates,
            'confirmed_orders': len(product_orders),
            'confirmed_measurement_bookings':len(measurement_bookings),
            'other_service_confirmations':len(other_service_results),
            'followup_lead_ids': [r['lead_id'] for r in leads.values() if not r['opt_out'] and r['stage'] in ('inquiry','qualified','quoted')],
            'live_verified': False}


def reconcile(invoice, payments, as_of=None):
    if invoice.get('status') not in ('issued', 'partially_paid', 'paid'):
        raise ValueError('Only issued invoices can be reconciled as receivables')
    if not invoice.get('id') or not invoice.get('currency'):
        raise ValueError('Invoice id and currency required')
    value = number(invoice['amount'])
    total = Decimal(0)
    ids, evidence = set(), set()
    for payment in payments:
        if payment.get('invoice_id') != invoice['id'] or payment.get('currency') != invoice['currency']:
            raise ValueError('Payment invoice/currency mismatch')
        pid, proof = payment.get('id'), payment.get('evidence')
        if not pid or not proof or pid in ids or proof in evidence:
            raise ValueError('Missing or duplicate payment/evidence')
        ids.add(pid); evidence.add(proof)
        total += number(payment['amount'])
    balance = max(value-total, Decimal(0))
    credit = max(total-value, Decimal(0))
    due = invoice.get('due_date')
    overdue = (date.fromisoformat(due) < date.fromisoformat(as_of) and balance > 0) if due and as_of else None
    return {'invoice_id':invoice['id'], 'currency':invoice['currency'], 'paid':amount(total),
            'balance':amount(balance), 'credit':amount(credit), 'status':'paid' if not balance else 'partially_paid' if total else 'unpaid',
            'overdue':overdue, 'bank_verified':False}


def margin(retainer, currency, costs):
    value = number(retainer)
    total = Decimal(0)
    ids = set()
    for row in costs:
        if row.get('currency') != currency:
            raise ValueError('Do not pool cost currencies')
        if not row.get('id') or row['id'] in ids or not row.get('evidence'):
            raise ValueError('Missing or duplicate cost/receipt')
        ids.add(row['id'])
        total += number(row['amount'])
    return {'currency':currency, 'retainer':amount(value), 'known_costs':amount(total),
            'contribution_before_unknown_overhead_and_tax':amount(value-total), 'net_profit':None}


def analyze(case):
    if case.get('data_kind') not in ('synthetic', 'user_supplied'):
        raise ValueError('Explicit data_kind required')
    return {'data_kind':case['data_kind'], 'campaigns':campaign_report(case['campaigns']),
            'crm':clean_crm(case['crm']), 'receivables':reconcile(case['invoice'],case['payments']),
            'agency':margin('450.00','USD',case['agency_costs']), 'external_actions_executed':False}


if __name__ == '__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('input'); parser.add_argument('--out', required=True)
    args=parser.parse_args()
    try:
        result=analyze(json.loads(Path(args.input).read_text(encoding='utf-8')))
        root=Path(__file__).resolve().parents[1]
        target=Path(args.out).resolve()
        if not target.is_relative_to((root/'private').resolve()):
            raise ValueError('Operational reports must be inside private/')
        target.parent.mkdir(parents=True,exist_ok=True)
        target.write_text(json.dumps(result,ensure_ascii=False,indent=2,allow_nan=False)+'\n',encoding='utf-8')
        print(json.dumps({'saved':str(target),'data_kind':case_kind if (case_kind:=result['data_kind']) else None}))
    except (ValueError,KeyError,TypeError,OSError) as exc:
        parser.exit(1,f'{exc}\n')
