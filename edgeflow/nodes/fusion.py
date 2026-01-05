from collections import deque
from .base import BaseNode
from ..comms import Frame
import time

class FusionNode(BaseNode):
    def __init__(self, broker, app, slop=0.1, **kwargs):
        super().__init__(broker=broker, app=app, **kwargs)
        self.input_topics = []
        self.output_topic = None
        self.slop = slop
        self.buffers = {}

    def configure(self):
        pass

    def setup(self):
        self.configure()
        self.buffers = {t: deque(maxlen=50) for t in self.input_topics}
        print(f"🔗 SyncNode Listening on: {self.input_topics} -> Output: {self.output_topic}")

    def process(self, frames):
        raise NotImplementedError
    
    def run(self):
        last_metric_publish_time = time.time() # For periodic metrics publishing
        while self.running:
            for topic in self.input_topics:
                data = self.broker.pop(topic, timeout=0.01)
                if data:
                    frame = Frame.from_bytes(data)
                    if frame:
                        self.buffers[topic].append(frame)
            
            # --- Metrics Start ---
            # FusionNode FPS and Latency measurement happens inside _try_sync after a successful fusion
            # --- Metrics End ---
            self._try_sync()

            # --- Publish Metrics periodically ---
            current_time = time.time()
            if current_time - last_metric_publish_time > self.metrics_interval_sec:
                self._publish_metrics()
                last_metric_publish_time = current_time

    def _try_sync(self):
        if not self.input_topics: return
        # [DEBUG START] 현재 버퍼 상태 훔쳐보기
        # debug_status = []
        # for t in self.input_topics:
        #     count = len(self.buffers[t])
        #     if count > 0:
        #         # 가장 오래된 데이터(0번)와 최신 데이터(-1번) 시간 확인
        #         first_ts = self.buffers[t][0].timestamp
        #         last_ts = self.buffers[t][-1].timestamp
        #         debug_status.append(f"{t}: {count}개 ({first_ts:.2f} ~ {last_ts:.2f})")
        #     else:
        #         debug_status.append(f"{t}: 0개 (EMPTY)")
        
        # print(f"🔍 Buffer Status: { ' | '.join(debug_status) }")
        # [DEBUG END]


        base_topic = self.input_topics[0]
        if not self.buffers[base_topic]:
            return 
        
        base_frame = self.buffers[base_topic][0]
        target_ts = base_frame.timestamp

        matched_frames = [base_frame]
        all_matched = True

        for topic in self.input_topics[1:]:
            match = self._find_match(topic, target_ts)
            if match:
                matched_frames.append(match)
            else:
                all_matched = False
                break 
        
        if all_matched:
            # 1. 버퍼 정리
            self.buffers[base_topic].popleft()
            for i, topic in enumerate(self.input_topics[1:]):
                self._remove_frame(topic, matched_frames[i+1])
            
            # 2. 프로세스 실행 (and measure processing latency)
            process_start_time = time.time()
            result = self.process(matched_frames)
            process_end_time = time.time()
            
            # --- Metrics Collection for FusionNode ---
            self._start_frame_timer() # For FPS
            self._record_latency('processing', process_end_time - process_start_time)
            self._record_latency('end_to_end', process_end_time - base_frame.timestamp)
            # --- End Metrics Collection ---

            # 3. 결과 전송
            if result is not None:
                if isinstance(result, Frame):
                    out_frame = result
                else:
                    out_frame = Frame(
                        frame_id=base_frame.frame_id, 
                        timestamp=base_frame.timestamp, 
                        meta={}, 
                        data=result
                    )
                
                self.send_result(out_frame)
        else:
            should_drop = False
            
            # 1. 다른 센서(라이다)의 가장 옛날 데이터가 이미 '미래'라면?
            # -> 현재 카메라 프레임(과거)은 영원히 짝을 만날 수 없음 -> 즉시 삭제
            for topic in self.input_topics[1:]:
                if self.buffers[topic]:
                    oldest_other_ts = self.buffers[topic][0].timestamp
                    # 오차 범위를 넘어서 미래에 있다면
                    if oldest_other_ts > (target_ts + self.slop):
                        should_drop = True
                        break
            
            # 2. 혹은 너무 오래된 데이터라면 (기존 타임아웃 로직 유지)
            if time.time() - target_ts > (self.slop * 2):
                should_drop = True

            if should_drop:
                # 가망 없는 프레임 과감하게 버림
                self.buffers[base_topic].popleft()
        
    def _find_match(self, topic, target_ts):
        best_frame = None
        min_diff = float('inf')
        for frame in list(self.buffers[topic]):
            diff = abs(frame.timestamp - target_ts)
            if diff <= self.slop:
                if diff < min_diff:
                    min_diff = diff
                    best_frame = frame
        return best_frame
    
    def _remove_frame(self, topic, target_frame):
        try:
            self.buffers[topic].remove(target_frame)
        except ValueError:
            pass