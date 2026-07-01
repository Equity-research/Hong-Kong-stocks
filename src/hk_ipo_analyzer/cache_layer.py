"""
港股 IPO 数据缓存层

参考: Marvae/hk-ipo-research-assistant 的缓存策略

策略：
- 短期 TTL (30min): 孖展实时数据
- 中期 TTL (24h): 当前招股列表、详情
- 长期 TTL (7d): 保荐人数据、行业分类
- 永久: 历史 IPO 记录（只增不删）
"""

from __future__ import annotations

import json
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Callable, Optional, TypeVar

T = TypeVar("T")

# TTL 常量（秒）
TTL_SHORT = 1800         # 30 分钟
TTL_MEDIUM = 86400       # 24 小时
TTL_LONG = 604800        # 7 天
TTL_PERMANENT = -1       # 永久

CACHE_DIR = Path("data/.cache")


class CacheLayer:
    """文件系统缓存，带 TTL 和原子写入"""

    def __init__(self, cache_dir: str = "data/.cache"):
        self.dir = Path(cache_dir)
        self.dir.mkdir(parents=True, exist_ok=True)

    def _path(self, key: str) -> Path:
        return self.dir / f"{key}.json"

    def get(self, key: str) -> Optional[dict]:
        """读取缓存，过期返回 None"""
        path = self._path(key)
        if not path.exists():
            return None

        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            ttl = data.get("_ttl", TTL_SHORT)
            if ttl == TTL_PERMANENT:
                return data.get("payload")
            age = time.time() - data.get("_created", 0)
            if age < ttl:
                return data.get("payload")
        except (json.JSONDecodeError, IOError):
            pass

        return None

    def set(self, key: str, payload: Any, ttl: int = TTL_SHORT) -> None:
        """原子写入缓存（先写临时文件再 rename）"""
        path = self._path(key)
        path.parent.mkdir(parents=True, exist_ok=True)

        wrapper = {
            "_created": time.time(),
            "_ttl": ttl,
            "_key": key,
            "payload": payload,
        }

        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps(wrapper, ensure_ascii=False, default=str), encoding="utf-8")
        tmp.replace(path)

    def get_or_fetch(self, key: str, fetcher: Callable[[], T], ttl: int = TTL_SHORT) -> T:
        """缓存优先：命中返回缓存，未命中调 fetcher 并缓存"""
        cached = self.get(key)
        if cached is not None:
            return cached

        data = fetcher()
        self.set(key, data, ttl)
        return data

    def clear_expired(self) -> int:
        """清理过期缓存"""
        count = 0
        now = time.time()
        for path in self.dir.glob("*.json"):
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
                ttl = data.get("_ttl", TTL_SHORT)
                if ttl != TTL_PERMANENT and (now - data.get("_created", 0)) >= ttl:
                    path.unlink()
                    count += 1
            except (json.JSONDecodeError, IOError):
                path.unlink()
                count += 1
        return count

    def stats(self) -> dict:
        """缓存统计"""
        files = list(self.dir.glob("*.json"))
        total_size = sum(f.stat().st_size for f in files)
        now = time.time()
        active = 0
        expired = 0
        for f in files:
            try:
                data = json.loads(f.read_text(encoding="utf-8"))
                ttl = data.get("_ttl", TTL_SHORT)
                if ttl == TTL_PERMANENT or (now - data.get("_created", 0)) < ttl:
                    active += 1
                else:
                    expired += 1
            except Exception:
                expired += 1
        return {
            "total_files": len(files),
            "active": active,
            "expired": expired,
            "total_size_kb": round(total_size / 1024, 1),
        }


# 全局缓存实例
cache = CacheLayer()
