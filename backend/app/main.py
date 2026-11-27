from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from .config import FRONTEND_DIST
from .routers import analytics, applications, io, reasons

app = FastAPI(
    title="ApplyTrail",
    description="Local-first job application tracker with failure-point analytics.",
    version="0.1.0",
)

app.include_router(applications.router)
app.include_router(analytics.router)
app.include_router(io.router)
app.include_router(reasons.router)


@app.get("/api/health")
def health():
    return {"ok": True}


# Serve the built React app (``npm run build``) so daily use needs only one process.
if FRONTEND_DIST.is_dir():
    app.mount("/", StaticFiles(directory=FRONTEND_DIST, html=True), name="frontend")
