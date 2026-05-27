# OIDC / OAuth2 / Keycloak Patterns (v1.38.0)

Complete reference for all three authentication integration patterns with Keycloak, plus filter ordering guidance.

## Filter Ordering (Critical)

The correct ordering of HTTP filters from first to last:

```
oauth2 (browser SSO)
→ jwt_authn (JWT validation)
→ rbac (access control)
→ wasm (custom WASM plugin)
→ ext_authz (external auth, optional)
→ local_ratelimit (rate limiting)
→ cors (CORS preflight handling)
→ header_mutation (header manipulation)
→ health_check (health check passthrough)
→ lua (scripting)
→ router (final forwarding)
```

**Rules:**
- `router` must always be last.
- `oauth2` must come before `jwt_authn` — OAuth2 sets cookies that JWT validation reads.
- `jwt_authn` before `rbac` — RBAC rules should check decoded JWT claims.
- `ext_authz` before `local_ratelimit` — Auth decision precedes rate limit.
- Never place `cors` before `ext_authz` — OPTIONS preflight bypasses auth.

## Keycloak URL Patterns

| Endpoint | Keycloak URL Pattern | Description |
|----------|---------------------|-------------|
| Discovery | `https://keycloak.example.com/realms/{realm}/.well-known/openid-configuration` | OIDC provider metadata |
| Authorization | `https://keycloak.example.com/realms/{realm}/protocol/openid-connect/auth` | OAuth2 authorization endpoint |
| Token | `https://keycloak.example.com/realms/{realm}/protocol/openid-connect/token` | Token issuance endpoint |
| JWKS | `https://keycloak.example.com/realms/{realm}/protocol/openid-connect/certs` | Public key set for JWT verification |
| Userinfo | `https://keycloak.example.com/realms/{realm}/protocol/openid-connect/userinfo` | User info endpoint |
| Logout | `https://keycloak.example.com/realms/{realm}/protocol/openid-connect/logout` | Logout redirect endpoint |
| Introspect | `https://keycloak.example.com/realms/{realm}/protocol/openid-connect/token/introspect` | Token introspection |

**Realm URL:** `https://keycloak.example.com/realms/{realm}`

Replace `{realm}` with your realm name (default: `master` for admin, or a custom realm like `production`).

---

## Pattern A — Native OAuth2 Filter (Browser SSO)

### Purpose
Handles browser-based single sign-on via OAuth2 authorization code flow.

### OAuth2 Filter Configuration

```yaml
http_filters:
- name: envoy.filters.http.oauth2
  typed_config:
    "@type": type.googleapis.com/envoy.extensions.filters.http.oauth2.v3.OAuth2
    token_endpoint:
      cluster: oauth_service
      uri: "https://keycloak.example.com/realms/myrealm/protocol/openid-connect/token"
      timeout: 3s
    authorization_endpoint: "https://keycloak.example.com/realms/myrealm/protocol/openid-connect/auth"
    redirect_uri: "%REQ(x-forwarded-proto)%://%REQ(:authority)%/callback"
    redirect_path_matcher:
      path:
        exact: /callback
    signout_path:
      path:
        exact: /signout
    pass_through_matcher:
      header_matcher:
        exact_match: "public"
        name: x-auth-mode
    forward_bearer_token: true
    auth_scopes: ["openid", "profile", "email"]
    credentials:
      client_id: "envoy-proxy"
      token_secret:
        name: oauth_token
        sds_config:
          path: "/etc/envoy/secrets/oauth-token.yaml"
      hmac_secret:
        name: oauth_hmac
        sds_config:
          path: "/etc/envoy/secrets/oauth-hmac.yaml"
    use_refresh_token: true
    cookie_names:
      bearer_token: "OAuth2_BearerToken"
      hmac: "OAuth2_HMAC"
      expires: "OAuth2_Expires"
      id_token: "OAuth2_IdToken"
      refresh_token: "OAuth2_RefreshToken"
    deny_redirect_matcher:
      header_matcher:
        regex_match: "X-Requested-With:.*XMLHttpRequest|application/json"
        name: x-requested-with
```

### SDS Secrets for OAuth2

OAuth2 filter needs two secrets via SDS:
1. **token_secret** — `GenericSecret` containing the OAuth2 client secret
2. **hmac_secret** — `GenericSecret` for HMAC-encoding OAuth2 cookies

Both are served from a single SDS watch file:

```yaml
# /etc/envoy/secrets/oauth-secrets.yaml
resources:
- "@type": type.googleapis.com/envoy.extensions.transport_sockets.tls.v3.Secret
  name: oauth_token
  generic_secret:
    secret:
      filename: "/etc/envoy/secrets/oauth-client-secret.txt"  # OAuth2 client secret
- "@type": type.googleapis.com/envoy.extensions.transport_sockets.tls.v3.Secret
  name: oauth_hmac
  generic_secret:
    secret:
      filename: "/etc/envoy/secrets/oauth-hmac-secret.txt"    # HMAC key, 16+ bytes
```

### Route Config for OAuth2

```yaml
route_config:
  name: main_route
  virtual_hosts:
  - name: web_app
    domains: ["proxy.example.com"]
    routes:
    - match:
        path: /callback
      route:
        cluster: oauth_service
        timeout: 3s
      # Per-route: disable OAuth2 on callback
      typed_per_filter_config:
        type.googleapis.com/envoy.extensions.filters.http.oauth2.v3.OAuth2PerRoute:
          disabled: true

    - match:
        path: /signout
      direct_response:
        status: 302
        headers:
        - header:
            key: Location
            value: "https://keycloak.example.com/realms/myrealm/protocol/openid-connect/logout?redirect_uri=https://proxy.example.com/"
      typed_per_filter_config:
        type.googleapis.com/envoy.extensions.filters.http.oauth2.v3.OAuth2PerRoute:
          disabled: true

    - match:
        prefix: /
      route:
        cluster: web_service
        timeout: 30s
```

### SDS GenericSecret Pattern for OAuth2

OAuth2 filter needs two secrets via SDS:
1. **token_secret** — `GenericSecret` containing the OAuth2 client secret
2. **hmac_secret** — `GenericSecret` for HMAC-encoding OAuth2 cookies

```yaml
# /etc/envoy/secrets/generic-secret.yaml
resources:
- "@type": type.googleapis.com/envoy.extensions.transport_sockets.tls.v3.Secret
  name: oauth_token
  generic_secret:
    secret:
      filename: "/etc/envoy/secrets/oauth-client-secret.txt"  # OAuth2 client secret
- "@type": type.googleapis.com/envoy.extensions.transport_sockets.tls.v3.Secret
  name: oauth_hmac
  generic_secret:
    secret:
      filename: "/etc/envoy/secrets/oauth-hmac-secret.txt"    # Arbitrary string, 16+ bytes recommended
```

### Public Routes (pass_through_matcher)

```yaml
routes:
- match:
    prefix: /public/
    headers:
    - name: x-auth-mode
      exact_match: "public"
  route:
    cluster: public_service
  typed_per_filter_config:
    type.googleapis.com/envoy.extensions.filters.http.oauth2.v3.OAuth2PerRoute:
      disabled: true
    type.googleapis.com/envoy.extensions.filters.http.jwt_authn.v3.JwtAuthenticationPerRoute:
      disabled: true
```

---

## Pattern B — JWT Validation Only (API-to-API)

### Purpose
Validates JWT tokens for service-to-service authentication (no browser session management).

### JWT Filter Configuration

```yaml
http_filters:
- name: envoy.filters.http.jwt_authn
  typed_config:
    "@type": type.googleapis.com/envoy.extensions.filters.http.jwt_authn.v3.JwtAuthentication
    providers:
      keycloak_provider:
        issuer: "https://keycloak.example.com/realms/myrealm"
        audiences:
        - "envoy-proxy"
        - "backend-service"
        remote_jwks:
          http_uri:
            uri: "https://keycloak.example.com/realms/myrealm/protocol/openid-connect/certs"
            timeout: 5s
            cluster: keycloak_jwks
          cache_duration: 300s
          overlapping_unit: 60s
        from_headers:
        - name: "Authorization"
          value_prefix: "Bearer "
        from_params:
        - name: "access_token"
        from_cookies:
        - name: "jwt_token"
        claim_to_headers:
        - key: "x-subject"
          claim: "sub"
          format: "Bearer %s"
        - key: "x-email"
          claim: "email"
        - key: "x-audience"
          claim: "aud"
        - key: "x-realm-access-roles"
          claim: "realm_access.roles"
          format: "%s"
    rules:
    # Public API: no JWT required
    - match:
        prefix: /public/
      requires: ""  # Empty = no JWT required

    # Authenticated API: JWT required
    - match:
        prefix: /api/
      requires: "valid-jwt"

    # Admin API: JWT required + specific role
    - match:
        prefix: /admin/
      requires_any:
        requirements:
        - "valid-jwt"
        - "admin-role"

    - match:
        path: /api/internal
        headers:
        - name: x-forwarded-for
          prefix_match: "10.0.0."
      requires_any:
        requirements:
        - "valid-jwt"
        - "internal-network"

    requires:
      valid-jwt:
        provider_name: keycloak_provider
        forward: true
        forward_payload_header: "x-forwarded-jwt-payload"
      admin-role:
        provider_name: keycloak_provider
        require_audience: "admin-service"
        require_claims:
        - key: "realm_access.roles"
          string_values: ["admin"]
        forward: true
      internal-network:
        provider_name: keycloak_provider
        forward: false
```

### Per-Route JWT Override

```yaml
- match:
    path: /api/health
  route:
    cluster: backend_service
  typed_per_filter_config:
    type.googleapis.com/envoy.extensions.filters.http.jwt_authn.v3.JwtAuthenticationPerRoute:
      disabled: true
```

### JWT Security Notes

| Setting | Recommendation |
|---------|---------------|
| `remote_jwks.cache_duration` | 300s (5 min) — balance between freshness and performance |
| `remote_jwks.overlapping_unit` | 60s — overlap window for JWKS rotation |
| `from_headers.value_prefix` | "Bearer " (with trailing space) |
| `forward` | true — forward original token to upstream |
| `forward_payload_header` | Use non-standard header to avoid confusion |

---

## Pattern C — ExtAuthz with oauth2-proxy Sidecar

### Purpose
Offload OIDC authentication to a sidecar `oauth2-proxy` (backed by Keycloak), letting ExtAuthz handle the auth decision.

### ExtAuthz Configuration

```yaml
http_filters:
- name: envoy.filters.http.ext_authz
  typed_config:
    "@type": type.googleapis.com/envoy.extensions.filters.http.ext_authz.v3.ExtAuthz
    http_service:
      server_uri:
        cluster: oauth2_proxy
        uri: /api/auth
        port_value: 4180
      authorization_request:
        allowed_headers:
        - "authorization"
        - "cookie"
        - "x-forwarded-for"
        - "x-forwarded-proto"
        - "x-forwarded-host"
        - "x-forwarded-port"
        - "x-request-id"
        allowed_upstream_headers:
        - "Location"
        - "Set-Cookie"
        - "X-Auth-Request-Redirect"
        - "X-Auth-Request-User"
        - "X-Auth-Request-Email"
        - "X-Auth-Request-Groups"
      failure_mode_allow: false  # ← Deny if proxy is down
    transport_api_version: V3
```

### oauth2-proxy Configuration (Keycloak Backend)

```bash
# Typical oauth2-proxy flags for Keycloak
oauth2-proxy \
  --provider="keycloak-oidc" \
  --email-domain="example.com" \
  --upstream="http://127.0.0.1:8080" \
  --http-address="0.0.0.0:4180" \
  --skip-jwt-access-tokens \
  --set-xauthrequest="true" \
  --set-authorization-header="true" \
  --cookie-secret="$(cat /etc/oauth2-proxy/secret.txt)" \
  --client-id="envoy-proxy" \
  --client-secret="$(cat /etc/oauth2-proxy/client-secret.txt)" \
  --cookie-domain=".proxy.example.com" \
  --cookie-samesite="lax" \
  --cookie-secure="true" \
  --oidc-issuer-url="https://keycloak.example.com/realms/myrealm" \
  --insecure-oauth2-endpoint \
  --redirect-url="https://proxy.example.com/callback" \
  --whitelist-domain=".proxy.example.com" \
  --pass-basic-auth="false" \
  --pass-user-headers \
  --passes-all-headers \
  --request_logging \
  --request-logging-enable \
  --debug
```

### OAuth2-Proxy Sidecar Cluster

```yaml
- name: oauth2_proxy
  type: STRICT_DNS
  lb_policy: ROUND_ROBIN
  load_assignment:
    cluster_name: oauth2_proxy
    endpoints:
    - lb_endpoints:
      - endpoint:
          address:
            socket_address:
              address: oauth2-proxy
              port_value: 4180
```

---

## Complete Filter Chain Example (OAuth2 + JWT + RBAC)

```yaml
http_filters:
# 1. OAuth2 — browser SSO
- name: envoy.filters.http.oauth2
  typed_config:
    "@type": type.googleapis.com/envoy.extensions.filters.http.oauth2.v3.OAuth2
    # ... (as shown in Pattern A)

# 2. JWT — API auth
- name: envoy.filters.http.jwt_authn
  typed_config:
    "@type": type.googleapis.com/envoy.extensions.filters.http.jwt_authn.v3.JwtAuthentication
    # ... (as shown in Pattern B)

# 3. RBAC — IP + role-based access
- name: envoy.filters.http.rbac
  typed_config:
    "@type": type.googleapis.com/envoy.extensions.filters.http.rbac.v3.RBAC
    rules:
      allow_admin:
        action: ALLOW
        policies:
          admin-policy:
            permission:
              and_rules:
                rules:
                - header:
                    name: "x-forwarded-for"
                    prefix_match: "10.0.0."
                - header:
                    name: "x-admin"
                    exact_match: "true"
            principal:
              authenticated:
                principal_name:
                  exact_match: "cluster.local/ns/default/sa/admin-sa"
      deny_external:
        action: DENY
        policies:
          deny-external-admin:
            permission:
              header:
                name: "x-admin"
                exact_match: "true"
            principal:
              not_principal:
                authenticated:
                  principal_name:
                    regex_match: "cluster\\.local/ns/default/sa.*"

# 4. CORS
- name: envoy.filters.http.cors
  typed_config:
    "@type": type.googleapis.com/envoy.extensions.filters.http.cors.v3.Cors
    allow_origin_string_match:
    - prefix: "https://app.example.com"
    allow_methods: "GET, POST, PUT, DELETE, OPTIONS, PATCH"
    allow_headers: "authorization, content-type, x-request-id, x-forwarded-for"
    expose_headers: "x-request-id, x-auth-user"
    max_age: "3600"
    supports_credentials: true

# 5. Router (last)
- name: envoy.filters.http.router
  typed_config:
    "@type": type.googleapis.com/envoy.extensions.filters.http.router.v3.Router
```

---

## Keycloak Configuration Checklist

| Setting | Required Value | Notes |
|---------|---------------|-------|
| Client Type | `openid-connect` | Standard OIDC client |
| Access Type | `confidential` | For OAuth2 auth code flow |
| Root URL | `https://proxy.example.com/*` | Must match proxy domain |
| Valid Redirect URIs | `https://proxy.example.com/callback` | OAuth2 callback URL |
| Web Origins | `https://proxy.example.com` | CORS origins |
| Logout URL | `https://proxy.example.com/signout` | Logout redirect |
| Service Accounts | `ENABLED` (if using machine-to-machine) | For service account flow |
| Standard Flow | `ENABLED` | Authorization code flow |
| Direct Access Grants | `DISABLED` (unless needed) | Resource Owner flow |
| Client Credentials | `ENABLED` (if needed) | For machine-to-machine |

---

## Common Pitfalls

| Pitfall | Impact | Fix |
|---------|--------|-----|
| Wrong Keycloak realm URL | Auth flow fails with 401/404 | Use `/realms/{realm}/protocol/openid-connect/...` format |
| Missing `hmac_secret` in OAuth2 filter | Cookies can't be set/verified | Configure both `token_secret` and `hmac_secret` via SDS |
| `pass_through_matcher` not set on public routes | Public routes go through OAuth flow | Use `pass_through_matcher` or per-route `OAuth2PerRoute: {disabled: true}` |
| `redirect_uri` scheme mismatch (http vs https) | Keycloak rejects callback | Use `%REQ(x-forwarded-proto)%` for correct scheme from TLS terminator |
| Missing `tls_minimum_protocol_version` | Weak TLS allowed | Set `TLS_V1_2` minimum |
| CORS before ext_authz on same listener | OPTIONS requests bypass auth | Place CORS after ext_authz or use `filter_enabled` on OPTIONS routes |
| `failure_mode_allow: false` with single oauth2-proxy | Total auth failure on proxy restart | Add multiple replicas behind a load balancer |
| jwt_authn `from_params` enabled on production | JWT in URL (bookmarks, logs) | Use `from_headers` only for production; `from_params` for debugging |
| JWT `issuer` not matching Keycloak | All JWT validation fails | Set `issuer: "https://keycloak.example.com/realms/myrealm"` exactly |
| Missing `audiences` in jwt_authn | Token accepted without audience check | Always configure `audiences` list |
| Redundant JWT validation + OAuth2 | Requests validated twice | Disable JWT validation on routes covered by OAuth2 cookie |
| Keycloak client secret as plain text in config | Secret exposure risk | Always use SDS `GenericSecret` — never inline |
