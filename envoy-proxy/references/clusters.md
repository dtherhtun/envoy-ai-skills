# Envoy Cluster Patterns (v1.38.0)

Complete reference for upstream cluster types, load balancing, health checks, circuit breakers, and outlier detection.

## Cluster Types

| Type | Resolution | Use Case | Dynamics |
|------|-----------|----------|----------|
| `STATIC` | Config-time | Fixed endpoints, local services | Static — no DNS resolution |
| `STRICT_DNS` | Per-connection | Most common | Fresh DNS on every new connection |
| `LOGICAL_DNS` | Per-load-balanced-request | Small dynamic pools | Fresh DNS on every LB decision |
| `EDS` (Endpoint Discovery Service) | Push/pull discovery | Kubernetes, cloud-native | Fully dynamic — API-driven |
| `ORIGINAL_DST` | OS routing | Service mesh passthrough | IP pulled from connection |

### Static Cluster Example

```yaml
- name: static_backend
  type: STATIC
  lb_policy: ROUND_ROBIN
  load_assignment:
    cluster_name: static_backend
    endpoints:
    - lb_endpoints:
      - endpoint:
          address:
            socket_address:
              address: 10.0.0.1
              port_value: 8080
      - endpoint:
          address:
            socket_address:
              address: 10.0.0.2
              port_value: 8080
          health_check:
            port_value: 8081
```

### STRICT_DNS with multiple ports

```yaml
- name: dns_backend
  type: STRICT_DNS
  lb_policy: ROUND_ROBIN
  dns_refresh_rate: 30s
  load_assignment:
    cluster_name: dns_backend
    endpoints:
    - lb_endpoints:
      - endpoint:
          address:
            socket_address:
              address: backend.example.com
              port_value: 443
```

### EDS Cluster

```yaml
- name: eds_backend
  type: EDS
  eds_config:
    api_config_source:
      api_type: DELTA_GRPC
      grpc_services:
      - envoy_grpc:
          cluster_name: eds_service
      transport_api_version: V3
  load_assignment:
    cluster_name: eds_backend
```

## Load Balancing Policies

| Policy | Description | Best For |
|--------|-------------|----------|
| `ROUND_ROBIN` | Cycles through healthy hosts sequentially | Default, simple workloads |
| `LEAST_REQUEST` | Picks host with fewest active requests | Batch jobs, variable latency |
| `RANDOM` | Random host selection | When load is naturally distributed |
| `RING_HASH` | Consistent hashing on hash key | Sticky sessions, cache affinity |
| `RANDOM` | Random host selection | Simple round-robin when host health varies |
| `MAGLEV` | Maglev consistent hashing | Higher-quality distribution than RING_HASH |
| `WEIGHTED_ROUND_ROBIN` | Weighted cyclic selection | Canary deployments, zone-affinity |
| `WEIGHTED_LEAST_REQUEST` | Weighted least requests | Canary + bursty workloads |

### RING_HASH with hash key

```yaml
lb_policy: RING_HASH
ring_hash_lb_config:
  minimum_ring_size: 1024
  hash_function: MURMER_HASH
  hash_source:
    filter_enabled:
      runtime_key: ring_hash_enabled
      default_value:
        numerator: 100
        denominator: HUNDRED
  hash_key:
    header_name: ":path"
  hash_filters:
  - name: envoy.hash_policies.previous_ring_hash
    typed_config:
      "@type": type.googleapis.com/envoy.extensions.hash_policies.previous_ring_hash.v3.PreviousRingHash
```

### LEAST_REQUEST with outlier detection interaction

```yaml
lb_policy: LEAST_REQUEST
least_request_lb_config:
  choice_count: 2
  fast_stale_stats: true
```

### MAGLEV

```yaml
lb_policy: MAGLEV
maglev_lb_config:
  table_size: 65536
  seed: 42
```

## Health Check Configuration

### Active Health Check

```yaml
health_checks:
- timeout: 5s
  interval: 10s
  interval_jitter: 1s
  initial_delay: 3s
  unhealthy_threshold: 3
  healthy_threshold: 2
  http_health_check:
    path: /healthz
    request_headers_to_add:
    - header:
        key: X-Envoy-Healthcheck
        value: "true"
    expected_statuses:
    - status_range:
        start: 200
        end: 299
    connect_timeout: 3s
  tcp_health_check:
    send:
      string_matcher: "PING"
    receive:
    - string_matcher: "PONG"
  http2_health_check:
    path: /healthz
  grpc_health_check:
    service_name: "health"
```

### Passive (Outbound-Only) Health Check

```yaml
health_checks:
- timeout: 5s
  interval: 10s
  unhealthy_threshold: 3
  healthy_threshold: 2
  http_health_check:
    path: /healthz
  tcp_health_check:
    idle_timeout: 30s
```

### Multi-Health Check (HTTP + TCP)

```yaml
health_checks:
- timeout: 5s
  interval: 10s
  unhealthy_threshold: 3
  healthy_threshold: 2
  http_health_check:
    path: /healthz
- timeout: 3s
  interval: 15s
  unhealthy_threshold: 2
  tcp_health_check:
    idle_timeout: 10s
```

## Outlier Detection

```yaml
outlier_detection:
  consecutive_gateway_failure: 3        # Consecutive 502/503/504 to eject
  consecutive_5xx: 5                    # Consecutive 5xx to eject
  consecutive_200_to_5xx:              # Ratio-based ejection
    consecutive: 3
    status_code:
      code: 503
  consecutive_local_origin_failures: 5  # Failures for local-origin endpoints
  interval: 15s                         # How often to check ejected hosts
  base_ejection_time: 30s               # Minimum ejection duration
  max_ejection_percent: 50              # Max % of hosts ejected from pool
  min_health_percent: 10                # Don't eject if remaining < 10%
  consecutive_spurious_connect_failure:  # Spurious reconnection failures
    consecutive: 5
```

## Circuit Breaker

```yaml
# Circuit breaker thresholds
common_lb_config:
  circuit_breakers:
    thresholds:
    - priority: DEFAULT
      max_connections: 1024
      max_pending_requests: 1024
      max_requests: 1024
      max_retries: 3
    - priority: HIGH
      max_connections: 2048
      max_pending_requests: 2048
      max_requests: 2048
      max_retries: 3
```

## Cluster-Level Transport & Protocol Options

```yaml
- name: h2_backend
  type: STRICT_DNS
  lb_policy: ROUND_ROBIN
  typed_extension_protocol_options:
    envoy.extensions.upstreams.http.v3.HttpProtocolOptions:
      "@type": type.googleapis.com/envoy.extensions.upstreams.http.v3.HttpProtocolOptions
      explicit_http_config:
        http2_protocol_options: {}
      # Or for HTTP/1.1:
      # explicit_http_config:
      #   http_protocol_options: {}
  load_assignment:
    cluster_name: h2_backend
    endpoints:
    - lb_endpoints:
      - endpoint:
          address:
            socket_address:
              address: backend.example.com
              port_value: 443
```

## Common Pitfalls

| Pitfall | Impact | Fix |
|---------|--------|-----|
| Missing `typed_extension_protocol_options` on H2 upstream | HTTP/2 upstream connections fail | Add `HttpProtocolOptions` → `http2_protocol_options: {}` |
| `outlier_detection` with `min_health_percent: 0` | All hosts can be ejected, causing 503s | Set `min_health_percent: 10` to keep minimum pool |
| No `max_ejection_percent` | Single outlier can eject entire cluster | Set `max_ejection_percent: 50` (or appropriate) |
| `consecutive_5xx` without `consecutive_gateway_failure` | 500s count but not always meaningful | Add `consecutive_gateway_failure: 3` for 502/503/504 |
| Health check `timeout` > `interval` | Health check may overlap | Keep `timeout < interval` (e.g., timeout: 5s, interval: 10s) |
| Missing `interval_jitter` | All hosts checked simultaneously (thundering herd) | Add `interval_jitter: 1s` (or similar) |
| Static cluster without `load_assignment` | No endpoints to route to | Always include `load_assignment` with at least one endpoint |
| EDS without `api_config_source` | No endpoint updates received | Configure `eds_config` with gRPC or REST API source |
| `initial_back_off_bound` too large for latency-sensitive | Requests timeout waiting for backup | Tune `initial_back_off: 0.1s`, `max_back_off: 1s` for latency-sensitive |
| Circuit breaker `max_connections` lower than LB connections | New connections rejected immediately | Match `max_connections` to expected concurrent connections |
