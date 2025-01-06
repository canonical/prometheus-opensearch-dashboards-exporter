# Copyright 2024 Canonical Ltd.
# See LICENSE file for licensing details.

from unittest.mock import ANY, MagicMock, patch

import pytest

from src import main
from src.main import logging


def test_setup_logging(caplog):
    main.setup_logging()

    with caplog.at_level(logging.INFO):
        logging.info("Test log message")

    assert len(caplog.records) == 1
    log_record = caplog.records[0]
    assert log_record.levelname == "INFO"
    assert log_record.message == "Test log message"


@pytest.mark.parametrize(
    "command, expected_url, expected_port",
    [
        (["--url", "http://10.12.21.8:5601","--port", "8080"], "http://10.12.21.8:5601", 8080),
        # default port and url
        ([], "http://localhost:5601", 9684),
    ],
)
def test_parse_command_line(command, expected_url, expected_port):
    args = main.parse_command_line(command)
    assert args.url == expected_url
    assert args.port == expected_port


@pytest.mark.parametrize("args", [["-h"], ["--help"], ["help"]])
@patch(
    "src.main.argparse.ArgumentParser.print_help",
    autospec=True,
)
@patch("src.main.argparse.ArgumentParser.exit", autospec=True)
def test_parse_command_line_help(mock_exit, mock_print_help, args):
    mock_exit.side_effect = SystemExit
    with pytest.raises(SystemExit):
        main.parse_command_line(args)
    mock_print_help.assert_called_once()
    mock_exit.assert_called_once_with(ANY)


@patch("src.main.APP")
def test_metrics_app(mocked_app):
    mocked_environ = MagicMock()
    mocked_environ.get.return_value = "/metrics"
    mocked_start_response = MagicMock()

    main.metrics_app(mocked_environ, mocked_start_response)
    mocked_app.assert_called_with(mocked_environ, mocked_start_response)


@pytest.mark.parametrize("path", ["/", "/foo", "/metrics/thread"])
def test_metrics_app_other_path(path):
    mocked_environ = MagicMock()
    mocked_environ.get.return_value = path
    mocked_start_response = MagicMock()

    assert main.metrics_app(mocked_environ, mocked_start_response) == [b"404 Not Found"]


@patch("src.main.DashBoardsCollector")
@patch("src.main.REGISTRY")
@patch("src.main.make_server")
@patch("src.main.metrics_app")
@patch("src.main.setup_logging")
@patch("src.main.parse_command_line")
def test_main(
    mock_cli, mock_setup_logging, mock_metrics_app, mock_server, mock_registry, mock_collector
):
    # Configure the mock CLI response
    cli_response = MagicMock()
    cli_response.port = 9684
    cli_response.url = "https://localhost"
    mock_cli.return_value = cli_response

    main.main()

    mock_cli.assert_called_once()
    mock_setup_logging.assert_called_once()
    mock_server.assert_called_once_with("", 9684, mock_metrics_app)
    mock_collector.assert_called_once()
    mock_registry.register.assert_called_once()
