---
title: コードブロック テーマデモ
category: Sample
tags: demo, code, theme
publish: true
---

# コードブロック テーマデモ

設定 > 外観テーマ > 「コードブロックのテーマ」から切り替えて、各コードブロックの見た目の変化を確認してください。

> [!info] 利用可能なテーマ
> GitHub Dark / GitHub Light / Dracula / Nord / Tokyo Night / Atom One Dark

---

## Python

```python
import asyncio
from dataclasses import dataclass, field
from typing import Optional

@dataclass
class User:
    """ユーザー情報を保持するデータクラス"""
    name: str
    age: int
    email: Optional[str] = None
    tags: list[str] = field(default_factory=list)

    @property
    def is_adult(self) -> bool:
        return self.age >= 18

async def fetch_users(url: str, limit: int = 100) -> list[User]:
    # TODO: 実際のAPI呼び出しに置き換え
    users = [
        User("Alice", 30, "alice@example.com", ["admin", "editor"]),
        User("Bob", 17, tags=["viewer"]),
    ]
    await asyncio.sleep(0.1)
    return [u for u in users if u.is_adult][:limit]

if __name__ == "__main__":
    result = asyncio.run(fetch_users("https://api.example.com/users"))
    for user in result:
        print(f"{user.name} ({user.age}) - {user.email or 'N/A'}")
```

## JavaScript / TypeScript

```javascript
class EventEmitter {
  #listeners = new Map();

  on(event, callback) {
    if (!this.#listeners.has(event)) {
      this.#listeners.set(event, []);
    }
    this.#listeners.get(event).push(callback);
    return () => this.off(event, callback); // unsubscribe
  }

  off(event, callback) {
    const cbs = this.#listeners.get(event) ?? [];
    this.#listeners.set(event, cbs.filter(cb => cb !== callback));
  }

  emit(event, ...args) {
    for (const cb of this.#listeners.get(event) ?? []) {
      cb(...args);
    }
  }
}

// 使用例
const bus = new EventEmitter();
const unsub = bus.on("message", (text) => {
  console.log(`Received: ${text}`);
});
bus.emit("message", "Hello, World!"); // => Received: Hello, World!
unsub();
```

## HTML / CSS

```html
<!DOCTYPE html>
<html lang="ja">
<head>
  <meta charset="UTF-8">
  <title>テーマデモ</title>
  <style>
    :root {
      --primary: #6c5ce7;
      --bg: #1a1a2e;
      --text: #eaeaea;
    }
    body {
      background: var(--bg);
      color: var(--text);
      font-family: 'Inter', sans-serif;
      margin: 0;
      display: grid;
      place-items: center;
      min-height: 100vh;
    }
    .card {
      background: rgba(255, 255, 255, 0.05);
      border: 1px solid rgba(255, 255, 255, 0.1);
      border-radius: 12px;
      padding: 2rem;
      backdrop-filter: blur(10px);
    }
    .card h1 { color: var(--primary); }
  </style>
</head>
<body>
  <div class="card">
    <h1>Hello</h1>
    <p>テーマプレビュー用のカードです。</p>
  </div>
</body>
</html>
```

## Rust

```rust
use std::collections::HashMap;

#[derive(Debug, Clone)]
struct Config {
    name: String,
    values: HashMap<String, f64>,
    enabled: bool,
}

impl Config {
    fn new(name: &str) -> Self {
        Self {
            name: name.to_string(),
            values: HashMap::new(),
            enabled: true,
        }
    }

    fn get(&self, key: &str) -> Option<f64> {
        self.values.get(key).copied()
    }
}

fn main() {
    let mut config = Config::new("production");
    config.values.insert("timeout".into(), 30.0);
    config.values.insert("max_retries".into(), 3.0);

    if let Some(timeout) = config.get("timeout") {
        println!("Timeout: {:.1}s", timeout);
    }

    let items: Vec<i32> = (1..=10)
        .filter(|x| x % 2 == 0)
        .map(|x| x * x)
        .collect();

    println!("{:?}", items); // [4, 16, 36, 64, 100]
}
```

## SQL

```sql
WITH monthly_sales AS (
    SELECT
        DATE_TRUNC('month', order_date) AS month,
        category,
        SUM(amount) AS total,
        COUNT(DISTINCT customer_id) AS customers
    FROM orders
    WHERE order_date >= '2025-01-01'
      AND status != 'cancelled'
    GROUP BY 1, 2
)
SELECT
    month,
    category,
    total,
    customers,
    ROUND(total / NULLIF(customers, 0), 2) AS avg_per_customer,
    LAG(total) OVER (PARTITION BY category ORDER BY month) AS prev_month
FROM monthly_sales
ORDER BY month DESC, total DESC
LIMIT 50;
```

## JSON / YAML

```json
{
  "app": {
    "name": "obsidian-viewer",
    "version": "2.1.0",
    "features": ["markdown", "mermaid", "katex"],
    "config": {
      "port": 8000,
      "debug": false,
      "cache_ttl": 3600,
      "allowed_origins": ["https://example.com"]
    }
  }
}
```

## Bash

```bash
#!/bin/bash
set -euo pipefail

readonly LOG_FILE="/var/log/deploy.log"
readonly MAX_RETRIES=3

log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*" | tee -a "$LOG_FILE"
}

deploy() {
    local env="${1:?Environment required}"
    local version="${2:-latest}"

    log "Deploying v${version} to ${env}..."

    for i in $(seq 1 "$MAX_RETRIES"); do
        if docker pull "myapp:${version}" 2>/dev/null; then
            docker-compose -f "docker-compose.${env}.yml" up -d
            log "Deploy successful (attempt ${i})"
            return 0
        fi
        log "Attempt ${i}/${MAX_RETRIES} failed, retrying..."
        sleep $((i * 5))
    done

    log "ERROR: Deploy failed after ${MAX_RETRIES} attempts"
    return 1
}

deploy "$@"
```
