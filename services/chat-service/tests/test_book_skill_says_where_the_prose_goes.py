"""The book skill's own prose was telling the model to do the thing that stranded four chapters.

🔴 MEASURED across two live authoring runs, 2026-09-04. Every chapter left at 0 words came from a
TITLE-ONLY `book_chapter_create`, and the turn ended before any `book_chapter_save_draft` filled
it. The tool schema said `body` was `"plain-text body (optional)"` — fixed separately in
book-service — and **this skill, which the model reads every single turn, said:**

    `body` is optional plain text (empty is fine — save prose later with
    `book_chapter_save_draft`)

*"empty is fine"* — the surface actively recommending the shape that loses the author's chapter.
Fixing the tool schema and leaving this would have left the louder of the two voices unchanged.

🔴 AND THE SPLIT THE MODEL INVENTED. Asked for 1800-2500 words it announced *"I am writing this in
two parts… I will save Part Two immediately after this"* and the turn ended. **Part Two arrived 0
times out of 4 across both runs.** The owner's ruling (2026-09-04) is that the ~1500-word ceiling
is the MODEL'S limit and the platform already answers it with PlanForge/scenes — so the skill now
points there instead of letting the model improvise a split it never finishes.

⚠️ WHAT THIS FILE CAN AND CANNOT PROVE. It asserts the SKILL TEXT the model is given. It does not
prove the model obeys it — only a live run does that, and the post-fix run is the evidence there
(3 chapters, 3 creates, every one carrying its body). A prompt assertion that pretended to be a
behavioural one would be the "mechanism that fires without mattering" this repo keeps paying for.
"""
from __future__ import annotations

from app.services.book_skill import BOOK_SKILL_PROMPT as P


def test_the_create_line_no_longer_says_empty_is_fine():
    """🔴 THE MEASURED SENTENCE. It read as a recommendation and the model took it as one."""
    assert "empty is fine" not in P, (
        "the book skill still tells the model an empty chapter is fine on create — that sentence "
        "is what four stranded chapters were created by"
    )


def test_the_create_line_tells_the_model_to_pass_the_prose():
    """The positive half. Removing the bad advice is not the same as giving the good advice: the
    one-call path (`create` WITH `body`) already worked and produced complete chapters, and
    nothing on this surface pointed at it."""
    i = P.index("book_chapter_create(book_id")
    window = P[i:i + 700]
    assert "PASS IT AS `body`" in window, window[:300]
    assert "ONE tool call" in window


def test_the_create_line_names_the_cost_of_omitting_body():
    """"Optional" reads as harmless. What it costs is a chapter the author cannot read."""
    i = P.index("book_chapter_create(book_id")
    window = P[i:i + 700]
    assert "0 words" in window and "cannot read" in window, window[:300]


def test_body_is_still_described_as_OPTIONAL():
    """🔴 THE ARM THAT KEEPS THIS HONEST. A skeleton of empty chapters, filled in later, is real
    authoring and was never the defect. If this text ever hardens into "body is required" it will
    be refusing a legitimate workflow to prevent a mistake the model no longer makes."""
    i = P.index("book_chapter_create(book_id")
    window = P[i:i + 700]
    assert "optional" in window.lower(), window[:300]


def test_the_skill_forbids_the_two_part_split_and_says_why():
    """The split is the model's own invention and it never completes it. The prohibition carries
    its measurement so a future reader can check it rather than trust it."""
    assert "Do NOT announce a multi-part split" in P
    assert "0 times out" in P, "the prohibition must carry the measurement that justifies it"


def test_the_skill_points_at_the_composition_path_for_long_chapters():
    """The owner's ruling: the ceiling is the model's, and PlanForge/scenes is the platform's
    answer. A prohibition with no alternative would just leave the model stuck."""
    i = P.index("## Length:")
    window = P[i:i + 1400]
    assert "composition" in window.lower(), window[:400]
    assert "scenes" in window.lower()
    # And it must name the ceiling, or "more than that" has no referent.
    assert "1,200-1,500 words" in window


def test_the_length_section_does_not_re_teach_composition():
    """🔴 THE STANDARD THIS REPO ALREADY HOLDS (skill-authoring spec §8b.5): a skill cross-
    references an adjacent domain, never re-teaches it. Two copies of the composition workflow
    would go stale in one of them and then actively mislead."""
    i = P.index("## Length:")
    window = P[i:i + 1400]
    assert "do not re-derive it here" in window
    # A re-teach would name the actual tools; a cross-reference names the family.
    for tool in ("composition_outline_node_edit", "composition_generate", "composition_create_work"):
        assert tool not in window, f"{tool} is re-taught in the length section; cross-reference it"
