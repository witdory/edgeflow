# EdgeFlow v0.2.0

**EdgeFlow**는 Redis Pub/Sub 기반의 분산 프레임워크입니다. **아두이노(Arduino) 스타일**의 개발 패턴을 도입하여 비디오 스트리밍, AI 추론, 센서 퓨전 등의 파이프라인을 매우 직관적으로 구축할 수 있습니다.

[![Version](https://img.shields.io/badge/version-0.2.0-blue.svg)](pyproject.toml)
[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![License: Apache 2.0](https://img.shields.io/badge/License-Apache_2.0-blue.svg)](LICENSE)

[🇺🇸 English](README.md) | [🇰🇷 Korean](README_kr.md) | [🏗 Architecture](architecture.md)

---

## ⚡ 빠른 시작 (Quick Start)

### 1. 프레임워크 설치

기본적인 `pip`으로 설치할 수 있지만, 최대 100배 빠른 **[uv](https://github.com/astral-sh/uv)** 사용을 강력 권장합니다.
(어떤 방법을 쓰셔도 사용법은 동일합니다.)

**방법 A: `uv` 사용 (속도 추천)**
```bash
# GitHub에서 최신 버전 설치
uv pip install git+https://github.com/witdory/edgeflow.git
```

**방법 B: `pip` 사용 (기본)**
```bash
# GitHub에서 최신 버전 설치
pip install git+https://github.com/witdory/edgeflow.git
```

> **참고**: `edgeflow deploy`로 Docker 배포 시에는 **자동으로 uv가 사용**되므로, 개발 환경에 uv가 없어도 배포 속도는 빠릅니다.

### 2. 예제 실행

로컬에서 바로 실행해 볼 수 있는 `my-robot` 예제를 제공합니다.

```bash
# 아직 소스 코드를 받지 않았다면
git clone https://github.com/witdory/edgeflow.git
cd edgeflow/examples/my-robot

# 예제 의존성 설치
uv pip install -r requirements.txt  # 또는 pip install ...

# 실행
python main.py
```
**대시보드 접속:** http://localhost:30080/video/camera

---

## 🏗 핵심 개념 (Core Concepts)

v0.2.0부터는 **아두이노 스타일 (`setup`, `loop`)** 패턴을 사용하여 누구나 쉽게 노드를 개발할 수 있습니다.

### 1. 노드 정의 (클래스 기반)

`ProducerNode`, `ConsumerNode`, `GatewayNode` 중 하나를 상속받고, `setup()`과 `loop()`만 구현하면 됩니다.

**폴더 구조:**
```
nodes/
  camera/
    __init__.py
    node.toml  (노드 전용 의존성 관리)
```

**구현 예시:**
```python
# nodes/camera/__init__.py
from edgeflow.nodes import ProducerNode
import cv2

class Camera(ProducerNode):
    def setup(self):
        # 초기화 (한 번만 실행)
        self.cap = cv2.VideoCapture(0)

    def loop(self):
        # 반복 실행 (FPS는 자동 제어됨)
        ret, frame = self.cap.read()
        return frame
```

### 2. 시스템 설계 (`main.py`)

복잡한 import 없이 경로 기반으로 시스템을 설계합니다. (`Lazy Loading`)

```python
# main.py
from edgeflow import System

# 시스템 초기화 (브로커 설정)
sys = System("my-robot", broker=DualRedisBroker())

# 노드 등록: 클래스를 import 하지 않고 경로만 지정
cam = sys.node("nodes/camera", fps=30)
ai  = sys.node("nodes/yolo", replicas=2)
gw  = sys.node("nodes/gateway")

# 연결 (Wiring): 데이터 흐름 정의
sys.link(cam).to(ai).to(gw)

if __name__ == "__main__":
    sys.run()
```

---

## 🚀 CLI 도구

개발부터 배포까지 터미널 명령어 하나로 해결합니다.

### 패키지 관리
`node.toml`을 직접 수정할 필요 없이 명령어로 추가하세요.
```bash
edgeflow add numpy --node nodes/camera
```

### 쿠버네티스 배포
Docker 이미지를 **uv로 초고속 빌드**하고 K8s 매니페스트를 자동 생성합니다.
```bash
edgeflow deploy main.py --registry localhost:5000
```

### 운영 및 모니터링
분산된 노드의 로그를 한곳에서 조회합니다.
```bash
edgeflow logs camera
```

---

## 📖 기술 문서

- [**CLI 사용 가이드**](cli_usage_kr.md): 명령어 상세 설명
- [**마이그레이션 기술 보고서**](migration_report_kr.md): v0.1에서 달라진 점 심층 분석
- [**아키텍처 다이어그램**](architecture.md): 내부 구조 시각화

---

## 라이선스

Apache 2.0 License - 자세한 내용은 [LICENSE](LICENSE) 파일을 참조하세요.
