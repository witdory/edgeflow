# EdgeFlow

**엣지 AI 파이프라인을 위한 경량 분산 프레임워크**

EdgeFlow는 엣지 디바이스에서 실시간 비디오 처리 및 AI 추론 파이프라인을 쉽게 구축할 수 있도록 설계된 분산 프레임워크입니다.

[![Version](https://img.shields.io/badge/version-0.2.0-blue.svg)](../pyproject.toml)
[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![License: Apache 2.0](https://img.shields.io/badge/License-Apache_2.0-blue.svg)](../LICENSE)

[🇺🇸 English](../README.md) | [🇰🇷 한국어](README_kr.md) | [📖 기술 상세 문서](TECHNICAL_DEEP_DIVE.md)

---

## ✨ 주요 기능

| 기능 | 설명 |
|------|------|
| **Arduino 스타일 API** | `setup()` / `loop()` 패턴으로 직관적인 노드 개발 |
| **Fluent Wiring DSL** | `sys.link(cam).to(gpu).to(gw)` 체이닝으로 파이프라인 정의 |
| **QoS 기반 스트리밍** | REALTIME (최신만) / DURABLE (순차 처리) 소비 모드 |
| **프로토콜 추상화** | Redis Stream / TCP 자동 선택, 사용자 코드는 통신 무관 |
| **멀티프로세스 격리** | 각 노드가 별도 프로세스로 실행 (GIL 우회) |
| **Kubernetes 지원** | `edgeflow deploy`로 K8s 매니페스트 자동 생성 |

---

## 🚀 빠른 시작

```python
from edgeflow import System, QoS
from edgeflow.comms import DualRedisBroker

# 1. System 정의
sys = System("my-robot", broker=DualRedisBroker())

# 2. 노드 등록 (Lazy Loading)
cam = sys.node("nodes/camera", fps=30)
gpu = sys.node("nodes/yolo", replicas=2)
gw  = sys.node("nodes/gateway")

# 3. 파이프라인 연결
sys.link(cam).to(gpu, qos=QoS.REALTIME).to(gw)  # AI 스트림
sys.link(cam).to(gw)                             # 원본 스트림

# 4. 실행
sys.run()
```

**대시보드 접속:** http://localhost:8000/dashboard

---

## 🏗 아키텍처

```
Camera (30fps) ─┬─→ [Redis Stream] ─→ YOLO (GPU) ─→ [TCP] ─→ Gateway
                │                                              ↑
                └──────────────────── [TCP] ───────────────────┘
```

- **Producer**: 데이터 생성 (카메라, 센서)
- **Consumer**: 데이터 처리 (AI 추론, 필터링)
- **Gateway**: 외부 스트리밍 (Web Dashboard, API)

---

## 📖 문서

| 문서 | 설명 |
|------|------|
| [**기술 상세 문서**](TECHNICAL_DEEP_DIVE.md) | 핵심 설계 철학 및 디자인 패턴 해설 |
| [**아키텍처**](architecture.md) | 시스템 아키텍처 다이어그램 |
| [**성능 최적화 로그**](PERFORMANCE_LOG.md) | 성능 최적화 히스토리 |
| [**CLI 사용법**](cli_usage_kr.md) | CLI 도구 사용법 |
| [**English README**](../README.md) | 영문 문서 |

---

## 🛠 설치

```bash
# 1. uv 설치
pip install uv

# 2. edgeflow CLI 설치 (전역 사용 가능)
uv tool install git+https://github.com/seolgugu/edgeflow.git

# 3. (선택) 개발용 설치
git clone https://github.com/seolgugu/edgeflow.git
cd edgeflow
uv sync
```

## 🖥 CLI 사용법

```bash
# 설치 확인
edgeflow --help

# Kubernetes 배포
edgeflow deploy main.py --registry localhost:5000

# 프레임워크 업데이트
edgeflow upgrade
```

---

## 💡 설계 하이라이트

### 1. `link.to()` 체이닝

Fluent Builder Pattern으로 파이프라인 연결을 한 줄로 표현:

```python
sys.link(cam).to(gpu).to(gw)  # Camera → GPU → Gateway
sys.link(cam).to(logger)       # Fan-out 분기
```

### 2. Handler 추상화

통신 프로토콜을 자동 선택하여 사용자 코드에서 분리:

```python
class YoloProcessor(ConsumerNode):
    def loop(self, data):
        result = self.inference(data)
        return result  # 프레임워크가 Redis/TCP 자동 처리
```

### 3. QoS 기반 소비

동일 스트림에서 AI (REALTIME)와 로깅 (DURABLE)이 공존:

```python
sys.link(cam).to(gpu, qos=QoS.REALTIME)    # 최신 프레임만 처리
sys.link(cam).to(logger, qos=QoS.DURABLE)  # 모든 프레임 순차 처리
```

---

## 📊 기술 스택

| 계층 | 기술 |
|------|------|
| IPC | Redis Stream (Message Queue) |
| 스트리밍 | TCP + MJPEG (WebInterface) |
| 병렬 처리 | Python Multiprocessing |
| 오케스트레이션 | Kubernetes |
| 직렬화 | struct + JSON |

---

## 🎓 적용된 개념

- **디자인 패턴**: Blueprint, Template Method, Strategy, Builder, Observer
- **분산 시스템**: Message Queue, Consumer Group, Backpressure
- **네트워킹**: TCP Framing (Length-Prefix), Async I/O
- **성능 최적화**: Deduplication, Redis Pipelining

> 자세한 내용은 [기술 상세 문서](TECHNICAL_DEEP_DIVE.md)를 참조하세요.

---

## 기여하기

기여를 환영합니다! 저장소를 포크하고 Pull Request를 제출해 주세요.

## 라이선스

Apache 2.0 License - 자세한 내용은 [LICENSE](../LICENSE) 파일을 참조하세요.
