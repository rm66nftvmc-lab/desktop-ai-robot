"""Only public assistant text is accumulated; tool and reasoning frames are ignored."""

class CancellationUnconfirmed(RuntimeError):
    pass


class HarnessTextStream:
    def __init__(self, request_id, baseline, publish):
        self.request_id, self.baseline, self.publish = request_id, baseline, publish
        self.ours = False
        self.revision = 0
        self.blocks = {}

    def event(self, record):
        event = record.get('event', {})
        if event.get('seq', -1) <= self.baseline:
            return
        data = event.get('data', {})
        if event.get('type') == 'user/message' and data.get('source', {}).get('kind', 'user') == 'user':
            self.ours = data.get('source', {}).get('rpcId') == self.request_id
        elif event.get('type') == 'assistant/message' and self.ours:
            text = ''.join(block.get('text', '') for block in data.get('message', {}).get('content', [])
                           if block.get('type') == 'text')
            self.publish(text)
        elif event.get('type') == 'turn/end':
            self.ours = False

    def accept(self, value):
        if value.get('type') == 'snapshot':
            self.ours = False
            for record in value.get('records', []):
                self.event(record)
            state = value.get('assistantStream', {})
            self.revision = state.get('revision', 0)
            self.blocks = {}
            attempt = state.get('activeAttempt', {})
            if self.ours and attempt.get('startedAfterSeq', -1) >= self.baseline:
                for record in attempt.get('stream', []):
                    if record.get('type') == 'text-chunks':
                        index = record['index']
                        self.blocks[index] = self.blocks.get(index, '') + ''.join(record.get('texts', []))
                    elif record.get('type') == 'chunk':
                        self.chunk(record.get('chunk', {}))
                self.publish(''.join(self.blocks[i] for i in sorted(self.blocks)))
        elif value.get('type') == 'event':
            self.event(value)
        elif value.get('type') == 'assistant-stream':
            frame = value.get('frame', {})
            if frame.get('revision', 0) <= self.revision:
                return
            if frame.get('revision') != self.revision + 1:
                raise ValueError('Assistant stream revision gap; reconnect for baseline')
            self.revision = frame['revision']
            if frame.get('type') == 'start':
                self.blocks = {}
                if self.ours:
                    self.publish('')
            elif frame.get('type') == 'chunk' and self.ours:
                self.chunk(frame.get('chunk', {}))
                self.publish(''.join(self.blocks[i] for i in sorted(self.blocks)))

    def chunk(self, chunk):
        if chunk.get('type') == 'text-delta':
            index = chunk.get('index', 0)
            self.blocks[index] = self.blocks.get(index, '') + chunk.get('text', '')
        elif chunk.get('type') == 'block-end' and chunk.get('block', {}).get('type') == 'text':
            self.blocks[chunk.get('index', 0)] = chunk['block'].get('text', '')
