from __future__ import annotations

import logging
import time
from urllib.parse import urlparse
from urllib.robotparser import RobotFileParser

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

LOGGER = logging.getLogger(__name__)


class RobotsDeniedError(RuntimeError):
    pass


class PoliteHttpClient:
    """带 robots.txt 校验、重试及按域名限速的 HTTP 客户端。"""

    def __init__(self, config: dict):
        self.user_agent = config["user_agent"]
        self.timeout = config.get("timeout_seconds", 30)
        self.min_interval = float(config.get("min_interval_seconds", 2.0))
        self.respect_robots = config.get("respect_robots_txt", True)
        self._last_request: dict[str, float] = {}
        self._robots: dict[str, RobotFileParser] = {}
        self.session = requests.Session()
        self.session.headers.update({"User-Agent": self.user_agent, "Accept-Language": "zh-HK,en;q=0.8"})
        retry = Retry(
            total=int(config.get("retries", 3)),
            backoff_factor=0.8,
            status_forcelist=(429, 500, 502, 503, 504),
            allowed_methods=("GET", "HEAD"),
        )
        self.session.mount("https://", HTTPAdapter(max_retries=retry))

    def _allowed(self, url: str) -> bool:
        if not self.respect_robots:
            return True
        parsed = urlparse(url)
        origin = f"{parsed.scheme}://{parsed.netloc}"
        if origin not in self._robots:
            parser = RobotFileParser(f"{origin}/robots.txt")
            try:
                response = self.session.get(parser.url, timeout=self.timeout)
                if response.status_code == 200:
                    parser.parse(response.text.splitlines())
                else:
                    LOGGER.warning("robots.txt 返回 %s，按保守策略允许普通公开页面", response.status_code)
            except requests.RequestException as exc:
                LOGGER.warning("无法读取 robots.txt：%s；按保守策略允许普通公开页面", exc)
            self._robots[origin] = parser
        parser = self._robots[origin]
        return True if not parser.mtime() else parser.can_fetch(self.user_agent, url)

    def get(self, url: str, **kwargs) -> requests.Response:
        if not self._allowed(url):
            raise RobotsDeniedError(f"robots.txt 不允许抓取：{url}")
        host = urlparse(url).netloc
        wait = self.min_interval - (time.monotonic() - self._last_request.get(host, 0.0))
        if wait > 0:
            time.sleep(wait)
        response = self.session.get(url, timeout=self.timeout, **kwargs)
        self._last_request[host] = time.monotonic()
        response.raise_for_status()
        return response
