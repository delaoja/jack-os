import os
import logging
from contextlib import asynccontextmanager
from collections.abc import AsyncIterator

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

from app.api.routes import router
from app.config import settings

logger = logging.getLogger("jack_os")

@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    logger.info("Jack-OS subsystem initialized on node %s", settings.node_id)
    yield
    logger.info("Jack-OS subsystem shutdown on node %s", settings.node_id)

app = FastAPI(
    title="Jack-OS Core Engine",
    version="1.0.0",
    debug=settings.debug,
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Core API routes
app.include_router(router)

# Mount Frontend UI
ui_dir = os.path.join(os.path.dirname(__file__), "ui")
app.mount("/static", StaticFiles(directory=ui_dir), name="static")

@app.get("/")
def serve_dashboard():
    return FileResponse(os.path.join(ui_dir, "index.html"))

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app.main:app", host="127.0.0.1", port=8080, reload=True)