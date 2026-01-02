# edgeflow/nodes/sequencer.py
import heapq
from .base import BaseNode
from ..comms import Frame

class SequencerNode(BaseNode):
    def __init__(self, broker, buffer_size=30):
        super().__init__(broker)
        self.buffer = [] # 최소 힙 (Min-Heap)
        self.next_frame_id = 0
        self.buffer_size = buffer_size # 너무 오래된 건 버리기 위해

    def process(self, frame):
        # 1. 버퍼에 저장 (frame_id 기준 정렬)
        # 힙에 (id, frame) 튜플로 저장
        heapq.heappush(self.buffer, (frame.frame_id, frame))

        result_frames = []

        # 2. 순서가 맞으면 방출
        while self.buffer:
            # 가장 작은 번호 확인
            smallest_id, _ = self.buffer[0]

            if smallest_id == self.next_frame_id:
                # 순서 맞음! 방출
                _, frm = heapq.heappop(self.buffer)
                result_frames.append(frm)
                self.next_frame_id += 1
            
            elif len(self.buffer) > self.buffer_size:
                # 버퍼 꽉 참 -> 이가 빠진 프레임 포기하고 강제 방출 (Skip)
                print(f"⚠️ Frame missing! Skipping {self.next_frame_id}...")
                _, frm = heapq.heappop(self.buffer)
                self.next_frame_id = frm.frame_id + 1
                result_frames.append(frm)
            else:
                # 아직 앞 번호가 안 옴 -> 대기
                break
        
        # 3. 결과 리턴 (BaseNode가 알아서 Gateway로 쏨)
        # 여러 개일 수 있으므로 리스트 처리가 필요할 수 있음
        return result_frames[-1] if result_frames else None