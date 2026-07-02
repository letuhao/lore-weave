"""Pure metric helpers of the Track 4 salience eval CLI (eval/run_salience_eval.py)."""

from eval.run_salience_eval import ArmReport, build_queries, passages_mention, rank_of


class TestPassagesMention:
    def test_hit_inside_block(self):
        xml = "<memory><passages><passage>Lâm Uyển xuất hiện</passage></passages></memory>"
        assert passages_mention(xml, "Lâm Uyển") is True

    def test_miss_inside_block(self):
        xml = "<memory><passages><passage>khác</passage></passages></memory>"
        assert passages_mention(xml, "Lâm Uyển") is False

    def test_name_outside_block_does_not_count(self):
        xml = "<memory><glossary>Lâm Uyển</glossary><passages><passage>x</passage></passages></memory>"
        assert passages_mention(xml, "Lâm Uyển") is False

    def test_no_block_is_none(self):
        assert passages_mention("<memory></memory>", "X") is None


class TestPassageHitRate:
    def test_none_entries_excluded(self):
        arm = ArmReport(label="x", ranks=[1, 1, 1], passage_hits=[True, None, False])
        assert arm.passage_hit_rate == 0.5

    def test_all_none_is_none(self):
        arm = ArmReport(label="x", ranks=[1], passage_hits=[None])
        assert arm.passage_hit_rate is None

    def test_unset_is_none(self):
        arm = ArmReport(label="x", ranks=[1])
        assert arm.passage_hit_rate is None


class TestRankOf:
    def test_first_is_rank_1(self):
        assert rank_of("a", ["a", "b", "c"]) == 1

    def test_absent_is_none(self):
        assert rank_of("z", ["a", "b"]) is None

    def test_empty_list(self):
        assert rank_of("a", []) is None


class TestArmReport:
    def test_mrr_counts_misses_as_zero(self):
        # ranks 1 and None over 2 queries → (1/1 + 0) / 2 = 0.5
        arm = ArmReport(label="x", ranks=[1, None])
        assert arm.mrr == 0.5

    def test_mean_rank_ignores_misses(self):
        arm = ArmReport(label="x", ranks=[1, 3, None])
        assert arm.mean_rank == 2.0

    def test_hit_rate(self):
        arm = ArmReport(label="x", ranks=[1, None, 2, None])
        assert arm.hit_rate == 0.5

    def test_empty(self):
        arm = ArmReport(label="x", ranks=[])
        assert arm.mrr == 0.0 and arm.mean_rank is None and arm.hit_rate == 0.0


class TestBuildQueries:
    def test_focus_split_and_shape(self):
        ents = [
            {"entity_id": "e1", "name": "Lâm Uyển"},
            {"entity_id": "e2", "name": "Hắc Vũ"},
            {"entity_id": "e3", "name": "Tông môn"},
        ]
        focus, others = build_queries(ents, focus_n=2)
        assert [q["expect"] for q in focus] == ["e1", "e2"]
        assert [q["expect"] for q in others] == ["e3"]
        assert "Lâm Uyển" in focus[0]["q"]

    def test_nameless_entities_skipped(self):
        focus, others = build_queries([{"entity_id": "e1", "name": None}], focus_n=2)
        assert focus == [] and others == []
