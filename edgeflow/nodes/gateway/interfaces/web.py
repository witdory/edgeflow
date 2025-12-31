#edgeflow/nodes/gateway/interfaces/web.py
import asyncio
import time
import uvicorn
from fastapi import FastAPI
from fastapi.responses import StreamingResponse, JSONResponse
from .base import BaseInterface
from ....comms import Frame

class WebInterface(BaseInterface):
    def __init__(self, port=8000):
        self.port = port
        self.app = FastAPI(title="EdgeFlow Viewer")
        self.latest_frame = None
        self.latest_meta = {}
        self.lock = asyncio.Lock() # 동시성 제어
        self._custom_routes = []
        
    def setup(self):
        # 라우트 등록
        self.app.get("/video")(self.video_feed)
        self.app.get("/api/status")(self.get_status)
        for r in self._custom_routes:
            self.app.add_api_route(
                path=r["path"], 
                endpoint=r["endpoint"], 
                methods=r["methods"]
            )
            print(f"  + Custom Route Added: {r['path']}")
        print(f"🌍 WebInterface prepared on port {self.port}")

    async def on_frame(self, frame):
        # Gateway가 이 함수를 호출해서 데이터를 넣어줌
        async with self.lock:
            # 송출용으로 변환하여 저장 (가장 최신 1개만 유지)
            # Frame 객체의 헬퍼 사용
            self.latest_frame = frame.get_data_bytes()

            if frame.meta:
                self.latest_meta.update(frame.meta)

    def route(self, path, methods=["GET"]):
        def decorator(func):
            # 실행 시점이 아니라, 등록 시점에 정보만 저장해둠
            self._custom_routes.append({
                "path": path, 
                "endpoint": func, 
                "methods": methods
            })
            return func
        return decorator

    async def _gen(self):
        while True:
            data = None
            async with self.lock:
                data = self.latest_frame
            
            if data:
                yield (b'--frameboundary\r\n'
                       b'Content-Type: image/jpeg\r\n\r\n' + data + b'\r\n')
                await asyncio.sleep(0.033) # 약 30FPS 제한
            else:
                await asyncio.sleep(0.1)

    async def video_feed(self):
        return StreamingResponse(self._gen(), media_type="multipart/x-mixed-replace; boundary=frameboundary")

    async def get_status(self):
        async with self.lock:
            return JSONResponse(content=self.latest_meta)

    async def run_loop(self):
        # 웹 서버 실행 (Gateway 메인 루프와 함께 돔)
        config = uvicorn.Config(self.app, host="0.0.0.0", port=self.port, log_level="error")
        server = uvicorn.Server(config)
        await server.serve()