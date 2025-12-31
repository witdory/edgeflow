#edgeflow/config.py
import os
from dataclasses import dataclass

@dataclass
class Config:
    # Redis 설정
    REDIS_HOST: str = os.getenv("REDIS_HOST", "localhost")
    REDIS_PORT: int = int(os.getenv("REDIS_PORT", 6379))
    REDIS_KEY: str = os.getenv("REDIS_KEY", "default")

    # Gateway 설정
    GATEWAY_HOST: str = os.getenv("GATEWAY_HOST", "localhost")
    GATEWAY_TCP_PORT: int = int(os.getenv("GATEWAY_TCP_PORT", 8080))
    GATEWAY_HTTP_PORT: int = int(os.getenv("GATEWAY_HTTP_PORT", 8000))

# 전역 설정 객체
settings = Config()