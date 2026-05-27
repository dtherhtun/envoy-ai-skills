# Envoy TLS / mTLS Configuration (v1.38.0)

Complete reference for TLS termination, mTLS, SDS cert rotation, and SPIFFE/SVID integration.

## TLS Context Types

| Context | Direction | Description |
|---------|-----------|-------------|
| `DownstreamTlsContext` | Downstream (client → Envoy) | TLS termination on incoming connections |
| `UpstreamTlsContext` | Upstream (Envoy → backend) | Outbound TLS to upstream services |
| `TransportSocket` | Both | Transport socket wrapping for any direction |

## TLS Filter Chain Example (Downstream TLS Termination)

```yaml
static_resources:
  listeners:
  - name: https_listener
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
              tls_maximum_protocol_version: TLS_V1_3
              cipher_suites:
              - "ECDHE-ECDSA-AES128-GCM-SHA256"
              - "ECDHE-RSA-AES128-GCM-SHA256"
              - "ECDHE-ECDSA-AES256-GCM-SHA384"
              - "ECDHE-RSA-AES256-GCM-SHA384"
            tls_certificates:
            - certificate_chain:
                sds_config:
                  path: "/etc/envoy/certs/server-cert.yaml"
              private_key:
                sds_config:
                  path: "/etc/envoy/certs/server-key.yaml"
            alpn_protocols:
            - "h2"
            - "http/1.1"
            # Client certificate validation (mTLS)
            combined_validation_context:
              match_typed_subject_alt_names:
              - spiffe_id: "cluster.example.svc.cluster.local"
              validation_context:
                trusted_ca:
                  sds_config:
                    path: "/etc/envoy/certs/ca-cert.yaml"
              default_validation_context:
                typed_extension_protocol_options:
                  envoy.extensions.transport_sockets.tls.v3.DownstreamTlsContext: {}
              match_typed_subject_alt_names:
              - type: OIDCI
                value: "spiffe://example.com/ns/default/sa/backend"
          require_client_certificate: true  # Strict mTLS — reject non-TLS clients
      filters:
      - name: envoy.filters.network.http_connection_manager
        typed_config:
          "@type": type.googleapis.com/envoy.extensions.filters.network.http_connection_manager.v3.HttpConnectionManager
          stat_prefix: https_ingress
          route_config:
            name: local_route
            virtual_hosts:
            - name: web_app
              domains: ["proxy.example.com"]
              routes:
              - match:
                  prefix: /
                route:
                  cluster: web_service
```

## Upstream mTLS Configuration

```yaml
clusters:
- name: secure_backend
  type: STRICT_DNS
  lb_policy: ROUND_ROBIN
  load_assignment:
    cluster_name: secure_backend
    endpoints:
    - lb_endpoints:
      - endpoint:
          address:
            socket_address:
              address: secure-backend.example.com
              port_value: 443
  transport_socket:
    name: envoy.transport_sockets.tls
    typed_config:
      "@type": type.googleapis.com/envoy.extensions.transport_sockets.tls.v3.UpstreamTlsContext
      sni: secure-backend.example.com  # Must match server cert CN/SAN
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
          - spiffe_id: "secure-backend.example.svc.cluster.local"
```

## SDS Secret Watch Files

### Server Certificate Secret

```yaml
# /etc/envoy/certs/server-cert.yaml
resources:
- "@type": type.googleapis.com/envoy.extensions.transport_sockets.tls.v3.Secret
  name: server_cert
  tls_certificate:
    certificate_chain:
      filename: /etc/envoy/certs/server.crt
    private_key:
      filename: /etc/envoy/certs/server.key
```

### Client Certificate Secret

```yaml
# /etc/envoy/certs/client-cert.yaml
resources:
- "@type": type.googleapis.com/envoy.extensions.transport_sockets.tls.v3.Secret
  name: client_cert
  tls_certificate:
    certificate_chain:
      filename: /etc/envoy/certs/client.crt
    private_key:
      filename: /etc/envoy/certs/client.key
```

### CA Certificate Secret (Trusted CA)

```yaml
# /etc/envoy/certs/ca-cert.yaml
resources:
- "@type": type.googleapis.com/envoy.extensions.transport_sockets.tls.v3.Secret
  name: ca_cert
  validation_context:
    trusted_ca:
      filename: /etc/envoy/certs/ca.crt
```

### SDS GenericSecret for OAuth2 (see oidc-oauth2-keycloak.md)

```yaml
# /etc/envoy/secrets/oauth-token.yaml
resources:
- "@type": type.googleapis.com/envoy.extensions.transport_sockets.tls.v3.Secret
  name: oauth_token
  generic_secret:
    secret:
      filename: /etc/envoy/secrets/oauth-token.secret
- "@type": type.googleapis.com/envoy.extensions.transport_sockets.tls.v3.Secret
  name: oauth_hmac
  generic_secret:
    secret:
      filename: /etc/envoy/secrets/oauth-hmac-secret.txt
```

## SDS Secret Rotation Workflow

```bash
# 1. Update the secret watch file (example: server cert rotation)
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

# 2. Signal Envoy for hot reload
kill -USR1 $(cat /var/run/envoy.pid)

# 3. Verify secrets were loaded
curl http://127.0.0.1:9901/config_dump?mask=secrets | jq '.configs[].dynamic_secrets[]?.name'

# 4. Verify listener status
curl http://127.0.0.1:9901/listeners?format=json | jq '.configs[].listener[].filter_chains[].transport_socket.typed_config.common_tls_context.tls_certificates[].certificate_chain.typed_config.secret_name'

# 5. Check certificate expiry with admin API
curl http://127.0.0.1:9901/certs
```

### Periodic Secret Rotation via External Process

```bash
#!/bin/bash
# Rotate certificates every 24 hours, signal Envoy after update

CERT_DIR="/etc/envoy/certs"
PID_FILE="/var/run/envoy.pid"

rotate_secrets() {
  # Generate new certs (example with openssl)
  openssl req -x509 -newkey rsa:4096 -nodes \
    -keyout "${CERT_DIR}/server.key" \
    -out "${CERT_DIR}/server.crt" \
    -days 365 \
    -subj "/CN=proxy.example.com/O=Example/C=US"

  # Update SDS secret watch file
  cat > "${CERT_DIR}/server-cert.yaml" << 'EOF'
resources:
- "@type": type.googleapis.com/envoy.extensions.transport_sockets.tls.v3.Secret
  name: server_cert
  tls_certificate:
    certificate_chain:
      filename: ${CERT_DIR}/server.crt
    private_key:
      filename: ${CERT_DIR}/server.key
EOF

  # Signal Envoy
  kill -USR1 "$(cat "${PID_FILE}")"
}

# Run in background, check every hour
while true; do
  rotate_secrets
  sleep 86400  # 24 hours
done
```

## SPIFFE/SVID Integration

### Matching SPIFFE IDs on Clients

```yaml
combined_validation_context:
  match_typed_subject_alt_names:
  - match_option:
      spiffe_id: "cluster.default.svc.cluster.local"
  validation_context:
    trusted_ca:
      sds_config:
        path: "/etc/envoy/certs/ca-cert.yaml"
```

### Matching SPIFFE IDs on Servers (Upstream)

```yaml
common_tls_context:
  validation_context:
    match_typed_subject_alt_names:
    - spiffe_id: "secure-backend.example.svc.cluster.local"
    trusted_ca:
      sds_config:
        path: "/etc/envoy/certs/ca-cert.yaml"
```

## Security Parameters Reference

| Parameter | Recommended Value | Notes |
|-----------|-------------------|-------|
| `tls_minimum_protocol_version` | `TLS_V1_2` | Block TLS 1.0/1.1 |
| `tls_maximum_protocol_version` | `TLS_V1_3` | Use TLS 1.3 when available |
| `cipher_suites` | ECDHE+AES-GCM only | No CBC, no SHA1 MAC, no RC4, no MD5 |
| `alpn_protocols` | `h2` + `http/1.1` | HTTP/2 with fallback |
| `require_client_certificate` | `true` (mTLS) | False for TLS-only termination |
| `match_typed_subject_alt_names` | Use `spiffe_id` enum | SPIFFE identity matching via MatchTypedSubjectAltNames |
| `verify_subject_alt_name` | SAN matching | Alternative to SPIFFE matching |

## Common Pitfalls

| Pitfall | Impact | Fix |
|---------|--------|-----|
| TLS config without SDS | Secrets exposed in static config | Always use SDS `sds_config` for cert rotation |
| Missing `sni` on upstream TLS | Server cert validation may fail if SNI doesn't match | Set `sni` to the expected server hostname |
| `require_client_certificate: false` without caution | Accepts both TLS and non-TLS clients | Use `require_client_certificate: true` for strict mTLS |
| Wildcard in `verify_subject_alt_name` | Too broad, validates wrong servers | Use specific SAN patterns, not `*.*` |
| Self-signed CA in production | No trust verification | Use proper CA-signed certs |
| Missing `tls_params.tls_minimum_protocol_version` | Allows weak TLS versions | Always set `TLS_V1_2` minimum |
| Wrong `secret_name` reference | Config validation passes but runtime fails | Ensure `sds_config.path` points to correct SDS file, and `name` matches |
| Admin API on `0.0.0.0` without TLS | Sensitive data exposed to network | Bind admin to `127.0.0.1`, optionally add TLS |
| No health check on upstream TLS cluster | Stale TLS errors go undetected | Add `http_health_check` or `tcp_health_check` |
| Certificate expiration | Service goes down silently | Monitor cert expiry via admin `/certs` endpoint |
| Missing `alpn_protocols` | HTTP/2 negotiation fails | Add `h2` to `alpn_protocols` for HTTP/2 support |
| SDS path not symlink-friendly | Hot reload breaks with cert tools | Use consistent path structure; avoid symlinks in SDS paths |
