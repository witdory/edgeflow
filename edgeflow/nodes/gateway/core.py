#edgeflow/nodes/gateway/core.py
import asyncio
import os
import traceback
from ..base import BaseNode
from ...comms import Frame
from ...config import settings

class GatewayNode(BaseNode):
    def __init__(self, broker=None):
        super().__init__(broker)
        self.tcp_port = settings.GATEWAY_TCP_PORT
        self.interfaces = [] # 등록된 인터페이스 목록
        self.server = None

    def add_interface(self, interface):
        """플러그인 장착"""
        self.interfaces.append(interface)

    # [신규] 사용자가 오버라이드 할 메서드 (빈 껍데기)
    def configure(self):
        """
        [User Hook]
        이 메서드를 오버라이드하여 add_interface()를 호출하세요.
        """
        pass

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
            traceback.print_exec()
        finally:
            writer.close()
            await writer.wait_closed()

    async def _run_async(self):
        # TCP 서버 태스크
        server = await asyncio.start_server(self._tcp_handler, '0.0.0.0', self.tcp_port)
        print(f"Hub Listening on TCP {self.tcp_port}")
        
        tasks = [server.serve_forever()]
        
        # 인터페이스별 별도 루프(웹서버 등)가 있다면 함께 실행
        for iface in self.interfaces:
            task = iface.run_loop()
            if task: tasks.append(task)
            
        await asyncio.gather(*tasks)

    def run(self):
        asyncio.run(self._run_async())