# Copyright 2024 Canonical Ltd.
# See LICENSE file for licensing details.
"""OpenSearch Dashboards Collector."""

import json
import logging
from dataclasses import dataclass
from typing import Generator, Optional

import requests
from prometheus_client.core import GaugeMetricFamily, Metric
from prometheus_client.registry import Collector
from requests.auth import HTTPBasicAuth
from requests.exceptions import HTTPError, RequestException, Timeout

METRICS_PREFIX = "opensearch_dashboards_"
API_STATUS_ENDPOINT = "/api/status"

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class Config:
    """Wrap CLI arguments and environment variables necessary to get metrics from the API."""

    url: str
    user: str
    password: str


class DashBoardsCollector(Collector):
    """OpenSearch Dashboards Collector"""

    def __init__(self, config: Config) -> None:
        super().__init__()
        self.config = config

    def collect(self) -> Generator[Metric, None, None]:
        """Collect all the metrics from /api/status to be exported.

        Yields:
            Generator[Metric]: the internal status metrics of status
        """
        api_up = GaugeMetricFamily(
            name=f"{METRICS_PREFIX}up",
            documentation="Whether the data source is reachable (1 for up, 0 for down)",
        )
        try:
            if api_metrics := collect_api_status(self.config):
                api_up.add_metric([], 1)
                for metric in self.metrics(api_metrics):
                    description, value = metric
                    if value:
                        yield value
                    else:
                        logger.error("It was not possible to get the metric: %s", description)
            else:
                api_up.add_metric([], 0)

        except Exception as e:  # pylint: disable=broad-except
            logger.error("An unexpected error occurred: %s", e)
            api_up.add_metric([], 0)

        yield api_up

    def metrics(self, api_metrics: dict) -> list[tuple[str, Optional[Metric]]]:
        """Get the OpenSearch dashboard prometheus metrics.

        Returns:
            list[tuple[str, Optional[Metric]]]: Prometheus Gauge metrics of the dashboards
        """
        return [
            ("status", _get_overall_status_metric(api_metrics)),
            ("current_connections", _get_current_connections_metric(api_metrics)),
            ("up_time", _get_up_time_metric(api_metrics)),
            ("event_loop_delay", _get_event_loop_delay_metric(api_metrics)),
            ("heap_total", _get_heap_total(api_metrics)),
            ("heap_used", _get_heap_used(api_metrics)),
            ("heap_limit", _get_heap_limit(api_metrics)),
            ("re_set_size", _get_resident_set_size(api_metrics)),
            ("load_1m", _get_load_1m(api_metrics)),
            ("load_5m", _get_load_5m(api_metrics)),
            ("load_15m", _get_load_15m(api_metrics)),
            ("os_mem_total", _get_os_mem_total(api_metrics)),
            ("os_mem_free", _get_os_mem_free(api_metrics)),
            ("os_mem_used", _get_os_mem_used(api_metrics)),
            ("resp_time_avg", _get_resp_time_avg(api_metrics)),
            ("resp_time_max", _get_resp_time_max(api_metrics)),
            ("req_disconnects", _get_req_disconnects(api_metrics)),
            ("req_total", _get_req_total(api_metrics)),
        ] + [("statuses", status) for status in _get_statuses_metrics(api_metrics)]


def collect_api_status(config: Config) -> dict:
    """Use the dashboard API to get the status of the dashboard.

    Args:
        config (Config): Config necessary to access the information.

    Returns:
        dict: Raw response from the API
    """
    auth = HTTPBasicAuth(config.user, config.password)
    headers = {"Accept": "application/json"}
    url = f"{config.url}{API_STATUS_ENDPOINT}"

    try:
        with requests.Session() as session:
            response = session.get(
                url,
                auth=auth,
                verify=False,
                headers=headers,
                timeout=5,
            )
        response.raise_for_status()
        return json.loads(response.text)
    except HTTPError as e:
        logger.error(
            "Request to %s status code: %s response text %s.",
            url,
            e.response.status_code,
            e.response.text,
        )
    except Timeout:
        logger.error("Request to %s timed out.", url)
    except RequestException as e:
        logger.error("It was not possible to collect the OpenSearch Dashboards metrics %s", e)

    return {}


def _get_overall_status_metric(api_metrics: dict) -> Optional[Metric]:
    """Get the overall status of the dashboards.

    Args:
        api_metrics (dict): Response from the API

    Returns:
        Optional[Metric]: Prometheus Gauge metric if the metric exist in the API
    """
    metric_name = f"{METRICS_PREFIX}status"
    match api_metrics:
        case {"status": {"overall": value}}:
            overall_status_metric = GaugeMetricFamily(
                name=metric_name,
                documentation="General state of the dashboards cluster",
                labels=value.keys(),
            )
            overall_status_metric.add_metric(list(value.values()), _get_status_value(value))
            return overall_status_metric
        case _:
            return None


def _get_status_value(status: dict[str, str]) -> float:
    """Get the status from the dashboard depending on the color.

    If the cluster is green, it will return 0
    If the cluster is yellow, it will return 1
    If the cluster is red, it will return 2
    If the metric is unknown, it will return -1

    Note that the this output value is to match the same behavior from the OpenSearch exporter.

    Args:
        status (dict[str, str]): _description_

    Returns:
        int: _description_
    """
    match status:
        case {"state": "green"}:
            return 0
        case {"state": "yellow"}:
            return 1
        case {"state": "red"}:
            return 2
        case _:
            return -1


def _get_statuses_metrics(api_metrics: dict) -> list[Metric]:
    """Get the OpenSearch dashboards granular state of plugins and core components.

    Args:
        api_metrics (dict): Response from the API

    Returns:
        Optional[list[Metric]]: Prometheus Gauge metrics if the statuses exist in the API
    """
    metric_name = f"{METRICS_PREFIX}statuses"
    statuses_metrics = []
    match api_metrics:
        case {"status": {"statuses": statuses}}:
            for status_labels in statuses:
                overall_status_metric = GaugeMetricFamily(
                    name=metric_name,
                    documentation=(
                        "OpenSearch dashboards granular state of plugins and core components"
                    ),
                    labels=status_labels.keys(),
                )
                overall_status_metric.add_metric(
                    status_labels.values(), _get_status_value(status_labels)
                )
                statuses_metrics.append(overall_status_metric)
            return statuses_metrics
        case _:
            return statuses_metrics


def _get_current_connections_metric(api_metrics: dict) -> Optional[Metric]:
    """Get the OpenSearch dashboards number of concurrent connections.

    Args:
        api_metrics (dict): Response from the API

    Returns:
        Optional[Metric]: Prometheus Gauge metric if the metric exist in the API
    """
    metric_name = f"{METRICS_PREFIX}current_connections"
    match api_metrics:
        case {"metrics": {"concurrent_connections": concurrent_connections}}:
            return GaugeMetricFamily(
                name=metric_name,
                documentation="OpenSearch dashboards number of concurrent connections",
                value=concurrent_connections,
            )
        case _:
            return None


def _get_up_time_metric(api_metrics: dict) -> Optional[Metric]:
    """Get the OpenSearch dashboards up time in milliseconds.

    Args:
        api_metrics (dict): Response from the API

    Returns:
        Optional[Metric]: Prometheus Gauge metric if the metric exist in the API
    """
    metric_name = f"{METRICS_PREFIX}up_time"
    match api_metrics:
        case {"metrics": {"process": {"uptime_in_millis": value}}}:
            return GaugeMetricFamily(
                name=metric_name,
                documentation="OpenSearch dashboards up time in milliseconds",
                value=value,
            )
        case _:
            return None


def _get_event_loop_delay_metric(api_metrics: dict) -> Optional[Metric]:
    """Get the Opensearch dashboards event loop delay in milliseconds.

    Args:
        api_metrics (dict): Response from the API

    Returns:
        Optional[Metric]: Prometheus Gauge metric if the metric exist in the API
    """
    metric_name = f"{METRICS_PREFIX}event_loop_delay"
    match api_metrics:
        case {"metrics": {"process": {"event_loop_delay": value}}}:
            return GaugeMetricFamily(
                name=metric_name,
                documentation="Opensearch dashboards event loop delay in milliseconds",
                value=value,
            )
        case _:
            return None


def _get_resident_set_size(api_metrics: dict) -> Optional[Metric]:
    """Get the Opensearch dashboards resident set size in bytes.

    Args:
        api_metrics (dict): Response from the API

    Returns:
        Optional[Metric]: Prometheus Gauge metric if the metric exist in the API
    """
    metric_name = f"{METRICS_PREFIX}re_set_size"
    match api_metrics:
        case {"metrics": {"process": {"memory": {"resident_set_size_in_bytes": value}}}}:
            return GaugeMetricFamily(
                name=metric_name,
                documentation="Opensearch dashboards resident set size in bytes",
                value=value,
            )
        case _:
            return None


def _get_heap_total(api_metrics: dict) -> Optional[Metric]:
    """Get the Opensearch dashboards memory heap total in bytes.

    Args:
        api_metrics (dict): Response from the API

    Returns:
        Optional[Metric]: Prometheus Gauge metric if the metric exist in the API
    """
    metric_name = f"{METRICS_PREFIX}heap_total"
    match api_metrics:
        case {"metrics": {"process": {"memory": {"heap": {"total_in_bytes": value}}}}}:
            return GaugeMetricFamily(
                name=metric_name,
                documentation="Opensearch dashboards memory heap total in bytes",
                value=value,
            )
        case _:
            return None


def _get_heap_used(api_metrics: dict) -> Optional[Metric]:
    """Get the Opensearch dashboards memory heap used in bytes.

    Args:
        api_metrics (dict): Response from the API

    Returns:
        Optional[Metric]: Prometheus Gauge metric if the metric exist in the API
    """
    metric_name = f"{METRICS_PREFIX}heap_used"
    match api_metrics:
        case {"metrics": {"process": {"memory": {"heap": {"used_in_bytes": value}}}}}:
            return GaugeMetricFamily(
                name=metric_name,
                documentation="Opensearch dashboards memory heap used in bytes",
                value=value,
            )
        case _:
            return None


def _get_heap_limit(api_metrics: dict) -> Optional[Metric]:
    """Get theOpensearch dashboards memory heap limit set in bytes.

    Args:
        api_metrics (dict): Response from the API

    Returns:
        Optional[Metric]: Prometheus Gauge metric if the metric exist in the API
    """
    metric_name = f"{METRICS_PREFIX}heap_limit"
    match api_metrics:
        case {"metrics": {"process": {"memory": {"heap": {"size_limit": value}}}}}:
            return GaugeMetricFamily(
                name=metric_name,
                documentation="Opensearch dashboards memory heap limit set in bytes",
                value=value,
            )
        case _:
            return None


def _get_load_1m(api_metrics: dict) -> Optional[Metric]:
    """Get the OpenSearch dashboards load average 1m.

    Args:
        api_metrics (dict): Response from the API

    Returns:
        Optional[Metric]: Prometheus Gauge metric if the metric exist in the API
    """
    metric_name = f"{METRICS_PREFIX}load1m"
    match api_metrics:
        case {"metrics": {"os": {"load": {"1m": value}}}}:
            return GaugeMetricFamily(
                name=metric_name,
                documentation="OpenSearch dashboards load average 1m",
                value=value,
            )
        case _:
            return None


def _get_load_5m(api_metrics: dict) -> Optional[Metric]:
    """Get the OpenSearch dashboards load average 5m.

    Args:
        api_metrics (dict): Response from the API

    Returns:
        Optional[Metric]: Prometheus Gauge metric if the metric exist in the API
    """
    metric_name = f"{METRICS_PREFIX}load5m"
    match api_metrics:
        case {"metrics": {"os": {"load": {"5m": value}}}}:
            return GaugeMetricFamily(
                name=metric_name,
                documentation="OpenSearch dashboards load average 5m",
                value=value,
            )
        case _:
            return None


def _get_load_15m(api_metrics: dict) -> Optional[Metric]:
    """Get the OpenSearch dashboards load average 15m.

    Args:
        api_metrics (dict): Response from the API

    Returns:
        Optional[Metric]: Prometheus Gauge metric if the metric exist in the API
    """
    metric_name = f"{METRICS_PREFIX}load15m"
    match api_metrics:
        case {"metrics": {"os": {"load": {"15m": value}}}}:
            return GaugeMetricFamily(
                name=metric_name,
                documentation="OpenSearch dashboards load average 15m",
                value=value,
            )
        case _:
            return None


def _get_os_mem_total(api_metrics: dict) -> Optional[Metric]:
    """Get the OpenSearch dashboards memory total in bytes.

    Args:
        api_metrics (dict): Response from the API

    Returns:
        Optional[Metric]: Prometheus Gauge metric if the metric exist in the API
    """
    metric_name = f"{METRICS_PREFIX}os_mem_total"
    match api_metrics:
        case {"metrics": {"os": {"memory": {"total_in_bytes": value}}}}:
            return GaugeMetricFamily(
                name=metric_name,
                documentation="OpenSearch dashboards memory total in bytes",
                value=value,
            )
        case _:
            return None


def _get_os_mem_free(api_metrics: dict) -> Optional[Metric]:
    """Get the free memory in bytes from the dashboard machine.

    Args:
        api_metrics (dict): Response from the API

    Returns:
        Optional[Metric]: Prometheus Gauge metric if the metric exist in the API
    """
    metric_name = f"{METRICS_PREFIX}os_mem_free"
    match api_metrics:
        case {"metrics": {"os": {"memory": {"free_in_bytes": value}}}}:
            return GaugeMetricFamily(
                name=metric_name,
                documentation="OpenSearch dashboards memory free in bytes",
                value=value,
            )
        case _:
            return None


def _get_os_mem_used(api_metrics: dict) -> Optional[Metric]:
    """Get the memory used in bytes from the dashboard machine.

    Args:
        api_metrics (dict): Response from the API

    Returns:
        Optional[Metric]: Prometheus Gauge metric if the metric exist in the API
    """
    metric_name = f"{METRICS_PREFIX}os_mem_used"
    match api_metrics:
        case {"metrics": {"os": {"memory": {"used_in_bytes": value}}}}:
            return GaugeMetricFamily(
                name=metric_name,
                documentation="OpenSearch dashboards memory used in bytes",
                value=value,
            )
        case _:
            return None


def _get_resp_time_avg(api_metrics: dict) -> Optional[Metric]:
    """Get the OpenSearch dashboards average response time in milliseconds.

    Args:
        api_metrics (dict): Response from the API

    Returns:
        Optional[Metric]: Prometheus Gauge metric if the metric exist in the API
    """
    metric_name = f"{METRICS_PREFIX}resp_time_avg"
    match api_metrics:
        case {"metrics": {"response_times": {"avg_in_millis": value}}}:
            return GaugeMetricFamily(
                name=metric_name,
                documentation="OpenSearch dashboards average response time in milliseconds",
                value=value,
            )
        case _:
            return None


def _get_resp_time_max(api_metrics: dict) -> Optional[Metric]:
    """Get the OpenSearch dashboards maximum response time in milliseconds.

    Args:
        api_metrics (dict): Response from the API

    Returns:
        Optional[Metric]: Prometheus Gauge metric if the metric exist in the API
    """
    metric_name = f"{METRICS_PREFIX}resp_time_max"
    match api_metrics:
        case {"metrics": {"response_times": {"max_in_millis": value}}}:
            return GaugeMetricFamily(
                name=metric_name,
                documentation="OpenSearch dashboards maximum response time in milliseconds",
                value=value,
            )
        case _:
            return None


def _get_req_disconnects(api_metrics: dict) -> Optional[Metric]:
    """Get the OpenSearch dashboards request disconnections count.

    Args:
        api_metrics (dict): Response from the API

    Returns:
        Optional[Metric]: Prometheus Gauge metric if the metric exist in the API
    """
    metric_name = f"{METRICS_PREFIX}req_disconnects"
    match api_metrics:
        case {"metrics": {"requests": {"disconnects": value}}}:
            return GaugeMetricFamily(
                name=metric_name,
                documentation="OpenSearch dashboards request disconnections count",
                value=value,
            )
        case _:
            return None


def _get_req_total(api_metrics: dict) -> Optional[Metric]:
    """Get the OpenSearch dashboards total request count.

    Args:
        api_metrics (dict): Response from the API

    Returns:
        Optional[Metric]: Prometheus Gauge metric if the metric exist in the API
    """
    metric_name = f"{METRICS_PREFIX}req_total"
    match api_metrics:
        case {"metrics": {"requests": {"disconnects": value}}}:
            return GaugeMetricFamily(
                name=metric_name,
                documentation="OpenSearch dashboards total request count",
                value=value,
            )
        case _:
            return None
