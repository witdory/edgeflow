# EdgeFlow

**A Lightweight Framework for Distributed Edge AI Pipelines**

EdgeFlow는 엣지 디바이스에서 실시간 비디오 처리 및 AI 추론 파이프라인을 쉽게 구축할 수 있도록 설계된 분산 프레임워크입니다.

[![Version](https://img.shields.io/badge/version-0.2.0-blue.svg)](pyproject.toml)
[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![License: Apache 2.0](https://img.shields.io/badge/License-Apache_2.0-blue.svg)](LICENSE)

[🇺🇸 English](README.md) | [🇰🇷 한국어](docs/README_kr.md) | [📖 Technical Deep Dive](docs/TECHNICAL_DEEP_DIVE.md)

---

## ✨ Key Features

| Feature | Description |
|---------|-------------|
| **Arduino-Style API** | `setup()` / `loop()` 패턴으로 직관적인 노드 개발 |
| **Fluent Wiring DSL** | `sys.link(cam).to(gpu).to(gw)` 체이닝으로 파이프라인 정의 |
| **QoS-based Streaming** | REALTIME (최신만) / DURABLE (순차 처리) 소비 모드 |
| **Protocol Abstraction** | Redis Stream / TCP 자동 선택, 사용자 코드는 통신 무관 |
| **Multi-Process Isolation** | 각 노드가 별도 프로세스로 실행 (GIL 우회) |
| **Kubernetes Ready** | `edgeflow deploy`로 K8s 매니페스트 자동 생성 |

---

## 🚀 Quick Example

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

**Access Dashboard:** http://localhost:8000/dashboard

---

## 🏗 Architecture

```
Camera (30fps) ─┬─→ [Redis Stream] ─→ YOLO (GPU) ─→ [TCP] ─→ Gateway
                │                                              ↑
                └──────────────────── [TCP] ───────────────────┘
```

- **Producer**: 데이터 생성 (카메라, 센서)
- **Consumer**: 데이터 처리 (AI 추론, 필터링)
- **Gateway**: 외부 스트리밍 (Web Dashboard, API)

---

## 📖 Documentation

| Document | Description |
|----------|-------------|
| [**Technical Deep Dive**](docs/TECHNICAL_DEEP_DIVE.md) | 핵심 설계 철학 및 디자인 패턴 해설 |
| [**Architecture**](docs/architecture.md) | 시스템 아키텍처 다이어그램 |
| [**Performance Log**](docs/PERFORMANCE_LOG.md) | 성능 최적화 히스토리 |
| [**CLI Usage**](docs/cli_usage_kr.md) | CLI 도구 사용법 |
| [**한국어 README**](docs/README_kr.md) | 한국어 문서 |

---

## 🛠 Installation

```bash
# Using uv (Recommended)
uv pip install git+https://github.com/witdory/edgeflow.git

# Using pip
pip install git+https://github.com/witdory/edgeflow.git
```

---

## 💡 Design Highlights

### 1. `link.to()` Chaining

파이프라인 연결을 한 줄로 표현하는 Fluent Builder Pattern:

```python
sys.link(cam).to(gpu).to(gw)  # Camera → GPU → Gateway
sys.link(cam).to(logger)       # Fan-out 분기
```

### 2. Handler Abstraction

통신 프로토콜을 자동 선택하여 사용자 코드에서 분리:

```python
class YoloProcessor(ConsumerNode):
    def loop(self, data):
        result = self.inference(data)
        return result  # 프레임워크가 Redis/TCP 자동 처리
```

### 3. QoS-based Consumption

동일 스트림에서 AI(REALTIME)와 로깅(DURABLE)이 공존:

```python
sys.link(cam).to(gpu, qos=QoS.REALTIME)  # 최신 프레임만 처리
sys.link(cam).to(logger, qos=QoS.DURABLE)  # 모든 프레임 순차 처리
```

---

## 📊 Technical Stack

| Layer | Technology |
|-------|------------|
| IPC | Redis Stream (Message Queue) |
| Streaming | TCP + MJPEG (WebInterface) |
| Parallelism | Python Multiprocessing |
| Orchestration | Kubernetes |
| Serialization | struct + JSON |

---

## 🎓 Applied Concepts

- **Design Patterns**: Blueprint, Template Method, Strategy, Builder, Observer
- **Distributed Systems**: Message Queue, Consumer Group, Backpressure
- **Networking**: TCP Framing (Length-Prefix), Async I/O
- **Performance**: Deduplication, Redis Pipelining

> 자세한 내용은 [Technical Deep Dive](docs/TECHNICAL_DEEP_DIVE.md)를 참조하세요.

---

## Contributing

Contributions are welcome! Please fork the repository and submit a pull request.

## License

Apache 2.0 License - see [LICENSE](LICENSE) file for details.
