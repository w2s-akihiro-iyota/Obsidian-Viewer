"""APIルーター集約モジュール"""
from fastapi import APIRouter

from app.api.content import router as content_router
from app.api.sync import router as sync_router
from app.api.editor import router as editor_router

router = APIRouter()
router.include_router(content_router)
router.include_router(sync_router)
router.include_router(editor_router)
