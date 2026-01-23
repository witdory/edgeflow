#edgeflow/core.py
import sys
import argparse
import time
import threading
import importlib
from dataclasses import dataclass, field
from typing import Dict, Any, Optional
from .handlers import RedisHandler, TcpHandler
from .config import settings


@dataclass
class NodeSpec:
    """Metadata holder for lazy node loading (Blueprint Pattern)"""
    path: str                          # e.g., "nodes/camera"
    config: Dict[str, Any] = field(default_factory=dict)  # replicas, device, fps 등
    name: str = ""                     # Auto-generated from path if not provided
    
    def __post_init__(self):
        if not self.name:
            # nodes/camera -> camera, nodes/yolo -> yolo
            self.name = self.path.replace("/", "_").replace("nodes_", "")


class Linker:
    def __init__(self, system: 'System', source: NodeSpec):
        self.system = system
        self.source = source

    def to(self, target: NodeSpec, channel: str = None) -> 'Linker':
        """Register a connection between nodes (lazy, metadata only)"""
        self.system._links.append({
            'source': self.source,
            'target': target,
            'channel': channel
        })
        return Linker(self.system, target)


class System:
    """
    Infrastructure Definition (Blueprint Pattern)
    - Lazy loading: node() does NOT import classes
    - Wiring: link() stores metadata only
    - Execution: run() loads classes and executes
    """
    def __init__(self, name: str, broker):
        self.name = name
        self.broker = broker
        self.specs: Dict[str, NodeSpec] = {}
        self._links = []  # Deferred connections
        self._instances = {}  # Populated at run()

    def node(self, path: str, **kwargs) -> NodeSpec:
        """Register node by path (lazy loading, no import)"""
        spec = NodeSpec(path=path, config=kwargs)
        self.specs[spec.name] = spec
        return spec

    def link(self, source: NodeSpec) -> Linker:
        """Create connection builder for wiring nodes"""
        return Linker(self, source)

    def _load_node_class(self, node_path: str):
        """Dynamically load EdgeNode subclass from folder"""
        # nodes/camera -> nodes.camera
        module_path = node_path.replace("/", ".")
        module = importlib.import_module(module_path)
        
        # Find EdgeNode subclass DEFINED in this module (not imported)
        from .nodes import EdgeNode, ProducerNode, ConsumerNode, GatewayNode, FusionNode
        base_classes = {EdgeNode, ProducerNode, ConsumerNode, GatewayNode, FusionNode}
        
        for name, obj in vars(module).items():
            if isinstance(obj, type) and issubclass(obj, EdgeNode):
                # Skip imported base classes
                if obj in base_classes:
                    continue
                # Only return classes defined in THIS module
                if obj.__module__ == module.__name__:
                    return obj
        
        raise ImportError(f"No EdgeNode subclass found in {node_path}")

    def _instantiate_nodes(self):
        """Load and instantiate all registered nodes"""
        for name, spec in self.specs.items():
            cls = self._load_node_class(spec.path)
            instance = cls(broker=self.broker, **spec.config)
            instance.name = name
            self._instances[name] = instance
            print(f"📦 Loaded: {name} ({cls.__name__}, type={cls.node_type})")

    def _wire_connections(self):
        """Apply registered links to node instances"""
        for link in self._links:
            source = self._instances[link['source'].name]
            target = self._instances[link['target'].name]
            channel = link.get('channel')

            # Gateway (TCP) connection
            if getattr(target, 'input_protocol', 'redis') == 'tcp':
                source_id = channel if channel else source.name
                gw_host = settings.GATEWAY_HOST
                gw_port = settings.GATEWAY_TCP_PORT
                handler = TcpHandler(gw_host, gw_port, source_id)
                source.output_handlers.append(handler)
                print(f"🔗 [Direct] {source.name} ==(TCP)==> {target.name} (Channel: {source_id})")

            # Redis connection
            else:
                topic = f"{source.name}_to_{target.name}"
                target.input_topics.append(topic)
                limit = getattr(source, 'queue_size', 1)
                handler = RedisHandler(self.broker, topic, queue_size=limit)
                source.output_handlers.append(handler)
                print(f"🔗 [Queue] {source.name} --(Redis)--> {target.name} (Topic: {topic})")

    def run(self):
        """
        [Hybrid Run Mode]
        1. --node <name> -> Run single node (distributed)
        2. No args -> Run all nodes in threads (local test)
        """
        parser = argparse.ArgumentParser()
        parser.add_argument("--node", help="Run specific node only")
        args, unknown = parser.parse_known_args()

        # Load and wire nodes
        print("📦 Loading nodes...")
        self._instantiate_nodes()
        print("🔗 Wiring connections...")
        self._wire_connections()

        target_name = args.node

        # [Mode 1: Distributed] python main.py --node cam
        if target_name:
            if target_name in self._instances:
                print(f"▶️ [Distributed] Launching single node: {target_name}")
                node = self._instances[target_name]
                node.execute()
            else:
                print(f"❌ Node '{target_name}' not found. Available: {list(self._instances.keys())}")

        # [Mode 2: Local Simulation] python main.py
        else:
            print(f"▶️ [Local] Launching ALL nodes ({len(self._instances)})")
            threads = []
            for name, node in self._instances.items():
                t = threading.Thread(target=node.execute, daemon=True)
                t.start()
                threads.append(t)

            try:
                while True:
                    time.sleep(0.5)
            except KeyboardInterrupt:
                print("\n👋 System Shutdown - Stopping all nodes...")
                sys.exit(0)


# Backward compatibility alias
EdgeApp = System