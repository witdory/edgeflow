from collections import deque
from .base import BaseNode
from ..comms import Frame


#**[검증 필요]**
class FusionNode(BaseNode):
    """
    [FusionNode]
    여러 토픽의 데이터를 구독하여, 타임스탬프(Timestamp) 기준으로 동기화(Sync)한 뒤
    process() 메서드로 전달합니다.
    """
    def __init__(self, broker, slop=0.1):
        super().__init__(broker)
        self.input_topics = []
        self.output_topic = None
        self.slop = slop
        self.buffers = {}

    def setup(self):
        """User Configure 실행 후 호출됨"""
        self.buffers = {t: deque() for t in self.input_topics}
        print(f"🔗 SyncNode Listening on: {self.input_topics} -> Output: {self.output_topic}")

    def process(self, frames):
        """사용자 구현 (frames: [frame_topic1, frame_topic2])"""
        raise NotImplementedError
    
    def run(self):
        while self.running:
            for topic in self.input_topics:
                data = self.broker.pop(topic, timeout=0.1) # 짧은 타임아웃으로 모든 토픽을 빠르게 순회
                if data:
                    frame = Frame.from_bytes(data)
                    if frame:
                        self.buffers[topic].append(frame)
            self._try_sync()

    def _try_sync(self):
        if not self.input_topics: return

        base_topic = self.input_topics[0]
        if not self.buffers[base_topic]:
            return 
        
        base_frame = self.buffers[base_topic][0]
        target_ts = base_frame.timestamp

        matched_frames = [base_frame]

        for topic in self.input_topics[1:]:
            match = self._find_match(topic, target_ts)
            if match:
                matched_frames.append(match)
            else:
                #짝이 없으면 대기(타임아웃/drop 로직 필요)
                break
                
        self.buffers[base_topic].popleft()
        result = self.process(matched_frames)

        if result and self.output_topic:
            out_frame = result if isinstance(result, Frame) else Frame(result)

            if 'topic' not in out_frame.meta:
                out_frame.meta['topic'] = self.output_topic
            
            self.broker.push(self.output_topic, out_frame.to_bytes())

    def _find_match(self, topic, target_ts):
        """오차 범위 내 가장 가까운 프레임 찾기 & 버퍼에서 제거"""
        best_frame = None
        min_diff = float('inf')

        for frame in list(self.buffers[topic]):
            diff = abs(frame.timestamp - target_ts)
            if diff <= self.slop:
                if diff < min_diff:
                    min_diff = diff
                    best_frame = frame
            
        if best_frame:
            self.buffers[topic].remove(best_frame)
            return best_frame
        return None