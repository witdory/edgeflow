# edgeflow/gateway_engine.py
import asyncio
import struct
import json

class GatewayEngine:
    def __init__(self, port, handler):
        self.port = port
        self.handler = handler # 사용자가 작성한 로직(함수)

    async def run_server(self):
        server = await asyncio.start_server(self._handle_client, '0.0.0.0', self.port)
        async with server:
            await server.serve_forever()

    async def _handle_client(self, reader, writer):
        while True:
            try:
                # 1. 헤더(4바이트 길이) 읽기
                header = await reader.readexactly(4)
                length = struct.unpack('>I', header)[0]
                # 2. 바디 읽기
                body = await reader.readexactly(length)
                data = json.loads(body.decode('utf-8'))
                
                # 3. 사용자 핸들러 실행 (여기서 데이터가 넘어감)
                if asyncio.iscoroutinefunction(self.handler):
                    await self.handler(data)
                else:
                    self.handler(data)
            except:
                break
        writer.close()