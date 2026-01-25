#edgeflow/nodes/gateway/core.py
"""
GatewayNode - 외부 스트리밍 엔드포인트

Arduino Pattern:
- setup(): 인터페이스 등록 (WebInterface 등)
- loop(): 게이트웨이는 비동기로 동작하므로 별도 구현 불필요
"""
import asyncio
import os
import traceback
from ..base import EdgeNode
from ...comms import Frame
from ...config import settings


class GatewayNode(EdgeNode):
    """외부로 데이터를 스트리밍하는 엔드포인트 노드"""
    node_type = "gateway"
    input_protocol = "tcp"  # [Fix] Class Attribute로 이동 (Wiring 감지용)
    
    def __init__(self, broker=None, **kwargs):
        super().__init__(broker, **kwargs)
        self.tcp_port = settings.GATEWAY_TCP_PORT
        self.interfaces = []
        self.server = None
        self.active_clients = set()

    def add_interface(self, interface):
        """인터페이스 플러그인 등록"""
        if hasattr(interface, 'set_broker'):
            interface.set_broker(self.broker)
        self.interfaces.append(interface)

    def setup(self):
        """
        [User Hook] 인터페이스를 등록하세요.
        예: self.add_interface(WebInterface())
        """
        pass

    def _setup(self):
        """[Internal] 사용자 setup() 호출 후 인터페이스 초기화"""
        print("⚙️ Configuring Gateway...")
        self.setup()
        
        if not self.interfaces:
            print("⚠️ Warning: No interfaces registered in Gateway.")
        
        for iface in self.interfaces:
            iface.setup()
            print(f"  - Interface Prepared: {iface.__class__.__name__}")

    def loop(self):
        """Gateway는 비동기 이벤트 루프로 동작 (사용자 구현 불필요)"""
        pass

    def _run_loop(self):
        """[Internal] 비동기 이벤트 루프 실행"""
        asyncio.run(self._run_async())

    async def _tcp_handler(self, reader, writer):
        addr = writer.get_extra_info('peername')
        self.active_clients.add(addr)
        print(f"🔌 Client Connected: {addr} | Active: {len(self.active_clients)}")
        
        try:
            while True:
                # 4바이트 길이 읽기
                try:
                    len_bytes = await reader.readexactly(4)
                except asyncio.IncompleteReadError:
                    break

                total_len = int.from_bytes(len_bytes, 'big')
                
                # 본문 읽기
                try:
                    payload = await reader.readexactly(total_len)
                except asyncio.IncompleteReadError:
                    break

                frame = Frame.from_bytes(payload, avoid_decode=True)
                if not frame:
                    continue

                # 모든 인터페이스에게 브로드캐스트
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
        # TCP 서버 시작
        server = await asyncio.start_server(self._tcp_handler, '0.0.0.0', self.tcp_port)
        print(f"Hub Listening on TCP {self.tcp_port}")
        
        tasks = [server.serve_forever()]
        
        # 인터페이스별 별도 루프 실행
        for iface in self.interfaces:
            task = iface.run_loop()
            if task:
                tasks.append(task)
            
        await asyncio.gather(*tasks)