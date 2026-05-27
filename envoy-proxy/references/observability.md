# Envoy Observability (v1.38.0)

Complete reference for metrics, tracing, access logging, and admin API endpoints.

## Prometheus Stats

### Admin Endpoint

```bash
curl http://127.0.0.1:9901/stats/prometheus
```

### Enable Prometheus in Configuration

```yaml
admin:
  address:
    socket_address:
      address: 127.0.0.1
      port_value: 9901
  stats_sinks:
  - name: envoy.stats_sinks.prometheus
    typed_config:
      "@type": type.googleapis.com/envoy.config.metrics.v3.MetricsSink
  stats_config:
    use_all_default_tags: true
    stats_tags:
    - tag_name: "x-envoy-upstream-service-time"
      regex: "upstream_rq_time\\((.*)\\.\\d+\\.\\d+\\.\\d+\\.\\d+_:\\d+\\)"
    - tag_name: "response_code"
      regex: "upstream_rq_time\\((.*)\\.\\d+\\.\\d+\\.\\d+_.+\\.\\d+\\)"
```

### Key Metrics by Category

**Cluster metrics:**
- `envoy_cluster_upstream_cx_active` — Active connections
- `envoy_cluster_upstream_rq_total` — Total upstream requests
- `envoy_cluster_upstream_rq_time` — Request duration histogram
- `envoy_cluster_upstream_rq_retry` — Retry count
- `envoy_cluster_load_balancing_fail` — LB failures
- `envoy_cluster_outlier_detection_ejections_active` — Ejected hosts

**Listener metrics:**
- `envoy_listener_downstream_cx_active` — Active connections
- `envoy_listener_downstream_cx_total` — Total connections
- `envoy_listener_downstream_cx_destroy` — Destroyed connections
- `envoy_listener_downstream_rq_total` — Total requests

**Filter metrics:**
- `envoy_http_downstream_rq_total` — Total HTTP requests
- `envoy_http_downstream_rq_time` — Request duration
- `envoy_http_downstream_rq_response_code_2xx` — 2xx responses
- `envoy_http_downstream_rq_response_code_5xx` — 5xx responses
- `envoy_http_downstream_cx_ssl_fail` — SSL connection failures

**WASM metrics:**
- `envoy_wasm_*` — WASM filter metrics

**Route metrics:**
- `envoy_server_route_match` — Route match statistics

**Health check metrics:**
- `envoy_cluster_health_check_*` — Health check statistics

---

## Zipkin Tracing

```yaml
tracing:
  http:
    name: envoy.tracers.zipkin
    typed_config:
      "@type": type.googleapis.com/envoy.config.trace.v3.ZipkinConfig
      collector_cluster: zipkin_collector
      collector_endpoint: "/api/v2/spans"
      collector_endpoint_version: JSON
      shared_span_context: false
      trace_id_128bit: true
```

### Zipkin Collector Cluster

```yaml
- name: zipkin_collector
  type: STRICT_DNS
  lb_policy: ROUND_ROBIN
  load_assignment:
    cluster_name: zipkin_collector
    endpoints:
    - lb_endpoints:
      - endpoint:
          address:
            socket_address:
              address: zipkin.example.com
              port_value: 9411
```

### Route-Level Sampling Override

```yaml
route_config:
  virtual_hosts:
  - name: web_app
    domains: ["proxy.example.com"]
    routes:
    - match:
        prefix: /
      route:
        cluster: web_service
      typed_filter_config:
        type.googleapis.com/envoy.extensions.filters.http.router.v3.RouterConfig:
          sampling:
            per_sampling_config:
              default_config:
                random:
                  numerator: 50  # 50% random sampling on this route
```

---

## OpenTelemetry Tracing

```yaml
tracing:
  http:
    name: envoy.tracers.opentelemetry
    typed_config:
      "@type": type.googleapis.com/envoy.config.trace.v3.OpenTelemetryConfig
      grpc_service:
        envoy_grpc:
          cluster_name: otel_collector
        timeout: 5s
      service_name: "envoy-proxy"
      resource_attributes:
      - key: "k8s.pod.name"
        value:
          string_value: "%DOWNSTREAM_PEER_CERT_V2_SAN%"
      - key: "k8s.namespace.name"
        value:
          string_value: "default"
      resource_attributes_v1: true  # Send as Resource.attributes (not deprecated resource)
      propagators:
      - trace_context
      - baggage
```

### OTel Collector Cluster

```yaml
- name: otel_collector
  type: STRICT_DNS
  lb_policy: ROUND_ROBIN
  load_assignment:
    cluster_name: otel_collector
    endpoints:
    - lb_endpoints:
      - endpoint:
          address:
            socket_address:
              address: otel-collector
              port_value: 4317  # gRPC endpoint
```

### Route-Level Tracing Control

```yaml
- match:
    prefix: /
  route:
    cluster: web_service
  tracing:
    provider_name_override: "opentelemetry"
    random_sampling:
      numerator: 10
    per_request_sampling: true
```

---

## Access Logging

### JSON Access Log (Production Standard)

```yaml
http_filters:
- name: envoy.filters.network.http_connection_manager
  typed_config:
    "@type": type.googleapis.com/envoy.extensions.filters.network.http_connection_manager.v3.HttpConnectionManager
    access_log:
    - name: envoy.access_loggers.file
      typed_config:
        "@type": type.googleapis.com/envoy.extensions.access_loggers.file.v3.FileAccessLog
        log_format:
          typed_json_format:
            timestamp: "%START_TIME(%Y-%m-%dT%H:%M:%S.%3zZ)%"
            method: "%REQ(:METHOD)%"
            path: "%REQ(:PATH)%"
            protocol: "%PROTOCOL%"
            response_code: "%RESPONSE_CODE%"
            response_flags: "%RESPONSE_FLAGS%"
            duration: "%DURATION%"
            upstream_address: "%UPSTREAM_ADDRESS%"
            upstream_transport_failure_reason: "%UPSTREAM_TRANSPORT_FAILURE_REASON%"
            user_agent: "%REQ(User-Agent)%"
            request_id: "%REQ(X-REQUEST-ID,-)%"
            bytes_received: "%BYTES_RECEIVED%"
            bytes_sent: "%BYTES_SENT%"
            downstream_client_ip: "%DOWNSTREAM_REMOTE_ADDRESS_WITHOUT_PORT%"
            forward_for: "%REQ(X-FORWARDED-FOR,-)%"
            downstream_local_port: "%DOWNSTREAM_LOCAL_PORT%"
            upstream_service_time: "%RESP(X-ENVOY-UPSTREAM-SERVICE-TIME,-)%"
            upstream_cluster: "%UPSTREAM_CLUSTER%"
            downstream_peer_subject: "%DOWNSTREAM_PEER_SUBJECT%"
            downstream_cert_v_start: "%DOWNSTREAM_PEER_CERT_V_START%"
            downstream_cert_v_end: "%DOWNSTREAM_PEER_CERT_V_END%"
        path: /var/log/envoy/access.log
```

### Common Command Operators

| Operator | Description |
|----------|-------------|
| `%START_TIME%` | Request start time |
| `%REQ(:METHOD)%` | HTTP method |
| `%REQ(:PATH)%` | Request path |
| `%PROTOCOL%` | Protocol version (HTTP/1.1, HTTP/2, etc.) |
| `%RESPONSE_CODE%` | HTTP response status code |
| `%RESPONSE_FLAGS%` | Envoy response flags (e.g., "NR", "UCO", "UT" for upstream errors) |
| `%DURATION%` | Request duration in microseconds |
| `%RESP(X-ENVOY-UPSTREAM-SERVICE-TIME,-)%` | Upstream service time header |
| `%UPSTREAM_ADDRESS%` | Upstream address:port |
| `%UPSTREAM_CLUSTER%` | Target cluster name |
| `%UPSTREAM_TRANSPORT_FAILURE_REASON%` | TLS/transport failure reason |
| `%DOWNSTREAM_REMOTE_ADDRESS_WITHOUT_PORT%` | Client IP address |
| `%DOWNSTREAM_LOCAL_PORT%` | Listening port |
| `%DOWNSTREAM_PEER_SUBJECT%` | Client certificate subject (mTLS) |
| `%DOWNSTREAM_PEER_CERT_V_START%` | Client cert validity start |
| `%DOWNSTREAM_PEER_CERT_V_END%` | Client cert validity end |
| `%REQ(X-REQUEST-ID,-)%` | Request ID (with default) |
| `%BYTES_RECEIVED%` / `%BYTES_SENT%` | Transfer sizes in bytes |

### Response Flags Reference

| Flag | Meaning |
|------|---------|
| `NR` | No route found |
| `UC` | Upstream connection failure |
| `UT` | Upstream request timeout |
| `UO` | Upstream overflow |
| `UF` | Upstream framing error |
| `DC` | Downstream connection termination |
| `DT` | Downstream connection timeout |
| `DCO` | Downstream connection overflow |
| `RL` | Rate limited |
| `URX` | Response exceeded max response headers |
| `UTR` | Upstream request header timeout |

---

## Admin API Endpoints

### Read-Only (GET)

| Endpoint | Description |
|----------|-------------|
| `/` | Admin page index |
| `/server_info` | Envoy server version, state, uptime, PID |
| `/server_info?format=json` | JSON-serialized response |
| `/clusters?format=json` | Cluster status with health check details |
| `/clusters?format=json&filter=state` | Filter by cluster state |
| `/clusters?format=json&filter=enforcement_status` | Enforcement status per cluster |
| `/clusters?format=json&filter=enforcement_failure_rate&ignore_ports` | Failure rate per host |
| `/clusters?format=json&filter=hosts` | All hosts across clusters |
| `/clusters?format=json&filter=cluster_names` | Just the cluster names |
| `/clusters?format=json&filter=host_stats` | Per-host statistics |
| `/clusters?format=json&filter=outlier_ejection` | Ejection status |
| `/clusters?format=json&filter=connection_balance` | Connection balance per host |
| `/listeners` | Listener status summary |
| `/listeners?format=json` | JSON-serialized listener details |
| `/listeners?format=json&filter=address` | Address info per listener |
| `/listeners?format=json&filter=config` | Full listener config |
| `/config_dump` | Full config snapshot (bootstrap, all config) |
| `/config_dump?mask=clusters` | Just cluster configs |
| `/config_dump?mask=clusters,dynamic_active_secrets` | Clusters + secrets |
| `/config_dump?mask=secrets` | SDS secrets dump |
| `/config_dump?mask=listeners` | Listener configs |
| `/config_dump?mask=route_configs` | Route configs |
| `/stats` | All stats (custom format) |
| `/stats?format=prometheus` | Prometheus format |
| `/stats?filter=upstream_cx_total` | Filtered stats |
| `/server_info?format=json` | Server metadata |
| `/runtime` | Current runtime values |
| `/runtime?format=json` | JSON runtime dump |
| `/runtime?filter=envoy.reloadable_features` | Runtime guards |
| `/hot_restart_version` | Hot restart version |
| `/memory` | Memory usage details |
| `/certs` | TLS certificate info |
| `/ready` | Readiness check |
| `/healthcheck/fail` | Mark Envoy as unhealthy (no drain) |
| `/healthcheck/serve` | Health check response |
| `/cache_tracers_stats?format=json` | Tracer statistics |
| `/bootstrap` | Bootstrap config dump |
| `/certs` | TLS certificate details |

### Write Operations (POST)

| Endpoint | Description |
|----------|-------------|
| `/quitquitquit` | Graceful shutdown (equivalent to SIGTERM) |
| `/drain_listeners` | Drain listeners (402 = all, 403 = internal, 404 = external, 405 = all + wait for draining) |
| `/restart` | Restarts Envoy process |

---

## Observability Checklist

| Item | Status | Configuration |
|------|--------|--------------|
| Prometheus stats enabled | ✅ | Admin `/stats/prometheus` endpoint |
| Access log structured | ✅ | JSON format with key operators |
| Response flags captured | ✅ | `%RESPONSE_FLAGS%` in access log |
| Tracing configured | ✅ | Zipkin or OpenTelemetry provider |
| Health check monitoring | ✅ | `consecutive_5xx`, outlier detection |
| Circuit breaker limits | ✅ | Connection/request thresholds |
| Admin API access restricted | ⚠️ | Bind to `127.0.0.1` only, firewall |
| TLS on admin API | ⚠️ | Optional but recommended for remote monitoring |

---

## Common Pitfalls

| Pitfall | Impact | Fix |
|---------|--------|-----|
| Missing `stats_sinks` config | No Prometheus metrics exported | Add `stats_sinks` with `PrometheusConfig` |
| Using `format` instead of `json_format` | Hard to parse access logs | Use `typed_json_format` with structured fields |
| Tracing with `random_sampling: 0.0` in production | No trace data collected | Set reasonable sampling rate (1.0-10.0) |
| Tracing to wrong Zipkin endpoint | No trace data | Verify endpoint path (`/api/v2/spans` for v2) |
| OTel collector using HTTP instead of gRPC | Protocol mismatch | Use `envoy_grpc` transport for OTel |
| Admin API on `0.0.0.0` | Exposed to network, information leak | Bind admin to `127.0.0.1` or internal VPC |
| `healthcheck/fail` without drain | No connection drain before shutdown | Use `/drain_listeners` followed by `/quitquitquit` |
| Access log missing `%RESPONSE_FLAGS%` | Can't distinguish failures | Always include `%RESPONSE_FLAGS%` |
| Multiple access loggers writing same data | Log duplication, high I/O | Use single logger or strategic routing |
| Not filtering admin stats | Performance degradation from too many stats | Use `stats_config` with `stats_tags` for tag-based filtering |
