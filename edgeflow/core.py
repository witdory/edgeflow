#edgeflow/core.py
import sys
import time
import os
import asyncio
import logging
import json
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

        self.gateway_port = 8000
        self.gateway_buffer_size = 0.5

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
                logger.info("🛑 종료 신호(EOF) 수신.")
                break
            if len(packet) < 16: # 헤더(12) + JSON길이(4) = 최소 16바이트
                continue

            # 1. 헤더 분리
            header = packet[:12]
            
            # 2. 페이로드(데이터) 분리 및 구조 파싱
            # Producer가 보낸 구조: [JSON_Len(4B)] + [JSON] + [Image]
            payload = packet[12:]
            
            try:
                # JSON 길이 확인
                json_len = struct.unpack('!I', payload[:4])[0]
                json_start = 4
                json_end = 4 + json_len
                
                # (옵션) Consumer도 Producer가 보낸 메타데이터를 쓰고 싶다면 여기서 json.loads 하면 됨
                # producer_meta = json.loads(payload[json_start:json_end])

                # 3. 순수 이미지 데이터 추출
                image_bytes = payload[json_end:]

                # 4. 이미지 디코딩
                is_image_mode = (self.input_type == "image")
                input_data = self._deserialize(image_bytes, as_image=is_image_mode)

                if input_data is None:
                    continue

                # 5. 사용자 함수 실행
                result = self.consumer_func(input_data)

                if result is not None: 
                    if isinstance(result, tuple) and len(result) == 2:
                        out_frame, out_meta = result
                    else:
                        out_frame, out_meta = result, {}

                    # 타입 체크 (디버깅용)
                    if not isinstance(out_frame, (np.ndarray, bytes)):
                        logger.error(f"❌ Consumer 리턴 오류: 이미지가 아닌 {type(out_frame)} 반환됨. (cv2 함수 대입 실수 확인 필요)")
                        continue

                    final_data = self._serialize(out_frame, out_meta)
                    sender.send(header + final_data)

            except Exception as e:
                logger.error(f"Consumer Logic Error: {e}")


            
            
            

    # 1. 직렬화 (Producer/Consumer용)
    def _serialize(self, data, meta={}):
        """
        data: 이미지 (numpy array) 또는 bytes
        meta: JSON으로 보낼 딕셔너리 (기본값 {})
        """
        # 1. 이미지 인코딩
        if isinstance(data, np.ndarray):
            _, buf = cv2.imencode('.jpg', data)
            img_bytes = buf.tobytes()
        elif isinstance(data, bytes):
            img_bytes = data
        else:
            raise TypeError("이미지 데이터 타입 오류")

        # 2. 메타데이터(JSON) 인코딩
        json_str = json.dumps(meta)     # 딕셔너리 -> 문자열
        json_bytes = json_str.encode('utf-8') # 문자열 -> 바이트
        json_len = len(json_bytes)      # 길이 측정

        # 3. 패킷 합치기 (순서 중요!)
        # [JSON길이(4바이트)] + [JSON바이트] + [이미지바이트]
        # '!I'는 unsigned int (4byte)를 의미함
        packed_data = struct.pack('!I', json_len) + json_bytes + img_bytes
        
        return packed_data

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
        from fastapi.responses import StreamingResponse, JSONResponse
        
        app = FastAPI(title="EdgeFlow Gateway")

        latest_meta = {}
        lock = asyncio.Lock()
        
        # [Stream 모드]
        latest_packet = None
        last_update_time = 0.0

        # [Ordered 모드]
        packet_buffer = [] 
        
        async def tcp_server(reader, writer):
            nonlocal latest_packet, last_update_time 

            try:
                while True:
                    len_bytes = await reader.readexactly(4)
                    total_length = int.from_bytes(len_bytes, 'big')
                    data = await reader.readexactly(total_length)
                    
                    header = data[:12]
                    frame_id, timestamp = struct.unpack('!Id', header)

                    json_len = struct.unpack('!I', data[12:16])[0]
                    json_start = 16
                    json_end = 16 + json_len
                    
                    if json_len > 0:
                        try:
                            meta_bytes = data[json_start:json_end]
                            meta_dict = json.loads(meta_bytes.decode('utf-8'))
                            latest_meta.update(meta_dict)
                        except: pass

                    image_bytes = data[json_end:]

                    if self.gateway_func:
                        final_img = self.gateway_func(image_bytes)
                    else:
                        final_img = image_bytes

                    if not final_img: continue

                    current_time = time.time()

                    # [수정] self.mode 사용
                    async with lock:
                        if self.mode == "stream":
                            latest_packet = final_img
                            last_update_time = current_time
                        
                        elif self.mode == "ordered":
                            heapq.heappush(packet_buffer, (timestamp, final_img))
                            
            except asyncio.IncompleteReadError:
                pass
            except Exception as e:
                logger.error(f"Gateway TCP Error: {e}")

        async def mjpeg_gen():
            nonlocal latest_packet, last_update_time
            last_sent_time = 0.0

            while True:
                frame_to_send = None
                
                # [수정] self.mode 사용
                if self.mode == "stream":
                    async with lock:
                        if latest_packet is not None and last_update_time > last_sent_time:
                            frame_to_send = latest_packet
                            last_sent_time = last_update_time
                    
                    if frame_to_send:
                        yield _wrap_mjpeg(frame_to_send)
                        await asyncio.sleep(0.001)
                    else:
                        await asyncio.sleep(0.01)

                elif self.mode == "ordered":
                    now = time.time()
                    async with lock:
                        if packet_buffer:
                            ts, _ = packet_buffer[0]
                            if (now - ts) > self.gateway_buffer_size:
                                _, frame_to_send = heapq.heappop(packet_buffer)
                    
                    if frame_to_send:
                        yield _wrap_mjpeg(frame_to_send)
                        await asyncio.sleep(1/30)
                    else:
                        await asyncio.sleep(0.01)

        def _wrap_mjpeg(frame_bytes):
            return (b'--frameboundary\r\n'
                    b'Content-Type: image/jpeg\r\n\r\n' + frame_bytes + b'\r\n')

        @app.get("/video_stream")
        def stream():
            return StreamingResponse(mjpeg_gen(), media_type="multipart/x-mixed-replace; boundary=frameboundary")
        
        @app.get("/api/status")
        def get_status():
            return JSONResponse(content=latest_meta)
            
        @app.on_event("startup")
        async def startup():
            asyncio.create_task(asyncio.start_server(tcp_server, '0.0.0.0', 8080))

        # [수정] 로그에도 self.mode 출력
        logger.info(f"📺 Gateway Started (Mode: {self.mode}, Port: {self.gateway_port})")
        uvicorn.run(app, host="0.0.0.0", port=self.gateway_port)