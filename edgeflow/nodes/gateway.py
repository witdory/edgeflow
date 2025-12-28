import asyncio
import struct
import json
import heapq
import time
import uvicorn
from fastapi import FastAPI
from fastapi.responses import StreamingResponse, JSONResponse
from .base import BaseNode
from ..comms import Frame

class GatewayNode(BaseNode):
    def __init__(self, port=8000, tcp_port=8080, buffer_size=0.5):
        super().__init__()
        self.http_port = port
        self.tcp_port = tcp_port
        self.buffer_size = buffer_size
        
        # 상태 관리
        self.app = FastAPI(title="EdgeFlow Gateway")
        self.packet_buffer = []
        self.state = {"meta": {}}
        self.lock = asyncio.Lock()
        
        # 인터페이스 등록 (사용자 커스텀 로직)
        self.custom_handler = None

    def on_message(self, frame, meta):
        """기본 핸들러: 사용자가 오버라이드 하지 않으면 그대로 통과"""
        return frame

    def setup(self):
        # FastAPI 라우트 등록
        self.app.get("/video_stream")(self.stream_video)
        self.app.get("/api/status")(self.get_status)

    async def _tcp_handler(self, reader, writer):
        """기존 TCP 서버 로직"""
        try:
            while True:
                len_bytes = await reader.readexactly(4)
                total_length = int.from_bytes(len_bytes, 'big')
                payload = await reader.readexactly(total_length)

                frame = Frame.from_bytes(payload)
                if not frame: continue

                # 사용자 로직 (오버라이드 가능)
                processed_data = self.on_message(frame.data, frame.meta)
                
                # 결과 저장
                if processed_data is not None:
                    # 화면 송출용 데이터 준비 (이미지 -> 바이트)
                    # 여기서는 간단히 Frame 객체의 헬퍼 사용
                    temp_frame = Frame(data=processed_data)
                    final_bytes = temp_frame.get_data_bytes()

                    async with self.lock:
                        heapq.heappush(self.packet_buffer, (frame.timestamp, final_bytes))
                        self.state["meta"].update(frame.meta)

        except Exception as e:
            print(f"Gateway TCP Error: {e}")
        finally:
            writer.close()

    async def _mjpeg_gen(self):
        """MJPEG 스트리밍 생성기"""
        last_sent_ts = 0.0
        while True:
            now = time.time()
            frame_to_send = None
            
            async with self.lock:
                # 버퍼 관리 로직 (기존과 동일)
                while self.packet_buffer:
                    oldest_ts, _ = self.packet_buffer[0]
                    deadline = now - self.buffer_size
                    
                    if oldest_ts < deadline - 0.05: # 너무 오래된 것 버림
                        heapq.heappop(self.packet_buffer)
                    else:
                        break
                
                # 송출 로직
                if self.packet_buffer:
                     oldest_ts, data = self.packet_buffer[0]
                     should_play = (self.buffer_size == 0.0) or (oldest_ts <= now - self.buffer_size)
                     
                     if should_play:
                         if oldest_ts > last_sent_ts:
                             last_sent_ts = oldest_ts
                             frame_to_send = data
                             # 뷰어용이므로 데이터를 pop하지 않고 유지할 수도 있지만, 
                             # 여기선 간단히 큐에서 제거하지 않고(peek) 쓰거나 구조에 따라 다름.
                             # 기존 로직 유지를 위해 pop 하지 않거나 적절히 처리.
                             # (단순화를 위해 여기선 가장 최신만 보낸다고 가정할 수도 있음)
                         else:
                             pass 

            if frame_to_send:
                yield (b'--frameboundary\r\n'
                       b'Content-Type: image/jpeg\r\n\r\n' + frame_to_send + b'\r\n')
                await asyncio.sleep(0.033)
            else:
                await asyncio.sleep(0.01)

    async def stream_video(self):
        return StreamingResponse(self._mjpeg_gen(), media_type="multipart/x-mixed-replace; boundary=frameboundary")

    async def get_status(self):
        async with self.lock:
            return JSONResponse(content=self.state["meta"])

    async def _run_loop(self):
        # TCP 서버 시작
        server = await asyncio.start_server(self._tcp_handler, '0.0.0.0', self.tcp_port)
        print(f"📺 Gateway TCP Listening on {self.tcp_port}")
        
        # FastAPI(Uvicorn) 시작
        config = uvicorn.Config(self.app, host="0.0.0.0", port=self.http_port, log_level="error")
        server_u = uvicorn.Server(config)
        
        # 동시에 실행
        await asyncio.gather(server.serve_forever(), server_u.serve())

    def run(self):
        # Asyncio 루프 생성 및 진입
        asyncio.run(self._run_loop())