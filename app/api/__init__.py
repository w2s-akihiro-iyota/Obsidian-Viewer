from datetime import datetime

from fastapi.templating import Jinja2Templates

from app.config import TEMPLATES_DIR

templates = Jinja2Templates(directory=str(TEMPLATES_DIR))
templates.env.globals["timestamp"] = int(datetime.now().timestamp())
