# Copyright 2024 Canonical Ltd.
# See LICENSE file for licensing details.
"""OpenSearch Dashboards Collector."""

import json
import logging
from dataclasses import dataclass
from enum import Enum
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


class Heap(Enum):
    """Possible heap types for the metrics"""

    USED = "used_in_bytes"
    TOTAL = "total_in_bytes"
    SIZE = "size_limit"


class Load(Enum):
    """Possible heap types for the metrics"""

    ONE_M = "1m"
    FIVE_M = "5m"
    FIFTEEN_M = "15m"


class Memory(Enum):
    """Possible memory types for the metrics"""

    USED = "used_in_bytes"
    TOTAL = "total_in_bytes"
    FREE = "free_in_bytes"


class Response(Enum):
    """Possible response times types for the metrics"""

    MAX = "max_in_millis"
    AVG = "avg_in_millis"


class RequestsCount(Enum):
    """Possible requests count types for the metrics"""

    DISCONNECTS = "disconnects"
    TOTAL = "total"


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
        api_metrics = collect_api_status(self.config)
        api_up = GaugeMetricFamily(
            name=f"{METRICS_PREFIX}up",
            documentation="Whether the data source is reachable (1 for up, 0 for down)",
            value=1 if api_metrics else 0,
        )
        yield api_up

        for metric in self.metrics(api_metrics):
            description, value = metric
            if value:
                yield value
            else:
                logger.error("It was not possible to get the metric: %s", description)

    def metrics(self, api_metrics: dict) -> list[tuple[str, Optional[Metric]]]:
        """Get the OpenSearch dashboard prometheus metrics.

        Args:
            api_metrics (dict): Metrics from the OpenSearch Dashboards API

        Returns:
            list[tuple[str, Optional[Metric]]]: Prometheus Gauge metrics of the dashboards
        """
        if api_metrics:
            return [
                ("status", _get_overall_status_metric(api_metrics)),
                ("current_connections", _get_current_connections_metric(api_metrics)),
                ("up_time", _get_up_time_metric(api_metrics)),
                ("event_loop_delay", _get_event_loop_delay_metric(api_metrics)),
                ("heap_total", _get_heap(api_metrics, Heap.TOTAL)),
                ("heap_used", _get_heap(api_metrics, Heap.USED)),
                ("heap_size", _get_heap(api_metrics, Heap.SIZE)),
                ("re_set_size", _get_resident_set_size(api_metrics)),
                ("load_1m", _get_load(api_metrics, Load.ONE_M)),
                ("load_5m", _get_load(api_metrics, Load.FIVE_M)),
                ("load_15m", _get_load(api_metrics, Load.FIFTEEN_M)),
                ("os_mem_total", _get_os_mem(api_metrics, Memory.TOTAL)),
                ("os_mem_free", _get_os_mem(api_metrics, Memory.FREE)),
                ("os_mem_used", _get_os_mem(api_metrics, Memory.USED)),
                ("resp_time_avg", _get_resp_time(api_metrics, Response.AVG)),
                ("resp_time_max", _get_resp_time(api_metrics, Response.MAX)),
                ("req_disconnects", _get_req(api_metrics, RequestsCount.DISCONNECTS)),
                ("req_total", _get_req(api_metrics, RequestsCount.TOTAL)),
            ] + [("statuses", status) for status in _get_statuses_metrics(api_metrics)]
        return []


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
        status (dict[str, str]): Status of the health of the cluster or plugins

    Returns:
        float: status as a number representing the health.
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
        case {"metrics": {"concurrent_connections": value}}:
            return GaugeMetricFamily(
                name=metric_name,
                documentation="OpenSearch dashboards number of concurrent connections",
                value=value,
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


def _get_heap(api_metrics: dict, heap: Heap) -> Optional[Metric]:
    """Get the Opensearch dashboards memory heap used in bytes.

    Args:
        api_metrics (dict): Response from the API
        heap (Heap): Possible heap types from the API

    Returns:
        Optional[Metric]: Prometheus Gauge metric if the metric exist in the API
    """
    heap_value = heap.value
    prefix = heap_value.split("_")[0]
    metric_name = f"{METRICS_PREFIX}heap_{prefix}"
    match api_metrics:
        case {
            "metrics": {"process": {"memory": {"heap": heap_values}}}
        } if heap_value in heap_values:
            return GaugeMetricFamily(
                name=metric_name,
                documentation=f"Opensearch dashboards memory heap {prefix} in bytes",
                value=heap_values[heap_value],
            )
        case _:
            return None


def _get_load(api_metrics: dict, load: Load) -> Optional[Metric]:
    """Get the OpenSearch dashboards load average.

    Args:
        api_metrics (dict): Response from the API
        load (Load): Possible load types from the API

    Returns:
        Optional[Metric]: Prometheus Gauge metric if the metric exist in the API
    """
    load_value = load.value
    metric_name = f"{METRICS_PREFIX}load_{load_value}"
    match api_metrics:
        case {"metrics": {"os": {"load": load_values}}} if load_value in load_values:
            return GaugeMetricFamily(
                name=metric_name,
                documentation=f"OpenSearch dashboards load average {load_value}",
                value=load_values[load_value],
            )
        case _:
            return None


def _get_os_mem(api_metrics: dict, memory: Memory) -> Optional[Metric]:
    """Get the OpenSearch dashboards memory total in bytes.

    Args:
        api_metrics (dict): Response from the API
        memory (Memory): Possible memory types from the API

    Returns:
        Optional[Metric]: Prometheus Gauge metric if the metric exist in the API
    """
    mem_value = memory.value
    prefix = mem_value.split("_")[0]
    metric_name = f"{METRICS_PREFIX}os_mem_{prefix}"
    match api_metrics:
        case {"metrics": {"os": {"memory": mem_values}}} if mem_value in mem_values:
            return GaugeMetricFamily(
                name=metric_name,
                documentation=f"OpenSearch dashboards memory {prefix} in bytes",
                value=mem_values[mem_value],
            )
        case _:
            return None


def _get_resp_time(api_metrics: dict, response: Response) -> Optional[Metric]:
    """Get the OpenSearch dashboards response time in milliseconds.

    Args:
        api_metrics (dict): Response from the API
        response (Response): Possible response time types from the API

    Returns:
        Optional[Metric]: Prometheus Gauge metric if the metric exist in the API
    """
    response_value = response.value
    prefix = response_value.split("_")[0]
    metric_name = f"{METRICS_PREFIX}resp_time_{prefix}"
    match api_metrics:
        case {"metrics": {"response_times": response_values}} if response_value in response_values:
            return GaugeMetricFamily(
                name=metric_name,
                documentation=f"OpenSearch dashboards {prefix} response time in milliseconds",
                value=response_values[response_value],
            )
        case _:
            return None


def _get_req(api_metrics: dict, req: RequestsCount) -> Optional[Metric]:
    """Get the OpenSearch dashboards request count.

    Args:
        api_metrics (dict): Response from the API
        req (RequestsCount): Possible request types from the API

    Returns:
        Optional[Metric]: Prometheus Gauge metric if the metric exist in the API
    """
    requests_value = req.value
    metric_name = f"{METRICS_PREFIX}req_{requests_value}"
    match api_metrics:
        case {"metrics": {"requests": requests_values}} if requests_value in requests_values:
            return GaugeMetricFamily(
                name=metric_name,
                documentation=f"OpenSearch dashboards request {requests_value} count",
                value=requests_values[requests_value],
            )
        case _:
            return None
