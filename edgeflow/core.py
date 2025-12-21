#edgeflow/core.py
import sys
import time
import os
import asyncio
import logging
import json
from .comms import RedisBroker, GatewaySender, Frame
import struct
import numpy as np
import cv2
import inspect

# 로거 설정
logging.basicConfig(level=logging.INFO, format='[%(name)s] %(message)s')
logger = logging.getLogger("EdgeFlow")

class EdgeApp:
    def __init__(self, name):
        self.name = name
        self.producer_func = None
        self.consumer_func = None
        self.gateway_func = None

        # self.mode = "stream"
        self.max_redis_size = 1
        self.fps = 30
        self.replicas = 1

        self.gateway_port = 8000
        self.gateway_buffer_size = 0.0

    # --- Decorators ---
    def producer(self, mode="stream", fps=30, queue_size=1):
        def decorator(func):
            self.producer_func = func
            self.max_redis_size = queue_size
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

    def gateway(self, port=8000, mode=None, buffer_size=0.5):
        def decorator(func):
            self.gateway_func = func
            self.gateway_port = port
            if mode:
                self.mode = mode
            self.gateway_buffer_size = buffer_size
            return func
        return decorator

    # --- Runtime Entrypoint ---
    def run(self, role = None):

        if role is None:
            if len(sys.argv) > 1:
                role = sys.argv[1]
            else:
                role = "consumer"

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
        logger.info(f"🚀 Producer 시작 (REDIS_BUFFER: {self.max_redis_size}, FPS: {self.fps})")
        frame_id = 0
        while True:
            start = time.time()
            try:
                raw_data = self.producer_func() # 사용자 함수 실행
                if raw_data is None: break

                # # 데이터 소진 처리
                # if raw_data is None:
                #     if self.mode == "batch":
                #         logger.info("✅ Batch 완료. 종료 신호(EOF) 전송.")
                #         for _ in range(self.replicas): 
                #             broker.push(b"EOF")
                #         break
                #     else:
                #         logger.warning("⚠️ 스트림 끊김. 재시도...")
                #         time.sleep(1); 
                #         continue

                frame = Frame(frame_id=frame_id, timestamp=time.time(), data=raw_data)
                packet = frame.to_bytes()
                
                
                """ 
                원래 redis list의 길이를 1로 고정하였으나, 
                일시적 지연에 의해 fps가 떨어질때를 대비해 
                2중 버퍼로 redis list의 길이를 조절할 수 있도록 함
                """
                broker.push(packet)
                broker.trim(self.max_redis_size)
                

                frame_id += 1
                elapsed = time.time() - start
                time.sleep(max(0, (1.0/self.fps) - elapsed))
            

                

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
            raw_packet = broker.pop(timeout=1)
            
            if not raw_packet: continue
            if raw_packet == b"EOF":
                logger.info("🛑 종료 신호(EOF) 수신.")
                break
            if len(raw_packet) < 16: # 헤더(12) + JSON길이(4) = 최소 16바이트
                continue
            # Producer가 보낸 구조: [JSON_Len(4B)] + [JSON] + [Image]

            is_image = (self.input_type == "image")
            frame = Frame.from_bytes(raw_packet, is_image=is_image)

            if frame is None: continue

            try:
                result = self.consumer_func(frame.data)

                if result is not None:
                    # 유저 커스텀 consumer가 tuple을 리턴한다면 첫요소는 프레임데이터, 두번째 요소는 메타데이터
                    if isinstance(result, tuple) and len(result) == 2:
                        out_img, out_meta = result
                    else:
                        out_img, out_meta = result, {}
            
                    response_frame = Frame(
                        frame_id = frame.frame_id,
                        timestamp = frame.timestamp,
                        meta = out_meta,
                        data = out_img
                    )
                    sender.send(response_frame.to_bytes())
            except Exception as e:
                logger.error(f"Consumer Logic Error: {e}")



    def _run_gateway(self):
        import uvicorn
        from fastapi import FastAPI
        from fastapi.responses import StreamingResponse, JSONResponse
        import asyncio
        import heapq    

        app = FastAPI(title="EdgeFlow Gateway")

        # 1. 상태 관리 통합 (state 객체 하나로 통일)

        packet_buffer = []
        state = {"meta": {}}
        lock = asyncio.Lock()

        # 유저 핸들러 설정 (클래스면 setup, on_message 실행, 함수면 그대로 실행)
        gateway_instance = None
        if inspect.isclass(self.gateway_func):
            gateway_instance = self.gateway_func()
            if hasattr(gateway_instance, 'setup'):
                gateway_instance.setup()
            handler = gateway_instance.on_message
        else:
            handler = self.gateway_func

        async def tcp_server(reader, writer):
            try:
                while True:
                    len_bytes = await reader.readexactly(4)
                    total_length = int.from_bytes(len_bytes, 'big')
                    payload = await reader.readexactly(total_length)

                    frame = Frame.from_bytes(payload)
                    if not frame: continue

                    # 유저 핸들러 실행
                    processed_data = handler(frame.data, frame.meta)

                    # 결과가 넘파이든 바이트든 전송용(bytes)으로 강제 변환
                    if processed_data is not None:
                        output_frame = Frame(
                            frame_id=frame.frame_id, 
                            timestamp=frame.timestamp, 
                            meta=frame.meta, 
                            data=processed_data
                        )
                        final_bytes = output_frame.get_data_bytes()
                        
                        async with lock:
                            heapq.heappush(packet_buffer, (frame.timestamp, final_bytes))
                            state["meta"].update(frame.meta)

            except Exception as e:
                logger.error(f"Gateway TCP Error: {e}")
            finally:
                writer.close()

        async def mjpeg_gen():
            last_sent_ts = 0.0
            while True:
                now = time.time()
                frame_to_send = None
                
                # 3. state에서 데이터를 가져오도록 수정
                async with lock:
                    while packet_buffer:
                        oldest_ts, _ = packet_buffer[0]
                        deadline = now - self.gateway_buffer_size

                        if oldest_ts < deadline - 0.05: #50ms 정도 마진
                            heapq.heappop(packet_buffer)
                        else:
                            break

                    while packet_buffer:
                        oldest_ts, _ = packet_buffer[0]
                        
                        # 🚨 버퍼가 0이면 시간 비교 하지말고 무조건 통과
                        should_play = (self.gateway_buffer_size == 0.0) or (oldest_ts <= now - self.gateway_buffer_size)

                        if should_play:
                            # 1. 최신 프레임이면 보냄
                            if oldest_ts > last_sent_ts:
                                _, frame_to_send = heapq.heappop(packet_buffer)
                                last_sent_ts = oldest_ts
                                break
                            # 2. 이미 보낸 과거 프레임이면 버림
                            else:
                                heapq.heappop(packet_buffer)
                        else:
                            break

                
                if frame_to_send is not None:
                    yield (b'--frameboundary\r\n'
                           b'Content-Type: image/jpeg\r\n\r\n' + frame_to_send + b'\r\n')
                    await asyncio.sleep(0.001)
                else:
                    await asyncio.sleep(1 / (self.fps * 2)) # 새로운 프레임 대기

        @app.get("/video_stream")
        async def stream():
            return StreamingResponse(mjpeg_gen(), media_type="multipart/x-mixed-replace; boundary=frameboundary")
        
        @app.get("/api/status")
        async def get_status():
            async with lock:
                return JSONResponse(content=state["meta"])
            
        @app.on_event("startup")
        async def startup():
            # TCP 서버 시작 (포트 8080)
            asyncio.create_task(asyncio.start_server(tcp_server, '0.0.0.0', 8080))

        logger.info(f"📺 Gateway Started (Port: {self.gateway_port})")
        uvicorn.run(app, host="0.0.0.0", port=self.gateway_port)