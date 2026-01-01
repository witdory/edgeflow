#edgeflow/comms/frame.py
import time
import struct
import json
import numpy as np
import cv2

class NumpyEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, (np.int_, np.intc, np.intp, np.int8,
                            np.int16, np.int32, np.int64, np.uint8,
                            np.uint16, np.uint32, np.uint64)):
            return int(obj)
        elif isinstance(obj, (np.float_, np.float16, np.float32, np.float64)):
            return float(obj)
        elif isinstance(obj, (np.ndarray,)):
            return obj.tolist()
        return json.JSONEncoder.default(self, obj)

class Frame:
    """
    EdgeFlow 데이터 전송 표준 객체
    - Numpy(이미지)와 Bytes(전송 데이터) 상태를 모두 처리 가능
    - Gateway 성능 최적화를 위한 avoid_decode 옵션 지원
    """
    def __init__(self, frame_id=0, timestamp=0.0, meta=None, data=None):
        self.frame_id = frame_id
        self.timestamp = timestamp
        self.meta = meta or {}
        
        # [Latency Tracking] 생성 시점 기록
        if 'trace' not in self.meta:
            self.meta['trace'] = {}
        if 't0' not in self.meta['trace']:
            self.mark('t0')

        self.data = data  # 타입: numpy.ndarray(이미지) 또는 bytes(인코딩됨)

    def mark(self, step_name):
        """현재 시간을 기록 (타임스탬프)"""
        self.meta['trace'][step_name] = time.time()

    def analyze_latency(self):
        """지연 시간 분석 결과 반환 (ms 단위)"""
        trace = self.meta['trace']
        t0 = trace.get('t0', time.time())
        current = trace.get('gateway_in', time.time())
        
        return {
            "total": (current - t0) * 1000,
            "breakdown": trace
        }

    @classmethod
    def from_bytes(cls, raw_bytes, avoid_decode=False):
        """
        네트워크 패킷(Bytes) -> Frame 객체 변환
        :param avoid_decode: True일 경우 이미지 디코딩을 건너뛰고 bytes 상태로 유지 (Gateway용)
        """
        # 헤더 최소 길이(16 bytes) 체크
        if not raw_bytes or len(raw_bytes) < 16:
            return None
        
        try:
            # 1. 고정 헤더 파싱 (Frame ID, Timestamp) - 12 bytes
            f_id, ts = struct.unpack('!Id', raw_bytes[:12])
            
            # 2. 메타데이터 길이 파싱 - 4 bytes
            json_len = struct.unpack('!I', raw_bytes[12:16])[0]
            
            # 3. 메타데이터 바디 파싱
            meta_end_idx = 16 + json_len
            meta_bytes = raw_bytes[16:meta_end_idx]
            meta = json.loads(meta_bytes.decode('utf-8'))
            
            # 4. 데이터 페이로드 추출
            payload = raw_bytes[meta_end_idx:]

            # [핵심 로직] 디코딩 여부 결정
            # payload가 있고, avoid_decode가 False일 때만 Numpy로 변환
            if not avoid_decode and len(payload) > 0:
                # 이미지 데이터라고 가정하고 디코딩 시도
                nparr = np.frombuffer(payload, np.uint8)
                img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
                # 디코딩 성공 시 Numpy 배열로 교체, 실패 시 bytes 유지(일반 데이터일 수 있음)
                if img is not None:
                    payload = img
                
            return cls(frame_id=f_id, timestamp=ts, meta=meta, data=payload)
            
        except Exception as e:
            # 상용에서는 로깅 필요 (print는 디버깅용)
            print(f"[Frame Error] Deserialization failed: {e}")
            return None

    def to_bytes(self):
        """Frame 객체 -> 네트워크 패킷(Bytes) 변환"""
        data_bytes = b""

        # 1. 데이터 타입 처리
        if isinstance(self.data, np.ndarray):
            success, buf = cv2.imencode('.jpg', self.data)
            if success:
                data_bytes = buf.tobytes()
        elif isinstance(self.data, bytes):
            data_bytes = self.data
        
        # 2. 메타데이터 직렬화 (cls=NumpyEncoder 추가!)
        # AI 결과값(score 등)이 Numpy 타입이어도 에러가 안 나게 처리
        meta_bytes = json.dumps(self.meta, cls=NumpyEncoder).encode('utf-8')
        
        # 3. 헤더 패킹 (강제 형변환 적용 확인됨 ✅)
        header = struct.pack('!Id', int(self.frame_id), float(self.timestamp))
        meta_len_header = struct.pack('!I', len(meta_bytes))
        
        return header + meta_len_header + meta_bytes + data_bytes

    def get_data_bytes(self):
        """WebInterface 등 외부 송출을 위해 순수 데이터만 Bytes로 반환"""
        if isinstance(self.data, np.ndarray):
            success, buf = cv2.imencode('.jpg', self.data)
            return buf.tobytes() if success else b""
        
        return self.data if isinstance(self.data, bytes) else b""