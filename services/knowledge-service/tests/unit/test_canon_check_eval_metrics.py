"""Pure metric helpers of the canon-check judge eval CLI (eval/run_canon_check_eval.py)."""

from eval.run_canon_check_eval import FixtureResult, ModelReport


def _r(fixture_id, expected, confirmed, why="", note=""):
    return FixtureResult(fixture_id, expected, confirmed, why, note)


class TestFixtureResultOutcome:
    def test_correct_when_matches(self):
        assert _r("a", True, True).outcome == "correct"
        assert _r("a", False, False).outcome == "correct"

    def test_wrong_when_mismatched(self):
        assert _r("a", True, False).outcome == "wrong"
        assert _r("a", False, True).outcome == "wrong"

    def test_inconclusive_when_none(self):
        assert _r("a", True, None).outcome == "inconclusive"


class TestModelReportAccuracy:
    def test_accuracy_over_resolved_only(self):
        report = ModelReport(label="x", results=[
            _r("a", True, True), _r("b", True, False), _r("c", False, None),
        ])
        # c is inconclusive -> excluded from the denominator
        assert report.accuracy == 0.5
        assert report.inconclusive_count == 1

    def test_accuracy_none_when_all_inconclusive(self):
        report = ModelReport(label="x", results=[_r("a", True, None)])
        assert report.accuracy is None

    def test_accuracy_perfect(self):
        report = ModelReport(label="x", results=[_r("a", True, True), _r("b", False, False)])
        assert report.accuracy == 1.0


class TestModelReportConfusionPrecisionRecall:
    def test_confusion_counts(self):
        report = ModelReport(label="x", results=[
            _r("tp", True, True), _r("fp", False, True),
            _r("tn", False, False), _r("fn", True, False),
        ])
        assert report.confusion == {"tp": 1, "fp": 1, "tn": 1, "fn": 1}
        assert report.precision == 0.5
        assert report.recall == 0.5

    def test_precision_none_when_never_flags(self):
        report = ModelReport(label="x", results=[_r("tn", False, False)])
        assert report.precision is None

    def test_recall_none_when_no_positive_fixtures(self):
        report = ModelReport(label="x", results=[_r("tn", False, False)])
        assert report.recall is None

    def test_inconclusive_excluded_from_confusion(self):
        report = ModelReport(label="x", results=[_r("tp", True, True), _r("inc", True, None)])
        assert report.confusion == {"tp": 1, "fp": 0, "tn": 0, "fn": 0}


class TestModelReportToDict:
    def test_misses_lists_only_non_correct(self):
        report = ModelReport(label="x", results=[
            _r("ok", True, True, why="right"),
            _r("bad", True, False, why="missed it", note="hard case"),
        ])
        d = report.to_dict()
        assert len(d["misses"]) == 1
        assert d["misses"][0]["fixture_id"] == "bad"
        assert d["misses"][0]["note"] == "hard case"
