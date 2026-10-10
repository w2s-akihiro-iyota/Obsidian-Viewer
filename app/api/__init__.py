from datetime import datetime

from fastapi.templating import Jinja2Templates

from app import shortcuts
from app.config import TEMPLATES_DIR
from app.utils.messages import get_system

templates = Jinja2Templates(directory=str(TEMPLATES_DIR))
templates.env.globals["timestamp"] = int(datetime.now().timestamp())
# テンプレートから app/messages.yaml の system メッセージを引く（例: {{ system_message("S203") }}）
templates.env.globals["system_message"] = get_system
# ショートカットの定義（F-9）。ヘルプの表・チートシート・下の段のヒントは、すべてここから描く（例: shortcuts.group("tree")）
templates.env.globals["shortcuts"] = shortcuts
