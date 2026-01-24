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
    - Execution: run() loads classes and executesk
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
        2. No args -> Run all nodes in MULTI-PROCESS mode (local simulation)
        """
        parser = argparse.ArgumentParser()
        parser.add_argument("--node", help="Run specific node only")
        args, unknown = parser.parse_known_args()

        target_name = args.node

        # [Mode 1: Distributed] python main.py --node cam
        # In distributed mode, we assume the environment (Docker) is set up.
        # We can just instantiate and run in THIS process.
        if target_name:
            # We need to instantiate just THIS node
            if target_name not in self.specs:
                print(f"❌ Node '{target_name}' not found. Available: {list(self.specs.keys())}")
                return

            spec = self.specs[target_name]
            # wiring resolution relative to this node
            print(f"▶️ [Distributed] Launching single node: {target_name}")
            
            # Using the injected broker object directly
            cls = self._load_node_class(spec.path)
            node = cls(broker=self.broker, **spec.config)
            node.name = target_name
            
            # Apply wiring (We need to resolve all links to find MY outputs)
            self._apply_wiring_for_node(node, self.broker)
            
            node.execute()

        # [Mode 2: Local Simulation (Multiprocessing)] python main.py
        else:
            print(f"▶️ [Local] Launching ALL nodes ({len(self.specs)}) in separate processes")
            import multiprocessing
            
            processes = []
            
            # Extract config from broker using the serialization protocol
            broker_config = self.broker.to_config()
            
            for name, spec in self.specs.items():
                # Prepare wiring config (targets) for this specific node
                wiring_config = self._resolve_wiring_config(name)
                
                p = multiprocessing.Process(
                    target=self._run_node_process,
                    args=(name, spec.path, spec.config, broker_config, wiring_config),
                    daemon=True
                )
                p.start()
                processes.append(p)

            try:
                while True:
                    time.sleep(0.5)
            except KeyboardInterrupt:
                print("\n👋 System Shutdown - Stopping all processes...")
                for p in processes:
                    p.terminate()
                sys.exit(0)

    def _resolve_wiring_config(self, node_name: str) -> Dict[str, Any]:
        """Resolve wiring for a specific node into serializable config"""
        outputs = []
        inputs = []
        
        # Check links where I am the source
        for link in self._links:
            if link['source'].name == node_name:
                target_name = link['target'].name
                channel = link.get('channel')
                
                # Check target protocol (Need to peek at target class? Or assume Redis?)
                # For lazy loading, we might need to assume Redis unless config says otherwise.
                # In v0.2.0, protocol flows are implicit. We will default to Redis topic mapping.
                
                # TODO: Lazy protocol check. For now, we assume Redis unless channel is explicit (gateway)
                # Ideally, we should check the target's class `input_protocol` but that requires loading class.
                # We will Load class briefly to check protocol if needed, or rely on naming conventions.
                
                target_cls = self._load_node_class(link['target'].path)
                protocol = getattr(target_cls, 'input_protocol', 'redis')
                
                outputs.append({
                    'target': target_name,
                    'protocol': protocol,
                    'channel': channel,
                    'queue_size': getattr(self._load_node_class(link['source'].path), 'queue_size', 1)
                })
            
            if link['target'].name == node_name:
                source_name = link['source'].name
                inputs.append(f"{source_name}_to_{node_name}")
                
        return {'outputs': outputs, 'inputs': inputs}

    def _apply_wiring_for_node(self, node, broker):
        """Apply wiring using an ACTIVE broker instance (Thread Mode / Single Node Mode)"""
        # This is used for Distributed Mode where we have an object
        wiring = self._resolve_wiring_config(node.name)
        self._hydrate_node_handlers(node, broker, wiring)

    @staticmethod
    def _hydrate_node_handlers(node, broker, wiring):
        """Hydrate node with handlers based on wiring config"""
        # Inputs
        # (ConsumerNode automatically subscribes based on input_topics list)
        for topic in wiring['inputs']:
            if topic not in node.input_topics:
                node.input_topics.append(topic)
                
        # Outputs
        for out in wiring['outputs']:
            if out['protocol'] == 'tcp':
                # Gateway connection
                source_id = out['channel'] if out['channel'] else node.name
                gw_host = settings.GATEWAY_HOST
                gw_port = settings.GATEWAY_TCP_PORT
                handler = TcpHandler(gw_host, gw_port, source_id)
                node.output_handlers.append(handler)
                print(f"🔗 [Direct] {node.name} ==(TCP)==> {out['target']}")
            else:
                # Redis connection
                topic = f"{node.name}_to_{out['target']}"
                handler = RedisHandler(broker, topic, queue_size=out['queue_size'])
                node.output_handlers.append(handler)
                print(f"🔗 [Queue] {node.name} --(Redis)--> {out['target']}")

    @staticmethod
    def _run_node_process(name: str, path: str, node_config: Dict, broker_config: Dict, wiring_config: Dict):
        """Bootstrap function running in a separate process"""
        # 1. Re-establish Broker Connection using the serialization protocol
        # Dynamic import based on broker_config
        module_path, class_name = broker_config['__class_path__'].rsplit('.', 1)
        module = importlib.import_module(module_path)
        BrokerClass = getattr(module, class_name)
        
        # Use the from_config protocol method
        broker = BrokerClass.from_config(broker_config)
        print(f"⚡ [Process:{name}] Broker connected: {broker_config.get('host')} ({class_name})", flush=True)

        # 2. Load Class & Instantiate
        # We need to replicate _load_node_class logic or import it.
        # Since this is static, we can't call self._load_node_class easily unless we duplicate logic 
        # or make _load_node_class static.
        # For simplicity, we'll re-implement import logic here or make _load static.
        
        module_path = path.replace("/", ".")
        module = importlib.import_module(module_path)
        
        # Find class
        from .nodes import EdgeNode, ProducerNode, ConsumerNode, GatewayNode, FusionNode
        base_classes = {EdgeNode, ProducerNode, ConsumerNode, GatewayNode, FusionNode}
        
        node_cls = None
        for obj_name, obj in vars(module).items():
            if isinstance(obj, type) and issubclass(obj, EdgeNode):
                if obj in base_classes: continue
                if obj.__module__ == module.__name__:
                    node_cls = obj
                    break
        
        if not node_cls:
            print(f"❌ [Process:{name}] No EdgeNode found in {path}", flush=True)
            return

        node = node_cls(broker=broker, **node_config)
        node.name = name
        
        # 3. Wiring (Handlers)
        System._hydrate_node_handlers(node, broker, wiring_config)
        
        # 4. Execute
        print(f"🚀 [Process:{name}] Starting execution loop...", flush=True)
        node.execute()

# Backward compatibility alias
EdgeApp = System