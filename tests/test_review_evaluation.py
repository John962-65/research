from pathlib import Path
import json
import unittest

from research_agent.review_evaluation import evaluate_case, summarize_sessions


class ReviewEvaluationTest(unittest.TestCase):
    def test_repository_cases_use_real_decision_functions(self):
        path = Path(__file__).resolve().parents[1] / 'examples/review-evaluation-cases.json'
        for case in json.loads(path.read_text())['cases']:
            with self.subTest(case=case['id']):
                self.assertEqual(evaluate_case(case), case['expected'])

    def test_no_observations_means_not_measured(self):
        self.assertEqual(summarize_sessions([], [])['status'], 'not_measured')

    def test_paired_measurements_count_false_release_and_time(self):
        cases = [{'id': 'invalid', 'expected': 'blocked'}]
        rows = [
            dict(participant_id='p1', pair_id='a', condition='manual', case_id='invalid', seconds='100', decision='publishable'),
            dict(participant_id='p1', pair_id='a', condition='assisted', case_id='invalid', seconds='70', decision='blocked'),
        ]
        report = summarize_sessions(rows, cases)
        self.assertEqual(report['median_paired_seconds_saved'], 30)
        self.assertEqual(report['conditions']['manual']['false_release_rate'], 1)
        self.assertEqual(report['conditions']['assisted']['false_release_rate'], 0)
        self.assertEqual(report['participants'], 1)
        with self.assertRaises(ValueError):
            summarize_sessions(rows[:1], cases)
        with self.assertRaises(ValueError):
            summarize_sessions(rows + rows[:1], cases)
        for value in ('nan', 'inf', '-1', '0'):
            with self.subTest(seconds=value), self.assertRaises(ValueError):
                summarize_sessions([rows[0] | {'seconds': value}, rows[1]], cases)
