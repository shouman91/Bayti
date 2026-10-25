import importlib.util
from pathlib import Path
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('handoffs',ROOT/'scripts/handoffs.py')
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)


class HandoffTests(unittest.TestCase):
    def files(self,root):
        for name,text in [('brief.md','Campaign brief'),('product.json','CAT-043'),('script.md','Draft copy'),('pack.md','Publishing draft')]:
            (root/name).write_text(text,encoding='utf-8')

    def test_real_file_dependency_chain(self):
        with tempfile.TemporaryDirectory() as tmp:
            r=Path(tmp);self.files(r)
            m.register(r,'p1','catalog-manager','CAT-043',['brief.md'],['product.json'])
            m.register(r,'w1','writer','CAT-043',['product.json'],['script.md'],['p1'])
            m.register(r,'u1','publisher','CAT-043',['script.md'],['pack.md'],['w1'])
            self.assertTrue(m.verify(r)['valid'])

    def test_product_change_invalidates_descendants(self):
        with tempfile.TemporaryDirectory() as tmp:
            r=Path(tmp);self.files(r)
            m.register(r,'p1','catalog-manager','CAT-043',['brief.md'],['product.json'])
            m.register(r,'w1','writer','CAT-043',['product.json'],['script.md'],['p1'])
            m.register(r,'u1','publisher','CAT-043',['script.md'],['pack.md'],['w1'])
            (r/'product.json').write_text('Revised dimensions',encoding='utf-8')
            result=m.verify(r)
            self.assertFalse(result['valid'])
            self.assertEqual(result['stale_ids'],['p1','u1','w1'])

    def test_product_mismatch_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            r=Path(tmp);self.files(r)
            m.register(r,'p1','catalog-manager','CAT-026',[],['product.json'])
            with self.assertRaises(ValueError):m.register(r,'w1','writer','CAT-043',['product.json'],['script.md'],['p1'])

    def test_dependency_requires_consuming_the_output(self):
        with tempfile.TemporaryDirectory() as tmp:
            r=Path(tmp);self.files(r)
            m.register(r,'p1','catalog-manager','CAT-043',[],['product.json'])
            with self.assertRaises(ValueError):m.register(r,'w1','writer','CAT-043',['brief.md'],['script.md'],['p1'])

    def test_missing_artifact_and_path_escape_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            r=Path(tmp);self.files(r)
            for output in ('not-there.md','../outside.txt'):
                with self.subTest(output=output),self.assertRaises(ValueError):m.register(r,'x','writer','CAT-043',[],[output])

    def test_duplicate_handoff_id_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            r=Path(tmp);self.files(r)
            m.register(r,'w1','writer','CAT-043',[],['script.md'])
            with self.assertRaises(ValueError):m.register(r,'w1','writer','CAT-043',[],['script.md'])

    def test_deleted_output_detected(self):
        with tempfile.TemporaryDirectory() as tmp:
            r=Path(tmp);self.files(r)
            m.register(r,'w1','writer','CAT-043',[],['script.md'])
            (r/'script.md').unlink()
            self.assertFalse(m.verify(r)['valid'])

    def test_unknown_dependency_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            r=Path(tmp);self.files(r)
            with self.assertRaises(ValueError):m.register(r,'w1','writer','CAT-043',['product.json'],['script.md'],['missing'])

    def test_revisions_repair_changed_chain_without_deleting_history(self):
        with tempfile.TemporaryDirectory() as tmp:
            r=Path(tmp);self.files(r)
            m.register(r,'p1','catalog-manager','CAT-043',['brief.md'],['product.json'])
            m.register(r,'w1','writer','CAT-043',['product.json'],['script.md'],['p1'])
            (r/'product.json').write_text('Corrected specification',encoding='utf-8')
            result=m.register(r,'p2','catalog-manager','CAT-043',['brief.md'],['product.json'],supersedes='p1')
            self.assertFalse(result['job_valid_after_recording'])
            (r/'script.md').write_text('Copy updated from corrected product',encoding='utf-8')
            m.register(r,'w2','writer','CAT-043',['product.json'],['script.md'],['p2'],supersedes='w1')
            report=m.verify(r)
            self.assertTrue(report['valid'])
            self.assertEqual(report['handoff_count'],4)
            self.assertEqual(report['active_handoff_count'],2)

    def test_revision_cannot_replace_different_role(self):
        with tempfile.TemporaryDirectory() as tmp:
            r=Path(tmp);self.files(r)
            m.register(r,'p1','catalog-manager','CAT-043',[],['product.json'])
            with self.assertRaises(ValueError):m.register(r,'w1','writer','CAT-043',[],['script.md'],supersedes='p1')

    def test_unknown_role_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            r=Path(tmp);self.files(r)
            with self.assertRaises(ValueError):m.register(r,'x','invented-employee','CAT-043',[],['script.md'])


if __name__=='__main__':unittest.main()
