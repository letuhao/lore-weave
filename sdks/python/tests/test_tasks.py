

# TOOLV2 LOOP #229 — TaskNotFound's message was the id the caller had just sent.
#
# Measured on composition_task_provide_input with an unknown task_id:
#
#     Error executing tool composition_task_provide_input: '019f0000-0000-7000-8000-000000000000'
#
# That is the whole message. TaskNotFound subclasses KeyError, and KeyError.__str__ renders
# repr(args[0]), so `raise TaskNotFound(task_id)` produces the id in quotes and nothing else — no
# noun, no state, no next step. The subclassing is load-bearing for callers that catch KeyError,
# so __str__ is overridden rather than every raise site rewritten.
def test_task_not_found_reads_as_a_sentence_not_a_bare_id():
    from loreweave_mcp.tasks import TaskNotFound

    msg = str(TaskNotFound("019f0000-0000-7000-8000-000000000000"))
    assert msg != "'019f0000-0000-7000-8000-000000000000'", "the bare-id rendering is back"
    assert "no pending task" in msg
    # The three states that produce it are genuinely indistinguishable from outside, so naming all
    # three is honest where picking one would be a guess.
    assert "never created" in msg and "already" in msg and "expired" in msg
    # ...and a next step, which is the part a bare id can never carry.
    assert "Re-run the action" in msg


def test_the_id_and_the_keyerror_contract_both_survive():
    """Callers catch KeyError and read args[0]; the nicer message must not cost either."""
    from loreweave_mcp.tasks import TaskNotFound

    exc = TaskNotFound("019f0000-0000-7000-8000-000000000000")
    assert isinstance(exc, KeyError)
    assert exc.args[0] == "019f0000-0000-7000-8000-000000000000"
    assert "019f0000-0000-7000-8000-000000000000" in str(exc)


def test_it_does_not_explode_when_raised_without_an_id():
    from loreweave_mcp.tasks import TaskNotFound

    assert "none given" in str(TaskNotFound())
