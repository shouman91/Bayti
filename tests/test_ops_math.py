import copy
import importlib.util
import json
from pathlib import Path
import unittest

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('ops_math',ROOT/'scripts/ops_math.py')
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
CASE=json.loads((ROOT/'tests/fixtures/agency-case.json').read_text(encoding='utf-8'))


class OperationsTests(unittest.TestCase):
    def test_different_business_results_and_zero_not_invented(self):
        result=m.campaign_report(CASE['campaigns'])
        self.assertEqual(result[0]['cost_per_confirmed_result'],'20.00')
        self.assertIsNone(result[1]['cost_per_confirmed_result'])
        self.assertEqual(result[1]['result_type'],'measurement_booking')
        self.assertIsNone(result[1]['contribution_after_ads'])

    def test_roas_and_known_contribution_not_net_profit(self):
        result=m.campaign_report(CASE['campaigns'])[0]
        self.assertEqual(result['reported_roas'],'15.00')
        self.assertEqual(result['contribution_after_ads'],'340.00')
        self.assertTrue(result['not_net_profit'])

    def test_missing_conversations_not_zero_or_false_metric(self):
        rows=copy.deepcopy(CASE['campaigns']);rows[0]['conversations']=None
        self.assertIsNone(m.campaign_report(rows)[0]['cost_per_conversation'])

    def test_duplicate_campaign_id_rejected(self):
        with self.assertRaises(ValueError):m.campaign_report(CASE['campaigns']*2)

    def test_bad_amounts_and_fractional_counts_rejected(self):
        for value in ('NaN','Infinity','-1',True):
            with self.subTest(value=value),self.assertRaises(ValueError):m.number(value)
        row=copy.deepcopy(CASE['campaigns'][0]);row['confirmed_results']=1.5
        with self.assertRaises(ValueError):m.campaign_report([row])

    def test_currency_context_stays_separate(self):
        rows=copy.deepcopy(CASE['campaigns']);rows[1]['currency']='ILS'
        result=m.campaign_report(rows)
        self.assertEqual([x['currency'] for x in result],['USD','ILS','USD'])
        self.assertIsInstance(result,list) # no unsupported pooled grand total

    def test_exact_duplicate_lead_dedup_and_optout_and_cancelled(self):
        result=m.clean_crm(CASE['crm'])
        self.assertEqual(result['duplicates_removed'],1)
        self.assertEqual(result['confirmed_orders'],1)
        self.assertEqual(result['followup_lead_ids'],['L3'])

    def test_conflicting_lead_does_not_choose_latest_without_date(self):
        rows=copy.deepcopy(CASE['crm']);rows[1]['stage']='delivered'
        with self.assertRaises(ValueError):m.clean_crm(rows)

    def test_confirmed_measurement_booking_is_not_a_product_order(self):
        rows=copy.deepcopy(CASE['crm']);rows[3]['stage']='confirmed';rows[3]['order_id']='BOOK1'
        result=m.clean_crm(rows)
        self.assertEqual(result['confirmed_orders'],1)
        self.assertEqual(result['confirmed_measurement_bookings'],1)

    def test_other_service_confirmation_does_not_inflate_orders_or_measurement(self):
        rows=copy.deepcopy(CASE['crm']);rows[3].update(stage='confirmed',order_id='SVC1',product_key='service:other')
        result=m.clean_crm(rows)
        self.assertEqual(result['confirmed_orders'],1)
        self.assertEqual(result['confirmed_measurement_bookings'],0)
        self.assertEqual(result['other_service_confirmations'],1)

    def test_order_cannot_belong_to_two_leads(self):
        rows=copy.deepcopy(CASE['crm'][:1]);other=copy.deepcopy(rows[0]);other['lead_id']='L9';rows.append(other)
        with self.assertRaises(ValueError):m.clean_crm(rows)

    def test_partial_payments_and_unknown_due_date(self):
        result=m.reconcile(CASE['invoice'],CASE['payments'],as_of='2026-10-25')
        self.assertEqual((result['paid'],result['balance'],result['status']),('250.00','200.00','partially_paid'))
        self.assertIsNone(result['overdue'])

    def test_payment_currency_and_invoice_mismatch(self):
        for key,value in [('currency','ILS'),('invoice_id','OTHER')]:
            payments=copy.deepcopy(CASE['payments']);payments[0][key]=value
            with self.subTest(key=key),self.assertRaises(ValueError):m.reconcile(CASE['invoice'],payments)

    def test_payment_or_proof_cannot_be_reused(self):
        for key in ('id','evidence'):
            payments=copy.deepcopy(CASE['payments']);payments[1][key]=payments[0][key]
            with self.subTest(key=key),self.assertRaises(ValueError):m.reconcile(CASE['invoice'],payments)

    def test_draft_not_receivable(self):
        invoice=copy.deepcopy(CASE['invoice']);invoice['status']='draft'
        with self.assertRaises(ValueError):m.reconcile(invoice,CASE['payments'])

    def test_overpayment_credit_not_negative_balance(self):
        payments=copy.deepcopy(CASE['payments']);payments[0]['amount']='500.00'
        result=m.reconcile(CASE['invoice'],payments)
        self.assertEqual((result['balance'],result['credit']),('0.00','150.00'))

    def test_due_date_only_when_known(self):
        invoice=copy.deepcopy(CASE['invoice']);invoice['due_date']='2026-10-20'
        self.assertTrue(m.reconcile(invoice,CASE['payments'],as_of='2026-10-25')['overdue'])

    def test_margin_single_agency_fee_and_unknown_net(self):
        result=m.margin('450.00','USD',CASE['agency_costs'])
        self.assertEqual(result['known_costs'],'120.00')
        self.assertEqual(result['contribution_before_unknown_overhead_and_tax'],'330.00')
        self.assertIsNone(result['net_profit'])

    def test_missing_receipt_cost_currency_and_duplicate(self):
        for key,value in [('currency','ILS'),('evidence',None),('amount',None)]:
            rows=copy.deepcopy(CASE['agency_costs']);rows[0][key]=value
            with self.subTest(key=key),self.assertRaises(ValueError):m.margin('450','USD',rows)
        with self.assertRaises(ValueError):m.margin('450','USD',CASE['agency_costs']*2)

    def test_inputs_not_mutated_or_claimed_live(self):
        case=copy.deepcopy(CASE);before=copy.deepcopy(case);result=m.analyze(case)
        self.assertEqual(case,before)
        self.assertEqual(result['data_kind'],'synthetic')
        self.assertFalse(result['external_actions_executed'])

    def test_unknown_source_timezone_explicitly_limits_comparison(self):
        result=m.campaign_report(CASE['campaigns'])
        self.assertIsNone(result[0]['source_timezone'])
        self.assertIn('source_timezone_unknown',result[0]['comparison_limitations'])

    def test_different_source_timezones_are_preserved(self):
        rows=copy.deepcopy(CASE['campaigns'])
        rows[0]['source_timezone']='Asia/Amman';rows[1]['source_timezone']='Asia/Jerusalem'
        result=m.campaign_report(rows)
        self.assertEqual(result[0]['source_timezone'],'Asia/Amman')
        self.assertEqual(result[1]['source_timezone'],'Asia/Jerusalem')

    def test_invalid_timezone_type_rejected(self):
        rows=copy.deepcopy(CASE['campaigns']);rows[0]['source_timezone']=True
        with self.assertRaises(ValueError):m.campaign_report(rows)


if __name__=='__main__':unittest.main()
