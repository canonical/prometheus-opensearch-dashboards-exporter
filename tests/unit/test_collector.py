# Copyright 2024 Canonical Ltd.
# See LICENSE file for licensing details.

import json
from unittest.mock import MagicMock, patch

import pytest

from src import collector

# simulate a complete change in the API
UNKNOWN_API_RESPONSE = {
    "status": {"green": "foo"},
    "metrics": {"memory": "bar"},
    "name": "my-name",
    "uuid": "my-uuid",
    "version": "my-version",
}


def test_dashboard_collector_metrics(api_response, mock_config):
    dashboards_collector = collector.DashBoardsCollector(mock_config)

    # the mocked response at dashboards_response.json is suppose to have 20 metrics
    assert len(dashboards_collector.metrics(api_response)) == 20


def test_dashboard_collector_metrics_empty_response(api_response, mock_config):
    dashboards_collector = collector.DashBoardsCollector(mock_config)
    assert dashboards_collector.metrics({}) == []


def test_dashboard_collector_collect_success(mock_gauge, mock_collect_api_status, mock_config):
    dashboards_collector = collector.DashBoardsCollector(mock_config)
    collected = [metric for metric in dashboards_collector.collect()]

    # the mocked response at dashboards_response.json is suppose to have 20 metrics + 1 metric if
    # the data source is reachable
    assert len(collected) == 21
    mock_collect_api_status.assert_called_once_with(mock_config)
    # data source was reachable
    mock_gauge.assert_any_call(
        name=f"{collector.METRICS_PREFIX}up",
        documentation="Whether the data source is reachable (1 for up, 0 for down)",
        value=1,
    )


def test_dashboard_collector_collect_failed(mock_gauge, mock_collect_api_status, mock_config):
    dashboards_collector = collector.DashBoardsCollector(mock_config)
    # response from the API failed for some reason
    mock_collect_api_status.return_value = {}
    collected = [metric for metric in dashboards_collector.collect()]

    # just the metric that the service was not reachable returns
    assert len(collected) == 1
    mock_gauge.assert_any_call(
        name=f"{collector.METRICS_PREFIX}up",
        documentation="Whether the data source is reachable (1 for up, 0 for down)",
        value=0,
    )


@patch("src.collector.logger")
@patch("src.collector.DashBoardsCollector.metrics")
def test_dashboard_collector_collect_metric_failed(
    mock_metrics, mock_log, mock_gauge, mock_config, mock_collect_api_status
):
    dashboards_collector = collector.DashBoardsCollector(mock_config)
    # during the metrics process one metric failed to process, in this case the up time
    mock_metrics.return_value = [
        ("opensearch_dashboards_status", mock_gauge),
        ("opensearch_dashboards_up_time", None),
    ]

    [metric for metric in dashboards_collector.collect()]

    mock_log.error.assert_called_once()
    mock_gauge.assert_any_call(
        name=f"{collector.METRICS_PREFIX}up",
        documentation="Whether the data source is reachable (1 for up, 0 for down)",
        value=1,
    )


@patch("src.collector.requests.Session")
def test_collect_api_status_success(mock_session, api_response, mock_config):
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.text = json.dumps(api_response)
    mock_session.return_value.__enter__.return_value.get.return_value = mock_response

    assert collector.collect_api_status(mock_config) == api_response


@patch("src.collector.requests.Session")
@patch("src.collector.logger")
def test_collect_api_status_http_error(mock_logger, mock_session, mock_config):
    mock_response = MagicMock()
    mock_response.raise_for_status.side_effect = collector.HTTPError(
        response=MagicMock(status_code=500, text="Internal Server Error")
    )
    mock_session.return_value.__enter__.return_value.get.return_value = mock_response

    assert collector.collect_api_status(mock_config) == {}
    mock_logger.error.assert_called_once()


@pytest.mark.parametrize("exception", [collector.Timeout, collector.RequestException])
@patch("src.collector.requests.Session")
@patch("src.collector.logger")
def test_collect_api_status_other_errors(mock_logger, mock_session, mock_config, exception):
    mock_session.return_value.__enter__.return_value.get.side_effect = exception

    assert collector.collect_api_status(mock_config) == {}
    mock_logger.error.assert_called_once()


def test_get_overall_status_metric(api_response, mock_gauge):
    collector._get_overall_status_metric(api_response)
    expected_value = api_response["status"]["overall"]
    mock_gauge.assert_called_with(
        name="opensearch_dashboards_status",
        documentation="General state of the dashboards cluster",
        labels=expected_value.keys(),
    )
    mock_gauge.add_metric.assert_called_with(list(expected_value.values()), 0)


def test_get_statuses_metrics(api_response, mock_gauge):
    status_metrics = collector._get_statuses_metrics(api_response)
    # there are two statuses in the mocked api response
    assert len(status_metrics) == 2


@pytest.mark.parametrize(
    "status, expected_result",
    [
        ({"state": "green"}, 0),
        ({"state": "yellow"}, 1),
        ({"state": "red"}, 2),
        ({"state": "foo"}, -1),
    ],
)
def test_get_status_value(status, expected_result):
    assert collector._get_status_value(status) == expected_result


def test_get_current_connections_metric(api_response, mock_gauge):
    expected_value = api_response["metrics"]["concurrent_connections"]
    collector._get_current_connections_metric(api_response)
    mock_gauge.assert_called_with(
        name="opensearch_dashboards_current_connections",
        documentation="OpenSearch dashboards number of concurrent connections",
        value=expected_value,
    )


def test_get_up_time_metric(api_response, mock_gauge):
    expected_value = api_response["metrics"]["process"]["uptime_in_millis"]
    collector._get_up_time_metric(api_response)
    mock_gauge.assert_called_with(
        name="opensearch_dashboards_up_time",
        documentation="OpenSearch dashboards up time in milliseconds",
        value=expected_value,
    )


def test_get_event_loop_delay_metric(api_response, mock_gauge):
    expected_value = api_response["metrics"]["process"]["event_loop_delay"]
    collector._get_event_loop_delay_metric(api_response)
    mock_gauge.assert_called_with(
        name="opensearch_dashboards_event_loop_delay",
        documentation="Opensearch dashboards event loop delay in milliseconds",
        value=expected_value,
    )


def test_get_resident_set_size(api_response, mock_gauge):
    expected_value = api_response["metrics"]["process"]["memory"]["resident_set_size_in_bytes"]
    collector._get_resident_set_size(api_response)
    mock_gauge.assert_called_with(
        name="opensearch_dashboards_re_set_size",
        documentation="Opensearch dashboards resident set size in bytes",
        value=expected_value,
    )


@pytest.mark.parametrize("heap", [collector.Heap.TOTAL, collector.Heap.USED, collector.Heap.SIZE])
def test_get_heap(api_response, mock_gauge, heap):
    prefix = heap.value.split("_")[0]
    expected_value = api_response["metrics"]["process"]["memory"]["heap"][heap.value]
    collector._get_heap(api_response, heap)
    mock_gauge.assert_called_with(
        name=f"opensearch_dashboards_heap_{prefix}",
        documentation=f"Opensearch dashboards memory heap {prefix} in bytes",
        value=expected_value,
    )


@pytest.mark.parametrize(
    "load", [collector.Load.ONE_M, collector.Load.FIVE_M, collector.Load.FIFTEEN_M]
)
def test_get_load(api_response, mock_gauge, load):
    expected_value = api_response["metrics"]["os"]["load"][load.value]
    collector._get_load(api_response, load)
    mock_gauge.assert_called_with(
        name=f"opensearch_dashboards_load_{load.value}",
        documentation=f"OpenSearch dashboards load average {load.value}",
        value=expected_value,
    )


@pytest.mark.parametrize(
    "memory", [collector.Memory.USED, collector.Memory.FREE, collector.Memory.TOTAL]
)
def test_get_os_mem(api_response, mock_gauge, memory):
    prefix = memory.value.split("_")[0]
    expected_value = api_response["metrics"]["os"]["memory"][memory.value]
    collector._get_os_mem(api_response, memory)
    mock_gauge.assert_called_with(
        name=f"opensearch_dashboards_os_mem_{prefix}",
        documentation=f"OpenSearch dashboards memory {prefix} in bytes",
        value=expected_value,
    )


@pytest.mark.parametrize("response", [collector.Response.AVG, collector.Response.MAX])
def test_get_resp_time(api_response, mock_gauge, response):
    prefix = response.value.split("_")[0]
    expected_value = api_response["metrics"]["response_times"][response.value]
    collector._get_resp_time(api_response, response)
    mock_gauge.assert_called_with(
        name=f"opensearch_dashboards_resp_time_{prefix}",
        documentation=f"OpenSearch dashboards {prefix} response time in milliseconds",
        value=expected_value,
    )


@pytest.mark.parametrize(
    "request_count", [collector.RequestsCount.DISCONNECTS, collector.RequestsCount.TOTAL]
)
def test_get_req(api_response, mock_gauge, request_count):
    request_count_value = request_count.value
    expected_value = api_response["metrics"]["requests"][request_count_value]
    collector._get_req(api_response, request_count)
    mock_gauge.assert_called_with(
        name=f"opensearch_dashboards_req_{request_count_value}",
        documentation=f"OpenSearch dashboards request {request_count_value} count",
        value=expected_value,
    )


@pytest.mark.parametrize(
    "result_unknown_api",
    [
        collector._get_overall_status_metric(UNKNOWN_API_RESPONSE),
        collector._get_current_connections_metric(UNKNOWN_API_RESPONSE),
        collector._get_up_time_metric(UNKNOWN_API_RESPONSE),
        collector._get_event_loop_delay_metric(UNKNOWN_API_RESPONSE),
        collector._get_resident_set_size(UNKNOWN_API_RESPONSE),
        collector._get_heap(UNKNOWN_API_RESPONSE, collector.Heap.SIZE),
        collector._get_load(UNKNOWN_API_RESPONSE, collector.Load.ONE_M),
        collector._get_os_mem(UNKNOWN_API_RESPONSE, collector.Memory.TOTAL),
        collector._get_resp_time(UNKNOWN_API_RESPONSE, collector.Response.AVG),
        collector._get_req(UNKNOWN_API_RESPONSE, collector.RequestsCount.DISCONNECTS),
    ],
)
def test_get_unknown_api_response(result_unknown_api, mock_gauge):
    assert result_unknown_api is None
    assert mock_gauge.assert_not_called


def test_get_unknown_statuses_api_response(mock_gauge):
    assert collector._get_statuses_metrics(UNKNOWN_API_RESPONSE) == []
    assert mock_gauge.assert_not_called
