#edgeflow/nodes/gateway/core.py
import asyncio
import os
import traceback
import json
import threading
from ..base import BaseNode
from ...comms import Frame
from ...config import settings

class GatewayNode(BaseNode):
    def __init__(self, broker=None, app=None, **kwargs):
        super().__init__(broker=broker, app=app, **kwargs)
        self.tcp_port = settings.GATEWAY_TCP_PORT
        self.interfaces = [] # 등록된 인터페이스 목록
        self.server = None
        self.active_clients = set()
        self.input_protocol = "tcp"
        self.latest_metrics = {}
        self.metrics_lock = asyncio.Lock()

    def add_interface(self, interface):
        """플러그인 장착"""
        interface.broker = self.broker # Inject broker
        interface.edge_app = self.app  # Inject app
        interface.gateway = self       # Inject gateway instance itself
        self.interfaces.append(interface)

    def stop(self):
        """Gracefully stop the node and its asyncio loop."""
        super().stop()
        if hasattr(self, 'loop') and self.loop.is_running():
            self.loop.call_soon_threadsafe(self.loop.stop)

    # [사용자 훅] 사용자가 오버라이드 할 메서드 (빈 껍데기)
    def configure(self):
        """
        [User Hook]
        이 메서드를 오버라이드하여 add_interface()를 호출하세요.
        """
        pass

    async def get_latest_metrics(self):
        """Safely returns a copy of the latest metrics."""
        async with self.metrics_lock:
            return self.latest_metrics.copy()

    # [변경] 프레임워크가 제어하는 초기화 로직 (Final)
    def setup(self):
        # 1. 사용자의 설정(configure)을 먼저 실행
        print("⚙️ Configuring Gateway...")
        self.configure()
        
        # 2. 등록된 인터페이스들 초기화 (사용자가 신경 안 써도 됨)
        if not self.interfaces:
            print("⚠️ Warning: No interfaces registered in Gateway.")
        
        for iface in self.interfaces:
            iface.setup()
            print(f"  - Interface Prepared: {iface.__class__.__name__}")

    async def _tcp_handler(self, reader, writer):
        addr = writer.get_extra_info('peername')
        self.active_clients.add(addr)
        print(f"🔌 Client Connected: {addr} | Active: {len(self.active_clients)}")
        try:
            while True:
                # 1. TCP 데이터 수신
                try:
                    #4바이트 길이 읽기
                    len_bytes = await reader.readexactly(4)
                except asyncio.IncompleteReadError:
                    break

                total_len = int.from_bytes(len_bytes, 'big')
                try:
                    #본문 읽기
                    payload = await reader.readexactly(total_len)
                except asyncio.IncompleteReadError:
                    break

                
                frame = Frame.from_bytes(payload, avoid_decode=True)
                if not frame: continue

                # 2. [핵심] 모든 인터페이스에게 데이터 전파 (Broadcasting)
                # 비동기로 뿌리므로 인터페이스가 많아도 느려지지 않음
                tasks = [iface.on_frame(frame) for iface in self.interfaces]
                if tasks:
                    await asyncio.gather(*tasks)

        except Exception as e:
            print(f"Gateway TCP Error: {e}")
            traceback.print_exc()
        finally:
            self.active_clients.discard(addr)
            print(f"❌ Client Disconnected: {addr} | Active: {len(self.active_clients)}")
            writer.close()
            await writer.wait_closed()

    async def _run_async(self):
        self.loop = asyncio.get_running_loop()
        # TCP 서버 태스크
        server = await asyncio.start_server(self._tcp_handler, '0.0.0.0', self.tcp_port)
        print(f"Hub Listening on TCP {self.tcp_port}")
        
        tasks = [server.serve_forever()]
        
        # Start the metrics listener in a background thread
        listener_thread = threading.Thread(target=self._metrics_listener_loop, daemon=True)
        listener_thread.start()
        
        # 인터페이스별 별도 루프(웹서버 등)가 있다면 함께 실행
        for iface in self.interfaces:
            task = iface.run_loop()
            if task: tasks.append(task)
            
        await asyncio.gather(*tasks)

    def run(self):
        """Manually manage the asyncio event loop for graceful shutdown."""
        self.loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self.loop)
        
        try:
            # _run_async now only sets up the long-running tasks
            self.loop.run_until_complete(self._run_async())
            # run_forever() blocks until stop() is called.
            self.loop.run_forever()
        finally:
            print("🛑 Gateway loop shutting down.")
            # Gracefully close all tasks.
            tasks = asyncio.all_tasks(loop=self.loop)
            for task in tasks:
                task.cancel()
            
            group = asyncio.gather(*tasks, return_exceptions=True)
            self.loop.run_until_complete(group)
            self.loop.close()
            asyncio.set_event_loop(None)

    async def _update_metrics(self, data):
        """Safely updates the shared metrics dictionary."""
        node_name = data.get('node_name')
        if not node_name:
            return
        async with self.metrics_lock:
            self.latest_metrics[node_name] = data

    def _metrics_listener_loop(self):
        """The synchronous loop that listens to Redis Pub/Sub for metrics."""
        metrics_channel = f"{self.app.name}:metrics"
        
        pubsub = self.broker.redis.pubsub(ignore_subscribe_messages=True)
        pubsub.subscribe(metrics_channel)
        
        print(f"👂 Metrics listener started. Channel: {metrics_channel}")
        while self.running:
            try:
                message = pubsub.get_message(timeout=1.0)
                if message is None:
                    continue

                data = json.loads(message['data'])
                future = asyncio.run_coroutine_threadsafe(self._update_metrics(data), self.loop)
                future.result(timeout=2) # Add a timeout
            except Exception as e:
                # On shutdown, this might raise redis.exceptions.ConnectionError, which is fine.
                if self.running:
                    print(f"⚠️ Metrics Listener Error: {e}")
        
        print("🛑 Metrics listener stopped.")