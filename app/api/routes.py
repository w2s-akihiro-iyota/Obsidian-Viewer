"""APIルーター集約モジュール"""
from fastapi import APIRouter

from app.api.content import router as content_router
from app.api.sync import router as sync_router
from app.api.editor import router as editor_router
from app.api.graph import router as graph_router
from app.api.dashboard import router as dashboard_router

router = APIRouter()
router.include_router(content_router)
router.include_router(sync_router)
router.include_router(editor_router)
router.include_router(graph_router)
router.include_router(dashboard_router)
