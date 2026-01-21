# EdgeFlow

**EdgeFlow** is a distributed frame processing framework based on Redis Pub/Sub. It simplifies the development of multi-node pipelines for video streaming, AI inference, and sensor fusion applications.

[![Version](https://img.shields.io/badge/version-0.1.0-orange.svg)](pyproject.toml)
[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![License: Apache 2.0](https://img.shields.io/badge/License-Apache_2.0-blue.svg)](LICENSE)
[![Kubernetes](https://img.shields.io/badge/kubernetes-ready-326ce5.svg)](https://kubernetes.io/)

[🇺🇸 English](README.md) | [🇰🇷 Korean](README_kr.md)

---

## Quick Start

### Installation

```bash
git clone https://github.com/witdory/edgeflow.git
cd edgeflow
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install -e .
```

### Local Development

Create `main.py` (see [Examples](#examples) below).

**Option 1: All-in-One Mode (Recommended)**
Runs all nodes in a single process using threading.
```bash
python main.py
```

**Option 2: Distributed Mode**
Runs each node in a separate process/terminal.
```bash
# Terminal 1
python main.py --node camera

# Terminal 2
python main.py --node gateway
```

**Access Dashboard:** http://localhost:8000/dashboard

---

## Core Concepts

EdgeFlow abstracts distributed systems into simple Python classes. You implement data processing logic, and the framework handles communication, serialization, and deployment.

### 1. Application & Decorator (`EdgeApp`)
The entry point of your system. You define nodes using the `@app.node` decorator.

```python
from edgeflow import EdgeApp, RedisBroker

app = EdgeApp("my-robot", broker=RedisBroker())

@app.node(name="camera", type="producer", fps=30)
class MyCamera(ProducerNode): ...
```
- **name**: Unique identifier for the node.
- **type**: Node role (`producer`, `consumer`, `fusion`, `gateway`).
- **kwargs**: Additional config passed to the node (e.g., `fps`, `replicas`, `device`).

### 2. Node Types & Implementation

#### ProducerNode
Generates data (e.g., reads camera, mimics sensor).
*   **Must Implement:** `produce(self)`
*   **Returns:** `numpy.ndarray`, `bytes`, or `Frame` object.
*   **Key Attributes:** `self.fps` (from decorator).

#### ConsumerNode
Processes incoming frames.
*   **Must Implement:** `process(self, data)`
*   **Input:** Raw data (payload) from the input topic.
*   **Returns:** Processed data (sent to output topic) or `None`.
*   **Configuration:** Set `self.input_topics` and `self.output_topic` in `configure()`.

#### FusionNode
Synchronizes multiple streams based on timestamps.
*   **Must Implement:** `process(self, frames)`
*   **Input:** List of frames (one from each input topic), aligned by time.
*   **Configuration:**
    *   `self.input_topics`: List of topics to sync.
    *   `self.slop`: Max allowed time difference (seconds) between frames.

#### GatewayNode
Exposes data to external systems.
*   **Configuration:** Use `self.add_interface()` to attach protocols.
*   **Built-in:** `WebInterface` (MJPEG streaming, REST API, Dashboard).

### 3. Flow Chaining (`app.link`)
Instead of hardcoding topic names inside nodes, you can explicitly define the data flow in `main.py`. This auto-configures the `input_topics` and `output_handlers` for you.

```python
# Explicitly link nodes: Camera -> Filter -> Gateway
app.link("camera").to("filter").to("gateway")
```

*   **Readable:** visualized flow of data.
*   **Flexible:** Easily re-route data without changing node code.
*   **Protocol-Aware:** Automatically handles Redis (Queue) or TCP (Direct) connections based on node types.

---

## Examples

### Complete Pipeline (`main.py`)

This real-world example demonstrates a camera stream being processed by a GPU node, and visualized via Gateway using the Link Chain API.

```python
import time
import numpy as np
import cv2
import os

from edgeflow import EdgeApp
from edgeflow.nodes import ProducerNode, ConsumerNode, GatewayNode
from edgeflow.nodes.gateway.interfaces.web import WebInterface
from edgeflow.comms import RedisBroker
from edgeflow.config import settings

# Initialize App
app = EdgeApp("test-distributed-system", broker=RedisBroker())

# 1. Producer: Fake Camera with Animation
@app.node(name="fake_camera", type="producer", device="camera", fps=30)
class FakeCamera(ProducerNode):
    def configure(self):
        self.hostname = os.getenv("HOSTNAME", "unknown-host")

    def produce(self):
        # Generate moving ball animation
        img = np.zeros((480, 640, 3), dtype=np.uint8)
        img[:] = (30, 30, 30)
        
        t = time.time()
        cx = int(320 + 200 * np.sin(t * 2))
        cy = int(240 + 100 * np.cos(t * 2))
        cv2.circle(img, (cx, cy), 30, (0, 255, 255), -1)
        
        cv2.putText(img, f"Src: {self.hostname}", (10, 30), 
                    cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2)
        return img

# 2. Consumer: GPU Processing Simulation
@app.node(name="gpu_processor", type="consumer", device="gpu", replicas=2)
class GpuProcessor(ConsumerNode):
    def configure(self):
        self.hostname = os.getenv("HOSTNAME", "unknown-host")

    def process(self, frame):
        processed_img = frame.copy()
        # Draw bounding box (Simulating Object Detection)
        cv2.rectangle(processed_img, (150, 100), (490, 380), (0, 0, 255), 3)
        cv2.putText(processed_img, "AI DETECTED", (150, 90), 
                    cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 0, 255), 2)
        return processed_img

# 3. Gateway: Web Visualization
@app.node(name="gateway", type="gateway", node_port=30080)
class VideoGateway(GatewayNode):
    def configure(self):
        web = WebInterface(port=settings.GATEWAY_HTTP_PORT)
        self.add_interface(web)

# 4. Define Flow & Run
if __name__ == "__main__":
    # Chain: Camera -> GPU -> Gateway
    app.link("fake_camera").to("gpu_processor")
    app.link("gpu_processor").to("gateway")
    
    # Direct: Camera -> Gateway (Raw View)
    app.link("fake_camera").to("gateway")
    
    app.run()
```

---

## Deployment

### Node Scheduling (Labels)
EdgeFlow determines where to deploy each node based on Kubernetes labels.
*   **Infrastructure (Redis/Gateway):** Must run on nodes labeled `edgeflow.io/role=infra`.
*   **Application Nodes:** Run on nodes matching the `device` parameter in `@app.node`.

```bash
# 1. Label Infra Node (for Redis & Gateway)
kubectl label nodes <node-name> edgeflow.io/role=infra

# 2. Label Worker Nodes (for App Nodes)
# e.g., @app.node(..., device="camera")
kubectl label nodes <node-name> edgeflow.io/device=camera

# e.g., @app.node(..., device="gpu")
kubectl label nodes <node-name> edgeflow.io/device=gpu
```

### Kubernetes (K3s, EKS, GKE)

EdgeFlow includes a CLI tool to automate Docker builds and Kubernetes manifest generation.

```bash
# 1. Deploy (Builds image -> Pushes to registry -> Applies manifests)
edgeflow deploy main.py \
  --registry docker.io/your-username \
  --namespace edgeflow

# 2. Monitor
kubectl get pods -n edgeflow

# 3. Access Dashboard
# http://<node-ip>:30080/dashboard
```

### Environment Variables
The `deploy` command automatically injects these variables:
*   `REDIS_HOST`, `REDIS_PORT`: Service discovery.
*   `GATEWAY_HOST`, `GATEWAY_TCP_PORT`: Internal communication.
*   `NODE_NAME`: Identity of the running pod.

---

## Advanced: Dual Redis Architecture

For high-throughput video applications, separating control messages from frame data improves stability.

```python
from edgeflow.comms.brokers import DualRedisBroker

# Switch to Dual Redis mode
app = EdgeApp("app", broker=DualRedisBroker())
```
*   **Control Plane:** Standard Redis (queues, smaller messages).
*   **Data Plane:** dedicated Redis instance (large frame payloads).
*   **Auto-Deploy:** The `edgeflow deploy` command detects this and automatically provisions a second Redis service (`redis-data`).
---

## Roadmap

- [ ] **SinkNode**: Data persistence and storage (Database/File).
- [ ] **Latency Tracing**: End-to-end tracking of frame travel time to identify bottlenecks.
- [ ] **Cycle Detection**: Prevent infinite loops (e.g., A -> B -> A) in flow definitions.
- [ ] **ROS2 Interface**: Native support for ROS2 bridge.
- [ ] Prometheus metrics exporter
- [ ] Edge TPU support

---

## Contributing

Contributions are welcome! Please:
1. Fork the repository
2. Create a feature branch
3. Submit a pull request with tests

---

## License

Apache 2.0 License - see [LICENSE](LICENSE) file for details.
