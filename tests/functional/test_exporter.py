# Copyright 2024 Canonical Ltd.
# See LICENSE file for licensing details.

import requests


def test_exporter_metrics(prometheus_exporter, expected_metrics):
    # Query the Prometheus exporter's endpoint and check that all metrics are present
    response = requests.get("http://localhost:9684/metrics")
    metric_names = _get_prometheus_metric_names(response.text)

    assert response.status_code == 200
    assert expected_metrics.issubset(metric_names)
    # metrics are generated as expected
    assert "opensearch_dashboards_up 1.0" in response.text


def test_exporter_failing_export_metrics(wrong_prometheus_exporter, expected_metrics):
    # Prometheus server is not able to fetch the OpenSearch Dashboards metrics
    response = requests.get("http://localhost:9684/metrics")
    metric_names = _get_prometheus_metric_names(response.text)

    assert response.status_code == 200
    assert expected_metrics.issubset(metric_names) is False
    # metrics are not generated as expected
    assert "opensearch_dashboards_up 0.0" in response.text


def test_exporter_wrong_path(prometheus_exporter):
    # Prometheus server is not able to fetch the OpenSearch Dashboards metrics
    response = requests.get("http://localhost:9684")

    assert response.status_code == 404
    assert "404 Not Found" in response.text


def _get_prometheus_metric_names(response: str) -> set[str]:
    # remove comments from prometheus response
    metrics_values = [
        metrics_value for metrics_value in response.splitlines() if "#" not in metrics_value
    ]
    # remove values and labels to have just the metric name. E.g: opensearch_dashboards_up
    metrics = {metric.split()[0].split("{")[0] for metric in metrics_values}
    return metrics
