from __future__ import annotations

import os
from typing import Any

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from auth import router as auth_router
from config import APP_VERSION, GEMINI_API_KEY, GEMINI_MODEL
from database import init_database
from pantry import router as pantry_router
from recipes import router as recipes_router
from saved_recipes import router as saved_recipes_router
from shopping import router as shopping_router

app = FastAPI(
    title="Mottainai Kitchen API",
    description="大学生の一人暮らし向け・節約時短レシピ提案API（Gemini API対応）",
    version=APP_VERSION,
)

origins = [origin.strip() for origin in os.getenv(
    "FRONTEND_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173"
).split(",") if origin.strip()]
app.add_middleware(
    CORSMiddleware, allow_origins=origins, allow_credentials=False,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Content-Type", "Authorization"],
)

init_database()
app.include_router(auth_router)
app.include_router(pantry_router)
app.include_router(recipes_router)
app.include_router(saved_recipes_router)
app.include_router(shopping_router)


@app.get("/api/health")
def health() -> dict[str, Any]:
    return {
        "status": "ok",
        "service": "mottainai-kitchen-api",
        "version": APP_VERSION,
        "geminiConfigured": bool(GEMINI_API_KEY),
        "model": GEMINI_MODEL if GEMINI_API_KEY else None,
    }
