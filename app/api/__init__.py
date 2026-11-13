from datetime import datetime

from fastapi.templating import Jinja2Templates

from app import shortcuts
from app.config import TEMPLATES_DIR
from app.core.tag_syntax import tag_href
from app.utils.messages import get_system
from app.utils.static_version import static_url, stylesheet_urls

templates = Jinja2Templates(directory=str(TEMPLATES_DIR))
templates.env.globals["timestamp"] = int(datetime.now().timestamp())
# テンプレートから app/messages.yaml の system メッセージを引く（例: {{ system_message("S203") }}）
templates.env.globals["system_message"] = get_system
# ショートカットの定義（F-9）。ヘルプの表・チートシート・下の段のヒントは、すべてここから描く（例: shortcuts.group("tree")）
templates.env.globals["shortcuts"] = shortcuts
# CSS・JS の URL に中身から作った版（?v=）を付ける（Q-5。例: {{ static_url("js/modules/core.js") }}）
templates.env.globals["static_url"] = static_url
templates.env.globals["stylesheet_urls"] = stylesheet_urls
# タグ欄のリンク（X-1。本文のタグの描画と同じ URL の作り方。例: {{ tag_href(tag) }}）
templates.env.globals["tag_href"] = tag_href
