"""
NervaOS License Server - Main FastAPI Application

This server provides:
- License key generation and validation
- Hardware binding (HWID) verification
- Admin dashboard for license management
- User registration and activation
"""

import os
from datetime import datetime
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.middleware.cors import CORSMiddleware

from .api import licenses, auth, admin
from .models.database import init_db

# Get base directory
BASE_DIR = os.path.dirname(os.path.abspath(__file__))


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan - startup and shutdown"""
    # Startup
    await init_db()
    print("🚀 NervaOS License Server started")
    yield
    # Shutdown
    print("👋 NervaOS License Server shutting down")


# Create FastAPI app
app = FastAPI(
    title="NervaOS License Server",
    description="License management and activation server for NervaOS",
    version="1.0.0",
    lifespan=lifespan
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Configure for production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount static files
app.mount("/static", StaticFiles(directory=os.path.join(BASE_DIR, "static")), name="static")

# Templates
templates = Jinja2Templates(directory=os.path.join(BASE_DIR, "templates"))

# Include routers
app.include_router(auth.router, prefix="/api/auth", tags=["Authentication"])
app.include_router(licenses.router, prefix="/api/licenses", tags=["Licenses"])
app.include_router(admin.router, prefix="/api/admin", tags=["Admin"])


@app.get("/")
async def home(request: Request):
    """Home page"""
    return templates.TemplateResponse("index.html", {
        "request": request,
        "title": "NervaOS License Server"
    })


@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {
        "status": "healthy",
        "timestamp": datetime.utcnow().isoformat(),
        "version": "1.0.0"
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
