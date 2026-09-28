"""What a failed background task shows the user (AgentRun.error) - must never leak raw exception
class names, internal URLs, or library-generated text; the full exception still goes to the logs
via dispatch()'s log.exception call, this only governs what's user-facing."""

import httpx

from rolewise.worker.tasks import _user_facing_error


def test_deliberate_value_error_message_passes_through():
    exc = ValueError("Couldn't identify this job's source automatically. Paste the description instead.")
    assert _user_facing_error(exc) == "Couldn't identify this job's source automatically. Paste the description instead."


def test_deliberate_permission_error_message_passes_through():
    exc = PermissionError("Job source greenhouse:acme is not allow-listed")
    assert _user_facing_error(exc) == "Job source greenhouse:acme is not allow-listed"


def test_library_exception_is_replaced_with_a_generic_message():
    # The exact bug this regresses: an unhandled httpx error leaked the internal API URL and an
    # MDN documentation link straight into a user-facing error message.
    request = httpx.Request("GET", "https://boards-api.greenhouse.io/v1/boards/nonexistent/jobs")
    response = httpx.Response(404, request=request)
    exc = httpx.HTTPStatusError("404 Not Found", request=request, response=response)
    message = _user_facing_error(exc)
    assert message == "Something went wrong while processing this. Please try again."
    assert "greenhouse.io" not in message
    assert "HTTPStatusError" not in message
    assert "developer.mozilla.org" not in message


def test_unexpected_exception_type_is_replaced_with_a_generic_message():
    assert _user_facing_error(KeyError("some_internal_dict_key")) == \
        "Something went wrong while processing this. Please try again."


def test_value_error_with_no_message_falls_back_to_generic():
    # str(ValueError()) is "" - an empty message is not useful to show either.
    assert _user_facing_error(ValueError()) == "Something went wrong while processing this. Please try again."
