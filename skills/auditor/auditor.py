# Skill: Envoy Configuration Auditor
# Category: devops
# Description: Audits Envoy configuration manifests for production readiness, security hardening, and operational best practices.
# Envoy v1.38.0+ native static bootstrap configuration.

import yaml
import json
import logging
import sys
from typing import Dict, Any, List, Optional, Set, Tuple
from pathlib import Path

logger = logging.getLogger("EnvoyAuditor")
logger.setLevel(logging.INFO)


class AuditResult:
    """Accumulates audit findings with severity and priority classification."""

    CRITICAL = "CRITICAL"
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"
    PASS = "PASS"
    INFO = "INFO"

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

    def add_info(self, check_id: str, description: str, location_hint: str = ""):
        self.findings.append({
            "severity": self.INFO,
            "check_id": check_id,
            "description": description,
            "recommendation": "",
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


def _get(d: Optional[dict], *keys, default=None):
    """Safely traverse nested dicts."""
    if d is None:
        return default
    for key in keys:
        if isinstance(d, dict):
            d = d.get(key)
        else:
            return default
    return d if d is not None else default


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


class EnvoyAuditor:
    """
    Production readiness auditor for Envoy static bootstrap configuration.

    Checks cover:
    - Admin interface security
    - TLS configuration quality
    - Cluster health and resilience
    - Operational best practices
    """

    def __init__(self):
        self.result = AuditResult()
        self.cluster_names: Set[str] = set()
        self.listener_tls_map: Dict[int, bool] = {}

    def audit(self, config_content: str) -> Dict[str, Any]:
        """Run the full audit suite on a config string."""
        try:
            config = _load_config(config_content)
        except ValueError as e:
            self.result.add_finding(
                AuditResult.CRITICAL, "AUDIT-000",
                f"Configuration parsing failed: {e}",
                "Fix YAML/JSON syntax before running the auditor.",
                "input"
            )
            return self.result.to_report()

        if config is None or not isinstance(config, dict):
            self.result.add_finding(
                AuditResult.HIGH, "AUDIT-000",
                "Configuration is not a valid map.",
                "Provide a valid Envoy bootstrap configuration.",
                "root"
            )
            return self.result.to_report()

        self._audit_node(config)
        self._audit_admin(config)
        self._audit_static_resources(config)
        self._audit_cross_references(config)
        return self.result.to_report()

    # --- Node section ---

    def _audit_node(self, config: Dict[str, Any]):
        """Audit the node section for xDS readiness."""
        node = config.get("node")
        if node is None:
            self.result.add_info(
                "NODE-001",
                "No 'node' section. Fine for purely static config without management server.",
                "root.node"
            )
            return

        if not isinstance(node, dict):
            self.result.add_finding(
                AuditResult.HIGH, "NODE-002",
                "'node' is not a valid map.",
                "Provide a map with 'id' and 'cluster'.",
                "root.node"
            )
            return

        node_id = node.get("id")
        node_cluster = node.get("cluster")

        if not node_id:
            self.result.add_finding(
                AuditResult.MEDIUM, "NODE-003",
                "Node ID not set. Envoy uses listener addresses as fallback node ID, "
                "which causes conflicts in multi-proxy deployments.",
                "Set 'node.id' to a unique identifier (e.g., 'envoy-<hostname>-<zone>').",
                "root.node.id"
            )
        else:
            self.result.add_pass("NODE-003", f"Node ID: '{node_id}'.", "root.node.id")

        if not node_cluster:
            self.result.add_finding(
                AuditResult.MEDIUM, "NODE-004",
                "Node cluster not set. Required when Envoy connects to a management server (xDS).",
                "Set 'node.cluster' to the xDS management server cluster name.",
                "root.node.cluster"
            )

    # --- Admin interface ---

    def _audit_admin(self, config: Dict[str, Any]):
        """Audit admin interface for security hardening."""
        admin = config.get("admin")
        if admin is None:
            self.result.add_info(
                "ADMIN-001",
                "No admin interface configured. Optional but recommended for debugging.",
                "root.admin"
            )
            return

        if not isinstance(admin, dict):
            self.result.add_finding(
                AuditResult.HIGH, "ADMIN-002",
                "'admin' is not a valid object.",
                "Provide a map with at least an 'address' key.",
                "root.admin"
            )
            return

        addr = _get(admin, "address", "socket_address", default={})
        if isinstance(addr, dict):
            address = addr.get("address", "")
            port = addr.get("port_value")

            # CRITICAL: Admin must NOT bind to 0.0.0.0
            if address == "0.0.0.0" or address == "::" or address == "":
                self.result.add_finding(
                    AuditResult.CRITICAL, "ADMIN-003",
                    f"Admin interface bound to '{address or 'undefined'}'. "
                    "The admin interface exposes private information (certs, stats, config) "
                    "and allows destructive operations (shutdown, runtime modify).",
                    "Bind admin to '127.0.0.1' or a dedicated management network interface. "
                    "Example: address: 127.0.0.1, port_value: 9901",
                    "root.admin.address.socket_address.address"
                )
            elif address != "127.0.0.1":
                self.result.add_finding(
                    AuditResult.HIGH, "ADMIN-004",
                    f"Admin interface bound to '{address}'. "
                    "Consider restricting to loopback unless deliberately exposed on a management network.",
                    "Bind to '127.0.0.1' unless a dedicated management network is intended.",
                    "root.admin.address.socket_address.address"
                )
            else:
                self.result.add_pass("ADMIN-004",
                                     f"Admin interface bound to '127.0.0.1' (localhost).",
                                     "root.admin.address.socket_address.address")

            if port is None:
                self.result.add_finding(
                    AuditResult.MEDIUM, "ADMIN-005",
                    "Admin port not explicitly set (defaults to 9901).",
                    "Explicitly set 'port_value' for clarity and to avoid conflicts.",
                    "root.admin.address.socket_address.port_value"
                )
            else:
                self.result.add_pass("ADMIN-005",
                                     f"Admin port: {port}.",
                                     "root.admin.address.socket_address.port_value")

        # Check allow_paths
        allow_paths = _get(admin, "allow_paths")
        if not allow_paths:
            self.result.add_finding(
                AuditResult.HIGH, "ADMIN-006",
                "No 'allow_paths' configured on admin interface. "
                "Without allow_paths, all admin endpoints are accessible.",
                "Use 'allow_paths' to restrict access. Example: allow /ready and /stats, block /config_dump.",
                "root.admin.allow_paths"
            )
        else:
            if isinstance(allow_paths, list) and allow_paths:
                self.result.add_pass("ADMIN-006",
                                     f"Admin allow_paths configured ({len(allow_paths)} rule(s)).",
                                     "root.admin.allow_paths")
            else:
                self.result.add_finding(
                    AuditResult.MEDIUM, "ADMIN-007",
                    "'allow_paths' is empty or malformed.",
                    "Add path rules to restrict admin endpoint access.",
                    "root.admin.allow_paths"
                )

    # --- Static resources ---

    def _audit_static_resources(self, config: Dict[str, Any]):
        """Audit listeners and clusters for production readiness."""
        static = config.get("static_resources")
        if not isinstance(static, dict):
            return

        self._audit_listeners(static)
        self._audit_clusters(static)

    def _audit_listeners(self, static: Dict[str, Any]):
        """Audit listeners for security and operational best practices."""
        listeners = static.get("listeners")
        if not isinstance(listeners, list):
            return

        for idx, listener in enumerate(listeners):
            if not isinstance(listener, dict):
                continue

            prefix = f"root.static_resources.listeners[{idx}]"
            name = listener.get("name", f"listener[{idx}]")

            # Traffic direction
            direction = listener.get("traffic_direction")
            if direction and direction not in ("INBOUND", "OUTBOUND"):
                self.result.add_finding(
                    AuditResult.HIGH, f"LST-ADR-{idx}",
                    f"Listener '{name}' has invalid traffic_direction: '{direction}'.",
                    "Set to 'INBOUND' for serving traffic or 'OUTBOUND' for sidecar proxies.",
                    f"{prefix}.traffic_direction"
                )
            elif direction:
                self.result.add_pass(f"LST-ADR-{idx}",
                                     f"Listener '{name}' direction: {direction}.",
                                     f"{prefix}.traffic_direction")
            else:
                self.result.add_finding(
                    AuditResult.MEDIUM, f"LST-ADR-{idx}",
                    f"Listener '{name}' has no 'traffic_direction' set.",
                    "Explicitly set 'traffic_direction' for clarity and correct behavior in sidecar deployments.",
                    f"{prefix}.traffic_direction"
                )

            # Check filter chains for TLS
            filter_chains = listener.get("filter_chains", [])
            if not isinstance(filter_chains, list):
                continue

            for fc_idx, fc in enumerate(filter_chains):
                if not isinstance(fc, dict):
                    continue

                fc_prefix = f"{prefix}.filter_chains[{fc_idx}]"

                # TLS check
                transport_socket = fc.get("transport_socket")
                is_tls_listener = False
                if transport_socket and isinstance(transport_socket, dict):
                    ts_name = transport_socket.get("name", "")
                    if ts_name == "envoy.transport_sockets.tls":
                        is_tls_listener = True
                        ts_config = transport_socket.get("typed_config")
                        if ts_config and isinstance(ts_config, dict):
                            type_url = ts_config.get("@type", "")
                            if "DownstreamTlsContext" in type_url:
                                self._audit_downstream_tls(ts_config, fc_prefix, is_tls_listener)

                self.listener_tls_map[idx] = is_tls_listener

                # Check for HTTP connection manager
                filters = fc.get("filters")
                if isinstance(filters, list):
                    for flt in filters:
                        if isinstance(flt, dict) and flt.get("name") == "envoy.filters.network.http_connection_manager":
                            typed_config = flt.get("typed_config")
                            if typed_config and isinstance(typed_config, dict):
                                self._audit_hcm(typed_config, fc_prefix, is_tls_listener)

    def _audit_downstream_tls(self, tls_config: Dict[str, Any], prefix: str, is_tls: bool):
        """Audit downstream TLS configuration."""
        common_ctx = tls_config.get("common_tls_context")
        if not common_ctx or not isinstance(common_ctx, dict):
            self.result.add_finding(
                AuditResult.HIGH, f"TLS-CTX-{prefix}",
                "Downstream TLS missing 'common_tls_context'.",
                "Add common_tls_context with tls_certificates and tls_params.",
                f"{prefix}.common_tls_context"
            )
            return

        # TLS parameters
        tls_params = common_ctx.get("tls_params")
        if tls_params and isinstance(tls_params, dict):
            min_proto = tls_params.get("tls_minimum_protocol_version", "")
            if min_proto in ("TLSv1_0", "TLSv1_1"):
                self.result.add_finding(
                    AuditResult.CRITICAL, f"TLS-MIN-{prefix}",
                    f"Downstream TLS minimum protocol is '{min_proto}'. "
                    "TLS 1.0/1.1 are deprecated (RFC 8996) and vulnerable to attacks.",
                    "Set 'tls_minimum_protocol_version' to 'TLSv1_2' or 'TLSv1_3'. "
                    "Prefer 'TLSv1_3' for new deployments.",
                    f"{prefix}.common_tls_context.tls_params"
                )
            elif min_proto in ("TLSv1_2", "TLSv1_3"):
                self.result.add_pass(f"TLS-MIN-{prefix}",
                                     f"Minimum TLS protocol: {min_proto}.",
                                     f"{prefix}.common_tls_context.tls_params")
            else:
                self.result.add_finding(
                    AuditResult.MEDIUM, f"TLS-MIN-{prefix}",
                    f"Downstream TLS minimum protocol not explicitly set "
                    f"(defaults to TLSv1_2).",
                    "Explicitly set 'tls_minimum_protocol_version'.",
                    f"{prefix}.common_tls_context.tls_params"
                )

        # Cipher suites
        cipher_suites = _get(common_ctx, "tls_params", "cipher_suites")
        if cipher_suites and isinstance(cipher_suites, list) and len(cipher_suites) > 0:
            # Check for weak ciphers (simplified)
            weak = [c for c in cipher_suites if any(w in c.lower() for w in ("rc4", "des_", "3des", "anon", "null"))]
            if weak:
                self.result.add_finding(
                    AuditResult.HIGH, f"TLS-CIPHER-{prefix}",
                    f"Weak ciphers detected: {weak}.",
                    "Remove RC4, DES, 3DES, anonymous, and null ciphers. Use modern AEAD ciphers.",
                    f"{prefix}.common_tls_context.tls_params.cipher_suites"
                )
            else:
                self.result.add_pass(f"TLS-CIPHER-{prefix}",
                                     "Custom cipher suite list configured without known-weak ciphers.",
                                     f"{prefix}.common_tls_context.tls_params.cipher_suites")
        elif not cipher_suites:
            self.result.add_info(f"TLS-CIPHER-{prefix}",
                                 "Using default cipher suites. Review defaults for your Envoy build.",
                                 f"{prefix}.common_tls_context.tls_params.cipher_suites")

        # ECDH curves
        ecdh_curves = _get(common_ctx, "tls_params", "ecdh_curves")
        if ecdh_curves and isinstance(ecdh_curves, list):
            self.result.add_pass(f"TLS-ECDH-{prefix}",
                                 "Custom ECDH curves configured.",
                                 f"{prefix}.common_tls_context.tls_params.ecdh_curves")
        elif not ecdh_curves:
            self.result.add_info(f"TLS-ECDH-{prefix}",
                                 "Using default ECDH curves.",
                                 f"{prefix}.common_tls_context.tls_params.ecdh_curves")

        # Server certificates
        tls_certs = common_ctx.get("tls_certificates")
        sds_certs = common_ctx.get("tls_certificate_sds_secret_configs")
        if tls_certs and isinstance(tls_certs, list) and len(tls_certs) > 0:
            # Check that each cert has both chain and private key
            for ci, cert in enumerate(tls_certs):
                if isinstance(cert, dict):
                    cert_chain = cert.get("certificate_chain")
                    priv_key = cert.get("private_key")
                    if not cert_chain:
                        self.result.add_finding(
                            AuditResult.HIGH, f"TLS-CERT-{prefix}-{ci}",
                            f"TLS certificate at index {ci} missing 'certificate_chain'.",
                            "Add certificate_chain with filename or inline PEM data.",
                            f"{prefix}.common_tls_context.tls_certificates[{ci}]"
                        )
                    if not priv_key:
                        self.result.add_finding(
                            AuditResult.HIGH, f"TLS-KEY-{prefix}-{ci}",
                            f"TLS certificate at index {ci} missing 'private_key'.",
                            "Add private_key with filename or inline PEM data.",
                            f"{prefix}.common_tls_context.tls_certificates[{ci}]"
                        )
                else:
                    self.result.add_finding(
                        AuditResult.HIGH, f"TLS-CERT-{prefix}-{ci}",
                        f"TLS certificate at index {ci} is not a valid object.",
                        "Each tls_certificate must have 'certificate_chain' and 'private_key'.",
                        f"{prefix}.common_tls_context.tls_certificates[{ci}]"
                    )
        elif sds_certs:
            self.result.add_pass(f"TLS-SDS-{prefix}",
                                 "TLS certificates configured via SDS.",
                                 f"{prefix}.common_tls_context.tls_certificate_sds_secret_configs")
        else:
            self.result.add_finding(
                AuditResult.HIGH, f"TLS-NOCERT-{prefix}",
                "Downstream TLS has no server certificates configured "
                "(no tls_certificates and no SDS config). "
                "TLS termination cannot function without server certs.",
                "Add tls_certificates with certificate_chain and private_key, "
                "or configure tls_certificate_sds_secret_configs.",
                f"{prefix}.common_tls_context"
            )

        # Client certificate requirement (mTLS)
        require_client_cert = tls_config.get("require_client_certificate")
        if require_client_cert:
            self.result.add_pass(f"TLS-mTLS-{prefix}",
                                 "Client certificate required (mTLS enabled).",
                                 f"{prefix}.require_client_certificate")
        else:
            self.result.add_finding(
                AuditResult.MEDIUM, f"TLS-NOMTLS-{prefix}",
                "Client certificates are NOT required. Inbound HTTPS listeners "
                "should require client certificates for mutual TLS.",
                "Set 'require_client_certificate: true' for mTLS.",
                f"{prefix}.require_client_certificate"
            )

        # ALPN
        alpn = _get(common_ctx, "alpn_protocols")
        if alpn and isinstance(alpn, list) and len(alpn) > 0:
            self.result.add_pass(f"TLS-ALPN-{prefix}",
                                 f"ALPN protocols: {alpn}.",
                                 f"{prefix}.common_tls_context.alpn_protocols")

        # Session ticket keys
        session_keys = tls_config.get("session_ticket_keys")
        sds_ticket_keys = tls_config.get("session_ticket_keys_sds_secret_config")
        if not session_keys and not sds_ticket_keys:
            self.result.add_finding(
                AuditResult.LOW, f"TLS-SESS-{prefix}",
                "No session ticket keys configured. Stateless session resumption is disabled; "
                "stateful resumption uses internal keys (fails across hot restarts).",
                "Configure session_ticket_keys or session_ticket_keys_sds_secret_config.",
                f"{prefix}"
            )

    def _audit_hcm(self, hcm_config: Dict[str, Any], prefix: str, is_tls: bool):
        """Audit HTTP connection manager configuration."""
        stat_prefix = hcm_config.get("stat_prefix")
        if not stat_prefix:
            self.result.add_finding(
                AuditResult.MEDIUM, f"HCM-STAT-{prefix}",
                "HTTP connection manager missing 'stat_prefix'. "
                "Without it, Envoy generates default stat names that are hard to interpret.",
                "Set a descriptive stat_prefix (e.g., 'ingress_https', 'egress_api').",
                f"{prefix}.stat_prefix"
            )

        # Route config
        route_config = hcm_config.get("route_config")
        if not route_config or not isinstance(route_config, dict):
            self.result.add_finding(
                AuditResult.HIGH, f"HCM-ROUTE-{prefix}",
                "HTTP connection manager missing 'route_config'. "
                "No routing rules means the listener cannot route traffic.",
                "Configure route_config with virtual_hosts and routes.",
                f"{prefix}.route_config"
            )
        else:
            virtual_hosts = route_config.get("virtual_hosts", [])
            if not virtual_hosts:
                self.result.add_finding(
                    AuditResult.HIGH, f"HCM-VH-{prefix}",
                    "Route config has no 'virtual_hosts'. No traffic can be routed.",
                    "Add virtual_hosts with domains and routes.",
                    f"{prefix}.route_config.virtual_hosts"
                )
            else:
                self.result.add_pass(f"HCM-VH-{prefix}",
                                     f"{len(virtual_hosts)} virtual host(s) configured.",
                                     f"{prefix}.route_config.virtual_hosts")
                # Check domains include wildcard
                for vh_idx, vh in enumerate(virtual_hosts):
                    if not isinstance(vh, dict):
                        continue
                    domains = vh.get("domains", [])
                    routes = vh.get("routes", [])
                    if not routes:
                        self.result.add_finding(
                            AuditResult.MEDIUM, f"HCM-ROUTE-{prefix}-{vh_idx}",
                            f"Virtual host at index {vh_idx} has no routes. "
                            "Traffic matching this virtual host will receive 404.",
                            "Add at least one route to each virtual host.",
                            f"{prefix}.route_config.virtual_hosts[{vh_idx}].routes"
                        )

        # HTTP filters
        http_filters = hcm_config.get("http_filters")
        if not http_filters or not isinstance(http_filters, list):
            self.result.add_finding(
                AuditResult.HIGH, f"HCM-HFILTER-{prefix}",
                "HTTP connection manager missing 'http_filters'. "
                "No HTTP processing will occur.",
                "Add at least 'envoy.filters.http.router' to http_filters.",
                f"{prefix}.http_filters"
            )
        else:
            has_router = any(
                isinstance(hf, dict) and hf.get("name") == "envoy.filters.http.router"
                for hf in http_filters
            )
            if not has_router:
                self.result.add_finding(
                    AuditResult.CRITICAL, f"HCM-NOROUTER-{prefix}",
                    "http_filters does not include 'envoy.filters.http.router'. "
                    "Requests will not be forwarded to any cluster.",
                    "Add 'envoy.filters.http.router' as the last filter in http_filters.",
                    f"{prefix}.http_filters"
                )
            else:
                self.result.add_pass(f"HCM-ROUTER-{prefix}",
                                     "http_filters includes envoy.filters.http.router.",
                                     f"{prefix}.http_filters")

        # Check for access_log configuration
        # Access log is configured at the listener level via listener_filters or the HCM
        # In v3, access logs can be configured via the "envoy.access_loggers" extension
        # accessed through the HCM's "access_log" field
        access_log = hcm_config.get("access_log")
        if not access_log:
            self.result.add_finding(
                AuditResult.MEDIUM, f"HCM-ACCESSLOG-{prefix}",
                "No access_log configured on HTTP connection manager. "
                "Without access logs, troubleshooting and audit trails are severely limited.",
                "Add access_log with envoy.access_loggers.file or "
                "envoy.access_loggers.extension_file_config.",
                f"{prefix}.access_log"
            )

        # Check for codec_type
        codec = hcm_config.get("codec_type")
        if codec and codec != "AUTO":
            self.result.add_pass(f"HCM-CODEC-{prefix}",
                                 f"HTTP codec_type: {codec}.",
                                 f"{prefix}.codec_type")
        elif not codec:
            self.result.add_info(f"HCM-CODEC-{prefix}",
                                 "codec_type defaults to AUTO. Fine for most deployments.",
                                 f"{prefix}.codec_type")

        # Timeout defaults
        default_request_timeout = hcm_config.get("stream_idle_timeout")
        if not default_request_timeout:
            self.result.add_finding(
                AuditResult.LOW, f"HCM-TIMEOUT-{prefix}",
                "No stream_idle_timeout configured. Default is 5 minutes, which may be too long "
                "for APIs, or too short for long-poll SSE/WebSocket.",
                "Set stream_idle_timeout appropriate for your traffic pattern (e.g., '300s').",
                f"{prefix}.stream_idle_timeout"
            )

    def _audit_clusters(self, static: Dict[str, Any]):
        """Audit clusters for production readiness."""
        clusters = static.get("clusters")
        if not isinstance(clusters, list):
            return

        for idx, cluster in enumerate(clusters):
            if not isinstance(cluster, dict):
                continue

            prefix = f"root.static_resources.clusters[{idx}]"
            cluster_name = cluster.get("name", f"cluster[{idx}]")
            self.cluster_names.add(cluster_name)

            cluster_type = cluster.get("type", "STATIC")

            # connect_timeout
            connect_timeout = cluster.get("connect_timeout")
            if connect_timeout is None:
                self.result.add_finding(
                    AuditResult.HIGH, f"CLUST-TIMEOUT-{idx}",
                    f"Cluster '{cluster_name}' has no connect_timeout. "
                    "Default is 15s, which is too long for production — "
                    "failed connections hold threads for too long.",
                    "Set connect_timeout to a short value: '0.25s' for internal services, "
                    "'1s' for external. Never leave it at the 15s default.",
                    f"{prefix}.connect_timeout"
                )
            else:
                self.result.add_pass(f"CLUST-TIMEOUT-{idx}",
                                     f"Cluster '{cluster_name}' connect_timeout configured.",
                                     f"{prefix}.connect_timeout")

            # Health checks
            health_checks = cluster.get("health_checks")
            if not health_checks:
                self.result.add_finding(
                    AuditResult.HIGH, f"CLUST-HC-{idx}",
                    f"Cluster '{cluster_name}' has NO active health checks. "
                    "Without health checks, Envoy continues sending traffic to failed upstream hosts.",
                    "Add active health_checks with appropriate protocol (HTTP, gRPC) and thresholds.",
                    f"{prefix}.health_checks"
                )
            elif isinstance(health_checks, list) and len(health_checks) > 0:
                hc = health_checks[0] if health_checks else {}
                if isinstance(hc, dict):
                    interval = hc.get("interval")
                    timeout = hc.get("timeout")
                    if not interval:
                        self.result.add_finding(
                            AuditResult.MEDIUM, f"CLUST-HC-INT-{idx}",
                            f"Cluster '{cluster_name}' health check missing 'interval'. "
                            "Default is 15s.",
                            "Set interval to 5s-10s for responsive failure detection.",
                            f"{prefix}.health_checks[0].interval"
                        )
                    if not timeout:
                        self.result.add_finding(
                            AuditResult.MEDIUM, f"CLUST-HC-TOUT-{idx}",
                            f"Cluster '{cluster_name}' health check missing 'timeout'. "
                            "Default is 5s, often too long for quick failure detection.",
                            "Set timeout to 1s-3s (should be less than interval).",
                            f"{prefix}.health_checks[0].timeout"
                        )

                self.result.add_pass(f"CLUST-HC-{idx}",
                                     f"Cluster '{cluster_name}' has {len(health_checks)} health check(s).",
                                     f"{prefix}.health_checks")
            else:
                self.result.add_finding(
                    AuditResult.MEDIUM, f"CLUST-HC-{idx}",
                    f"Cluster '{cluster_name}' health_checks is malformed.",
                    "Provide a non-empty list of health check configurations.",
                    f"{prefix}.health_checks"
                )

            # Circuit breakers
            circuit_breakers = cluster.get("circuit_breakers")
            if not circuit_breakers:
                self.result.add_finding(
                    AuditResult.HIGH, f"CLUST-CB-{idx}",
                    f"Cluster '{cluster_name}' has NO circuit breakers. "
                    "Without circuit breakers, slow or failing upstreams can exhaust "
                    "all connection pools and cause cascading failures.",
                    "Add circuit_breakers with thresholds (max_connections, max_requests, "
                    "max_pending_requests, max_retries).",
                    f"{prefix}.circuit_breakers"
                )
            else:
                self.result.add_pass(f"CLUST-CB-{idx}",
                                     f"Cluster '{cluster_name}' has circuit breakers.",
                                     f"{prefix}.circuit_breakers")

            # Outlier detection
            outlier = cluster.get("outlier_detection")
            if not outlier:
                self.result.add_finding(
                    AuditResult.MEDIUM, f"CLUST-OD-{idx}",
                    f"Cluster '{cluster_name}' has NO outlier_detection. "
                    "Passive failure detection helps eject unhealthy hosts from the load balancing pool.",
                    "Add outlier_detection with consecutive_5xx, interval, base_ejection_time.",
                    f"{prefix}.outlier_detection"
                )
            else:
                if isinstance(outlier, dict) and outlier:
                    self.result.add_pass(f"CLUST-OD-{idx}",
                                         f"Cluster '{cluster_name}' has outlier_detection.",
                                         f"{prefix}.outlier_detection")
                else:
                    self.result.add_finding(
                        AuditResult.MEDIUM, f"CLUST-OD-{idx}",
                        f"Cluster '{cluster_name}' outlier_detection is empty/malformed.",
                        "Provide outlier_detection config with detection parameters.",
                        f"{prefix}.outlier_detection"
                    )

            # HTTP protocol options
            proto_opts = cluster.get("typed_extension_protocol_options")
            if proto_opts and isinstance(proto_opts, dict):
                http_opts = proto_opts.get(
                    "envoy.extensions.upstreams.http.v3.HttpProtocolOptions"
                )
                if http_opts and isinstance(http_opts, dict):
                    explicit = http_opts.get("explicit_http_config")
                    if explicit and isinstance(explicit, dict):
                        self.result.add_pass(f"CLUST-PROTO-{idx}",
                                             f"Cluster '{cluster_name}' has HttpProtocolOptions.",
                                             f"{prefix}.typed_extension_protocol_options")
                    else:
                        self.result.add_finding(
                            AuditResult.MEDIUM, f"CLUST-PROTO-MISS-{idx}",
                            f"Cluster '{cluster_name}' has HttpProtocolOptions but no explicit_http_config.",
                            "Add explicit_http_config with http2_protocol_options.",
                            f"{prefix}.typed_extension_protocol_options"
                        )
                else:
                    self.result.add_finding(
                        AuditResult.MEDIUM, f"CLUST-PROTO-MISS-{idx}",
                        f"Cluster '{cluster_name}' typed_extension_protocol_options "
                        "missing HttpProtocolOptions.",
                        "Non-EDS clusters need HttpProtocolOptions for automatic HTTP/1.1 to HTTP/2 upgrade.",
                        f"{prefix}.typed_extension_protocol_options"
                    )
            elif cluster_type in ("STATIC", "STRICT_DNS", "LOGICAL_DNS"):
                self.result.add_finding(
                    AuditResult.MEDIUM, f"CLUST-PROTO-MISS-{idx}",
                    f"Cluster '{cluster_name}' ({cluster_type}) missing typed_extension_protocol_options.",
                    "Non-EDS clusters require typed_extension_protocol_options for proper HTTP/1.1 -> HTTP/2 upgrade.",
                    f"{prefix}.typed_extension_protocol_options"
                )

            # Upstream TLS
            up_transport = cluster.get("transport_socket")
            if up_transport and isinstance(up_transport, dict):
                up_ts_name = up_transport.get("name", "")
                if up_ts_name == "envoy.transport_sockets.tls":
                    up_ts_config = up_transport.get("typed_config")
                    if up_ts_config and isinstance(up_ts_config, dict):
                        up_type_url = up_ts_config.get("@type", "")
                        if "UpstreamTlsContext" in up_type_url:
                            # Check validation context
                            common_ctx = up_ts_config.get("common_tls_context")
                            if common_ctx and isinstance(common_ctx, dict):
                                val_context = common_ctx.get("validation_context")
                                sds_val = common_ctx.get("validation_context_sds_secret_config")
                                if not val_context and not sds_val:
                                    self.result.add_finding(
                                        AuditResult.HIGH, f"CLUST-UPCERT-{idx}",
                                        f"Cluster '{cluster_name}' upstream TLS has no "
                                        "certificate validation context (trusted_ca or SDS). "
                                        "Upstream certificate verification is DISABLED by default.",
                                        "Add validation_context with trusted_ca (inline or filename), "
                                        "or use validation_context_sds_secret_config for SDS.",
                                        f"{prefix}.transport_socket.typed_config.common_tls_context"
                                    )
                                else:
                                    self.result.add_pass(f"CLUST-UPCERT-{idx}",
                                                         f"Cluster '{cluster_name}' upstream TLS cert verification configured.",
                                                         f"{prefix}.transport_socket.typed_config")

                                # Check SNI
                                sni = up_ts_config.get("sni")
                                if sni:
                                    self.result.add_pass(f"CLUST-SNI-{idx}",
                                                         f"Cluster '{cluster_name}' has SNI: '{sni}'.",
                                                         f"{prefix}.transport_socket.typed_config.sni")
                                else:
                                    self.result.add_finding(
                                        AuditResult.MEDIUM, f"CLUST-NOSNI-{idx}",
                                        f"Cluster '{cluster_name}' upstream TLS has no SNI configured.",
                                        "Set 'sni' to the expected server hostname, or "
                                        "use 'auto_host_sni: true' for DNS clusters.",
                                        f"{prefix}.transport_socket.typed_config.sni"
                                    )
                        elif "DownstreamTlsContext" in up_type_url:
                            self.result.add_finding(
                                AuditResult.HIGH, f"CLUST-TYPE-{idx}",
                                f"Cluster '{cluster_name}' transport_socket uses DownstreamTlsContext "
                                "(meant for inbound listeners), not UpstreamTlsContext.",
                                "Use envoy.transport_sockets.tls with UpstreamTlsContext for upstream clusters.",
                                f"{prefix}.transport_socket.typed_config"
                            )

            # Connection pool settings
            connection_pool = _get(cluster, "connection_pool_per_downstream_connection")
            if connection_pool:
                self.result.add_pass(f"CLUST-POOL-{idx}",
                                     f"Cluster '{cluster_name}' has per-downstream-connection pooling.",
                                     f"{prefix}.connection_pool_per_downstream_connection")
            # Also check load_assignment for endpoints
            load_assignment = cluster.get("load_assignment")
            if load_assignment and isinstance(load_assignment, dict):
                endpoints = load_assignment.get("endpoints")
                if not endpoints:
                    self.result.add_finding(
                        AuditResult.CRITICAL, f"CLUST-NENDPOINT-{idx}",
                        f"Cluster '{cluster_name}' load_assignment has NO endpoints. "
                        "Traffic has nowhere to route.",
                        "Add at least one lb_endpoints entry.",
                        f"{prefix}.load_assignment.endpoints"
                    )

    def _audit_cross_references(self, config: Dict[str, Any]):
        """Audit cross-references: routes referencing valid clusters."""
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
                            ref_cluster = route_action.get("cluster")
                            if ref_cluster and ref_cluster not in self.cluster_names:
                                self.result.add_finding(
                                    AuditResult.CRITICAL, f"ROUTE-XREF-{ref_cluster}",
                                    f"Route references cluster '{ref_cluster}' "
                                    f"which is NOT defined in any cluster.",
                                    f"Add cluster '{ref_cluster}' to static_resources.clusters, "
                                    f"or fix the route reference.",
                                    f"root.static_resources.listeners[{idx}].filter_chains[*].routes[*].route.cluster"
                                )

    def audit_from_file(self, file_path: str) -> Dict[str, Any]:
        """Load config from a file and audit it."""
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
        return self.audit(content)


def execute_auditor(config_content: str) -> Dict[str, Any]:
    """
    Public function for skill invocation. Accepts raw config string.
    """
    auditor = EnvoyAuditor()
    return auditor.audit(config_content)


def run_auditor_from_file(file_path: str) -> Dict[str, Any]:
    """Load config from a file and audit it."""
    auditor = EnvoyAuditor()
    return auditor.audit_from_file(file_path)


if __name__ == "__main__":
    print("=" * 60)
    print("Auditor Test: Broken production config")
    print("=" * 60)
    bad_config = """
admin:
  address:
    socket_address:
      address: 0.0.0.0
      port_value: 9901
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
              tls_minimum_protocol_version: TLSv1_0
            tls_certificates:
            - certificate_chain:
                filename: /etc/certs/server.crt
          require_client_certificate: false
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
                  cluster: missing_service
  clusters:
  - name: missing_service
    type: STATIC
    load_assignment:
      cluster_name: missing_service
      endpoints:
      - lb_endpoints:
        - endpoint:
            address:
              socket_address:
                address: api-service
                port_value: 8080
"""
    report = execute_auditor(bad_config)
    print(json.dumps(report, indent=2))
    print(f"\nOverall status: {report['summary']['overall_status']}")
    print(f"Passed: {report['summary']['passed_checks']}, Failed: {report['summary']['failed_checks']}")
