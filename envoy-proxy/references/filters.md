# Envoy HTTP Filter Catalog (v1.38.0)

Complete catalog of built-in HTTP filters with `@type` URLs, configuration patterns, and usage notes.

## Filter Ordering

Filter execution follows a strict chain — order matters. The canonical downstream filter order is:

```
oauth2 → jwt_authn → rbac → wasm → ext_authz → local_ratelimit → cors → header_mutation → health_check → lua → router
```

**Rules:**
- `router` must always be last — it's the final hop before upstream forwarding.
- `health_check` and `cors` have special semantics (they short-circuit OPTIONS requests).
- `ext_authz` security: if a downstream filter (like `lua`) calls `clearRouteCache()` after `ext_authz`, the request may be rerouted and bypass auth. Avoid `clearRouteCache()` after `ext_authz`.
- `ext_authz` must be placed before any filter that clears the route cache on the same listener.

## Full Filter Table

| # | Filter Name | @type URL | Downstream | Upstream | Short-Circuit? | Description |
|---|-------------|-----------|------------|----------|----------------|-------------|
| 1 | oauth2 | `type.googleapis.com/envoy.extensions.filters.http.oauth2.v3.OAuth2` | ✓ | — | Partial | Browser SSO, authorization code flow |
| 2 | jwt_authn | `type.googleapis.com/envoy.extensions.filters.http.jwt_authn.v3.JwtAuthentication` | ✓ | — | No | JWT signature + claim validation |
| 3 | rbac | `type.googleapis.com/envoy.extensions.filters.http.rbac.v3.RBAC` | ✓ | — | No | IP/header-based access control |
| 4 | wasm | `type.googleapis.com/envoy.extensions.filters.http.wasm.v3.Wasm` | ✓ | ✓ | No | Custom WASM plugin |
| 5 | ext_authz | `type.googleapis.com/envoy.extensions.filters.http.ext_authz.v3.ExtAuthz` | ✓ | — | No | External auth service call |
| 6 | local_ratelimit | `type.googleapis.com/envoy.extensions.filters.http.local_ratelimit.v3.LocalRateLimit` | ✓ | — | Yes | Distributed rate limiting |
| 7 | cors | `type.googleapis.com/envoy.extensions.filters.http.cors.v3.Cors` | ✓ | — | Yes | CORS preflight handling |
| 8 | header_mutation | `type.googleapis.com/envoy.extensions.filters.http.header_mutation.v3.HeaderMutation` | ✓ | ✓ | No | Request/response header manipulation |
| 9 | health_check | `type.googleapis.com/envoy.extensions.filters.http.health_check.v3.HealthCheck` | ✓ | — | Yes | Health check request passthrough |
| 10 | lua | `type.googleapis.com/envoy.extensions.filters.http.lua.v3.Lua` | ✓ | ✓ | Yes | Lua scripting |
| 11 | router | `type.googleapis.com/envoy.extensions.filters.http.router.v3.Router` | ✓ | — | No | Final routing to upstream cluster |
| 12 | grpc_json_transcoder | `type.googleapis.com/envoy.extensions.filters.http.grpc_json_transcoder.v3.GrpcJsonTranscoder` | ✓ | — | No | REST-to-gRPC transcoding |
| 13 | golang | `type.googleapis.com/envoy.extensions.filters.http.golang.v3alpha.Config` | ✓ | ✓ | No | Custom Go plugin |
| 14 | gcp_authn | `type.googleapis.com/envoy.extensions.filters.http.gcp_authn.v3.GcpAuthnFilterConfig` | ✓ | — | No | GCE metadata token injection |
| 15 | credential_injector | `type.googleapis.com/envoy.extensions.filters.http.credential_injector.v3.CredentialInjector` | ✓ | — | No | Auth header injection |
| 16 | csrf | `type.googleapis.com/envoy.extensions.filters.http.csrf.v3.CsrfPolicy` | ✓ | — | Yes | CSRF token validation |
| 17 | header_to_metadata | `type.googleapis.com/envoy.extensions.filters.http.header_to_metadata.v3.Config` | ✓ | — | No | Header → dynamic metadata |
| 18 | ip_tagging | `type.googleapis.com/envoy.extensions.filters.http.ip_tagging.v3.IpTagging` | ✓ | — | No | IP → dynamic metadata tagging |
| 19 | dynamic_modules | `type.googleapis.com/envoy.extensions.filters.http.dynamic_modules.v3.DynamicModule` | ✓ | ✓ | No | Dynamic module loading |
| 20 | ext_proc | `type.googleapis.com/envoy.extensions.filters.http.ext_proc.v3.ExternalProcessor` | ✓ | ✓ | No | External processing (Async) |

## Detailed Filter Specs

### 1. HttpConnectionManager (Network Filter)
**@type:** `type.googleapis.com/envoy.extensions.filters.network.http_connection_manager.v3.HttpConnectionManager`

Required fields: `stat_prefix`, `route_config` (or `rds`), `http_filters[]`.
Optional: `access_log`, `stream_idle_timeout`, `request_timeout`, `tracing`, `codec_type`, `http_protocol_options`, `codec_http2_settings`, `max_request_headers_kb`, `max_request_headers_count`, `headers_with_underscores_action`, `server_header_transformation`, `access_log` with formatters.

### 2. Router (Final Filter)
**@type:** `type.googleapis.com/envoy.extensions.filters.http.router.v3.Router`

Minimal config — just the `@type`. Controls: `x-envoy-original-path`, `x-envoy-original-host` preservation, retry headers, timeout overrides, hedging.

### 3. JwtAuthentication
**@type:** `type.googleapis.com/envoy.extensions.filters.http.jwt_authn.v3.JwtAuthentication`

Key fields: `providers` map (each with `issuer`, `audiences`, `local_jwks`/`remote_jwks`, `from_headers`/`from_params`/`from_cookies`), `rules` (each with `match`, `requires`/`requires_any`/`requires_all`).

Supported algorithms: ES256, ES384, ES512, HS256, HS384, HS512, RS256, RS384, RS512, PS256, PS384, PS512, EdDSA.

### 4. OAuth2
**@type:** `type.googleapis.com/envoy.extensions.filters.http.oauth2.v3.OAuth2`

⚠️ Under active development. Key fields: `token_endpoint`, `authorization_endpoint`, `redirect_uri`, `redirect_path_matcher`, `credentials` (with SDS `token_secret` and `hmac_secret`), `auth_scopes`.

### 5. RBAC
**@type:** `type.googleapis.com/envoy.extensions.filters.http.rbac.v3.RBAC`

Key fields: `rules` (ALLOW or DENY action), `policies`, `shadow_rules`. Denial response uses `rbac_access_denied_matched_policy[policy_name]` in `RESPONSE_CODE_DETAILS`. Supports `shadow_mode` for pre-production validation.

### 6. ExtAuthz
**@type:** `type.googleapis.com/envoy.extensions.filters.http.ext_authz.v3.ExtAuthz`

Key fields: `grpc_service` (for gRPC ext-authz service) or `http_service` (for HTTP ext-authz service). Configurable `authorization_request`/`authorization_response` header forwarding. `failure_mode_allow` controls behavior when ext-authz is down. Supports `typed_per_filter_config` with `ExtAuthzPerRoute`.

⚠️ **Security:** Filters after `ext_authz` that call `clearRouteCache()` can bypass auth by rerouting requests.

### 7. Local RateLimit
**@type:** `type.googleapis.com/envoy.extensions.filters.http.local_ratelimit.v3.LocalRateLimit`

Key fields: `stat_prefix`, `token_bucket`, `filter_enabled`, `filter_deadline`, `rate_limit_service` (for distributed rate limiting).

### 8. CORS
**@type:** `type.googleapis.com/envoy.extensions.filters.http.cors.v3.Cors`

Key fields: `origins`, `methods`, `headers`, `expose_headers`, `max_age`, `supports_credentials`, `filter_enabled`, `shadow_enabled`. Bypassed by direct responses or route redirects. Short-circuits OPTIONS requests.

### 9. Health Check (Filter)
**@type:** `type.googleapis.com/envoy.extensions.filters.http.health_check.v3.HealthCheck`

Parses `X-Envoy-Healthcheck: true` header to detect health check requests. Automatically fails when admin `/healthcheck/fail` is called.

### 10. Lua
**@type:** `type.googleapis.com/envoy.extensions.filters.http.lua.v3.Lua`

Key fields: `default_source_code` (inline or file), `source_codes` map for named scripts. Two global functions: `envoy_on_request(request_handle)`, `envoy_on_response(response_handle)`.

⚠️ Never assign stream handles to global variables. All I/O via Envoy APIs.

### 11. Header Mutation
**@type:** `type.googleapis.com/envoy.extensions.filters.http.header_mutation.v3.HeaderMutation`

Key fields: `request_headers_to_add/remove/append/update`, `response_headers_to_add/remove/append/update`, `query_parameter_mutations`. Can apply to request, response, or both. Per-route via `HeaderMutationPerRoute`.

### 12. gRPC-JSON Transcoder
**@type:** `type.googleapis.com/envoy.extensions.filters.http.grpc_json_transcoder.v3.GrpcJsonTranscoder`

Transcodes REST JSON → gRPC based on `.proto` definitions. Key fields: `proto_descriptor`, `services`, `convert_channel_tracing_to_warnings`, `ignore_unknown_query_parameters`.

### 13. WASM
**@type:** `type.googleapis.com/envoy.extensions.filters.http.wasm.v3.Wasm`

Key fields: `config` (name, root_id, configuration via `google.protobuf.StringValue`), `vm_config` (vm_id, runtime, code source). Supports v8, wamr, wasmtime, and null runtimes. Per-route disable via `typed_per_filter_config` with `WasmPerRoute`.

### 14. Access Logger (Not a filter, but related)
**@type:** `type.googleapis.com/envoy.extensions.access_loggers.file.v3.FileAccessLog`

Configured on HttpConnectionManager. Supports `format` (string) or `json_format`/`typed_json_format` (structured).

**Common command operators:**
- `%START_TIME%` — Request start time
- `%REQ(:METHOD)%` — HTTP method
- `%REQ(:PATH)%` — Request path
- `%PROTOCOL%` — Protocol version
- `%RESPONSE_CODE%` — HTTP status
- `%RESPONSE_FLAGS%` — Envoy response flags
- `%DURATION%` — Request duration (µs)
- `%RESP(X-ENVOY-UPSTREAM-SERVICE-TIME,-)%` — Upstream service time
- `%UPSTREAM_ADDRESS%` — Upstream address
- `%UPSTREAM_CLUSTER%` — Target cluster name
- `%DOWNSTREAM_REMOTE_ADDRESS%` — Client address

## Common Pitfalls

| Pitfall | Impact | Fix |
|---------|--------|-----|
| Missing `@type` on `typed_config` | Config rejected on `--mode validate` | Always include full v3 @type URL |
| Filtering with `config` (deprecated) | `typed_config` required in v1.31+ | Use `typed_config` with `@type`, migrate `config` → `typed_config` |
| `router` not last in chain | Routes unreachable; warnings in logs | Always place `router` as the last filter |
| `lua.clearRouteCache()` after `ext_authz` | Privilege escalation — auth bypass | Remove `clearRouteCache()` or ensure auth rules are preserved |
| `cors` filter with redirect route | CORS filter is bypassed on direct responses | Don't combine CORS with `direct_response` on same route |
| `jwt_authn` with no matching rule | JWT not validated (silent skip) | Empty `requires` → not required; no match → not required. Explicitly deny missing JWT with `require: { }` |
| Health check filter without header | Health check traffic treated as normal | Set `X-Envoy-Healthcheck: true` on health check requests |
| Missing `http2_protocol_options` on upstream | HTTP/2 upstreams may not work | Add `typed_extension_protocol_options` with `HttpProtocolOptions` → `http2_protocol_options: {}` |
| Multiple per-route `oauth2` configs sharing host | Cookie name collisions | Customize `cookie_names` per route |
| `failure_mode_allow: true` on ext_authz | Auth bypass on ext-authz service failure | Set `failure_mode_allow: false` for security-sensitive routes |
