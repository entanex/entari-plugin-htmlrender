"""Static probes for structured public rendering failures."""

from typing_extensions import assert_type

from entari_plugin_htmlrender import HtmlRenderError
from entari_plugin_htmlrender.errors import ErrorCause


def _probe(error: HtmlRenderError) -> None:
    assert_type(error.message, str)
    assert_type(error.message_truncated, bool)
    causes = assert_type(error.causes, tuple[ErrorCause, ...])
    assert_type(error.causes_truncated, bool)
    for cause in causes:
        assert_type(cause.exception_type, str)
        assert_type(cause.message, str)
        assert_type(cause.truncated, bool)
