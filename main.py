from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import Response, HTMLResponse
from fastapi.middleware.cors import CORSMiddleware
import sqlite3
import base64
import httpx
from datetime import datetime, timedelta
from collections import defaultdict
import time
import os

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# ──────────────────────────────────────────────
# Configuración
# ──────────────────────────────────────────────
DASHBOARD_TOKEN = os.environ.get("DASHBOARD_TOKEN", "")
DATA_DIR = "/data" if os.path.isdir("/data") else "."
DB_PATH = os.path.join(DATA_DIR, "visitas.db")

# ──────────────────────────────────────────────
# Base de datos (SQLite con WAL para concurrencia)
# ──────────────────────────────────────────────
def get_db():
    conn = sqlite3.connect(DB_PATH, timeout=10)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=5000")
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db()
    try:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS visitas (
                id         INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp  TEXT,
                ip         TEXT,
                pais       TEXT,
                ciudad     TEXT,
                referrer   TEXT,
                dispositivo TEXT,
                navegador  TEXT,
                pagina     TEXT
            )
        """)
        conn.commit()
    finally:
        conn.close()

init_db()

# ──────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────
PIXEL_GIF = base64.b64decode(
    "R0lGODlhAQABAIAAAAAAAP///yH5BAEAAAAALAAAAAABAAEAAAIBRAA7"
)

def get_real_ip(request: Request) -> str:
    """Obtiene la IP real del visitante detrás de proxies."""
    cf_ip = request.headers.get("cf-connecting-ip")
    if cf_ip:
        return cf_ip
    xff = request.headers.get("x-forwarded-for")
    if xff:
        return xff.split(",")[0].strip()
    xri = request.headers.get("x-real-ip")
    if xri:
        return xri
    return request.client.host

def parse_device(ua: str) -> str:
    ua = ua.lower()
    if "mobile" in ua or "android" in ua or "iphone" in ua:
        return "Móvil"
    if "tablet" in ua or "ipad" in ua:
        return "Tablet"
    return "Escritorio"

def parse_browser(ua: str) -> str:
    ua = ua.lower()
    if "edg" in ua:   return "Edge"
    if "chrome" in ua: return "Chrome"
    if "firefox" in ua: return "Firefox"
    if "safari" in ua: return "Safari"
    if "opera" in ua or "opr" in ua: return "Opera"
    return "Otro"

# ──────────────────────────────────────────────
# Cache de geolocalización (evita exceder 45 req/min de ip-api.com)
# ──────────────────────────────────────────────
geo_cache: dict[str, tuple[str, str]] = {}

async def get_geo(ip: str):
    if ip in geo_cache:
        return geo_cache[ip]
    try:
        async with httpx.AsyncClient(timeout=3) as client:
            r = await client.get(f"http://ip-api.com/json/{ip}?fields=country,city")
            data = r.json()
            result = (data.get("country", "Desconocido"), data.get("city", "Desconocido"))
            geo_cache[ip] = result
            return result
    except Exception:
        return "Desconocido", "Desconocido"

# ──────────────────────────────────────────────
# Rate limiting (20 req/min por IP)
# ──────────────────────────────────────────────
rate_limit_store: dict[str, list[float]] = defaultdict(list)

def is_rate_limited(ip: str, max_hits: int = 20, window: int = 60) -> bool:
    now = time.time()
    rate_limit_store[ip] = [t for t in rate_limit_store[ip] if now - t < window]
    if len(rate_limit_store[ip]) >= max_hits:
        return True
    rate_limit_store[ip].append(now)
    return False

# ──────────────────────────────────────────────
# Autenticación
# ──────────────────────────────────────────────
def check_auth(request: Request):
    """Verifica token para endpoints protegidos. Si no hay token configurado, acceso libre."""
    if not DASHBOARD_TOKEN:
        return
    token = request.query_params.get("token", "")
    if not token:
        auth_header = request.headers.get("authorization", "")
        if auth_header.startswith("Bearer "):
            token = auth_header[7:]
    if token != DASHBOARD_TOKEN:
        raise HTTPException(status_code=401, detail="No autorizado")

# ──────────────────────────────────────────────
# Helper para filtro de rango temporal
# ──────────────────────────────────────────────
def get_date_filter(range_param: str) -> str:
    """Retorna condición SQL para filtrar por rango temporal."""
    if range_param == "hoy":
        return "AND DATE(timestamp) = DATE('now')"
    elif range_param == "7d":
        return "AND DATE(timestamp) >= DATE('now', '-7 days')"
    elif range_param == "30d":
        return "AND DATE(timestamp) >= DATE('now', '-30 days')"
    return ""  # "todo" o default: sin filtro

# ──────────────────────────────────────────────
# Rutas
# ──────────────────────────────────────────────
@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/pixel")
async def pixel(request: Request, pagina: str = "principal"):
    """Endpoint que devuelve el pixel 1x1 y registra la visita."""
    ip = get_real_ip(request)
    ua = request.headers.get("user-agent", "")
    referrer = request.headers.get("referer", "Directo")

    # Solo registra si no está rate-limited (pero siempre retorna el GIF)
    if not is_rate_limited(ip):
        pais, ciudad = await get_geo(ip)
        conn = get_db()
        try:
            conn.execute(
                "INSERT INTO visitas (timestamp,ip,pais,ciudad,referrer,dispositivo,navegador,pagina) VALUES (?,?,?,?,?,?,?,?)",
                (datetime.utcnow().isoformat(), ip, pais, ciudad, referrer,
                 parse_device(ua), parse_browser(ua), pagina)
            )
            conn.commit()
        finally:
            conn.close()

    return Response(
        content=PIXEL_GIF,
        media_type="image/gif",
        headers={
            "Cache-Control": "no-store, no-cache, must-revalidate, max-age=0",
            "Pragma": "no-cache",
            "Expires": "0",
        },
    )


@app.get("/stats")
def stats(request: Request, pagina: str = "", range: str = "todo"):
    """Devuelve métricas en JSON. Filtra por artículo y/o rango temporal."""
    check_auth(request)

    date_filter = get_date_filter(range)
    page_filter = "AND pagina = ?" if pagina else ""
    params: list = []
    if pagina:
        params.append(pagina)

    def q(sql: str, extra_params: list | None = None):
        """Ejecuta query con los filtros de página y rango aplicados."""
        full_sql = sql.replace("{WHERE}", f"WHERE 1=1 {page_filter} {date_filter}")
        return conn.execute(full_sql, params + (extra_params or []))

    conn = get_db()
    try:
        total = q("SELECT COUNT(*) FROM visitas {WHERE}").fetchone()[0]
        hoy = conn.execute(
            f"SELECT COUNT(*) FROM visitas WHERE DATE(timestamp)=DATE('now') {'AND pagina = ?' if pagina else ''}",
            [pagina] if pagina else [],
        ).fetchone()[0]
        unicos = q("SELECT COUNT(DISTINCT ip) FROM visitas {WHERE}").fetchone()[0]

        paises = q(
            "SELECT pais, COUNT(*) as n FROM visitas {WHERE} GROUP BY pais ORDER BY n DESC LIMIT 8"
        ).fetchall()

        dispositivos = q(
            "SELECT dispositivo, COUNT(*) as n FROM visitas {WHERE} GROUP BY dispositivo"
        ).fetchall()

        navegadores = q(
            "SELECT navegador, COUNT(*) as n FROM visitas {WHERE} GROUP BY navegador ORDER BY n DESC LIMIT 8"
        ).fetchall()

        referrers = q(
            "SELECT referrer, COUNT(*) as n FROM visitas {WHERE} GROUP BY referrer ORDER BY n DESC LIMIT 8"
        ).fetchall()

        por_dia = q(
            "SELECT DATE(timestamp) as dia, COUNT(*) as n FROM visitas {WHERE} GROUP BY dia ORDER BY dia DESC LIMIT 14"
        ).fetchall()
    finally:
        conn.close()

    return {
        "total": total,
        "hoy": hoy,
        "unicos": unicos,
        "paises": [dict(r) for r in paises],
        "dispositivos": [dict(r) for r in dispositivos],
        "navegadores": [dict(r) for r in navegadores],
        "referrers": [dict(r) for r in referrers],
        "por_dia": [dict(r) for r in por_dia],
    }


@app.get("/pages")
def pages(request: Request):
    """Visitas agrupadas por nombre de página/artículo."""
    check_auth(request)
    conn = get_db()
    try:
        rows = conn.execute(
            "SELECT pagina, COUNT(*) as n FROM visitas GROUP BY pagina ORDER BY n DESC"
        ).fetchall()
    finally:
        conn.close()
    return [dict(r) for r in rows]


@app.get("/recent")
def recent(request: Request, pagina: str = ""):
    """Últimas 20 visitas. Filtra por artículo si se pasa ?pagina=."""
    check_auth(request)
    conn = get_db()
    try:
        if pagina:
            rows = conn.execute(
                "SELECT timestamp, pais, ciudad, dispositivo, navegador, pagina FROM visitas WHERE pagina=? ORDER BY id DESC LIMIT 20",
                (pagina,),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT timestamp, pais, ciudad, dispositivo, navegador, pagina FROM visitas ORDER BY id DESC LIMIT 20"
            ).fetchall()
    finally:
        conn.close()
    return [dict(r) for r in rows]


@app.get("/dashboard", response_class=HTMLResponse)
def dashboard(request: Request):
    """Sirve el dashboard HTML."""
    check_auth(request)
    with open("dashboard.html") as f:
        return f.read()
