import subprocess
import os

def build_and_push(image_tag):
    # 임시 Dockerfile 생성
    dockerfile = """
FROM python:3.9-slim
WORKDIR /app
RUN apt-get update && apt-get install -y libgl1-mesa-glx
COPY requirements.txt .
RUN pip install -r requirements.txt
# 프레임워크 자체도 설치 (개발 중엔 COPY로 대체 가능)
COPY . /app
"""
    with open("Dockerfile.temp", "w") as f:
        f.write(dockerfile)

    try:
        # Build & Push
        subprocess.run([
        "docker", "buildx", "build",
        "--platform", "linux/amd64,linux/arm64", # ⭐ 핵심: 두 아키텍처 모두 지원
        "-f", "Dockerfile.temp",
        "-t", image_tag,
        "--push", # 빌드 후 바로 푸시
        "."
    ], check=True)
    
    finally:
        if os.path.exists("Dockerfile.temp"):
            os.remove("Dockerfile.temp")