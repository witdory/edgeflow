#edgeflow/core.py
import time
import os
import asyncio
import logging
from .comms import RedisBroker, GatewaySender
import struct
import numpy as np
import cv2

# 로거 설정
logging.basicConfig(level=logging.INFO, format='[%(name)s] %(message)s')
logger = logging.getLogger("EdgeFlow")

class EdgeApp:
    def __init__(self, name):
        self.name = name
        self.producer_func = None
        self.consumer_func = None
        self.gateway_func = None
        self.mode = "stream"
        self.fps = 30
        self.replicas = 1

    # --- Decorators ---
    def producer(self, mode="stream", fps=30):
        def decorator(func):
            self.producer_func = func
            self.mode = mode
            self.fps = fps
            return func
        return decorator

    def consumer(self, replicas=1, input_type="image"):
        def decorator(func):
            self.consumer_func = func
            self.replicas = replicas
            self.input_type = input_type
            return func
        return decorator

    def gateway(self, port=8000):
        def decorator(func):
            self.gateway_func = func
            self.gateway_port = port
            return func
        return decorator

    # --- Runtime Entrypoint ---
    def run(self, role):
        redis_host = os.getenv("REDIS_HOST", "localhost")
        
        if role == "producer":
            self._run_producer(redis_host)
        elif role == "consumer":
            self._run_consumer(redis_host)
        elif role == "gateway":
            self._run_gateway()
        else:
            logger.error(f"Unknown role: {role}")

    
    # --- Internal Loops ---
    def _run_producer(self, host):
        broker = RedisBroker(host)
        logger.info(f"🚀 Producer 시작 (Mode: {self.mode}, FPS: {self.fps})")
        frame_id = 0
        while True:
            start = time.time()
            try:
                raw_data = self.producer_func() # 사용자 함수 실행

                # 데이터 소진 처리
                if raw_data is None:
                    if self.mode == "batch":
                        logger.info("✅ Batch 완료. 종료 신호(EOF) 전송.")
                        for _ in range(self.replicas): 
                            broker.push(b"EOF")
                        break
                    else:
                        logger.warning("⚠️ 스트림 끊김. 재시도...")
                        time.sleep(1); 
                        continue

                packet_data = self._serialize(raw_data)
                header = struct.pack('!Id', frame_id, time.time())
                packet = header + packet_data

                frame_id += 1
                elapsed = time.time() - start

                if self.mode == "stream":
                    broker.push(packet)
                    broker.trim(1) # 최신 상태 유지
                    time.sleep(max(0, (1.0/self.fps) - elapsed))
                elif self.mode == "ordered":
                    time.sleep(max(0, (1.0/self.fps) - elapsed))
                elif self.mode == "batch"  :
                    pass

            except Exception as e:
                logger.error(f"Producer User Function Error: {e}")
                time.sleep(1)
                continue
                

    def _run_consumer(self, host):
        broker = RedisBroker(host)
        gw_host = os.getenv("GATEWAY_HOST", "localhost")
        sender = GatewaySender(gw_host)
        logger.info(f"🧠 Consumer 시작 (Replicas: {self.replicas})")

        while True:
            packet = broker.pop(timeout=1)
            
            if not packet: continue
            if packet == b"EOF":
                logger.info("🛑 종료 신호(EOF) 수신. 종료합니다.")
                break
            if len(packet) < 12: 
                continue

            # 헤더와 데이터 분리
            payload = packet[12:]
            header = packet[:12]

            try:
                is_image_mode = (self.input_type == "image")
                input_data = self._deserialize(payload, as_image=is_image_mode)

                result = self.consumer_func(input_data) # 사용자 정의 AI 함수

                if result is not None: 
                    final_data = self._serialize(result)
                    sender.send(header + final_data)

            except Exception as e:
                logger.error(f"Consumer User Function Error: {e}")


            
            
            

    # 1. 직렬화 (Producer/Consumer용)
    def _serialize(self, data):
        if isinstance(data, bytes): return data
        if isinstance(data, np.ndarray):
            _, buf = cv2.imencode('.jpg', data)
            return buf.tobytes()
        raise TypeError("지원되지 않는 데이터 타입")

    # 2. 역직렬화 (Consumer용) - Gateway는 사용 안 함!
    def _deserialize(self, data, as_image=True):
        """
        [수정됨] as_image 인자를 받도록 복구하여 Consumer 호출과 호환
        """
        if not as_image:
            return data
        
        # 바이트 -> Numpy 이미지로 디코딩
        nparr = np.frombuffer(data, np.uint8)
        img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
        return img

    def _run_gateway(self):
        import uvicorn
        from fastapi import FastAPI
        from fastapi.responses import StreamingResponse
        
        app = FastAPI()
        # [검증된 코드 방식] Queue를 여기서 생성
        q = asyncio.Queue(maxsize=1)

        async def tcp_server(reader, writer):
            try:
                while True:
                    # 1. 길이 읽기
                    len_bytes = await reader.readexactly(4)
                    length = int.from_bytes(len_bytes, 'big')
                    
                    # 2. 데이터 읽기 (헤더+이미지Bytes)
                    data = await reader.readexactly(length)
                    
                    # [중요] Gateway는 역직렬화 하지 않음! Bytes 그대로 유지
                    # 사용자가 view 함수를 정의했다면 호출하되, 데이터는 bytes임
                    final = self.gateway_func(data) if self.gateway_func else data
                    
                    if final:
                        if q.full():
                            try: q.get_nowait()
                            except: pass
                        await q.put(final) # Bytes 넣기

            except asyncio.IncompleteReadError:
                pass
            except Exception as e:
                logger.error(f"Gateway TCP Error: {e}")

        async def mjpeg_gen():
            while True:
                packet = await q.get()
                # [검증된 코드 방식] 헤더(12바이트) 제거 후 이미지 데이터만 전송
                frame_data = packet[12:]
                
                # Bytes + Bytes 결합이므로 에러 없음
                yield (b'--frameboundary\r\n'
                       b'Content-Type: image/jpeg\r\n\r\n' + frame_data + b'\r\n')

        @app.get("/video_stream")
        def stream():
            return StreamingResponse(mjpeg_gen(), media_type="multipart/x-mixed-replace; boundary=frameboundary")

        @app.on_event("startup")
        async def startup():
            # [검증된 코드 방식] create_task로 비동기 실행
            asyncio.create_task(asyncio.start_server(tcp_server, '0.0.0.0', 8080))

        logger.info(f"📺 Gateway 시작 (HTTP: {self.gateway_port})")
        uvicorn.run(app, host="0.0.0.0", port=self.gateway_port)