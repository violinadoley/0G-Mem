"""0G Mem REST API. Run with: uvicorn api.main:app --reload --port 8000"""

import logging
import os
from contextlib import asynccontextmanager

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

load_dotenv()

from api.routes import memory, nft

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("0G Mem API starting")
    logger.info("Registry: %s", os.environ.get("MEMORY_REGISTRY_ADDRESS", "not set"))
    logger.info("NFT:      %s", os.environ.get("MEMORY_NFT_ADDRESS", "not set"))
    yield
    logger.info("0G Mem API shutting down")


app = FastAPI(
    title="0G Mem API",
    description="Verifiable, encrypted, user-owned AI memory on 0G Labs",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(memory.router)
app.include_router(nft.router)


@app.get("/")
def root():
    return {
        "name": "0G Mem API",
        "version": "0.1.0",
        "description": "Verifiable, encrypted, user-owned AI memory on 0G Labs",
        "docs": "/docs",
    }
