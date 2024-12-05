# Copyright 2024 Canonical Ltd.
# See LICENSE file for licensing details.

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


def test_get_overall_status_metric(api_response, mock_gauge):
    collector._get_overall_status_metric(api_response)
    expected_value = api_response["status"]["overall"]
    mock_gauge.assert_called_with(
        name="opensearch_dashboards_status",
        documentation="General state of the dashboards cluster",
        labels=expected_value.keys(),
    )
    mock_gauge.add_metric.assert_called_with(list(expected_value.values()), 0)


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


@pytest.mark.parametrize(
    "result_unknown_api",
    [
        collector._get_overall_status_metric(UNKNOWN_API_RESPONSE),
        collector._get_current_connections_metric(UNKNOWN_API_RESPONSE),
        collector._get_up_time_metric(UNKNOWN_API_RESPONSE),
        collector._get_event_loop_delay_metric(UNKNOWN_API_RESPONSE),
        collector._get_resident_set_size(UNKNOWN_API_RESPONSE),
        collector._get_heap_total(UNKNOWN_API_RESPONSE),
        collector._get_heap_used(UNKNOWN_API_RESPONSE),
        collector._get_heap_limit(UNKNOWN_API_RESPONSE),
        collector._get_load_1m(UNKNOWN_API_RESPONSE),
        collector._get_load_5m(UNKNOWN_API_RESPONSE),
        collector._get_load_15m(UNKNOWN_API_RESPONSE),
        collector._get_os_mem_total(UNKNOWN_API_RESPONSE),
        collector._get_os_mem_free(UNKNOWN_API_RESPONSE),
        collector._get_os_mem_used(UNKNOWN_API_RESPONSE),
        collector._get_resp_time_avg(UNKNOWN_API_RESPONSE),
        collector._get_resp_time_max(UNKNOWN_API_RESPONSE),
        collector._get_req_disconnects(UNKNOWN_API_RESPONSE),
        collector._get_req_total(UNKNOWN_API_RESPONSE),
    ],
)
def test_get_unknown_api_response(result_unknown_api, mock_gauge):
    assert result_unknown_api is None
    assert mock_gauge.assert_not_called


def test_get_unknown_statuses_api_response(mock_gauge):
    assert collector._get_statuses_metrics(UNKNOWN_API_RESPONSE) == []
    assert mock_gauge.assert_not_called
