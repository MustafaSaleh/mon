from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
import os

from app.routes import router
from app.database import init_db
from app.auth import init_auth_db, create_default_admin
from app.monitor import start_monitoring

app = FastAPI()

# Ensure data directory exists
os.makedirs("/app/data", exist_ok=True)

# Update database path
DATABASE_PATH = "/app/data/monitor.db"

@app.on_event("startup")
async def startup_event():
    init_db(DATABASE_PATH)
    init_auth_db(DATABASE_PATH)
    await create_default_admin()
    await start_monitoring()

@app.get("/")
async def read_root():
    return FileResponse("static/status.html")

@app.get("/api/health")
async def health_check():
    return {"status": "healthy"}

app.include_router(router, prefix="/api")
app.mount("/", StaticFiles(directory="static", html=True), name="static")

