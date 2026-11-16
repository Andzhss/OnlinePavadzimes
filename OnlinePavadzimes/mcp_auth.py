"""OAuth pieteikšanās publiskajam MCP serverim (claude.ai connector).

Viena kopīga parole (PAVADZ_PASSWORD). Klienti un tokeni glabājas DATA_DIR/oauth.json,
lai pēc restarta nav jāpiesakās no jauna; autorizācijas kodi — tikai atmiņā (5 min).
"""
import asyncio
import hmac
import html
import json
import os
import secrets
import threading
import time

from starlette.requests import Request
from starlette.responses import HTMLResponse, RedirectResponse, Response

from mcp.server.auth.provider import (
    AccessToken, AuthorizationCode, AuthorizationParams, RefreshToken,
    TokenError, construct_redirect_uri,
)
from mcp.shared.auth import OAuthClientInformationFull, OAuthToken

ACCESS_TTL = 8 * 3600
REFRESH_TTL = 90 * 24 * 3600
CODE_TTL = 300
PENDING_TTL = 600


class PasswordOAuthProvider:
    def __init__(self, data_dir, password, issuer_url):
        self.path = os.path.join(data_dir, "oauth.json")
        self.password = password
        self.issuer = issuer_url.rstrip("/")
        self._lock = threading.Lock()
        self.pending = {}   # req_id -> (client_id, AuthorizationParams, created)
        self.codes = {}     # code -> AuthorizationCode
        self.db = {"clients": {}, "access": {}, "refresh": {}}
        if os.path.exists(self.path):
            with open(self.path) as f:
                self.db.update(json.load(f))

    def _save(self):
        now = time.time()
        self.db["access"] = {k: v for k, v in self.db["access"].items() if v["expires_at"] > now}
        self.db["refresh"] = {k: v for k, v in self.db["refresh"].items() if v["expires_at"] > now}
        tmp = self.path + ".tmp"
        with open(tmp, "w") as f:
            json.dump(self.db, f)
        os.chmod(tmp, 0o600)
        os.replace(tmp, self.path)

    # --- klienti -----------------------------------------------------------
    async def get_client(self, client_id):
        data = self.db["clients"].get(client_id)
        return OAuthClientInformationFull.model_validate(data) if data else None

    async def register_client(self, client_info):
        with self._lock:
            self.db["clients"][client_info.client_id] = client_info.model_dump(mode="json")
            self._save()

    # --- autorizācija ------------------------------------------------------
    async def authorize(self, client, params: AuthorizationParams):
        now = time.time()
        self.pending = {k: v for k, v in self.pending.items() if now - v[2] < PENDING_TTL}
        req_id = secrets.token_urlsafe(24)
        self.pending[req_id] = (client.client_id, params, now)
        return f"{self.issuer}/login?req={req_id}"

    async def load_authorization_code(self, client, authorization_code):
        code = self.codes.get(authorization_code)
        if code and code.client_id == client.client_id and code.expires_at > time.time():
            return code
        return None

    async def exchange_authorization_code(self, client, authorization_code):
        self.codes.pop(authorization_code.code, None)
        return self._issue(client.client_id, authorization_code.scopes, authorization_code.resource)

    async def load_refresh_token(self, client, refresh_token):
        rt = self.db["refresh"].get(refresh_token)
        if rt and rt["client_id"] == client.client_id and rt["expires_at"] > time.time():
            return RefreshToken(token=refresh_token, **rt)
        return None

    async def exchange_refresh_token(self, client, refresh_token, scopes):
        with self._lock:
            self.db["refresh"].pop(refresh_token.token, None)
        return self._issue(client.client_id, scopes or refresh_token.scopes, refresh_token.resource)

    async def load_access_token(self, token):
        at = self.db["access"].get(token)
        if at and at["expires_at"] > time.time():
            return AccessToken(token=token, **at)
        return None

    async def revoke_token(self, token):
        with self._lock:
            self.db["access"].pop(token.token, None)
            self.db["refresh"].pop(token.token, None)
            self._save()

    async def exchange_identity_assertion(self, *args, **kwargs):
        raise TokenError("unsupported_grant_type")

    def _issue(self, client_id, scopes, resource):
        access, refresh = secrets.token_urlsafe(32), secrets.token_urlsafe(32)
        now = int(time.time())
        base = {"client_id": client_id, "scopes": list(scopes or []), "resource": resource, "subject": "bratus"}
        with self._lock:
            self.db["access"][access] = dict(base, expires_at=now + ACCESS_TTL)
            self.db["refresh"][refresh] = dict(base, expires_at=now + REFRESH_TTL)
            self._save()
        return OAuthToken(access_token=access, expires_in=ACCESS_TTL, refresh_token=refresh,
                          scope=" ".join(scopes) if scopes else None)

    # --- pieteikšanās lapa -------------------------------------------------
    def _page(self, req_id, error=""):
        err = f'<p class="err">{html.escape(error)}</p>' if error else ""
        return HTMLResponse(f"""<!doctype html><html lang="lv"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>SIA Bratus — pieteikšanās</title>
<style>body{{font-family:system-ui,sans-serif;background:#f5f3ee;display:grid;place-items:center;min-height:100vh;margin:0}}
form{{background:#fff;padding:28px;width:min(340px,90vw);box-shadow:0 2px 12px #0001}}
h1{{font-size:18px;margin:0 0 6px}}p{{color:#555;font-size:14px;margin:0 0 18px}}
input{{width:100%;box-sizing:border-box;padding:10px;font-size:16px;border:1px solid #ccc;margin-bottom:12px}}
button{{width:100%;padding:10px;font-size:16px;background:#111;color:#fff;border:0;cursor:pointer}}
.err{{color:#b00020}}</style></head><body><form method="post">
<h1>SIA Bratus pavadzīmes</h1><p>Claude lūdz piekļuvi rēķinu izrakstīšanai.</p>{err}
<input type="hidden" name="req" value="{html.escape(req_id)}">
<input type="password" name="password" placeholder="Parole" autofocus required>
<button>Atļaut piekļuvi</button></form></body></html>""")

    async def login(self, request: Request) -> Response:
        if request.method == "GET":
            req_id = request.query_params.get("req", "")
            if req_id not in self.pending:
                return HTMLResponse("Pieprasījums novecojis — mēģini pieslēgt vēlreiz no Claude.", status_code=400)
            return self._page(req_id)
        form = await request.form()
        req_id = str(form.get("req", ""))
        pending = self.pending.get(req_id)
        if not pending:
            return HTMLResponse("Pieprasījums novecojis — mēģini pieslēgt vēlreiz no Claude.", status_code=400)
        if not hmac.compare_digest(str(form.get("password", "")).encode(), self.password.encode()):
            await asyncio.sleep(2)
            return self._page(req_id, "Nepareiza parole")
        del self.pending[req_id]
        client_id, params, _ = pending
        code = secrets.token_urlsafe(32)
        self.codes[code] = AuthorizationCode(
            code=code, scopes=params.scopes or [], expires_at=time.time() + CODE_TTL,
            client_id=client_id, code_challenge=params.code_challenge,
            redirect_uri=params.redirect_uri,
            redirect_uri_provided_explicitly=params.redirect_uri_provided_explicitly,
            resource=params.resource, subject="bratus",
        )
        return RedirectResponse(construct_redirect_uri(str(params.redirect_uri), code=code, state=params.state),
                                status_code=302)
