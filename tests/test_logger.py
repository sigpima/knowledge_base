import logging

from app.infrastructure.observability.logger import get_logger


def test_get_logger_returns_named_logger():
    logger = get_logger("app.test.module")
    assert logger.name == "app.test.module"


def test_get_logger_is_configured_at_settings_log_level(caplog):
    logger = get_logger("app.test.level")
    with caplog.at_level(logging.INFO):
        logger.info("hello")
    assert "hello" in caplog.text
