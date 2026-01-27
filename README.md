# EdgeFlow

**A Lightweight Framework for Distributed Edge AI Pipelines**

EdgeFlow is a distributed framework designed to easily build real-time video processing and AI inference pipelines on edge devices.

[![Version](https://img.shields.io/badge/version-0.2.0-blue.svg)](pyproject.toml)
[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![License: Apache 2.0](https://img.shields.io/badge/License-Apache_2.0-blue.svg)](LICENSE)

[🇺🇸 English](README.md) | [🇰🇷 한국어](docs/README_kr.md) | [📖 Technical Deep Dive](docs/TECHNICAL_DEEP_DIVE.md)

---

## ✨ Key Features

| Feature | Description |
|---------|-------------|
| **Arduino-Style API** | Intuitive node development with `setup()` / `loop()` pattern |
| **Fluent Wiring DSL** | Define pipelines with `sys.link(cam).to(gpu).to(gw)` chaining |
| **QoS-based Streaming** | REALTIME (latest only) / DURABLE (sequential) consumption modes |
| **Protocol Abstraction** | Auto-select Redis Stream / TCP, user code is protocol-agnostic |
| **Multi-Process Isolation** | Each node runs in separate process (GIL bypass) |
| **Kubernetes Ready** | Auto-generate K8s manifests with `edgeflow deploy` |

---

## 🚀 Quick Example

```python
from edgeflow import System, QoS
from edgeflow.comms import DualRedisBroker

# 1. Define System
sys = System("my-robot", broker=DualRedisBroker())

# 2. Register Nodes (Lazy Loading)
cam = sys.node("nodes/camera", fps=30)
gpu = sys.node("nodes/yolo", replicas=2)
gw  = sys.node("nodes/gateway")

# 3. Wire Pipeline
sys.link(cam).to(gpu, qos=QoS.REALTIME).to(gw)  # AI stream
sys.link(cam).to(gw)                             # Raw stream

# 4. Run
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

- **Producer**: Data generation (camera, sensors)
- **Consumer**: Data processing (AI inference, filtering)
- **Gateway**: External streaming (Web Dashboard, API)

---

## 📖 Documentation

| Document | Description |
|----------|-------------|
| [**Technical Deep Dive**](docs/TECHNICAL_DEEP_DIVE.md) | Core design philosophy and pattern explanations |
| [**Architecture**](docs/architecture.md) | System architecture diagrams |
| [**Performance Log**](docs/PERFORMANCE_LOG.md) | Performance optimization history |
| [**CLI Usage**](docs/cli_usage_kr.md) | CLI tool usage guide |
| [**한국어 README**](docs/README_kr.md) | Korean documentation |

---

## 🛠 Installation

```bash
# 1. Install uv
pip install uv

# 2. Install edgeflow CLI (Available globally)
uv tool install git+https://github.com/seolgugu/edgeflow.git

# 3. (Optional) For Development
git clone https://github.com/seolgugu/edgeflow.git
cd edgeflow
uv sync
```

## 🖥 CLI Usage

```bash
# Verify installation
edgeflow --help

# Deploy to Kubernetes
edgeflow deploy main.py --registry localhost:5000

# Upgrade Framework
edgeflow upgrade
```

---

## 💡 Design Highlights

### 1. `link.to()` Chaining

Express pipeline connections in a single line with Fluent Builder Pattern:

```python
sys.link(cam).to(gpu).to(gw)  # Camera → GPU → Gateway
sys.link(cam).to(logger)       # Fan-out branching
```

### 2. Handler Abstraction

Protocol auto-selection separates communication from user code:

```python
class YoloProcessor(ConsumerNode):
    def loop(self, data):
        result = self.inference(data)
        return result  # Framework handles Redis/TCP automatically
```

### 3. QoS-based Consumption

AI (REALTIME) and logging (DURABLE) coexist on the same stream:

```python
sys.link(cam).to(gpu, qos=QoS.REALTIME)    # Process latest frame only
sys.link(cam).to(logger, qos=QoS.DURABLE)  # Process all frames sequentially
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

> For details, see [Technical Deep Dive](docs/TECHNICAL_DEEP_DIVE.md).

---

## Contributing

Contributions are welcome! Please fork the repository and submit a pull request.

## License

Apache 2.0 License - see [LICENSE](LICENSE) file for details.
