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

    # 1. [신규] 엄격한 직렬화 메서드 (보내는 쪽)
    def _serialize(self, data):
        """
        데이터를 전송 가능한 bytes로 변환합니다.
        허용 타입: bytes, numpy.ndarray
        그 외 타입: TypeError 발생
        """
        if isinstance(data, bytes):
            return data  # 바이트는 그대로 통과
        
        elif isinstance(data, np.ndarray):
            # Numpy 배열(이미지)은 고효율 JPEG로 압축
            success, encoded_img = cv2.imencode('.jpg', data)
            if not success:
                raise ValueError("이미지 인코딩 실패")
            return encoded_img.tobytes()
        
        else:
            # 엄격한 타입 제한: 그 외에는 에러 발생
            t = type(data).__name__
            raise TypeError(f"❌ 허용되지 않는 데이터 타입입니다: {t}. (bytes 또는 numpy.ndarray만 가능)")

    # 2. [신규] 역직렬화 메서드 (받는 쪽)
    def _deserialize(self, data, as_image=True):
        """
        받은 bytes를 원본 데이터로 복원합니다.
        as_image=True이면 Numpy 이미지로 디코딩합니다.
        """
        if not as_image:
            return data  # 이미지 처리가 필요 없으면 바이트 그대로 반환
        
        # 바이트 -> Numpy 이미지로 디코딩
        nparr = np.frombuffer(data, np.uint8)
        img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
        return img

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


            
            
            

    def _run_gateway(self):
        import uvicorn
        from fastapi import FastAPI
        from fastapi.responses import StreamingResponse
        
        app = FastAPI()
        q = asyncio.Queue(maxsize=1)

    async def tcp_server(reader, writer):
        try:
            while True:
                len_bytes = await reader.readexactly(4)
                length = int.from_bytes(len_bytes, 'big')
                packet = await reader.readexactly(length)

                if len(packet) < 12:
                    continue

                header = packet[:12]
                jpeg = packet[12:]

                if q.full():
                    q.get_nowait()
                await q.put((header, jpeg))

        except asyncio.IncompleteReadError:
            logger.info("Gateway TCP client disconnected")
        except Exception as e:
            logger.error(f"Gateway TCP Error: {e}")



        async def mjpeg_gen():
            while True:
                header, jpeg = await q.get()
                yield (
                    b"--frameboundary\r\n"
                    b"Content-Type: image/jpeg\r\n\r\n"
                    + jpeg +
                    b"\r\n"
                )


        @app.get("/video_stream")
        def stream():
            return StreamingResponse(mjpeg_gen(), media_type="multipart/x-mixed-replace; boundary=frameboundary")

        @app.on_event("startup")
        async def startup():
            asyncio.create_task(asyncio.start_server(tcp_server, '0.0.0.0', 8080))

        logger.info(f"📺 Gateway 시작 (HTTP: {self.gateway_port})")
        uvicorn.run(app, host="0.0.0.0", port=self.gateway_port)