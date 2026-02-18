
import yaml
from pathlib import Path
from functools import lru_cache

# キャッシュすることで毎回ファイルを開かないようにする
@lru_cache()
def get_all_messages() -> dict:
    """
    app/messages.yaml からすべてのメッセージ定義をロードします。
    """
    msg_path = Path(__file__).parent.parent / "messages.yaml"
    if not msg_path.exists():
        return {"errors": {}, "warnings": {}, "system": {}}
    
    with open(msg_path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)

def get_message(category: str, code: str, default: str = "") -> str:
    """
    指定されたカテゴリとコードに対応するメッセージを返します。
    """
    msgs = get_all_messages()
    return msgs.get(category, {}).get(code, default)

def get_error(code: str) -> str:
    return get_message("errors", code, f"Error {code}")

def get_warning(code: str) -> str:
    return get_message("warnings", code, f"Warning {code}")

def get_system(code: str) -> str:
    return get_message("system", code, f"System {code}")
