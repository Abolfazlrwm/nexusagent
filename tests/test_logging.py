import logging

import pytest

from nexusagent.logging import configure_logging, get_logger


@pytest.fixture(autouse=True)
def reset_nexusagent_logger():
    """Ensure each test starts and ends with a clean logger state."""
    logger = logging.getLogger("nexusagent")
    original_handlers = list(logger.handlers)
    original_level = logger.level
    original_propagate = logger.propagate

    logger.handlers.clear()

    yield

    logger.handlers.clear()
    logger.handlers.extend(original_handlers)
    logger.setLevel(original_level)
    logger.propagate = original_propagate


def test_get_logger_without_name_returns_root_nexusagent_logger():
    logger = get_logger()

    assert logger.name == "nexusagent"


def test_get_logger_with_name_returns_named_logger():
    logger = get_logger("nexusagent.agent")

    assert logger.name == "nexusagent.agent"


def test_configure_logging_attaches_console_handler():
    logger = configure_logging()

    stream_handlers = [h for h in logger.handlers if isinstance(h, logging.StreamHandler)]
    assert len(stream_handlers) == 1


def test_configure_logging_is_idempotent():
    configure_logging()
    configure_logging()
    logger = configure_logging()

    stream_handlers = [h for h in logger.handlers if isinstance(h, logging.StreamHandler)]
    assert len(stream_handlers) == 1


def test_configured_log_level_is_respected():
    logger = configure_logging(level="WARNING")

    assert logger.level == logging.WARNING


def test_invalid_log_level_raises_value_error():
    with pytest.raises(ValueError):
        configure_logging(level="NOT_A_LEVEL")


def test_log_output_contains_level_name_and_message(capsys):
    logger = configure_logging(level="INFO")

    logger.info("Something happened")

    captured = capsys.readouterr()
    assert "INFO" in captured.err
    assert "nexusagent" in captured.err
    assert "Something happened" in captured.err


def test_default_level_comes_from_settings(monkeypatch):
    monkeypatch.setenv("NEXUS_LOG_LEVEL", "DEBUG")

    logger = configure_logging()

    assert logger.level == logging.DEBUG
