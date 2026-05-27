# Envoy WASM Plugin Configuration (v1.38.0)

Complete reference for WASM filters, runtimes, source types, configuration patterns, and the OIDC-via-WASM integration pattern.

## WASM Filter Overview

**@type:** `type.googleapis.com/envoy.extensions.filters.http.wasm.v3.Wasm`

The WASM filter enables custom logic via WebAssembly plugins. Envoy supports multiple WASM runtimes and three source types for plugin deployment.

## Runtimes

| Runtime | Description | Best For |
|---------|-------------|----------|
| `v8` | V8 engine (C++ bindings) | JavaScript/TypeScript plugins, performance |
| `wamr` | WebAssembly Micro Runtime (interpretive) | Portability, interpreted execution |
| `wasmtime` | Cranelift-based runtime (AOT/JIT) | Performance, native-like speed |
| `null` | No-op runtime (for testing) | Debugging filter chain behavior |

**Selection:** Choose runtime via `vm_config.runtime`. Must be one of: `envoy.wasm.runtime.v8`, `envoy.wasm.runtime.wamr`, `envoy.wasm.runtime.wasmtime`, or `envoy.wasm.runtime.null`.

## Source Types

| Source | Use Case | Security |
|--------|----------|----------|
| `local_file` | Development, minimal ops | Verify file integrity externally |
| `remote_url` | CI/CD pipelines, centralized | SHA-256 verified download |
| `inline_bytes` | Embedding small plugins | No network required, size-limited |

## Complete WASM Configuration

### Remote WASM Plugin (Production-Grade)

```yaml
- name: envoy.filters.http.wasm
  typed_config:
    "@type": type.googleapis.com/envoy.extensions.filters.http.wasm.v3.Wasm
    config:
      name: "example-plugin"
      root_id: "example_root"
      configuration:
        "@type": "type.googleapis.com/google.protobuf.StringValue"
        value: |
          {
            "key1": "value1",
            "key2": "value2"
          }
    vm_config:
      vm_id: "unique_vm_id"           # Enables VM code sharing across filter instances
      runtime: envoy.wasm.runtime.wasmtime
      code:
        remote:
          http_uri:
            uri: "https://plugins.example.com/example.wasm"
            timeout: 30s
            sha256: "ab12cd34ef56..."  # SHA-256 of the .wasm binary
          trigger: ALWAYS
      allow_precompiled: true
      # Optional: per-proxy-wasm root config
      # vm_config_envoyvars: true
```

### Local File WASM Plugin (Development)

```yaml
- name: envoy.filters.http.wasm
  typed_config:
    "@type": type.googleapis.com/envoy.extensions.filters.http.wasm.v3.Wasm
    config:
      name: "local-plugin"
      root_id: "local_root"
      configuration:
        "@type": "type.googleapis.com/google.protobuf.StringValue"
        value: '{"debug": true}'
    vm_config:
      vm_id: "local_vm"
      runtime: envoy.wasm.runtime.wasmtime
      code:
        local_file: "/etc/envoy/plugins/example.wasm"
```

### Inline WASM Plugin (Small plugins only)

```yaml
- name: envoy.filters.http.wasm
  typed_config:
    "@type": type.googleapis.com/envoy.extensions.filters.http.wasm.v3.Wasm
    config:
      name: "inline-plugin"
      root_id: "inline_root"
    vm_config:
      vm_id: "inline_vm"
      runtime: envoy.wasm.runtime.v8
      code:
        inline_bytes: "<base64-wasm-binary>"  # Raw WASM bytes (base64)
      # NOTE: inline_bytes is limited to ~64KB by Envoy
```

## VM_ID: Code Sharing

When `vm_id` is identical across filter instances, Envoy shares a single WASM VM instance (one process memory space). This saves significant memory for large plugins.

```yaml
# Two filter instances sharing one VM
# Instance 1:
vm_config:
  vm_id: "auth-vm"
  # ... code config

# Instance 2 (on different listener/route):
vm_config:
  vm_id: "auth-vm"       # Same VM_ID = shared VM
  # ... code config
```

## Per-Route WASM Configuration

### Disable WASM on a specific route

```yaml
# In route configuration:
typed_per_filter_config:
  type.googleapis.com/envoy.extensions.filters.http.wasm.v3.WasmPerRoute:
    disabled: true

# Or filter-level override:
typed_per_filter_config:
  type.googleapis.com/envoy.extensions.filters.http.wasm.v3.WasmPerRoute:
    config:
      root_id: ""              # Empty root_id = no-op
      vm_id: ""
      # or:
      override:
        config:
          name: ""
```

### Per-route configuration override

```yaml
typed_per_filter_config:
  type.googleapis.com/envoy.extensions.filters.http.wasm.v3.WasmPerRoute:
    config:
      configuration:
        "@type": "type.googleapis.com/google.protobuf.StringValue"
        value: '{"mode": "override", "debug": true}'
    # You can also disable specific hooks or add new ones
```

## Configuration Block Pattern

The `configuration` field is a `google.protobuf.StringValue` containing JSON:

```yaml
configuration:
  "@type": "type.googleapis.com/google.protobuf.StringValue"
  value: |
    {
      "allow_public_routes": true,
      "require_signed": false,
      "plugins": ["/etc/envoy/plugins/"]
    }
```

This JSON is passed to the plugin at initialization time via `proxy_wasm_get_plugin_configuration()`.

## OIDC via WASM Pattern

This pattern uses a WASM plugin (typically `oidc.wasm` or similar proxy-wasm plugins) to implement OIDC authentication in Envoy when native Envoy OAuth2 filter is not desired or available.

```yaml
- name: envoy.filters.http.wasm
  typed_config:
    "@type": type.googleapis.com/envoy.extensions.filters.http.wasm.v3.Wasm
    config:
      name: "oidc-wasm-plugin"
      root_id: "oidc_root"
      configuration:
        "@type": "type.googleapis.com/google.protobuf.StringValue"
        value: |
          {
            "issuer_url": "https://keycloak.example.com/realms/myrealm",
            "client_id": "envoy-proxy",
            "client_secret": "REDACTED",
            "scopes": ["openid", "email"],
            "callback_url": "https://proxy.example.com/callback",
            "logout_url": "https://proxy.example.com/logout",
            "forward_access_token": true,
            "upstream_headers_to_add": [
              {"key": "Authorization", "value": "Bearer {{id_token}}"}
            ]
          }
    vm_config:
      vm_id: "oidc_vm"
      runtime: envoy.wasm.runtime.wasmtime
      code:
        remote:
          http_uri:
            uri: "https://plugins.example.com/oidc.wasm"
            timeout: 30s
            sha256: "sha256-hash-of-oidc.wasm"
          trigger: ALWAYS
```

### Keycloak Integration with OIDC WASM Plugin

```yaml
configuration:
  "@type": "type.googleapis.com/google.protobuf.StringValue"
  value: |
    {
      "issuer_url": "https://keycloak.example.com/realms/myrealm",
      "client_id": "envoy-proxy",
      "jwks_uri": "https://keycloak.example.com/realms/myrealm/protocol/openid-connect/certs",
      "scopes": ["openid", "profile", "email"],
      "callback_url": "https://proxy.example.com/oidc/callback",
      "logout_url": "https://proxy.example.com/oidc/logout",
      "forward_access_token": true,
      "access_token_header": "X-Access-Token",
      "id_token_header": "X-Id-Token",
      "upstream_headers_to_add": [
        {"key": "X-User-Email", "value": "{{email}}"},
        {"key": "X-User-Name", "value": "{{name}}"}
      ],
      "upstream_headers_to_remove": [
        "Authorization",
        "Cookie"
      ]
    }
```

## Common Pitfalls

| Pitfall | Impact | Fix |
|---------|--------|-----|
| SHA-256 mismatch between config and actual .wasm | Plugin download rejected | Always verify SHA-256 after downloading: `sha256sum plugin.wasm` |
| `root_id` mismatch between filter config and `vm_config` | Plugin initialization fails | `config.root_id` must exactly match the `vm_config` that references it |
| Missing `vm_id` for shared plugins | Each filter creates a separate VM, high memory | Set `vm_id` to the same value across filter instances |
| Using `inline_bytes` with large plugins | Envoy rejects the upload | Use `remote_url` or `local_file` for plugins > ~64KB |
| WASM on upstream cluster without `allow_precompiled` | Precompiled code may be rejected | Set `allow_precompiled: true` in `vm_config` |
| Multiple WASM filters on same listener | Conflicting execution, hard to debug | Use single WASM filter with multiple configurations via `typed_per_filter_config` |
| Forgetting `trigger: ALWAYS` on remote source | Plugin not re-fetched on Envoy restart | Use `trigger: ALWAYS` for remote WASM code |
| WASM runtime not available in binary | Envoy refuses config | Build Envoy with the target runtime (`v8`, `wasmtime`, or `wamr` compiled in) |
| No log level set for WASM | Hard to debug plugin issues | Set `config.log_level: "trace"` during development |
| WASM plugin blocks without using async API | Envoy request thread stuck | All I/O in WASM plugins must use async proxy-wasm APIs |
