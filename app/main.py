import asyncio
import logging

from app.logging_config import setup_logging
setup_logging()

logger = logging.getLogger("app.main")

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
    logger.info("Obsidian Viewer starting up")
    # Initialize cache in a thread to avoid blocking startup
    loop = asyncio.get_event_loop()
    loop.run_in_executor(None, refresh_global_caches)
    # Start background sync
    asyncio.create_task(background_sync_loop())
