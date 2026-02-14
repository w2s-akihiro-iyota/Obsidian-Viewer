---
title: コードテーマ確認用デモ
category: Sample
tags: [demo, test, syntax-highlighting]
---

# コードブロックテーマ確認用

このページは、設定「外観テーマ > コードブロックのテーマ」を変更した際の違いを確認するためのデモページです。
以下の各言語のコードブロックを見て、配色の違いを確認してください。

## JavaScript
```javascript
// コメント: JavaScriptのデモ
const greeting = "Hello, World!";
const number = 42;
const isAwesome = true;

function calculate(a, b) {
    return a + b;
}

class User {
    constructor(name) {
        this.name = name;
    }
}

console.log(`${greeting} The answer is ${calculate(20, 22)}.`);
```

## Python
```python
# コメント: Pythonのデモ
import os

def factorial(n):
    """再帰関数による階乗計算"""
    if n == 0:
        return 1
    else:
        return n * factorial(n - 1)

data = {
    "id": 1,
    "list": [1, 2, 3],
    "nested": {"key": "value"}
}

print(f"Factorial of 5 is {factorial(5)}")
```

## CSS
```css
/* コメント: CSSのデモ */
body {
    background-color: #f0f0f0;
    color: #333;
    font-family: 'Inter', sans-serif;
}

.container {
    display: flex;
    justify-content: center;
    padding: 2rem;
}

#header {
    margin-bottom: 20px;
    border-bottom: 2px solid var(--accent-color);
}
```

## HTML
```html
<!-- コメント: HTMLのデモ -->
<!DOCTYPE html>
<html lang="ja">
<head>
    <meta charset="UTF-8">
    <title>Demo Page</title>
</head>
<body>
    <div class="card">
        <h1>Title Here</h1>
        <p>This is a paragraph with <a href="#">link</a>.</p>
        <button disabled>Disabled</button>
    </div>
</body>
</html>
```

## SQL
```sql
-- コメント: SQLのデモ
SELECT u.id, u.username, COUNT(o.id) as order_count
FROM users u
LEFT JOIN orders o ON u.id = o.user_id
WHERE u.active = 1
  AND u.created_at > '2023-01-01'
GROUP BY u.id
ORDER BY order_count DESC;
```
