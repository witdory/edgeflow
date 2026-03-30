"""ROS2-backed Broker implementation for native ROS deployments."""
from __future__ import annotations

import os
import threading
import time
from collections import deque
from typing import Any, Deque, Dict, Optional

from .base import BrokerInterface


class ROSBroker(BrokerInterface):
    """
    BrokerInterface implementation using ROS2 topics.

    Notes:
    - Payload transport type is std_msgs/msg/ByteMultiArray.
    - Incoming messages are buffered per topic to support pop/pop_latest.
    - If rclpy is unavailable, constructor raises RuntimeError.
    """

    def __init__(
        self,
        node_name: str = "edgeflow_ros_broker",
        namespace: str = "",
        qos_depth: int = 100,
        spin_thread: bool = True,
        max_queue_size: int = 100,
        topic_prefix: str = "",
    ):
        # K3s/Kubernetes 환경에서는 네임스페이스 기반 분리를 기본값으로 사용
        if not namespace:
            namespace = os.getenv("EDGEFLOW_ROS_NAMESPACE", os.getenv("POD_NAMESPACE", "")).strip()

        self.node_name = node_name
        self.namespace = namespace
        self.qos_depth = qos_depth
        self.spin_thread = spin_thread
        self.max_queue_size = max_queue_size
        self.topic_prefix = topic_prefix.strip("/")

        self._buffers: Dict[str, Deque[bytes]] = {}
        self._limits: Dict[str, int] = {}
        self._publishers: Dict[str, Any] = {}
        self._subscriptions: Dict[str, Any] = {}
        self._lock = threading.Lock()
        self._cv = threading.Condition(self._lock)

        try:
            import rclpy
            from rclpy.executors import MultiThreadedExecutor
            from rclpy.qos import HistoryPolicy, QoSProfile, ReliabilityPolicy
            from std_msgs.msg import ByteMultiArray
        except Exception as exc:
            raise RuntimeError(
                "ROSBroker requires ROS2 Python packages (rclpy, std_msgs)."
            ) from exc

        self._rclpy = rclpy
        self._ByteMultiArray = ByteMultiArray
        self._qos = QoSProfile(
            depth=self.qos_depth,
            reliability=ReliabilityPolicy.RELIABLE,
            history=HistoryPolicy.KEEP_LAST,
        )

        if not self._rclpy.ok():
            self._rclpy.init(args=None)

        self._node = self._rclpy.create_node(self.node_name, namespace=self.namespace)
        self._executor = MultiThreadedExecutor()
        self._executor.add_node(self._node)

        self._spin_stop = threading.Event()
        self._spin_worker: Optional[threading.Thread] = None

        if self.spin_thread:
            self._spin_worker = threading.Thread(target=self._spin_loop, daemon=True)
            self._spin_worker.start()

    def _spin_loop(self):
        while not self._spin_stop.is_set() and self._rclpy.ok():
            self._executor.spin_once(timeout_sec=0.1)

    def _ensure_topic(self, topic: str):
        if topic not in self._buffers:
            self._buffers[topic] = deque(maxlen=self._limits.get(topic, self.max_queue_size))

    def _resolve_topic(self, topic: str) -> str:
        normalized = topic.strip("/")
        if self.topic_prefix:
            normalized = f"{self.topic_prefix}/{normalized}"
        return f"/{normalized}"

    def _ensure_publisher(self, topic: str):
        ros_topic = self._resolve_topic(topic)
        if ros_topic in self._publishers:
            return
        self._publishers[ros_topic] = self._node.create_publisher(
            self._ByteMultiArray,
            ros_topic,
            self._qos,
        )

    def _ensure_subscription(self, topic: str):
        ros_topic = self._resolve_topic(topic)
        if ros_topic in self._subscriptions:
            return

        def _callback(msg):
            payload = bytes(msg.data)
            with self._cv:
                self._ensure_topic(topic)
                self._buffers[topic].append(payload)
                self._cv.notify_all()

        self._subscriptions[ros_topic] = self._node.create_subscription(
            self._ByteMultiArray,
            ros_topic,
            _callback,
            self._qos,
        )

    def _spin_once_if_needed(self, timeout: float):
        if not self.spin_thread:
            self._executor.spin_once(timeout_sec=max(0.0, timeout))

    def push(self, topic: str, data: bytes):
        if not isinstance(data, (bytes, bytearray)):
            raise TypeError("ROSBroker.push expects bytes-like payload")

        self._ensure_publisher(topic)
        msg = self._ByteMultiArray()
        msg.data = list(data)
        self._publishers[self._resolve_topic(topic)].publish(msg)

    def pop(self, topic: str, timeout: int = 0, **kwargs) -> bytes | None:
        self._ensure_subscription(topic)
        deadline = time.time() + max(0, timeout)

        with self._cv:
            self._ensure_topic(topic)
            while True:
                if self._buffers[topic]:
                    return self._buffers[topic].popleft()

                remaining = deadline - time.time()
                if timeout <= 0 or remaining <= 0:
                    return None

                wait_for = min(0.1, remaining)
                self._cv.wait(timeout=wait_for)
                self._spin_once_if_needed(wait_for)

    def pop_latest(self, topic: str, timeout: int = 0, **kwargs) -> bytes | None:
        self._ensure_subscription(topic)
        deadline = time.time() + max(0, timeout)

        with self._cv:
            self._ensure_topic(topic)
            while True:
                if self._buffers[topic]:
                    latest = self._buffers[topic][-1]
                    self._buffers[topic].clear()
                    return latest

                remaining = deadline - time.time()
                if timeout <= 0 or remaining <= 0:
                    return None

                wait_for = min(0.1, remaining)
                self._cv.wait(timeout=wait_for)
                self._spin_once_if_needed(wait_for)

    def trim(self, topic: str, size: int):
        with self._cv:
            self._limits[topic] = max(1, int(size))
            self._ensure_topic(topic)
            items = list(self._buffers[topic])[-self._limits[topic] :]
            self._buffers[topic] = deque(items, maxlen=self._limits[topic])

    def queue_size(self, topic: str) -> int:
        with self._lock:
            self._ensure_topic(topic)
            return len(self._buffers[topic])

    def get_queue_stats(self) -> Dict[str, Dict[str, int]]:
        with self._lock:
            return {
                topic: {
                    "current": len(buf),
                    "max": buf.maxlen if buf.maxlen is not None else self.max_queue_size,
                }
                for topic, buf in self._buffers.items()
            }

    def reset(self):
        with self._cv:
            self._buffers.clear()
            self._limits.clear()

    def to_config(self) -> Dict[str, Any]:
        return {
            "__class_path__": f"{self.__class__.__module__}.{self.__class__.__name__}",
            "node_name": self.node_name,
            "namespace": self.namespace,
            "qos_depth": self.qos_depth,
            "spin_thread": self.spin_thread,
            "max_queue_size": self.max_queue_size,
            "topic_prefix": self.topic_prefix,
        }

    @classmethod
    def from_config(cls, config: Dict[str, Any]) -> "ROSBroker":
        return cls(
            node_name=config.get("node_name", "edgeflow_ros_broker"),
            namespace=config.get("namespace", ""),
            qos_depth=config.get("qos_depth", 100),
            spin_thread=config.get("spin_thread", True),
            max_queue_size=config.get("max_queue_size", 100),
            topic_prefix=config.get("topic_prefix", ""),
        )

    def shutdown(self):
        self._spin_stop.set()
        if self._spin_worker and self._spin_worker.is_alive():
            self._spin_worker.join(timeout=1.0)

        try:
            self._executor.remove_node(self._node)
        except Exception:
            pass

        try:
            self._node.destroy_node()
        except Exception:
            pass

    def __del__(self):
        try:
            self.shutdown()
        except Exception:
            pass
