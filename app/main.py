import asyncio
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from app.config import STATICS_DIR
from app.api.routes import router
from app.core.indexing import refresh_global_caches
from app.services.sync import background_sync_loop

app = FastAPI(title="Obsidian Viewer")

# Mount Static Files
app.mount("/static", StaticFiles(directory=str(STATICS_DIR)), name="static")

# Include API Router
app.include_router(router)

@app.on_event("startup")
async def startup_event():
    # Initialize cache
    refresh_global_caches()
    # Start background sync
    asyncio.create_task(background_sync_loop())
