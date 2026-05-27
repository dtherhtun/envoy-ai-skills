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

| File | Use when… |
|------|-----------|
| `filters.md` | Building filter chains, looking up `@type` URLs, understanding filter behavior |
| `clusters.md` | Defining upstream clusters, LB policies, health checks, circuit breakers, outlier detection |
| `wasm.md` | Configuring WASM plugins (v8/wamr/wasmtime), remote sources, OIDC via WASM |
| `oidc-oauth2-keycloak.md` | OAuth2, JWT authn, ExtAuthz patterns; Keycloak integration; filter ordering |
| `observability.md` | Prometheus stats, Zipkin/OTel tracing, access logs, admin API debugging |
| `tls.md` | TLS termination, mTLS, downstream/upstream TLS contexts, SDS cert rotation |

## Core Principles

1. **Always v3 API** — use `type.googleapis.com/envoy.extensions.*` fully-qualified protobuf types. Never mix v2 `config` fields with v3 `typed_config`.
2. **Filter ordering matters** — `oauth2` → `jwt_authn` → `rbac` → `wasm` → `ext_authz` → `local_ratelimit` → `cors` → `header_mutation` → `health_check` → `lua` → `router`. The `router` filter must be last.
3. **`typed_config` with `@type` is mandatory** on every filter. Deprecated `config` fields will be rejected.
4. **Secrets via SDS** — never embed TLS certs, JWT signing keys, or OAuth2 secrets inline in static config.
5. **Always validate** before apply: `envoy --mode validate -c envoy.yaml`

## Minimal Bootstrap Skeleton

```yaml
admin:
  address:
    socket_address:
      address: 127.0.0.1
      port_value: 9901

static_resources:
  listeners:
  - name: main_listener
    address:
      socket_address:
        address: 0.0.0.0
        port_value: 8443
    filter_chains:
    - transport_socket:
        name: envoy.transport_sockets.tls
        typed_config:
          "@type": type.googleapis.com/envoy.extensions.transport_sockets.tls.v3.DownstreamTlsContext
          common_tls_context:
            tls_params:
              tls_minimum_protocol_version: TLS_V1_2
            tls_certificates:
            - certificate_chain:
                sds_config:
                  path: "/etc/envoy/certs/server-cert.yaml"
              private_key:
                sds_config:
                  path: "/etc/envoy/certs/server-key.yaml"
            combined_validation_context:
              match_typed_subject_alt_names:
              - match_option:
                  spiffe_id: "cluster.example.svc.cluster.local"
              validation_context:
                trusted_ca:
                  sds_config:
                    path: "/etc/envoy/certs/ca-cert.yaml"
          require_client_certificate: true  # strict mTLS
      filters:
      - name: envoy.filters.network.http_connection_manager
        typed_config:
          "@type": type.googleapis.com/envoy.extensions.filters.network.http_connection_manager.v3.HttpConnectionManager
          stat_prefix: ingress_http
          http_filters:
          - name: envoy.filters.http.jwt_authn
            typed_config:
              "@type": type.googleapis.com/envoy.extensions.filters.http.jwt_authn.v3.JwtAuthentication
          - name: envoy.filters.http.oauth2
            typed_config:
              "@type": type.googleapis.com/envoy.extensions.filters.http.oauth2.v3.OAuth2
          - name: envoy.filters.http.rbac
            typed_config:
              "@type": type.googleapis.com/envoy.extensions.filters.http.rbac.v3.RBAC
          - name: envoy.filters.http.wasm
            typed_config:
              "@type": type.googleapis.com/envoy.extensions.filters.http.wasm.v3.Wasm
          - name: envoy.filters.http.cors
            typed_config:
              "@type": type.googleapis.com/envoy.extensions.filters.http.cors.v3.Cors
          - name: envoy.filters.http.router
            typed_config:
              "@type": type.googleapis.com/envoy.extensions.filters.http.router.v3.Router

  clusters:
  - name: web_service
    type: STRICT_DNS
    lb_policy: ROUND_ROBIN
    load_assignment:
      cluster_name: web_service
      endpoints:
      - lb_endpoints:
        - endpoint:
            address:
              socket_address:
                address: web_service
                port_value: 8080
    transport_socket:
      name: envoy.transport_sockets.tls
      typed_config:
        "@type": type.googleapis.com/envoy.extensions.transport_sockets.tls.v3.UpstreamTlsContext
        sni: web-service.example.svc.cluster.local
        common_tls_context:
          tls_certificates:
          - certificate_chain:
              sds_config:
                path: "/etc/envoy/certs/client-cert.yaml"
            private_key:
              sds_config:
                path: "/etc/envoy/certs/client-key.yaml"
          validation_context:
            trusted_ca:
              sds_config:
                path: "/etc/envoy/certs/ca-cert.yaml"
            match_typed_subject_alt_names:
            - spiffe_id: "web-service.example.svc.cluster.local"
    health_checks:
    - timeout: 5s
      interval: 10s
      unhealthy_threshold: 3
      http_health_check:
        path: /healthz
    outlier_detection:
      consecutive_5xx: 5
      interval: 15s
      base_ejection_time: 30s
      max_ejection_percent: 50
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
| RateLimit (local) | `type.googleapis.com/envoy.extensions.filters.http.local_ratelimit.v3.LocalRateLimit` |
| HealthCheck (filter) | `type.googleapis.com/envoy.extensions.filters.http.health_check.v3.HealthCheck` |
| Lua | `type.googleapis.com/envoy.extensions.filters.http.lua.v3.Lua` |
| HeaderMutation | `type.googleapis.com/envoy.extensions.filters.http.header_mutation.v3.HeaderMutation` |
| DownstreamTlsContext | `type.googleapis.com/envoy.extensions.transport_sockets.tls.v3.DownstreamTlsContext` |
| UpstreamTlsContext | `type.googleapis.com/envoy.extensions.transport_sockets.tls.v3.UpstreamTlsContext` |
| FileAccessLog | `type.googleapis.com/envoy.extensions.access_loggers.file.v3.FileAccessLog` |
|| ZipkinConfig | `type.googleapis.com/envoy.config.trace.v3.ZipkinConfig` |
|| OpenTelemetryConfig | `type.googleapis.com/envoy.config.trace.v3.OpenTelemetryConfig` |

## Key Config Patterns

### Active Health Check
```yaml
health_checks:
- timeout: 5s
  interval: 10s
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
  interval: 15s
  base_ejection_time: 30s
  max_ejection_percent: 50
  min_health_percent: 10
```

### Circuit Breaker
```yaml
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
    log_format:
      typed_json_format:
        method: "%REQ(:METHOD)%"
        path: "%REQ(:PATH)%"
        response_code: "%RESPONSE_CODE%"
        response_flags: "%RESPONSE_FLAGS%"
        duration: "%DURATION%"
        upstream_address: "%UPSTREAM_ADDRESS%"
        request_id: "%REQ(X-REQUEST-ID,-)%"
        bytes_received: "%BYTES_RECEIVED%"
        bytes_sent: "%BYTES_SENT%"
        downstream_client_ip: "%DOWNSTREAM_REMOTE_ADDRESS_WITHOUT_PORT%"
        upstream_cluster: "%UPSTREAM_CLUSTER%"
```

## Operations

### Validation
```bash
envoy --mode validate -c envoy.yaml
```

### Hot Reload (SIGUSR1)
```bash
kill -USR1 $(cat /var/run/envoy.pid)
# Or: envoy --hot-restarter -c envoy.yaml
```

### Admin API
```bash
curl http://127.0.0.1:9901/clusters?format=json     # Cluster status
curl http://127.0.0.1:9901/listeners?format=json     # Listener details
curl http://127.0.0.1:9901/config_dump?mask=secrets  # SDS secrets
curl http://127.0.0.1:9901/stats/prometheus          # Prometheus metrics
curl http://127.0.0.1:9901/runtime                   # Runtime values
curl http://127.0.0.1:9901/server_info               # Server metadata
curl http://127.0.0.1:9901/certs                     # TLS certificate info
```

### SDS Secret Rotation
```bash
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
kill -USR1 $(cat /var/run/envoy.pid)
curl http://127.0.0.1:9901/config_dump?mask=secrets | jq '.configs[].dynamic_secrets[]?.name'
```

## Reference Pointer

- Full HTTP filter catalog → `filters.md`
- Cluster/LB/health/outlier patterns → `clusters.md`
- WASM plugins, OIDC-via-WASM → `wasm.md`
- OIDC/OAuth2/JWT/Keycloak patterns → `oidc-oauth2-keycloak.md`
- Observability (Prometheus, tracing, access logs) → `observability.md`
- TLS/mTLS/SDS/SPIFFE → `tls.md`
