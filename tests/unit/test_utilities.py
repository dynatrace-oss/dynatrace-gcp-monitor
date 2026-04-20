import os
from unittest.mock import patch

from lib.utilities import safe_read_yaml


def test_safe_read_yaml_logs_on_file_error_fallback(tmp_path):
    """safe_read_yaml logs a warning when falling back to env var due to file read error."""
    non_existent_file = str(tmp_path / "does_not_exist.yaml")

    with patch.dict(os.environ, {"TEST_FALLBACK_VAR": "key: value"}):
        with patch("lib.utilities.LoggingContext") as mock_logging_context_cls:
            mock_ctx = mock_logging_context_cls.return_value
            result = safe_read_yaml(non_existent_file, "TEST_FALLBACK_VAR")

    assert result == {"key": "value"}
    mock_ctx.log.assert_called_once()
    log_message = mock_ctx.log.call_args[0][0]
    assert "does_not_exist.yaml" in log_message
    assert "TEST_FALLBACK_VAR" in log_message


def test_safe_read_yaml_reads_file_successfully(tmp_path):
    """safe_read_yaml reads a valid YAML file without falling back."""
    yaml_file = tmp_path / "config.yaml"
    yaml_file.write_text("services:\n  - name: test\n")

    result = safe_read_yaml(str(yaml_file), "UNUSED_ENV_VAR")

    assert result == {"services": [{"name": "test"}]}


def test_safe_read_yaml_returns_empty_dict_on_empty_file(tmp_path):
    """safe_read_yaml returns {} for empty/null YAML files."""
    yaml_file = tmp_path / "empty.yaml"
    yaml_file.write_text("")

    result = safe_read_yaml(str(yaml_file), "UNUSED_ENV_VAR")

    assert result == {}
