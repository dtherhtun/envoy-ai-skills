---
name: envoy-proxy
description: >
  Envoy proxy configuration for v1.38.0. Triggers on: "configure Envoy",
  "Envoy filter chain", "envoy.yaml", "Envoy proxy config", "HTTP filter",
  "WASM plugin Envoy", "Keycloak with Envoy", "JWT validation Envoy",
  "OAuth2 filter Envoy", "envoy circuit breaker", "Envoy health check",
  "outlier detection Envoy", "Envoy mTLS", "Envoy routing",
  "load balancing Envoy", "SDS secret rotation", "Envoy admin API",
  "Envoy access log", "Envoy tracing", "Envoy observability",
  "Envoy bootstrap", "Envoy listener cluster", "Envoy config validation".
version: "1.38.0"
api: v3
---

# Envoy Proxy Skill (v1.38.0)

Production-grade Envoy proxy configuration reference for v1.38.0 using the v3 API.

## Directory Map

| File                                                          | Use when… |
|---------------------------------------------------------------|-----------|
| [filters.md](references/filters.md)                           | Building filter chains, looking up `@type` URLs, understanding filter behavior |
| [clusters.md](references/clusters.md)                         | Defining upstream clusters, LB policies, health checks, circuit breakers, outlier detection |
| [wasm.md](references/wasm.md)                                 | Configuring WASM plugins (v8/wamr/wasmtime), remote sources, OIDC via WASM |
| [oidc-oauth2-keycloak.md](references/oidc-oauth2-keycloak.md) | OAuth2, JWT authn, ExtAuthz patterns; Keycloak integration; filter ordering |
| [observability.md](references/observability.md)               | Prometheus stats, Zipkin/OTel tracing, access logs, admin API debugging |
| [tls.md](references/tls.md)                                   | TLS termination, mTLS, downstream/upstream TLS contexts, SDS cert rotation |

## Core Principles

1. **Always v3 API** — use `type.googleapis.com/envoy.extensions.*` fully-qualified protobuf types. Never mix v2 `config` fields with v3 `typed_config`.
2. **Filter ordering matters** — `oauth2` → `jwt_authn` → `rbac` → `wasm` → `ext_authz` → `local_ratelimit` → `cors` → `header_mutation` → `health_check` → `lua` → `router`. The `router` filter must be last.
3. **`typed_config` with `@type` is mandatory** on every filter. Deprecated `config` fields will be rejected.
4. **Secrets via SDS** — never embed TLS certs, JWT signing keys, or OAuth2 secrets inline in static config.
5. **Always validate** before apply: `envoy --mode validate -c envoy.yaml`

## Minimal Bootstrap Skeleton

Plain HTTP, no TLS — the simplest valid config. See `tls.md` for TLS/mTLS variants.

```yaml
admin:
  address:
    socket_address:
      address: 127.0.0.1
      port_value: 9901

static_resources:
  listeners:
  - name: listener_0
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
          codec_type: AUTO
          route_config:
            name: local_route
            virtual_hosts:
            - name: local_service
              domains: ["*"]
              routes:
              - match:
                  prefix: "/"
                route:
                  cluster: service_backend
          http_filters:
          - name: envoy.filters.http.router
            typed_config:
              "@type": type.googleapis.com/envoy.extensions.filters.http.router.v3.Router

  clusters:
  - name: service_backend
    type: STRICT_DNS
    connect_timeout: 5s
    lb_policy: ROUND_ROBIN
    load_assignment:
      cluster_name: service_backend
      endpoints:
      - lb_endpoints:
        - endpoint:
            address:
              socket_address:
                address: backend
                port_value: 8080
```

## Full Filter Chain Skeleton (with auth)

When adding auth filters, always follow this order:

```yaml
http_filters:
- name: envoy.filters.http.oauth2          # 1. browser SSO (if needed)
  typed_config:
    "@type": type.googleapis.com/envoy.extensions.filters.http.oauth2.v3.OAuth2
    # ... see oidc-oauth2-keycloak.md
- name: envoy.filters.http.jwt_authn       # 2. JWT validation
  typed_config:
    "@type": type.googleapis.com/envoy.extensions.filters.http.jwt_authn.v3.JwtAuthentication
    # ... see oidc-oauth2-keycloak.md
- name: envoy.filters.http.rbac            # 3. role/IP access control
  typed_config:
    "@type": type.googleapis.com/envoy.extensions.filters.http.rbac.v3.RBAC
- name: envoy.filters.http.wasm            # 4. custom WASM plugin
  typed_config:
    "@type": type.googleapis.com/envoy.extensions.filters.http.wasm.v3.Wasm
- name: envoy.filters.http.local_ratelimit # 5. rate limiting
  typed_config:
    "@type": type.googleapis.com/envoy.extensions.filters.http.local_ratelimit.v3.LocalRateLimit
- name: envoy.filters.http.cors            # 6. CORS
  typed_config:
    "@type": type.googleapis.com/envoy.extensions.filters.http.cors.v3.Cors
- name: envoy.filters.http.router          # 7. ALWAYS LAST
  typed_config:
    "@type": type.googleapis.com/envoy.extensions.filters.http.router.v3.Router
```

## Common Filter @type URLs

| Filter | @type URL |
|--------|-----------|
| HttpConnectionManager | `type.googleapis.com/envoy.extensions.filters.network.http_connection_manager.v3.HttpConnectionManager` |
| Router | `type.googleapis.com/envoy.extensions.filters.http.router.v3.Router` |
| JwtAuthentication | `type.googleapis.com/envoy.extensions.filters.http.jwt_authn.v3.JwtAuthentication` |
| OAuth2 | `type.googleapis.com/envoy.extensions.filters.http.oauth2.v3.OAuth2` |
| RBAC | `type.googleapis.com/envoy.extensions.filters.http.rbac.v3.RBAC` |
| ExtAuthz | `type.googleapis.com/envoy.extensions.filters.http.ext_authz.v3.ExtAuthz` |
| Wasm | `type.googleapis.com/envoy.extensions.filters.http.wasm.v3.Wasm` |
| Cors | `type.googleapis.com/envoy.extensions.filters.http.cors.v3.Cors` |
| LocalRateLimit | `type.googleapis.com/envoy.extensions.filters.http.local_ratelimit.v3.LocalRateLimit` |
| HealthCheck (filter) | `type.googleapis.com/envoy.extensions.filters.http.health_check.v3.HealthCheck` |
| Lua | `type.googleapis.com/envoy.extensions.filters.http.lua.v3.Lua` |
| HeaderMutation | `type.googleapis.com/envoy.extensions.filters.http.header_mutation.v3.HeaderMutation` |
| DownstreamTlsContext | `type.googleapis.com/envoy.extensions.transport_sockets.tls.v3.DownstreamTlsContext` |
| UpstreamTlsContext | `type.googleapis.com/envoy.extensions.transport_sockets.tls.v3.UpstreamTlsContext` |
| FileAccessLog | `type.googleapis.com/envoy.extensions.access_loggers.file.v3.FileAccessLog` |
| ZipkinConfig | `type.googleapis.com/envoy.config.trace.v3.ZipkinConfig` |
| OpenTelemetryConfig | `type.googleapis.com/envoy.config.trace.v3.OpenTelemetryConfig` |
| Secret (SDS) | `type.googleapis.com/envoy.extensions.transport_sockets.tls.v3.Secret` |

## Key Config Patterns

### Active Health Check
```yaml
health_checks:
- timeout: 5s
  interval: 10s
  interval_jitter: 1s
  unhealthy_threshold: 3
  healthy_threshold: 2
  http_health_check:
    path: /healthz
    expected_statuses:
    - status_range:
        start: 200
        end: 299
```

### Outlier Detection
```yaml
outlier_detection:
  consecutive_5xx: 5
  consecutive_gateway_failure: 3
  interval: 15s
  base_ejection_time: 30s
  max_ejection_percent: 50
  min_health_percent: 10
```

### Circuit Breaker
```yaml
# Direct cluster-level field (NOT nested under common_lb_config)
circuit_breakers:
  thresholds:
  - priority: DEFAULT
    max_connections: 1024
    max_pending_requests: 1024
    max_requests: 1024
    max_retries: 3
```

### JSON Access Log
```yaml
access_log:
- name: envoy.access_loggers.file
  typed_config:
    "@type": type.googleapis.com/envoy.extensions.access_loggers.file.v3.FileAccessLog
    path: /dev/stdout
    log_format:
      typed_json_format:
        start_time: "%START_TIME%"
        method: "%REQ(:METHOD)%"
        path: "%REQ(:PATH)%"
        response_code: "%RESPONSE_CODE%"
        response_flags: "%RESPONSE_FLAGS%"
        duration: "%DURATION%"
        upstream_cluster: "%UPSTREAM_CLUSTER%"
        upstream_address: "%UPSTREAM_ADDRESS%"
        bytes_sent: "%BYTES_SENT%"
        bytes_received: "%BYTES_RECEIVED%"
        request_id: "%REQ(X-REQUEST-ID,-)%"
```

### SPIFFE SAN Matching
```yaml
# Correct SubjectAltNameMatcher structure — san_type + matcher
match_typed_subject_alt_names:
- san_type: URI
  matcher:
    exact: "spiffe://trust-domain/ns/default/sa/my-service"
```

## Operations

### Validation
```bash
envoy --mode validate -c envoy.yaml
```

### Hot Reload
```bash
kill -USR1 $(cat /var/run/envoy.pid)
```

### Admin API
```bash
curl http://127.0.0.1:9901/clusters?format=json      # Cluster health + stats
curl http://127.0.0.1:9901/listeners?format=json      # Listener details
curl http://127.0.0.1:9901/config_dump                # Full config snapshot
curl http://127.0.0.1:9901/config_dump?mask=secrets   # SDS secrets
curl http://127.0.0.1:9901/stats/prometheus           # Prometheus metrics
curl http://127.0.0.1:9901/certs                      # TLS certificate info
curl http://127.0.0.1:9901/server_info                # Version + state
curl http://127.0.0.1:9901/ready                      # Readiness probe
```

### SDS Secret Rotation
```bash
# Update the SDS watch file on disk, Envoy hot-reloads it automatically.
# No signal needed — Envoy watches the path and reloads on change.
cat > /etc/envoy/certs/server-cert.yaml << 'EOF'
resources:
- "@type": type.googleapis.com/envoy.extensions.transport_sockets.tls.v3.Secret
  name: server_cert
  tls_certificate:
    certificate_chain:
      filename: /etc/envoy/certs/server.crt
    private_key:
      filename: /etc/envoy/certs/server.key
EOF
# Verify pickup:
curl http://127.0.0.1:9901/certs
```

## Reference Pointer

- Full HTTP filter catalog → `filters.md`
- Cluster/LB/health/outlier patterns → `clusters.md`
- WASM plugins, OIDC-via-WASM → `wasm.md`
- OIDC/OAuth2/JWT/Keycloak patterns → `oidc-oauth2-keycloak.md`
- Observability (Prometheus, tracing, access logs) → `observability.md`
- TLS/mTLS/SDS/SPIFFE → `tls.md`