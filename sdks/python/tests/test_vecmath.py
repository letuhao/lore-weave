"""loreweave_vecmath tests — promoted cosine-similarity math (D-COSINE-SDK-PROMOTE).

Covers both call shapes' edge cases as exercised by the 4 migrated call sites:
empty/zero/mismatched-length vectors (never raise, always 0.0), the inline-norm
variant, and the pre-normalized hot-loop variant (+ its `l2_norm` helper).
"""
import math

from loreweave_vecmath import cosine_similarity, cosine_similarity_prenormed, l2_norm


def test_identical_vectors_score_one():
    v = [1.0, 2.0, 3.0]
    assert math.isclose(cosine_similarity(v, v), 1.0, rel_tol=1e-9)


def test_orthogonal_vectors_score_zero():
    assert math.isclose(cosine_similarity([1.0, 0.0], [0.0, 1.0]), 0.0, abs_tol=1e-12)


def test_opposite_vectors_score_negative_one():
    assert math.isclose(cosine_similarity([1.0, 2.0], [-1.0, -2.0]), -1.0, rel_tol=1e-9)


def test_empty_vector_returns_zero():
    assert cosine_similarity([], [1.0, 2.0]) == 0.0
    assert cosine_similarity([1.0, 2.0], []) == 0.0
    assert cosine_similarity([], []) == 0.0


def test_mismatched_length_returns_zero():
    assert cosine_similarity([1.0, 2.0], [1.0, 2.0, 3.0]) == 0.0


def test_zero_vector_returns_zero():
    assert cosine_similarity([0.0, 0.0], [1.0, 2.0]) == 0.0
    assert cosine_similarity([1.0, 2.0], [0.0, 0.0]) == 0.0
    assert cosine_similarity([0.0, 0.0], [0.0, 0.0]) == 0.0


def test_l2_norm():
    assert math.isclose(l2_norm([3.0, 4.0]), 5.0, rel_tol=1e-9)
    assert l2_norm([]) == 0.0
    assert l2_norm([0.0, 0.0]) == 0.0


def test_prenormed_matches_inline_norm_variant():
    a = [1.0, 2.0, 3.0]
    b = [4.0, -1.0, 2.0]
    na, nb = l2_norm(a), l2_norm(b)
    assert math.isclose(
        cosine_similarity_prenormed(a, na, b, nb),
        cosine_similarity(a, b),
        rel_tol=1e-9,
    )


def test_prenormed_zero_norm_returns_zero():
    a = [0.0, 0.0]
    b = [1.0, 2.0]
    assert cosine_similarity_prenormed(a, 0.0, b, l2_norm(b)) == 0.0
    assert cosine_similarity_prenormed(b, l2_norm(b), a, 0.0) == 0.0
    assert cosine_similarity_prenormed(a, 0.0, a, 0.0) == 0.0
