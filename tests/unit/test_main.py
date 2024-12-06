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
        (["http://localhost:5601", "--port", "8080"], "http://localhost:5601", 8080),
        # default port
        (["https://localhost:5601"], "https://localhost:5601", 9684),
    ],
)
def test_parse_command_line(command, expected_url, expected_port):
    args = main.parse_command_line(command)
    assert args.url == expected_url
    assert args.port == expected_port


@pytest.mark.parametrize("args", [[], ["-h"], ["--help"], ["help"]])
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


@patch("src.main.DashBoardsCollector")
@patch("src.main.REGISTRY")
@patch("src.main.make_server")
@patch("src.main.make_wsgi_app")
@patch("src.main.setup_logging")
@patch("src.main.parse_command_line")
def test_main(
    mock_cli, mock_setup_logging, mock_wsgi_app, mock_server, mock_registry, mock_collector
):
    # Configure the mock CLI response
    cli_response = MagicMock()
    cli_response.port = 9684
    cli_response.url = "https://localhost"
    mock_cli.return_value = cli_response

    # Configure the mock WSGI app
    mock_wsgi_app_instance = MagicMock()
    mock_wsgi_app.return_value = mock_wsgi_app_instance

    main.main()

    mock_cli.assert_called_once()
    mock_setup_logging.assert_called_once()
    mock_wsgi_app.assert_called_once()
    mock_server.assert_called_once_with("", 9684, mock_wsgi_app_instance)
    mock_collector.assert_called_once()
    mock_registry.register.assert_called_once()
