import unittest
from types import SimpleNamespace
from srw.modules.decision.assessment import calculate_assessment

class AssessmentTest(unittest.TestCase):
    def test_no_criteria_does_not_publish(self):
        a=calculate_assessment('c','h',[],[],decision_ready=False)
        self.assertIsNone(a.fit_score)
    def test_missing_not_penalized_or_ranked(self):
        a=calculate_assessment('c','h',[{'criterion_key':'a'},{'criterion_key':'b'}],[SimpleNamespace(criterion_key='a',status='met',evidence_level='strong')],decision_ready=False)
        self.assertIsNone(a.fit_score)
        self.assertEqual(a.unresolved_keys,('b',))
    def test_conflict_withholds_score(self):
        a=calculate_assessment('c','h',[{'criterion_key':'a'}],[SimpleNamespace(criterion_key='a',status='conflict',evidence_level='strong')],decision_ready=False)
        self.assertIsNone(a.fit_score)
        self.assertEqual(a.conflict_keys,('a',))
    def test_weighted_result(self):
        a=calculate_assessment('c','h',[{'criterion_key':'a','weight':3},{'criterion_key':'b','weight':1}],
          [SimpleNamespace(criterion_key='a',status='met',evidence_level='strong'),SimpleNamespace(criterion_key='b',status='partial',evidence_level='medium')],decision_ready=True)
        self.assertEqual(a.fit_score,87.5)
        self.assertEqual(a.evidence_coverage,0.925)
    def test_no_evidence_gives_no_score(self):
        a=calculate_assessment('c','h',[{'criterion_key':'a'}],[SimpleNamespace(criterion_key='a',status='met',evidence_level='none')],decision_ready=True)
        self.assertIsNone(a.fit_score)
    def test_invalid_weights(self):
        for weight in [0,-2,True,float('nan')]:
            with self.assertRaises(ValueError):
                calculate_assessment('c','h',[{'criterion_key':'a','weight':weight}],[],decision_ready=False)
    def test_duplicate_keys(self):
        with self.assertRaises(ValueError):
            calculate_assessment('c','h',[{'criterion_key':'a'},{'criterion_key':'a'}],[],decision_ready=False)

if __name__=='__main__': unittest.main()
