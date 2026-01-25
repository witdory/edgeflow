#edgeflow/core.py
import sys
import argparse
import time
import threading
import importlib
from dataclasses import dataclass, field
from typing import Dict, Any, Optional, List
from .handlers import RedisHandler, TcpHandler
from .config import settings
from .registry import NodeSpec, NodeRegistry
from .qos import QoS


class Linker:
    def __init__(self, system: 'System', source: NodeSpec):
        self.system = system
        self.source = source

    def to(self, target: NodeSpec, channel: str = None, qos: QoS = QoS.REALTIME) -> 'Linker':
        """Register a connection between nodes with QoS policy"""
        self.system._links.append({
            'source': self.source,
            'target': target,
            'channel': channel,
            'qos': qos,  # [신규] 연결별 QoS 정책
            'broker': self.system.broker
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
        """Register node by path (uses global registry for sharing)"""
        spec = NodeRegistry.get_or_create(path, **kwargs)
        self.specs[spec.name] = spec
        return spec

    def share(self, spec: NodeSpec) -> NodeSpec:
        """Import a node from another System (add to my scope)"""
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
                topic = source.name  # [수정] 토픽 = source 이름만
                target.input_topics.append({'topic': source.name, 'qos': link.get('qos', QoS.REALTIME)})
                limit = getattr(source, 'queue_size', 1)
                handler = RedisHandler(self.broker, topic, queue_size=limit)
                source.output_handlers.append(handler)
                print(f"🔗 [Stream] {source.name} --(QoS:{link.get('qos', QoS.REALTIME).name})--> {target.name}")

    def run(self):
        """
        Start the System execution (blocking)
        - Proxy to the top-level run() function
        """
        run(self)

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
                    'queue_size': getattr(self._load_node_class(link['source'].path), 'queue_size', 1),
                    'qos': link.get('qos', QoS.REALTIME)  # [신규] QoS 전달
                })
            
            if link['target'].name == node_name:
                source_name = link['source'].name
                qos = link.get('qos', QoS.REALTIME)
                inputs.append({'topic': source_name, 'qos': qos})  # [변경] 토픽=source, QoS 포함
                
        return {'outputs': outputs, 'inputs': inputs}

    def _apply_wiring_for_node(self, node, broker):
        """Apply wiring using an ACTIVE broker instance (Thread Mode / Single Node Mode)"""
        # This is used for Distributed Mode where we have an object
        wiring = self._resolve_wiring_config(node.name)
        self._hydrate_node_handlers(node, broker, wiring)

    @staticmethod
    def _hydrate_node_handlers(node, broker, wiring):
        # Inputs (now includes QoS)
        for inp in wiring['inputs']:
            topic = inp['topic'] if isinstance(inp, dict) else inp
            qos = inp.get('qos', QoS.REALTIME) if isinstance(inp, dict) else QoS.REALTIME
            if topic not in [t['topic'] if isinstance(t, dict) else t for t in node.input_topics]:
                node.input_topics.append({'topic': topic, 'qos': qos})
                
        # Outputs
        redis_topics = set()
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
                # Redis connection - topic is now just source name
                topic = node.name
                
                # Deduplicate: Only add one RedisHandler per topic
                if topic not in redis_topics:
                    handler = RedisHandler(broker, topic, queue_size=out['queue_size'])
                    node.output_handlers.append(handler)
                    redis_topics.add(topic)
                
                print(f"🔗 [Stream] {node.name} --(QoS:{out.get('qos', 'REALTIME').name if hasattr(out.get('qos'), 'name') else 'REALTIME'})--> {out['target']}")

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
        from .nodes import EdgeNode, ProducerNode, ConsumerNode, GatewayNode, FusionNode, SinkNode
        base_classes = {EdgeNode, ProducerNode, ConsumerNode, GatewayNode, FusionNode, SinkNode}
        
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


def run(*systems: System):
    """
    Run one or multiple Systems (Entry Point)
    
    - Single System: run(sys)
    - Multi System:  run(sys1, sys2)
    """
    import multiprocessing
    
    # 1. Collect all unique nodes
    all_specs: Dict[str, NodeSpec] = {}
    for s in systems:
        for name, spec in s.specs.items():
            all_specs[name] = spec
    
    # 2. Merge wiring from all systems
    all_links = []
    for s in systems:
        all_links.extend(s._links)
    
    # 3. Build wiring config per node (from ALL systems)
    def resolve_merged_wiring(node_name: str) -> Dict[str, Any]:
        outputs = []
        inputs = []
        
        for link in all_links:
            if link['source'].name == node_name:
                target_name = link['target'].name
                channel = link.get('channel')
                broker = link.get('broker')
                
                # Load target class to check protocol
                target_spec = all_specs.get(target_name)
                if not target_spec:
                    continue
                target_cls = systems[0]._load_node_class(target_spec.path)
                protocol = getattr(target_cls, 'input_protocol', 'redis')
                
                # Get queue_size from source
                source_spec = all_specs.get(node_name)
                source_cls = systems[0]._load_node_class(source_spec.path)
                queue_size = getattr(source_cls, 'queue_size', 1)
                
                outputs.append({
                    'target': target_name,
                    'protocol': protocol,
                    'channel': channel,
                    'queue_size': queue_size,
                    'broker_config': broker.to_config() if broker else None
                })
            
            if link['target'].name == node_name:
                source_name = link['source'].name
                qos = link.get('qos', QoS.REALTIME)
                inputs.append({'topic': source_name, 'qos': qos})  # [수정] 토픽=source
        
        return {'outputs': outputs, 'inputs': inputs}
    
    # 4. Launch processes
    processes = []
    
    # [Reset Broker State]
    # Assuming all systems share the same physical broker for now,
    # or separate brokers. We reset ALL brokers attached to systems.
    # To avoid double reset if shared, we can track checked brokers, 
    # but reset() is usually idempotent (FLUSHALL).
    
    # Simple strategy: Reset the broker of the first system (Master Broker)
    # or iterate all unique brokers.
    if processes == []:
        # Only reset once at the beginning
        if systems and hasattr(systems[0].broker, 'reset'):
             systems[0].broker.reset()

    default_broker_config = systems[0].broker.to_config()
    
    for name, spec in all_specs.items():
        wiring_config = resolve_merged_wiring(name)
        
        p = multiprocessing.Process(
            target=System._run_node_process,
            args=(name, spec.path, spec.config, default_broker_config, wiring_config),
            daemon=True
        )
        p.start()
        processes.append(p)
    
    print(f"▶️ [EdgeFlow] Launching {len(processes)} nodes from {len(systems)} system(s)")
    
    try:
        while True:
            time.sleep(0.5)
    except KeyboardInterrupt:
        print("\n👋 System Shutdown - Stopping all processes...")
        for p in processes:
            p.terminate()
        import sys as sys_module
        sys_module.exit(0)