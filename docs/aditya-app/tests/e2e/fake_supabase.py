"""Local stand-in for the parts of Supabase the app calls, backed by the REAL
local Postgres with the REAL migrations, so Row-Level Security and every
trigger is exercised exactly as in production.

Implements the subset supabase-js 2.45 uses in this app:
  /rest/v1/<table>   GET (select, eq/neq/in/gte/lte/is filters, order, limit,
                     single object via Accept), POST (insert / upsert with
                     on_conflict), PATCH (update), DELETE
  /rest/v1/rpc/<fn>  POST
  /auth/v1/token, /auth/v1/user, /auth/v1/logout
  /functions/v1/team-admin  (same behaviour as supabase/functions/team-admin)
  /storage/v1/...    upload, sign, signed download, remove (in memory)
  /app/              serves the app page, pointed at this server

TEST USE ONLY on localhost. Tokens are unsigned and passwords are kept in
memory. Never deploy this.
"""
import base64, json, re, sys, time, uuid, threading
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qsl, unquote
import psycopg
from psycopg.types.json import Jsonb

DSN = "host=/tmp port=54329 user=postgres dbname=aditya"
APP_FILE = sys.argv[2] if len(sys.argv) > 2 else "/home/claude/aditya-app/v2/index.html"
PORT = int(sys.argv[1]) if len(sys.argv) > 1 else 8765
IDENT = re.compile(r"^[a-z_][a-z0-9_]*$")
PASSWORDS = {}            # email -> (user_id, password)   test accounts only
FILES = {}                # storage path -> (bytes, content type)
LOCK = threading.Lock()


def ident(s):
    if not IDENT.match(s or ""):
        raise ApiError(400, "42601", f"bad identifier {s!r}")
    return '"' + s + '"'


class ApiError(Exception):
    def __init__(self, status, code, message):
        super().__init__(message); self.status, self.code, self.message = status, code, message


def b64(d):
    return base64.urlsafe_b64encode(json.dumps(d).encode()).rstrip(b"=").decode()


def make_token(uid, email):
    exp = int(time.time()) + 3600
    return "eyJhbGciOiJub25lIn0." + b64({"sub": uid, "email": email, "role": "authenticated", "aud": "authenticated", "exp": exp}) + ".x", exp


def token_claims(headers):
    a = headers.get("Authorization", "")
    if not a.startswith("Bearer "):
        return None
    parts = a[7:].split(".")
    if len(parts) != 3:
        return None
    try:
        c = json.loads(base64.urlsafe_b64decode(parts[1] + "=" * (-len(parts[1]) % 4)))
    except Exception:
        return None
    return c if c.get("role") == "authenticated" and c.get("exp", 0) > time.time() else None


def run_as(claims, sql, params=()):
    """One request = one transaction as 'authenticated' (or 'anon'), like PostgREST."""
    with psycopg.connect(DSN) as conn:
        with conn.cursor() as c:
            if claims:
                c.execute("set local role authenticated")
                c.execute("select set_config('request.jwt.claims', %s, true)", (json.dumps(claims),))
            else:
                c.execute("set local role anon")
            try:
                c.execute(sql, params)
                return c.fetchone()[0] if c.description else None
            except psycopg.Error as e:
                code = e.sqlstate or "XX000"
                msg = (e.diag.message_primary if e.diag else None) or str(e)
                status = 403 if code == "42501" else 409 if code == "23505" else 404 if code in ("42P01", "42883") else 400
                raise ApiError(status, code, msg)


FILTER_OPS = {"eq": "=", "neq": "<>", "gt": ">", "gte": ">=", "lt": "<", "lte": "<="}


def where_clause(qs):
    parts, params = [], []
    for k, v in qs:
        if k in ("select", "order", "limit", "offset", "on_conflict", "columns"):
            continue
        op, _, val = v.partition(".")
        col = ident(k)
        if op in FILTER_OPS:
            parts.append(f"{col} {FILTER_OPS[op]} %s"); params.append(val)
        elif op == "in":
            items = [x.strip().strip('"') for x in val.strip("()").split(",") if x.strip()]
            if not items:
                parts.append("false")
            else:
                parts.append(f"{col} in ({','.join(['%s'] * len(items))})"); params += items
        elif op == "is":
            parts.append(f"{col} is {'null' if val == 'null' else 'true' if val == 'true' else 'false'}")
        else:
            raise ApiError(400, "PGRST100", f"unsupported filter {op}")
    return (" where " + " and ".join(parts)) if parts else "", params


def select_list(qs):
    s = dict(qs).get("select", "*")
    if s.strip() == "*":
        return "*"
    return ",".join(ident(x.strip()) for x in s.split(",") if x.strip())


def order_limit(qs):
    d = dict(qs); out = ""
    if d.get("order"):
        terms = []
        for t in d["order"].split(","):
            bits = t.split(".")
            col = ident(bits[0]); dirn = "desc" if "desc" in bits[1:] else "asc"
            nulls = " nulls first" if "nullsfirst" in bits else " nulls last" if "nullslast" in bits else ""
            terms.append(f"{col} {dirn}{nulls}")
        out += " order by " + ", ".join(terms)
    if d.get("limit"):
        out += " limit " + str(int(d["limit"]))
    if d.get("offset"):
        out += " offset " + str(int(d["offset"]))
    return out


class H(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, *a):  # quiet
        pass

    def send(self, status, body=None, ctype="application/json", extra=None):
        data = b"" if body is None else (body if isinstance(body, bytes) else json.dumps(body, default=str).encode())
        self.send_response(status)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Access-Control-Allow-Origin", "*")
        for k, v in (extra or {}).items():
            self.send_header(k, v)
        self.end_headers()
        if data:
            self.wfile.write(data)

    def body(self):
        n = int(self.headers.get("Content-Length") or 0)
        return self.rfile.read(n) if n else b""

    def do_OPTIONS(self):
        self.send_response(204)
        for k, v in {"Access-Control-Allow-Origin": "*", "Access-Control-Allow-Headers": "*", "Access-Control-Allow-Methods": "*", "Content-Length": "0"}.items():
            self.send_header(k, v)
        self.end_headers()

    def handle_any(self, method):
        u = urlparse(self.path); path = u.path; qs = parse_qsl(u.query, keep_blank_values=True)
        try:
            if path in ("/app", "/app/"):
                html = open(APP_FILE, encoding="utf-8").read()
                cfg = f'<script>window.ADITYA_CONFIG={{url:location.origin,key:"local-anon-key"}};</script>\n<script src="https://cdn.jsdelivr.net'
                html = html.replace('<script src="https://cdn.jsdelivr.net', cfg, 1)
                return self.send(200, html.encode(), "text/html; charset=utf-8")
            if path.startswith("/auth/v1/"):
                return self.auth(method, path[9:], qs)
            if path.startswith("/rest/v1/rpc/"):
                return self.rpc(path[13:])
            if path.startswith("/rest/v1/"):
                return self.rest(method, path[9:], qs)
            if path.startswith("/functions/v1/team-admin"):
                return self.team_admin()
            if path.startswith("/storage/v1/"):
                return self.storage(method, path[12:], qs)
            self.send(404, {"message": "not found"})
        except ApiError as e:
            body = {"code": e.code, "message": e.message, "details": None, "hint": None}
            if path.startswith("/auth/"):
                body = {"error": "invalid_grant", "error_description": e.message, "msg": e.message, "code": e.status}
            self.send(e.status, body)
        except Exception as e:  # pragma: no cover
            self.send(500, {"message": repr(e)})

    do_GET = lambda self: self.handle_any("GET")
    do_POST = lambda self: self.handle_any("POST")
    do_PATCH = lambda self: self.handle_any("PATCH")
    do_DELETE = lambda self: self.handle_any("DELETE")
    do_PUT = lambda self: self.handle_any("PUT")

    # ---------------- auth
    def auth(self, method, sub, qs):
        if sub == "token":
            b = json.loads(self.body() or b"{}"); grant = dict(qs).get("grant_type")
            if grant == "password":
                rec = PASSWORDS.get((b.get("email") or "").lower())
                if not rec or rec[1] != b.get("password"):
                    raise ApiError(400, "invalid_credentials", "Invalid login credentials")
                uid, email = rec[0], b["email"].lower()
            elif grant == "refresh_token":
                try:
                    uid, email = b["refresh_token"].split("|", 1)
                except Exception:
                    raise ApiError(400, "bad_refresh", "Invalid Refresh Token")
            else:
                raise ApiError(400, "unsupported", "unsupported grant")
            tok, exp = make_token(uid, email)
            return self.send(200, {"access_token": tok, "token_type": "bearer", "expires_in": 3600, "expires_at": exp,
                                   "refresh_token": uid + "|" + email, "user": {"id": uid, "email": email, "aud": "authenticated", "role": "authenticated", "app_metadata": {}, "user_metadata": {}, "created_at": "2026-11-26T00:00:00Z"}})
        if sub == "user":
            c = token_claims(self.headers)
            if not c:
                raise ApiError(401, "no_auth", "invalid JWT")
            return self.send(200, {"id": c["sub"], "email": c["email"], "aud": "authenticated", "role": "authenticated", "app_metadata": {}, "user_metadata": {}})
        if sub == "logout":
            return self.send(204)
        raise ApiError(404, "nf", "not found")

    # ---------------- rest
    def rest(self, method, table, qs):
        claims = token_claims(self.headers); t = "public." + ident(table)
        want_obj = "vnd.pgrst.object" in (self.headers.get("Accept") or "")
        prefer = self.headers.get("Prefer") or ""
        cols = select_list(qs)
        if method == "GET":
            w, p = where_clause(qs)
            sql = f"select coalesce(json_agg(r), '[]'::json) from (select {cols} from {t}{w}{order_limit(qs)}) r"
            rows = run_as(claims, sql, p)
        else:
            w, p = where_clause(qs)
            if method == "DELETE":
                inner = f"delete from {t}{w} returning *"
                params = p
            else:
                payload = json.loads(self.body() or b"null")
                items = payload if isinstance(payload, list) else [payload]
                keys = sorted({k for it in items for k in it})
                if not keys:
                    raise ApiError(400, "PGRST102", "empty body")
                kl = ",".join(ident(k) for k in keys)
                if method == "POST":
                    inner = f"insert into {t} ({kl}) select {kl} from jsonb_populate_recordset(null::{t}, %s)"
                    params = [Jsonb(items)]
                    if "merge-duplicates" in prefer:
                        oc = dict(qs).get("on_conflict")
                        if not oc:
                            raise ApiError(400, "PGRST", "upsert needs on_conflict in this stand-in")
                        ocl = ",".join(ident(x) for x in oc.split(","))
                        upd = [k for k in keys if k not in oc.split(",")]
                        inner += f" on conflict ({ocl}) do " + ("update set " + ",".join(f"{ident(k)} = excluded.{ident(k)}" for k in upd) if upd else "nothing")
                    inner += " returning *"
                else:  # PATCH
                    inner = f"update {t} set ({kl}) = (select {kl} from jsonb_populate_record(null::{t}, %s)){w} returning *"
                    params = [Jsonb(items[0])] + p
            sel = cols if "return=representation" in prefer else "1"
            rows = run_as(claims, f"with r as ({inner}) select coalesce(json_agg(x), '[]'::json) from (select {sel} from r) x", params)
            if "return=representation" not in prefer:
                return self.send(204 if method != "POST" else 201)
        if want_obj:
            if len(rows) != 1:
                return self.send(406, {"code": "PGRST116", "message": "JSON object requested, multiple (or no) rows returned", "details": f"The result contains {len(rows)} rows", "hint": None})
            return self.send(200, rows[0])
        self.send(200 if method == "GET" else 201, rows)

    def rpc(self, fn):
        claims = token_claims(self.headers); args = json.loads(self.body() or b"{}")
        names = sorted(args)
        sql = f"select to_json(public.{ident(fn)}({', '.join(ident(k) + ' => %s' for k in names)}))"
        vals = []
        for k in names:
            v = args[k]
            vals.append(v if not isinstance(v, (list, dict)) else (v if isinstance(v, list) else Jsonb(v)))
        self.send(200, run_as(claims, sql, vals))

    # ---------------- edge function stand-in (mirrors supabase/functions/team-admin)
    def team_admin(self):
        claims = token_claims(self.headers)
        if not claims:
            return self.send(401, {"error": "Sign in first."})
        if not run_as(claims, "select public.is_admin()"):
            return self.send(403, {"error": "Only the owner or accountant can manage logins."})
        b = json.loads(self.body() or b"{}")
        pw = b.get("password") or ""
        if len(pw) < 8:
            return self.send(400, {"error": "Password must be at least 8 characters."})
        if b.get("action") == "create":
            email = (b.get("email") or "").lower().strip()
            if not re.match(r"^[^@\s]+@[^@\s]+\.[^@\s]+$", email):
                return self.send(400, {"error": "Enter a valid phone number or email."})
            if b.get("role") not in ("owner", "accountant", "staff"):
                return self.send(400, {"error": "Bad role."})
            with LOCK:
                if email in PASSWORDS:
                    return self.send(400, {"error": "A login with this phone/email already exists."})
                uid = str(uuid.uuid4())
                with psycopg.connect(DSN, autocommit=True) as conn:
                    conn.execute("insert into auth.users (instance_id, id, aud, role, email) values ('00000000-0000-0000-0000-000000000000', %s, 'authenticated', 'authenticated', %s)", (uid, email))
                    conn.execute("update public.profiles set full_name = %s, phone = %s, role = %s, active = true where id = %s", (b.get("full_name") or "", b.get("phone"), b["role"], uid))
                PASSWORDS[email] = (uid, pw)
            return self.send(200, {"ok": True, "user_id": uid})
        if b.get("action") == "set_password":
            with LOCK:
                for em, (uid, _) in list(PASSWORDS.items()):
                    if uid == b.get("user_id"):
                        PASSWORDS[em] = (uid, pw); return self.send(200, {"ok": True})
            return self.send(404, {"error": "Person not found."})
        self.send(400, {"error": "Unknown action."})

    # ---------------- storage (in memory, signed-in users only)
    def storage(self, method, sub, qs):
        claims = token_claims(self.headers)
        m = re.match(r"^object/sign/([^/]+)/(.+)$", sub)
        if m and method == "GET":
            f = FILES.get(m.group(1) + "/" + unquote(m.group(2)))
            return self.send(200, f[0], f[1]) if f and dict(qs).get("token") == "ok" else self.send(400, {"message": "bad signature"})
        if not claims or not run_as(claims, "select public.is_member()"):
            return self.send(403, {"statusCode": "403", "error": "Unauthorized", "message": "new row violates row-level security policy"})
        m = re.match(r"^object/sign/([^/]+)$", sub)
        if m and method == "POST":
            b = json.loads(self.body() or b"{}")
            return self.send(200, [{"path": p, "signedURL": f"/object/sign/{m.group(1)}/{p}?token=ok" if (m.group(1) + "/" + p) in FILES else None, "error": None if (m.group(1) + "/" + p) in FILES else "not found"} for p in b.get("paths", [])])
        m = re.match(r"^object/([^/]+)$", sub)
        if m and method == "DELETE":
            b = json.loads(self.body() or b"{}")
            for p in b.get("prefixes", []):
                FILES.pop(m.group(1) + "/" + p, None)
            return self.send(200, [])
        m = re.match(r"^object/([^/]+)/(.+)$", sub)
        if m and method in ("POST", "PUT"):
            key = m.group(1) + "/" + unquote(m.group(2))
            data = self.body(); ctype = self.headers.get("Content-Type") or "application/octet-stream"
            if "multipart/form-data" in ctype:  # supabase-js sends a File in a FormData body in browsers
                bnd = ctype.split("boundary=")[1].encode()
                parts = [x for x in data.split(b"--" + bnd) if b"\r\n\r\n" in x]
                part = ([x for x in parts if b"filename=" in x.split(b"\r\n\r\n", 1)[0]] or parts)[0]
                head, _, rest = part.partition(b"\r\n\r\n")
                data = rest.rsplit(b"\r\n", 1)[0]
                mt = re.search(rb"Content-Type: ([^\r\n]+)", head)
                ctype = mt.group(1).decode() if mt else "application/octet-stream"
            if key in FILES:
                return self.send(400, {"statusCode": "409", "error": "Duplicate", "message": "The resource already exists"})
            FILES[key] = (data, ctype)
            return self.send(200, {"Key": key, "Id": str(uuid.uuid4())})
        self.send(404, {"message": "not found"})


def seed_passwords():
    """Test logins are read from a local JSON file written by the test (never real passwords)."""
    import os
    p = os.environ.get("FAKE_SB_USERS")
    if p and os.path.exists(p):
        for email, (uid, pw) in json.load(open(p)).items():
            PASSWORDS[email.lower()] = (uid, pw)


if __name__ == "__main__":
    seed_passwords()
    print(f"fake supabase on http://127.0.0.1:{PORT}", flush=True)
    ThreadingHTTPServer(("127.0.0.1", PORT), H).serve_forever()
