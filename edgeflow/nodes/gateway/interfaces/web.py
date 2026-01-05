#edgeflow/nodes/gateway/interfaces/web.py
import asyncio
import time
import uvicorn
from fastapi import FastAPI
from fastapi.responses import StreamingResponse, JSONResponse
from .base import BaseInterface
from collections import defaultdict
from ....comms import Frame
from ....utils.buffer import TimeJitterBuffer

class WebInterface(BaseInterface):
    def __init__(self, port=8000, buffer_delay=0.2, enable_video=True, enable_metrics=True):
        super().__init__()
        self.port = port
        self.enable_video = enable_video
        self.enable_metrics = enable_metrics
        self.app = FastAPI(title="EdgeFlow Viewer")
        self.latest_frame = None
        self.latest_meta = {}
        self.lock = asyncio.Lock() # 동시성 제어
        self._custom_routes = []

        self.buffer_delay = buffer_delay
        self.buffers = defaultdict(lambda: TimeJitterBuffer(buffer_delay=self.buffer_delay))

    def setup(self):
        # 라우트 등록
        if self.enable_metrics:
            self.app.get("/api/metrics")(self.get_metrics)

        if self.enable_video:
            self.app.get("/api/status")(self.get_status)
            @self.app.get("/video")
            async def video_feed_default():
                return StreamingResponse(self.stream_generator("default"), media_type="multipart/x-mixed-replace; boundary=frameboundary")


            @self.app.get("/video/{topic_name}")
            async def video_feed_topic(topic_name: str):
                return StreamingResponse(
                    self.stream_generator(topic_name), # URL에서 받은 토픽 전달
                    media_type="multipart/x-mixed-replace; boundary=frameboundary"
                )
        
        for r in self._custom_routes:
            self.app.add_api_route(
                path=r["path"], 
                endpoint=r["endpoint"], 
                methods=r["methods"]
            )
            print(f"  + Custom Route Added: {r['path']}")
        print(f"🌍 WebInterface prepared on port {self.port}")

    async def on_frame(self, frame):
        if not self.enable_video:
            return
            
        # Gateway가 이 함수를 호출해서 데이터를 넣어줌
        async with self.lock:
            # 송출용으로 변환하여 저장 (가장 최신 1개만 유지)
            topic = frame.meta.get("topic", "default")
            self.buffers[topic].push(frame)

            if frame.meta:
                if topic not in self.latest_meta:
                    self.latest_meta[topic] = {}
                self.latest_meta[topic].update(frame.meta)

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

    async def stream_generator(self, topic):
        while True:
            data = None
            async with self.lock:
                if topic in self.buffers:
                    data = self.buffers[topic].pop()

            
            if data:
                yield (b'--frameboundary\r\n'
                       b'Content-Type: image/jpeg\r\n\r\n' + data + b'\r\n')
                wait_time = 0.001 if self.buffer_delay == 0.0 else 0.01
                await asyncio.sleep(wait_time) # 약 30FPS 제한
            else:
                await asyncio.sleep(0.01)


    async def get_metrics(self):
        async with self.gateway.metrics_lock:
            # Return a copy of the latest metrics
            return JSONResponse(content=dict(self.gateway.latest_metrics))

    async def get_status(self):
        async with self.lock:
            return JSONResponse(content=self.latest_meta)

    async def run_loop(self):
        # 웹 서버 실행 (Gateway 메인 루프와 함께 돔)
        config = uvicorn.Config(self.app, host="0.0.0.0", port=self.port, log_level="error")
        server = uvicorn.Server(config)
        await server.serve()
