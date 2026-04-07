from fastapi import FastAPI, Request
from fastapi.responses import Response, HTMLResponse
from fastapi.middleware.cors import CORSMiddleware
import sqlite3
import base64
import httpx
from datetime import datetime
import os

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# ──────────────────────────────────────────────
# Base de datos
# Railway provee /data como volumen persistente.
# Si no existe, usamos la carpeta local.
# ──────────────────────────────────────────────
DATA_DIR = "/data" if os.path.isdir("/data") else "."
DB_PATH  = os.path.join(DATA_DIR, "visitas.db")

def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db()
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
    conn.close()

init_db()

# ──────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────
PIXEL_GIF = base64.b64decode(
    "R0lGODlhAQABAIAAAAAAAP///yH5BAEAAAAALAAAAAABAAEAAAIBRAA7"
)

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
    if "opera" in ua:  return "Opera"
    return "Otro"

async def get_geo(ip: str):
    try:
        async with httpx.AsyncClient(timeout=3) as client:
            r = await client.get(f"http://ip-api.com/json/{ip}?fields=country,city")
            data = r.json()
            return data.get("country", "Desconocido"), data.get("city", "Desconocido")
    except:
        return "Desconocido", "Desconocido"

# ──────────────────────────────────────────────
# Rutas
# ──────────────────────────────────────────────
@app.get("/pixel")
async def pixel(request: Request, pagina: str = "principal"):
    """Endpoint que devuelve el pixel 1x1 y registra la visita."""
    ip = request.client.host
    ua = request.headers.get("user-agent", "")
    referrer = request.headers.get("referer", "Directo")
    pais, ciudad = await get_geo(ip)

    conn = get_db()
    conn.execute(
        "INSERT INTO visitas (timestamp,ip,pais,ciudad,referrer,dispositivo,navegador,pagina) VALUES (?,?,?,?,?,?,?,?)",
        (datetime.utcnow().isoformat(), ip, pais, ciudad, referrer,
         parse_device(ua), parse_browser(ua), pagina)
    )
    conn.commit()
    conn.close()

    return Response(content=PIXEL_GIF, media_type="image/gif",
                    headers={"Cache-Control": "no-store"})


@app.get("/stats")
def stats():
    """Devuelve métricas en JSON para el dashboard."""
    conn = get_db()

    total = conn.execute("SELECT COUNT(*) FROM visitas").fetchone()[0]
    hoy   = conn.execute("SELECT COUNT(*) FROM visitas WHERE DATE(timestamp)=DATE('now')").fetchone()[0]

    paises = conn.execute(
        "SELECT pais, COUNT(*) as n FROM visitas GROUP BY pais ORDER BY n DESC LIMIT 8"
    ).fetchall()

    dispositivos = conn.execute(
        "SELECT dispositivo, COUNT(*) as n FROM visitas GROUP BY dispositivo"
    ).fetchall()

    referrers = conn.execute(
        "SELECT referrer, COUNT(*) as n FROM visitas GROUP BY referrer ORDER BY n DESC LIMIT 8"
    ).fetchall()

    por_dia = conn.execute(
        "SELECT DATE(timestamp) as dia, COUNT(*) as n FROM visitas GROUP BY dia ORDER BY dia DESC LIMIT 14"
    ).fetchall()

    conn.close()

    return {
        "total": total,
        "hoy": hoy,
        "paises": [dict(r) for r in paises],
        "dispositivos": [dict(r) for r in dispositivos],
        "referrers": [dict(r) for r in referrers],
        "por_dia": [dict(r) for r in por_dia],
    }


@app.get("/pages")
def pages():
    """Visitas agrupadas por nombre de página."""
    conn = get_db()
    rows = conn.execute(
        "SELECT pagina, COUNT(*) as n FROM visitas GROUP BY pagina ORDER BY n DESC"
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


@app.get("/dashboard", response_class=HTMLResponse)
def dashboard():
    """Sirve el dashboard HTML."""
    with open("dashboard.html") as f:
        return f.read()
