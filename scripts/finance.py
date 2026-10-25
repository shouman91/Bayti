"""Local internal invoice drafts. No network, tax filing, issuance, or payments."""
import argparse
import csv
import json
import re
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def money(value):
    if isinstance(value, bool):
        raise ValueError('Boolean is not an amount')
    try:
        result = Decimal(str(value))
    except (InvalidOperation, ValueError) as exc:
        raise ValueError('Invalid amount') from exc
    if not result.is_finite() or result < 0:
        raise ValueError('Amount must be finite and nonnegative')
    return result.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)


def draft(period, agreement):
    if not isinstance(period, str) or not re.fullmatch(r'\d{4}-(0[1-9]|1[0-2])', period):
        raise ValueError('Service period must be YYYY-MM')
    terms = agreement['monthly_agency_retainer']
    if terms['currency'] != 'USD':
        raise ValueError('Current agreement is denominated in USD')
    return {
        'invoice_id': f'BAYTI-DRAFT-{period}',
        'client': 'BAYTI',
        'service_period': period,
        'currency': 'USD',
        'agency_fee': str(money(terms['amount'])),
        'status': 'draft',
        'tax_treatment': 'unconfirmed',
        'tax_amount': None,
        'invoice_total': None,
        'issued_at': None,
        'due_date': None,
        'paid_amount': None,
        'payment_status': 'unknown',
        'required_before_issuance': [
            'service period approval', 'supplier legal details',
            'tax treatment', 'payment terms', 'invoice number policy',
        ],
        'notes': 'One agency fee for the month, not per role. Ad spend is separate. Internal draft only.',
    }


def save_draft(period, directory):
    directory = Path(directory).resolve()
    private_root = (ROOT / 'private').resolve()
    if not directory.is_relative_to(private_root):
        raise ValueError('Invoice drafts must be inside repository private/')
    agreement = json.loads((ROOT / 'knowledge/operating-agreement.json').read_text(encoding='utf-8'))
    result = draft(period, agreement)
    # Search the whole private tree, so moving the output folder cannot duplicate a period.
    if private_root.exists():
        for register in private_root.rglob('invoice-register.csv'):
            with register.open(encoding='utf-8-sig', newline='') as handle:
                for row in csv.DictReader(handle):
                    if row.get('service_period') == period and row.get('invoice_id') and row.get('status') != 'void':
                        raise ValueError(f'Existing invoice/draft for {period}: {register.name}')
        for existing in private_root.rglob('*.json'):
            try:
                record = json.loads(existing.read_text(encoding='utf-8'))
            except (ValueError, OSError):
                continue
            if isinstance(record, dict) and record.get('client') == 'BAYTI' and record.get('service_period') == period and record.get('invoice_id') and record.get('status') != 'void':
                raise ValueError(f'Existing invoice/draft for {period}: {existing.name}')
    directory.mkdir(parents=True, exist_ok=True)
    target = directory / f'BAYTI-DRAFT-{period}.json'
    with target.open('x', encoding='utf-8') as handle:
        json.dump(result, handle, ensure_ascii=False, indent=2, allow_nan=False)
        handle.write('\n')
    return target


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--period', required=True)
    parser.add_argument('--out', default='private/invoices/')
    args = parser.parse_args()
    output = Path(args.out)
    if not output.is_absolute():
        output = ROOT / output
    try:
        print(json.dumps({'saved': str(save_draft(args.period, output)), 'status': 'draft'}, ensure_ascii=False))
    except (ValueError, OSError, KeyError) as exc:
        parser.exit(1, f'{exc}\n')


if __name__ == '__main__':
    main()
