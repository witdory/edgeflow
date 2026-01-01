import time
import heapq

class TimeJitterBuffer:
    """
    [공용 유틸리티] 타임스탬프 기반 지터 버퍼
    - buffer_delay > 0: 설정된 시간만큼 지연 재생 (Jitter 방지)
    - buffer_delay == 0: 들어오는 즉시 재생 (Low Latency)
    """
    def __init__(self, buffer_delay=0.2):
        self.buffer_delay = buffer_delay
        self.heap = [] # (timestamp, data_bytes)

    def push(self, frame):
        # 힙에 넣어 순서 정렬 (0.0이어도 순서 꼬임 방지용)
        # frame 객체 전체를 저장하지 않고 필요한 것만 저장할 수도 있음
        # 여기서는 범용성을 위해 frame 객체 자체를 받아서 처리한다고 가정하거나,
        # 사용자가 (ts, data)를 넘기게 할 수 있음.
        # 편의상 frame 객체를 받아서 (ts, data)로 저장.
        ts = frame.timestamp
        data = frame.get_data_bytes()
        heapq.heappush(self.heap, (ts, data))

    def pop(self):
        if not self.heap:
            return None

        # 1. 즉시 전송 모드
        if self.buffer_delay == 0.0:
            return heapq.heappop(self.heap)[1]

        # 2. 버퍼링 모드
        now = time.time()
        play_deadline = now - self.buffer_delay
        
        # [GC] 너무 오래된 데이터 삭제 (0.5초 이상 지연된 건 가망 없음)
        while self.heap and self.heap[0][0] < (play_deadline - 0.5):
            heapq.heappop(self.heap)

        if not self.heap:
            return None

        # 재생 시간 체크
        oldest_ts, data = self.heap[0]
        if oldest_ts <= play_deadline:
            heapq.heappop(self.heap)
            return data
        
        return None
    
    def clear(self):
        self.heap = []