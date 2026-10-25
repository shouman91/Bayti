import importlib.util
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('finance', ROOT / 'scripts/finance.py')
finance = importlib.util.module_from_spec(spec)
spec.loader.exec_module(finance)
AGREEMENT = json.loads((ROOT / 'knowledge/operating-agreement.json').read_text(encoding='utf-8'))


class FinanceTests(unittest.TestCase):
    def test_retainer_once_without_implied_tax_payment_or_issuance(self):
        result = finance.draft('2026-10', AGREEMENT)
        self.assertEqual(result['agency_fee'], '450.00')
        self.assertEqual(result['status'], 'draft')
        for key in ('tax_amount', 'invoice_total', 'paid_amount', 'issued_at', 'due_date'):
            self.assertIsNone(result[key], key)
        self.assertEqual(result['payment_status'], 'unknown')

    def test_invalid_periods(self):
        for period in ('2026-00', '2026-13', '2026-1', '../2026-10', None):
            with self.subTest(period=period), self.assertRaises(ValueError):
                finance.draft(period, AGREEMENT)

    def test_invalid_amounts_and_decimal_rounding(self):
        self.assertEqual(str(finance.money('0.105')), '0.11')
        for amount in ('NaN', 'Infinity', '-1', True, 'text'):
            with self.subTest(amount=amount), self.assertRaises(ValueError):
                finance.money(amount)

    def test_duplicate_period_blocked_across_output_directories(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / 'knowledge').mkdir()
            (root / 'knowledge/operating-agreement.json').write_text(json.dumps(AGREEMENT), encoding='utf-8')
            with patch.object(finance, 'ROOT', root):
                first = finance.save_draft('2026-10', root / 'private/invoices')
                self.assertTrue(first.exists())
                with self.assertRaises(ValueError):
                    finance.save_draft('2026-10', root / 'private/other')
                second = finance.save_draft('2026-11', root / 'private/invoices')
                self.assertTrue(second.exists())

    def test_public_and_path_escape_outputs_blocked(self):
        with tempfile.TemporaryDirectory() as tmp:
            with patch.object(finance, 'ROOT', Path(tmp)):
                for output in (Path(tmp) / 'public', Path(tmp) / 'private/../public'):
                    with self.assertRaises(ValueError):
                        finance.save_draft('2026-10', output)

    def test_issued_invoice_in_register_blocks_new_draft(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / 'knowledge').mkdir()
            (root / 'knowledge/operating-agreement.json').write_text(json.dumps(AGREEMENT), encoding='utf-8')
            (root / 'private').mkdir()
            (root / 'private/invoice-register.csv').write_text('invoice_id,service_period,status\nB-1,2026-10,issued\n', encoding='utf-8')
            with patch.object(finance, 'ROOT', root), self.assertRaises(ValueError):
                finance.save_draft('2026-10', root / 'private/invoices')


if __name__ == '__main__':
    unittest.main()
