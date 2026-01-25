# EdgeFlow v0.2.0

**EdgeFlow** is a distributed frame processing framework based on Redis Pub/Sub. It simplifies the development of multi-node pipelines for video streaming, AI inference, and sensor fusion applications using an **Arduino-style pattern**.

[![Version](https://img.shields.io/badge/version-0.2.0-blue.svg)](pyproject.toml)
[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![License: Apache 2.0](https://img.shields.io/badge/License-Apache_2.0-blue.svg)](LICENSE)

[🇺🇸 English](README.md) | [🇰🇷 Korean](README_kr.md) | [🏗 Architecture](architecture.md)

---

## ⚡ Quick Start

## ⚡ Quick Start

### 1. Installation

You can install EdgeFlow using standard `pip`, but we highly recommend **[uv](https://github.com/astral-sh/uv)** for faster installation.

**Option A: Using `uv` (Recommended for speed)**
```bash
# Install framework from GitHub
uv pip install git+https://github.com/witdory/edgeflow.git
```

**Option B: Using `pip` (Standard)**
```bash
# Install framework from GitHub
pip install git+https://github.com/witdory/edgeflow.git
```

> **Note**: For Docker deployment (`edgeflow deploy`), **`uv` is automatically used inside the build container**. You don't need to configure anything special for deployment!

### 2. Run Example

We provide a specialized example project `my-robot`.

```bash
# Clone repository first if you haven't
git clone https://github.com/witdory/edgeflow.git
cd edgeflow/examples/my-robot

# Install dependencies
uv pip install -r requirements.txt  # or pip install -r requirements.txt

# Run
python main.py
```
**Access Dashboard:** http://localhost:30080/video/camera

---

## 🏗 Core Concepts (v0.2.0)

EdgeFlow v0.2.0 uses an **Arduino-style pattern** (`setup` / `loop`) for intuitive development.

### 1. Define Nodes (Class-based)

Each node is a class inheriting from `ProducerNode`, `ConsumerNode`, or `GatewayNode`. You only need to implement `setup()` and `loop()`.

**Folder Structure:**
```
nodes/
  camera/
    __init__.py
    node.toml  (Dependencies)
```

**Implementation:**
```python
# nodes/camera/__init__.py
from edgeflow.nodes import ProducerNode
import cv2

class Camera(ProducerNode):
    def setup(self):
        # Called once at startup
        self.cap = cv2.VideoCapture(0)

    def loop(self):
        # Called repeatedly (Automatic FPS control)
        ret, frame = self.cap.read()
        return frame
```

### 2. System Blueprint (`main.py`)

No huge imports! Define your system layout using lightweight paths.

```python
# main.py
from edgeflow import System

# Initialize System with Broker Config
sys = System("my-robot", broker=DualRedisBroker())

# Lazy Loading: Class is NOT imported here
cam = sys.node("nodes/camera", fps=30)
ai  = sys.node("nodes/yolo", replicas=2)
gw  = sys.node("nodes/gateway")

# Wiring: Define data flow
sys.link(cam).to(ai).to(gw)

if __name__ == "__main__":
    sys.run()
```

---

## 🚀 CLI Tools

EdgeFlow provides a powerful CLI for development and operations.

### Dependency Management
Add packages to a specific node without editing `node.toml` manually.
```bash
edgeflow add numpy --node nodes/camera
```

### Deployment (Kubernetes)
Automatically builds Docker images (using `uv`) and generates K8s manifests.
```bash
edgeflow deploy main.py --registry localhost:5000
```

### Ops
View logs from distributed nodes.
```bash
edgeflow logs camera
```

---

## 📖 Documentation

- [**CLI Usage Guide**](cli_usage_kr.md)
- [**Migration Report (v0.1 -> v0.2)**](migration_report_kr.md)
- [**Architecture Diagram**](architecture.md)

---

## Contributing

Contributions are welcome! Please fork the repository and submit a pull request.

## License

Apache 2.0 License - see [LICENSE](LICENSE) file for details.
