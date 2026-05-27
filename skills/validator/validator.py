# Skill: Envoy Configuration Validator
# Category: devops
# Description: Validates Envoy configuration manifests (YAML) against structural integrity and known deployment prerequisites.
# Envoy v1.38.0+ native static bootstrap configuration.

import yaml
import json
import logging
import sys
from typing import Dict, Any, List, Optional, Tuple
from pathlib import Path

logger = logging.getLogger("EnvoyValidator")
logger.setLevel(logging.INFO)


class ValidationResult:
    """Accumulates validation results with severity classification."""

    CRITICAL = "CRITICAL"
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"
    PASS = "PASS"

    def __init__(self):
        self.findings: List[Dict[str, Any]] = []
        self.passed: List[Dict[str, Any]] = []

    def add_pass(self, check_id: str, description: str, location_hint: str = ""):
        self.passed.append({
            "severity": self.PASS,
            "check_id": check_id,
            "description": description,
            "location_hint": location_hint
        })

    def add_finding(self, severity: str, check_id: str, description: str,
                    recommendation: str, location_hint: str = ""):
        self.findings.append({
            "severity": severity,
            "check_id": check_id,
            "description": description,
            "recommendation": recommendation,
            "location_hint": location_hint
        })

    def to_report(self) -> Dict[str, Any]:
        status = "PASS"
        if any(f["severity"] in (self.CRITICAL, self.HIGH) for f in self.findings):
            status = "FAIL"
        elif self.findings:
            status = "WARNING"

        return {
            "summary": {
                "overall_status": status,
                "total_checks": len(self.findings) + len(self.passed),
                "passed_checks": len(self.passed),
                "failed_checks": len(self.findings),
                "critical_findings": sum(1 for f in self.findings if f["severity"] == self.CRITICAL),
                "high_findings": sum(1 for f in self.findings if f["severity"] == self.HIGH),
                "medium_findings": sum(1 for f in self.findings if f["severity"] == self.MEDIUM),
                "low_findings": sum(1 for f in self.findings if f["severity"] == self.LOW)
            },
            "findings": self.findings,
            "passed": self.passed
        }


def _load_config(config_content: str) -> Optional[Dict[str, Any]]:
    """Parse YAML or JSON config content."""
    config_content = config_content.strip()
    if not config_content:
        raise ValueError("Empty configuration input")

    if config_content.startswith('{') or config_content.startswith('['):
        try:
            return json.loads(config_content)
        except json.JSONDecodeError as e:
            raise ValueError(f"JSON parsing error: {e}")
    else:
        try:
            return yaml.safe_load(config_content)
        except yaml.YAMLError as e:
            raise ValueError(f"YAML parsing error: {e}")


def _get(d, *keys, default=None):
    """Safely traverse nested dicts."""
    for key in keys:
        if isinstance(d, dict):
            d = d.get(key)
        else:
            return default
    return d if d is not None else default


def _check_required_fields(result: ValidationResult, config: Dict[str, Any],
                           required_keys: List[str], section_name: str = "root"):
    """Check that required top-level keys exist."""
    for key in required_keys:
        if key not in config:
            result.add_finding(
                ValidationResult.CRITICAL,
                f"ROOT-{key.upper()}",
                f"Missing required top-level key: '{key}' in {section_name}.",
                f"Add '{key}' based on Envoy v1.38.0 static configuration schema.",
                f"root.{key}"
            )


def validate_node(result: ValidationResult, config: Dict[str, Any]):
    """Validate the `node` section (used when talking to xDS management servers)."""
    node = config.get("node")
    if node is None:
        return  # node is optional in static configs

    if not isinstance(node, dict):
        result.add_finding(
            ValidationResult.HIGH, "NODE-001",
            "'node' section is not a valid object.",
            "Provide a map with at least 'id' and 'cluster' keys.",
            "root.node"
        )
        return

    node_id = node.get("id")
    if not node_id:
        result.add_finding(
            ValidationResult.LOW, "NODE-002",
            "'node.id' is not set. Default listener address will be used as node ID.",
            "Set a unique 'id' for multi-proxy deployments.",
            "root.node.id"
        )
    else:
        result.add_pass("NODE-002", f"Node ID set to '{node_id}'.", "root.node.id")

    node_cluster = node.get("cluster")
    if not node_cluster:
        result.add_finding(
            ValidationResult.LOW, "NODE-003",
            "'node.cluster' is not set. Required for xDS management server communication.",
            "Set the 'cluster' field to reference the management server cluster.",
            "root.node.cluster"
        )


def validate_admin(result: ValidationResult, config: Dict[str, Any]):
    """Validate the admin interface configuration."""
    admin = config.get("admin")
    if admin is None:
        result.add_finding(
            ValidationResult.LOW, "ADMIN-001",
            "No admin interface configured. Admin interface is optional but recommended for debugging.",
            "Add an admin block bound to localhost (127.0.0.1) with restricted ports.",
            "root.admin"
        )
        return

    if not isinstance(admin, dict):
        result.add_finding(
            ValidationResult.HIGH, "ADMIN-002",
            "'admin' section is not a valid object.",
            "Provide a map with at least an 'address' key.",
            "root.admin"
        )
        return

    addr = _get(admin, "address", "socket_address", default={})
    if isinstance(addr, dict):
        address = addr.get("address", "")
        port = addr.get("port_value")

        if address == "0.0.0.0" or address == "::":
            result.add_finding(
                ValidationResult.HIGH, "ADMIN-003",
                f"Admin interface bound to '{address}' (all interfaces). "
                "The admin interface exposes private information and allows destructive operations.",
                "Bind admin to '127.0.0.1' or a dedicated management network. "
                "Use 'allow_paths' to restrict access to sensitive endpoints.",
                "root.admin.address.socket_address.address"
            )
        else:
            result.add_pass("ADMIN-003",
                            f"Admin interface bound to '{address}'.",
                            "root.admin.address.socket_address.address")

        if port is None:
            result.add_finding(
                ValidationResult.MEDIUM, "ADMIN-004",
                "Admin interface port not explicitly set.",
                "Explicitly set 'port_value' (default is 9901).",
                "root.admin.address.socket_address.port_value"
            )
        else:
            result.add_pass("ADMIN-004", f"Admin port set to {port}.",
                            "root.admin.address.socket_address.port_value")
    else:
        result.add_finding(
            ValidationResult.HIGH, "ADMIN-005",
            "'admin.address' is not properly structured.",
            "Use: address: socket_address: { address: '127.0.0.1', port_value: 9901 }",
            "root.admin.address"
        )

    # Check allow_paths
    allow_paths = _get(admin, "allow_paths")
    if not allow_paths:
        result.add_finding(
            ValidationResult.MEDIUM, "ADMIN-006",
            "No 'allow_paths' configured on admin interface.",
            "Use 'allow_paths' to restrict access to sensitive endpoints "
            "(e.g., only allow /ready and /stats, deny /config_dump).",
            "root.admin.allow_paths"
        )
    else:
        result.add_pass("ADMIN-006", "Admin 'allow_paths' is configured.",
                        "root.admin.allow_paths")


def validate_static_resources(result: ValidationResult, config: Dict[str, Any]):
    """Validate the static_resources block: listeners and clusters."""
    static = config.get("static_resources")
    if static is None:
        result.add_finding(
            ValidationResult.CRITICAL, "SR-001",
            "Missing 'static_resources' top-level key. Static configuration requires listeners and clusters.",
            "Add a 'static_resources' block with at least one listener and one cluster.",
            "root.static_resources"
        )
        return

    if not isinstance(static, dict):
        result.add_finding(
            ValidationResult.CRITICAL, "SR-002",
            "'static_resources' is not a valid object.",
            "Provide a map with 'listeners' and 'clusters' keys.",
            "root.static_resources"
        )
        return

    validate_listeners(result, static)
    validate_clusters(result, static)


def validate_listeners(result: ValidationResult, static: Dict[str, Any]):
    """Validate the listeners array within static_resources."""
    listeners = static.get("listeners")

    if listeners is None:
        result.add_finding(
            ValidationResult.CRITICAL, "LIST-001",
            "No 'listeners' defined in static_resources.",
            "Add at least one listener to handle inbound traffic.",
            "root.static_resources.listeners"
        )
        return

    if not isinstance(listeners, list):
        result.add_finding(
            ValidationResult.HIGH, "LIST-002",
            "'listeners' is not an array.",
            "Provide a list of listener objects.",
            "root.static_resources.listeners"
        )
        return

    if not listeners:
        result.add_finding(
            ValidationResult.CRITICAL, "LIST-003",
            "'listeners' array is empty.",
            "Add at least one listener configuration.",
            "root.static_resources.listeners"
        )
        return

    for idx, listener in enumerate(listeners):
        prefix = f"root.static_resources.listeners[{idx}]"

        if not isinstance(listener, dict):
            result.add_finding(
                ValidationResult.HIGH, f"LIST-004-{idx}",
                f"Listener at index {idx} is not a valid object.",
                "Each listener must be a map with 'name', 'address', and 'filter_chains'.",
                prefix
            )
            continue

        # Name check
        name = listener.get("name")
        if not name:
            result.add_finding(
                ValidationResult.LOW, f"LIST-005-{idx}",
                f"Listener at index {idx} has no 'name' field.",
                "Name each listener for identification in stats and logs.",
                f"{prefix}.name"
            )
        else:
            result.add_pass(f"LIST-005-{idx}", f"Listener named '{name}'.", f"{prefix}.name")

        # Address check
        addr = _get(listener, "address", "socket_address", default={})
        if isinstance(addr, dict):
            addr_ip = addr.get("address")
            addr_port = addr.get("port_value")
            if not addr_ip:
                result.add_finding(
                    ValidationResult.HIGH, f"LIST-006-{idx}",
                    f"Listener '{name}' missing socket_address.address.",
                    "Specify the bind address (e.g., '0.0.0.0' or '127.0.0.1').",
                    f"{prefix}.address.socket_address.address"
                )
            if addr_port is None:
                result.add_finding(
                    ValidationResult.HIGH, f"LIST-007-{idx}",
                    f"Listener '{name}' missing socket_address.port_value.",
                    "Specify the listening port.",
                    f"{prefix}.address.socket_address.port_value"
                )

        # Filter chains check
        filter_chains = listener.get("filter_chains")
        if filter_chains is None or not isinstance(filter_chains, list) or not filter_chains:
            result.add_finding(
                ValidationResult.CRITICAL, f"LIST-008-{idx}",
                f"Listener '{name}' has no 'filter_chains' defined.",
                "Every listener must have at least one filter chain with filters.",
                f"{prefix}.filter_chains"
            )
            continue

        for fc_idx, fc in enumerate(filter_chains):
            fc_prefix = f"{prefix}.filter_chains[{fc_idx}]"
            if not isinstance(fc, dict):
                result.add_finding(
                    ValidationResult.HIGH, f"LIST-009-{fc_idx}",
                    f"Filter chain at index {fc_idx} is not a valid object.",
                    "Each filter chain must be a map with 'filters'.",
                    fc_prefix
                )
                continue

            filters = fc.get("filters")
            if filters is None or not isinstance(filters, list) or not filters:
                result.add_finding(
                    ValidationResult.CRITICAL, f"LIST-010-{fc_idx}",
                    f"Filter chain at index {fc_idx} has no 'filters' defined.",
                    "Every filter chain must have at least one network or HTTP filter.",
                    f"{fc_prefix}.filters"
                )
                continue

            # Check for HTTP connection manager
            has_hcm = False
            hcm_idx = None
            for f_idx, flt in enumerate(filters):
                if isinstance(flt, dict) and flt.get("name") == "envoy.filters.network.http_connection_manager":
                    has_hcm = True
                    hcm_idx = f_idx

            if not has_hcm:
                # Check if there's a network filter (TCP proxy, etc.) — still valid
                network_filters = [f.get("name") for f in filters
                                   if isinstance(f, dict) and f.get("name", "").startswith("envoy.filters.network.")]
                if not network_filters:
                    result.add_finding(
                        ValidationResult.HIGH, f"LIST-011-{fc_idx}",
                        f"Filter chain at index {fc_idx} has no 'envoy.filters.network.*' filter.",
                        "Add at least one network filter (e.g., http_connection_manager, tcp_proxy).",
                        f"{fc_prefix}.filters"
                    )
                else:
                    result.add_pass(f"LIST-011-{fc_idx}",
                                    f"Filter chain has network filters: {network_filters}.",
                                    f"{fc_prefix}.filters")
            else:
                assert hcm_idx is not None, "hcm_idx must be set when has_hcm is True"
                result.add_pass(f"LIST-011-{fc_idx}",
                                f"HTTP connection manager found in filter chain.",
                                f"{fc_prefix}.filters")
                # Validate HCM typed_config
                hcm_filter = filters[hcm_idx]
                if isinstance(hcm_filter, dict):
                    typed_config = hcm_filter.get("typed_config")
                    if not typed_config or not isinstance(typed_config, dict):
                        result.add_finding(
                            ValidationResult.HIGH, f"LIST-012-{fc_idx}",
                            f"HCM filter at index {fc_idx} missing valid 'typed_config'.",
                            "Provide a typed_config with '@type', 'stat_prefix', and route configuration.",
                            f"{fc_prefix}.filters[{hcm_idx}].typed_config"
                        )
                    else:
                        # Check required HCM fields
                        stat_prefix = typed_config.get("stat_prefix")
                        if not stat_prefix:
                            result.add_finding(
                                ValidationResult.MEDIUM, f"LIST-013-{fc_idx}",
                                f"HCM filter at index {fc_idx} missing 'stat_prefix'.",
                                "Set 'stat_prefix' for Prometheus stats naming.",
                                f"{fc_prefix}.filters[{hcm_idx}].typed_config.stat_prefix"
                            )

                        # Check for route_config
                        route_config = typed_config.get("route_config")
                        if not route_config:
                            result.add_finding(
                                ValidationResult.HIGH, f"LIST-014-{fc_idx}",
                                f"HCM filter at index {fc_idx} missing 'route_config'.",
                                "Configure a route_config with virtual_hosts and routes.",
                                f"{fc_prefix}.filters[{hcm_idx}].typed_config.route_config"
                            )

                        # Check for http_filters (must include envoy.router)
                        http_filters = typed_config.get("http_filters")
                        if not http_filters:
                            result.add_finding(
                                ValidationResult.CRITICAL, f"LIST-015-{fc_idx}",
                                f"HCM filter at index {fc_idx} missing 'http_filters'.",
                                "Add at least 'envoy.filters.http.router' to http_filters.",
                                f"{fc_prefix}.filters[{hcm_idx}].typed_config.http_filters"
                            )
                        else:
                            has_router = any(
                                isinstance(hf, dict) and hf.get("name") == "envoy.filters.http.router"
                                for hf in http_filters
                            )
                            if not has_router:
                                result.add_finding(
                                    ValidationResult.CRITICAL, f"LIST-016-{fc_idx}",
                                    f"HCM filter at index {fc_idx} missing 'envoy.filters.http.router'.",
                                    "Add 'envoy.filters.http.router' as the last http_filter.",
                                    f"{fc_prefix}.filters[{hcm_idx}].typed_config.http_filters"
                                )
                            else:
                                result.add_pass(f"LIST-016-{fc_idx}",
                                                "http_filters includes envoy.filters.http.router.",
                                                f"{fc_prefix}.filters[{hcm_idx}].typed_config.http_filters")

            # Check transport_socket on filter chain (TLS for HTTPS)
            transport_socket = fc.get("transport_socket")
            if transport_socket and isinstance(transport_socket, dict):
                ts_name = transport_socket.get("name", "")
                if ts_name == "envoy.transport_sockets.tls":
                    result.add_pass(f"LIST-TLS-{fc_idx}",
                                    f"TLS configured on filter chain {fc_idx}.",
                                    f"{fc_prefix}.transport_socket")

                    # Validate downstream TLS context
                    ts_config = transport_socket.get("typed_config")
                    if ts_config and isinstance(ts_config, dict):
                        type_url = ts_config.get("@type", "")
                        if "DownstreamTlsContext" not in type_url:
                            result.add_finding(
                                ValidationResult.HIGH, f"LIST-TLS-{fc_idx}",
                                f"Filter chain {fc_idx} transport_socket @type is '{type_url}', "
                                "expected DownstreamTlsContext for downstream TLS.",
                                "Use type.googleapis.com/envoy.extensions.transport_sockets.tls.v3.DownstreamTlsContext.",
                                f"{fc_prefix}.transport_socket.typed_config"
                            )
                        else:
                            # Check common_tls_context
                            common_ctx = ts_config.get("common_tls_context")
                            if not common_ctx or not isinstance(common_ctx, dict):
                                result.add_finding(
                                    ValidationResult.HIGH, f"LIST-TLS-{fc_idx}",
                                    f"Downstream TLS on filter chain {fc_idx} missing 'common_tls_context'.",
                                    "Add common_tls_context with tls_certificates and validation_context.",
                                    f"{fc_prefix}.transport_socket.typed_config.common_tls_context"
                                )
                            else:
                                # Check for certificate chain
                                tls_certs = common_ctx.get("tls_certificates")
                                if not tls_certs:
                                    # Check SDS config instead
                                    sds_certs = common_ctx.get("tls_certificate_sds_secret_configs")
                                    if not sds_certs:
                                        result.add_finding(
                                            ValidationResult.HIGH, f"LIST-TLS-{fc_idx}",
                                            f"Downstream TLS on filter chain {fc_idx}: "
                                            "no tls_certificates or tls_certificate_sds_secret_configs defined.",
                                            "Configure server certificates for TLS termination.",
                                            f"{fc_prefix}.transport_socket.typed_config.common_tls_context"
                                        )
                                    else:
                                        result.add_pass(f"LIST-TLS-{fc_idx}",
                                                        "TLS certificates configured via SDS.",
                                                        f"{fc_prefix}.transport_socket.typed_config.common_tls_context")
                                else:
                                    result.add_pass(f"LIST-TLS-{fc_idx}",
                                                    "TLS certificates defined.",
                                                    f"{fc_prefix}.transport_socket.typed_config.common_tls_context")

                                # Check TLS parameters
                                tls_params = common_ctx.get("tls_params")
                                if tls_params and isinstance(tls_params, dict):
                                    min_proto = tls_params.get("tls_minimum_protocol_version", "")
                                    if min_proto and min_proto in ("TLSv1_0", "TLSv1_1"):
                                        result.add_finding(
                                            ValidationResult.HIGH, f"LIST-TLS-{fc_idx}",
                                            f"Downstream TLS minimum protocol is '{min_proto}'. "
                                            "TLS 1.0 and 1.1 are deprecated and insecure.",
                                            "Set tls_minimum_protocol_version to 'TLSv1_2' or higher.",
                                            f"{fc_prefix}.transport_socket.typed_config.common_tls_context.tls_params"
                                        )
                                else:
                                    result.add_pass(f"LIST-TLS-{fc_idx}",
                                                    "TLS parameters configured.",
                                                    f"{fc_prefix}.transport_socket.typed_config.common_tls_context.tls_params")

                                # Check client certificate requirement
                                require_client_cert = ts_config.get("require_client_certificate")
                                if require_client_cert:
                                    result.add_pass(f"LIST-TLS-{fc_idx}",
                                                    "Client certificate required (mTLS).",
                                                    f"{fc_prefix}.transport_socket.typed_config.require_client_certificate")


def validate_clusters(result: ValidationResult, static: Dict[str, Any]):
    """Validate the clusters array within static_resources."""
    clusters = static.get("clusters")

    if clusters is None:
        result.add_finding(
            ValidationResult.CRITICAL, "CLUST-001",
            "No 'clusters' defined in static_resources.",
            "Add at least one cluster definition.",
            "root.static_resources.clusters"
        )
        return

    if not isinstance(clusters, list):
        result.add_finding(
            ValidationResult.HIGH, "CLUST-002",
            "'clusters' is not an array.",
            "Provide a list of cluster objects.",
            "root.static_resources.clusters"
        )
        return

    if not clusters:
        result.add_finding(
            ValidationResult.CRITICAL, "CLUST-003",
            "'clusters' array is empty.",
            "Add at least one cluster configuration.",
            "root.static_resources.clusters"
        )
        return

    # Collect cluster names for route validation
    cluster_names = set()

    for idx, cluster in enumerate(clusters):
        prefix = f"root.static_resources.clusters[{idx}]"

        if not isinstance(cluster, dict):
            result.add_finding(
                ValidationResult.HIGH, f"CLUST-004-{idx}",
                f"Cluster at index {idx} is not a valid object.",
                "Each cluster must be a map with 'name' and 'load_assignment' or 'eds_cluster_config'.",
                prefix
            )
            continue

        cluster_name = cluster.get("name")
        if not cluster_name:
            result.add_finding(
                ValidationResult.HIGH, f"CLUST-005-{idx}",
                f"Cluster at index {idx} missing 'name'.",
                "All clusters must have a unique 'name'.",
                f"{prefix}.name"
            )
        else:
            cluster_names.add(cluster_name)
            result.add_pass(f"CLUST-005-{idx}", f"Cluster named '{cluster_name}'.", f"{prefix}.name")

        # Check connect_timeout
        connect_timeout = cluster.get("connect_timeout")
        if connect_timeout is None:
            result.add_finding(
                ValidationResult.HIGH, f"CLUST-006-{idx}",
                f"Cluster '{cluster_name}' missing 'connect_timeout'. Default is 15s, often too long.",
                "Set connect_timeout to a short value (e.g., '0.25s' or '1s').",
                f"{prefix}.connect_timeout"
            )
        else:
            result.add_pass(f"CLUST-006-{idx}",
                            f"Cluster '{cluster_name}' connect_timeout set.",
                            f"{prefix}.connect_timeout")

        # Check type
        cluster_type = cluster.get("type")
        if not cluster_type:
            result.add_finding(
                ValidationResult.MEDIUM, f"CLUST-007-{idx}",
                f"Cluster '{cluster_name}' missing 'type'. Default is STATIC.",
                "Explicitly set type: STATIC, STRICT_DNS, LOGICAL_DNS, or EDS.",
                f"{prefix}.type"
            )

        # Check load_assignment or eds_cluster_config
        load_assignment = cluster.get("load_assignment")
        eds_config = cluster.get("eds_cluster_config")

        if not load_assignment and not eds_config:
            result.add_finding(
                ValidationResult.HIGH, f"CLUST-008-{idx}",
                f"Cluster '{cluster_name}' missing both 'load_assignment' and 'eds_cluster_config'.",
                "Provide load_assignment for STATIC/STRICT_DNS/LOGICAL_DNS types, "
                "or eds_cluster_config for EDS.",
                f"{prefix}"
            )

        if load_assignment and isinstance(load_assignment, dict):
            la_name = load_assignment.get("cluster_name")
            if not la_name:
                result.add_finding(
                    ValidationResult.MEDIUM, f"CLUST-009-{idx}",
                    f"Cluster '{cluster_name}' load_assignment missing 'cluster_name'.",
                    "Set load_assignment.cluster_name to match the cluster name.",
                    f"{prefix}.load_assignment.cluster_name"
                )
            endpoints = _get(load_assignment, "endpoints", default=[])
            if not endpoints:
                result.add_finding(
                    ValidationResult.HIGH, f"CLUST-010-{idx}",
                    f"Cluster '{cluster_name}' load_assignment has no endpoints.",
                    "Add at least one lb_endpoints entry.",
                    f"{prefix}.load_assignment.endpoints"
                )

        # Check health_checks
        health_checks = cluster.get("health_checks")
        if not health_checks:
            result.add_finding(
                ValidationResult.MEDIUM, f"CLUST-011-{idx}",
                f"Cluster '{cluster_name}' has no health_checks configured.",
                "Add active health checks for production reliability.",
                f"{prefix}.health_checks"
            )
        else:
            if isinstance(health_checks, list) and health_checks:
                result.add_pass(f"CLUST-011-{idx}",
                                f"Cluster '{cluster_name}' has {len(health_checks)} health check(s).",
                                f"{prefix}.health_checks")

        # Check circuit_breakers
        circuit_breakers = cluster.get("circuit_breakers")
        if not circuit_breakers:
            result.add_finding(
                ValidationResult.MEDIUM, f"CLUST-012-{idx}",
                f"Cluster '{cluster_name}' has no circuit_breakers configured.",
                "Add circuit breakers to protect against cascading failures.",
                f"{prefix}.circuit_breakers"
            )
        else:
            result.add_pass(f"CLUST-012-{idx}",
                            f"Cluster '{cluster_name}' has circuit breakers.",
                            f"{prefix}.circuit_breakers")

        # Check outlier_detection
        outlier = cluster.get("outlier_detection")
        if not outlier:
            result.add_finding(
                ValidationResult.MEDIUM, f"CLUST-013-{idx}",
                f"Cluster '{cluster_name}' has no outlier_detection configured.",
                "Add outlier_detection for passive failure detection and host ejection.",
                f"{prefix}.outlier_detection"
            )

        # Check typed_extension_protocol_options (http protocol options)
        proto_opts = cluster.get("typed_extension_protocol_options")
        if proto_opts and isinstance(proto_opts, dict):
            http_opts = proto_opts.get(
                "envoy.extensions.upstreams.http.v3.HttpProtocolOptions"
            )
            if http_opts and isinstance(http_opts, dict):
                explicit = http_opts.get("explicit_http_config")
                if explicit and isinstance(explicit, dict):
                    http2_opts = explicit.get("http2_protocol_options")
                    if http2_opts is not None:
                        result.add_pass(f"CLUST-014-{idx}",
                                        f"Cluster '{cluster_name}' has http2_protocol_options.",
                                        f"{prefix}.typed_extension_protocol_options")
                    else:
                        result.add_finding(
                            ValidationResult.MEDIUM, f"CLUST-015-{idx}",
                            f"Cluster '{cluster_name}' has HttpProtocolOptions but no http2_protocol_options.",
                            "Set http2_protocol_options (even defaults) for HTTP/2 upstreams.",
                            f"{prefix}.typed_extension_protocol_options"
                        )
            else:
                result.add_finding(
                    ValidationResult.MEDIUM, f"CLUST-016-{idx}",
                    f"Cluster '{cluster_name}' typed_extension_protocol_options missing HttpProtocolOptions.",
                    "Add HttpProtocolOptions for HTTP upstreams.",
                    f"{prefix}.typed_extension_protocol_options"
                )
        elif cluster_type in ("STATIC", "STRICT_DNS", "LOGICAL_DNS"):
            # Non-EDS clusters should have typed_extension_protocol_options
            result.add_finding(
                ValidationResult.MEDIUM, f"CLUST-016-{idx}",
                f"Cluster '{cluster_name}' ({cluster_type}) missing typed_extension_protocol_options.",
                "Non-EDS clusters need typed_extension_protocol_options for HTTP/1.1 upgrade.",
                f"{prefix}.typed_extension_protocol_options"
            )

    return cluster_names


def validate_route_references(result: ValidationResult, config: Dict[str, Any],
                              cluster_names: set):
    """Validate that route references point to existing clusters."""
    static = config.get("static_resources", {})
    if not isinstance(static, dict):
        return

    listeners = static.get("listeners", [])
    if not isinstance(listeners, list):
        return

    for idx, listener in enumerate(listeners):
        if not isinstance(listener, dict):
            continue
        filter_chains = listener.get("filter_chains", [])
        if not isinstance(filter_chains, list):
            continue

        for fc in filter_chains:
            if not isinstance(fc, dict):
                continue
            filters = fc.get("filters", [])
            if not isinstance(filters, list):
                continue

            for flt in filters:
                if not isinstance(flt, dict):
                    continue
                if flt.get("name") != "envoy.filters.network.http_connection_manager":
                    continue

                typed_config = flt.get("typed_config")
                if not isinstance(typed_config, dict):
                    continue

                route_config = typed_config.get("route_config")
                if not isinstance(route_config, dict):
                    continue

                virtual_hosts = route_config.get("virtual_hosts", [])
                if not isinstance(virtual_hosts, list):
                    continue

                for vh in virtual_hosts:
                    if not isinstance(vh, dict):
                        continue
                    routes = vh.get("routes", [])
                    if not isinstance(routes, list):
                        continue

                    for route in routes:
                        if not isinstance(route, dict):
                            continue
                        route_action = route.get("route")
                        if not isinstance(route_action, dict):
                            continue
                        referenced_cluster = route_action.get("cluster")
                        if referenced_cluster and referenced_cluster not in cluster_names:
                            result.add_finding(
                                ValidationResult.HIGH, f"ROUTE-{referenced_cluster}",
                                f"Route references cluster '{referenced_cluster}' "
                                f"which is not defined in clusters.",
                                f"Either add cluster '{referenced_cluster}' to the clusters list "
                                f"or fix the route reference.",
                                f"root.static_resources.listeners[*].filter_chains[*].filters[*].typed_config.route_config.virtual_hosts[*].routes[*].route.cluster"
                            )


def validate_config(config_content: str) -> Dict[str, Any]:
    """
    Main entry point. Validates a native Envoy static configuration.

    Returns a structured report with findings and passed checks.
    """
    result = ValidationResult()

    try:
        config = _load_config(config_content)
    except ValueError as e:
        result.add_finding(
            ValidationResult.CRITICAL, "PARSE-001",
            f"Configuration parsing failed: {e}",
            "Review YAML/JSON syntax. Use 'envoy --mode dump' to validate.",
            "input"
        )
        return result.to_report()

    if config is None:
        result.add_finding(
            ValidationResult.CRITICAL, "PARSE-002",
            "Configuration parsed to null/None. The file may be empty or contain only comments.",
            "Provide a valid Envoy configuration.",
            "input"
        )
        return result.to_report()

    if not isinstance(config, dict):
        result.add_finding(
            ValidationResult.HIGH, "PARSE-003",
            "Configuration must be a top-level map/object.",
            "Envoy bootstrap configuration starts with key-value pairs.",
            "root"
        )
        return result.to_report()

    # Validate sections
    _check_required_fields(result, config, ["static_resources"], "static config")
    validate_node(result, config)
    validate_admin(result, config)
    validate_static_resources(result, config)

    # Cross-reference: validate routes reference valid clusters
    static = config.get("static_resources", {})
    if isinstance(static, dict):
        clusters = static.get("clusters")
        if isinstance(clusters, list):
            cluster_names = set()
            for c in clusters:
                if isinstance(c, dict):
                    name = c.get("name")
                    if name:
                        cluster_names.add(name)
            validate_route_references(result, config, cluster_names)

    return result.to_report()


def execute_validation(config_content: str) -> Dict[str, Any]:
    """
    Public function for skill invocation. Accepts raw config string.
    """
    return validate_config(config_content)


def run_validation_from_file(file_path: str) -> Dict[str, Any]:
    """Load config from a file and validate it."""
    path = Path(file_path)
    if not path.exists():
        return {
            "summary": {"overall_status": "FAIL", "total_checks": 0, "failed_checks": 1},
            "findings": [{
                "severity": "CRITICAL",
                "check_id": "FILE-001",
                "description": f"File not found: {file_path}",
                "recommendation": "Check the file path and permissions.",
                "location_hint": file_path
            }]
        }

    content = path.read_text()
    return validate_config(content)


if __name__ == "__main__":
    # --- Test Case 1: Valid minimal static config ---
    print("=" * 60)
    print("Test Case 1: Valid minimal static config")
    print("=" * 60)
    valid_config = """
node:
  id: envoy-node-1
  cluster: envoy-cluster
admin:
  address:
    socket_address:
      address: 127.0.0.1
      port_value: 9901
static_resources:
  listeners:
  - name: listener_http
    address:
      socket_address:
        address: 0.0.0.0
        port_value: 10000
    filter_chains:
    - filters:
      - name: envoy.filters.network.http_connection_manager
        typed_config:
          "@type": type.googleapis.com/envoy.extensions.filters.network.http_connection_manager.v3.HttpConnectionManager
          stat_prefix: ingress_http
          http_filters:
          - name: envoy.filters.http.router
            typed_config:
              "@type": type.googleapis.com/envoy.extensions.http.router.v3.Router
          route_config:
            name: local_route
            virtual_hosts:
            - name: local_service
              domains: ["*"]
              routes:
              - match:
                  prefix: "/"
                route:
                  cluster: some_service
  clusters:
  - name: some_service
    connect_timeout: 0.25s
    type: STATIC
    lb_policy: ROUND_ROBIN
    load_assignment:
      cluster_name: some_service
      endpoints:
      - lb_endpoints:
        - endpoint:
            address:
              socket_address:
                address: 127.0.0.1
                port_value: 8080
"""
    report = execute_validation(valid_config)
    print(json.dumps(report, indent=2))

    # --- Test Case 2: Missing critical fields ---
    print("\n" + "=" * 60)
    print("Test Case 2: Missing critical fields")
    print("=" * 60)
    bad_config = """
static_resources:
  listeners:
  - name: test
    address:
      socket_address:
        address: 0.0.0.0
        port_value: 80
"""
    report = execute_validation(bad_config)
    print(json.dumps(report, indent=2))

    # --- Test Case 3: Full production config with TLS ---
    print("\n" + "=" * 60)
    print("Test Case 3: Production config with TLS, health checks, circuit breakers")
    print("=" * 60)
    prod_config = """
node:
  id: prod-envoy-1
  cluster: prod-cluster
admin:
  address:
    socket_address:
      address: 127.0.0.1
      port_value: 9901
  allow_paths:
  - exact: /ready
    prefix: /stats
static_resources:
  listeners:
  - name: listener_https
    address:
      socket_address:
        address: 0.0.0.0
        port_value: 443
    filter_chains:
    - transport_socket:
        name: envoy.transport_sockets.tls
        typed_config:
          "@type": type.googleapis.com/envoy.extensions.transport_sockets.tls.v3.DownstreamTlsContext
          common_tls_context:
            tls_params:
              tls_minimum_protocol_version: TLSv1_2
            tls_certificates:
            - certificate_chain:
                filename: /etc/certs/server.crt
              private_key:
                filename: /etc/certs/server.key
          require_client_certificate: true
      filters:
      - name: envoy.filters.network.http_connection_manager
        typed_config:
          "@type": type.googleapis.com/envoy.extensions.filters.network.http_connection_manager.v3.HttpConnectionManager
          stat_prefix: https_ingress
          http_filters:
          - name: envoy.filters.http.router
            typed_config:
              "@type": type.googleapis.com/envoy.extensions.http.router.v3.Router
          route_config:
            name: prod_route
            virtual_hosts:
            - name: prod_service
              domains: ["api.example.com"]
              routes:
              - match:
                  prefix: "/api/v1"
                route:
                  cluster: api_service
  clusters:
  - name: api_service
    connect_timeout: 0.25s
    type: STRICT_DNS
    lb_policy: ROUND_ROBIN
    load_assignment:
      cluster_name: api_service
      endpoints:
      - lb_endpoints:
        - endpoint:
            address:
              socket_address:
                address: api-service
                port_value: 8080
    health_checks:
    - timeout: 5s
      interval: 10s
      healthy_threshold: 2
      unhealthy_threshold: 3
      http_health_check:
        path: /healthz
    circuit_breakers:
      thresholds:
      - priority: DEFAULT
        max_connections: 1024
        max_pending_requests: 1024
        max_requests: 1024
        max_retries: 3
    outlier_detection:
      consecutive_5xx: 5
      interval: 10s
      base_ejection_time: 30s
      max_ejection_percent: 50
    typed_extension_protocol_options:
      envoy.extensions.upstreams.http.v3.HttpProtocolOptions:
        "@type": type.googleapis.com/envoy.extensions.upstreams.http.v3.HttpProtocolOptions
        explicit_http_config:
          http2_protocol_options: {}
"""
    report = execute_validation(prod_config)
    print(json.dumps(report, indent=2))
    print(f"\nOverall status: {report['summary']['overall_status']}")
    print(f"Passed: {report['summary']['passed_checks']}, Failed: {report['summary']['failed_checks']}")
