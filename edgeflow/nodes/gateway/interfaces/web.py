#edgeflow/nodes/gateway/interfaces/web.py
import asyncio
import time
import uvicorn
from fastapi import FastAPI
from fastapi.responses import StreamingResponse, JSONResponse, HTMLResponse
from .base import BaseInterface
from collections import defaultdict
from ....comms import Frame
from ....utils.buffer import TimeJitterBuffer

class WebInterface(BaseInterface):
    def __init__(self, port=8000, buffer_delay=0.2):
        self.port = port
        self.app = FastAPI(title="EdgeFlow Viewer")
        self.latest_frame = None
        self.latest_meta = {}
        self.lock = asyncio.Lock() # 동시성 제어
        self._custom_routes = []

        self.buffer_delay = buffer_delay
        self.buffers = defaultdict(lambda: TimeJitterBuffer(buffer_delay=self.buffer_delay))

        # [신규] FPS 추적용 변수
        self.frame_counts = defaultdict(int)  # topic -> count
        self.fps_stats = {}  # topic -> fps (최근 계산값)
        self.last_fps_calc_time = time.time()

    def setup(self):
        # 라우트 등록
        self.app.add_api_route("/health", self.health_check, methods=["GET"])
        self.app.add_api_route("/api/status", self.get_status, methods=["GET"])
        self.app.add_api_route("/api/fps", self.get_fps, methods=["GET"])  # [신규]
        self.app.add_api_route("/dashboard", self.dashboard, methods=["GET"])  # [신규]

        @self.app.get("/video")
        async def video_feed_default():
            return StreamingResponse(self.stream_generator("default"), media_type="multipart/x-mixed-replace; boundary=frameboundary")

        @self.app.get("/video/{topic_name}")
        async def video_feed_topic(topic_name: str):
            return StreamingResponse(
                self.stream_generator(topic_name),
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
        # Gateway가 이 함수를 호출해서 데이터를 넣어줌
        async with self.lock:
            topic = frame.meta.get("topic", "default")
            self.buffers[topic].push(frame)
            self.frame_counts[topic] += 1  # [신규] FPS 카운트

            if frame.meta:
                if topic not in self.latest_meta:
                    self.latest_meta[topic] = {}
                self.latest_meta[topic].update(frame.meta)

    def route(self, path, methods=["GET"]):
        def decorator(func):
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
                await asyncio.sleep(wait_time)
            else:
                await asyncio.sleep(0.01)

    async def get_status(self):
        async with self.lock:
            return JSONResponse(content=self.latest_meta)

    async def health_check(self):
        return JSONResponse(content={"status": "ok"})

    # [신규] FPS 계산 및 API
    async def get_fps(self):
        async with self.lock:
            now = time.time()
            elapsed = now - self.last_fps_calc_time
            if elapsed > 0:
                for topic, count in self.frame_counts.items():
                    self.fps_stats[topic] = round(count / elapsed, 2)
                self.frame_counts = defaultdict(int)  # 리셋
                self.last_fps_calc_time = now
            return JSONResponse(content=self.fps_stats)

    # [신규] Dashboard HTML 페이지
    async def dashboard(self):
        # 템플릿 파일 로드
        import os
        template_path = os.path.join(os.path.dirname(__file__), 'templates', 'dashboard.html')
        with open(template_path, 'r', encoding='utf-8') as f:
            html = f.read()
        return HTMLResponse(content=html)

    async def run_loop(self):
        config = uvicorn.Config(self.app, host="0.0.0.0", port=self.port, log_level="error")
        server = uvicorn.Server(config)
        await server.serve()