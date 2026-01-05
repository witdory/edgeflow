#edgeflow/core.py
import sys
import argparse
import time
import threading
from .handlers import RedisHandler, TcpHandler
from .config import settings

class Linker:
    def __init__(self, app, source_node):
        self.app = app
        self.source = source_node

    def to(self, target_name, channel=None):
        target = self.app.nodes[target_name]

        # 1. Target이 TCP(Gateway)인 경우 -> TcpHandler 주입
        if getattr(target, 'input_protocol', 'redis') == 'tcp':
            
            source_id = channel if channel else self.source.name
            
            # Gateway 정보를 가져옴
            gw_host = settings.GATEWAY_HOST
            gw_port = settings.GATEWAY_TCP_PORT

            handler = TcpHandler(gw_host, gw_port, source_id)
            self.source.output_handlers.append(handler)
            print(f"🔗 [Direct] {self.source.name} ==(TCP)==> {target.name} (Channel: {source_id})")

        # 2. Target이 일반 노드(Redis)인 경우 -> RedisHandler 주입
        else:
            # 토픽 자동 생성: app_name:source_to_target
            topic = f"{self.app.name}:{self.source.name}_to_{target.name}"
            
            # [Target 설정] 받는 쪽은 토픽을 구독해야 함
            target.input_topics.append(topic)

            limit = getattr(self.source, 'queue_size', 1)
            handler = RedisHandler(self.app.broker, topic, queue_size=limit)
            # [Source 설정] 보내는 쪽은 토픽으로 쏴야 함
            handler = RedisHandler(self.app.broker, topic)
            self.source.output_handlers.append(handler)
            print(f"🔗 [Queue] {self.source.name} --(Redis)--> {target.name} (Topic: {topic})")

        return Linker(self.app, target)

# edgeflow/core.py

import sys
import argparse
import threading

class EdgeApp:
    def __init__(self, name, broker, profile="default"):
        self.name = name
        self.broker = broker
        self.nodes = {} # {name: instance}
        self.profile = profile

    def node(self, name, type="producer", **kwargs):
        def decorator(cls):
            # Apply profile-based queue_size only if not specified by the user
            if 'queue_size' not in kwargs:
                if self.profile == "realtime":
                    kwargs["queue_size"] = 1
                else:
                    kwargs["queue_size"] = 10 # Default queue size

            # 1. 인스턴스를 미리 생성 (Linker를 위해 필수)
            instance = cls(broker=self.broker, app=self, **kwargs)
            instance.name = name
            # 2. 딕셔너리에 저장
            self.nodes[name] = instance
            return cls
        return decorator

    def link(self, source_name):
        return Linker(self, self.nodes[source_name])

    def run(self):
        """
        [Hybrid Run Mode]
        1. 인자가 있으면 -> 해당 노드만 실행 (분산 환경용)
        2. 인자가 없으면 -> 모든 노드 스레드로 실행 (테스트용)
        """
        parser = argparse.ArgumentParser()
        parser.add_argument("--node", help="Run specific node only")
        args, unknown = parser.parse_known_args()

        target_name = args.node

        # [Mode 1: 분산 실행] python main.py --node cam
        if target_name:
            if target_name in self.nodes:
                print(f"▶️ [Distributed Mode] Launching single node: {target_name}")
                node = self.nodes[target_name]
                node.execute() # 블로킹 실행 (하나만 도니까)
            else:
                print(f"❌ Node '{target_name}' not found. Available: {list(self.nodes.keys())}")

        # [Mode 2: 통합 시뮬레이션] python main.py
        else:
            print(f"▶️ [Simulation Mode] Launching ALL nodes ({len(self.nodes)})")
            threads = []
            for name, node in self.nodes.items():
                # 스레드로 감싸서 실행
                t = threading.Thread(target=node.execute, daemon=True)
                t.start()
                threads.append(t)
            
            try:
                # Keep main thread alive while node threads are running
                while any(t.is_alive() for t in threads):
                    time.sleep(0.1)
            except KeyboardInterrupt:
                print("\n👋 App Shutdown signal received, stopping nodes...")
                for node in self.nodes.values():
                    node.running = False # Tell all node loops to stop
                
                # Wait for all threads to finish
                for t in threads:
                    t.join()
                print("✅ All nodes have been stopped.")