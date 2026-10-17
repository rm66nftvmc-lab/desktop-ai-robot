from bridge.app.protocol import AUDIO_UP, HELLO, FrameParser, encode


def test_fragmented_and_joined_frames():
    parser = FrameParser()
    first = encode(HELLO, 1, b'{"version":1}')
    second = encode(AUDIO_UP, 2, b"\x00\x01\xff\xfe")
    assert parser.feed(first[:4]) == []
    result = parser.feed(first[4:] + second)
    assert [(frame.kind, frame.sequence, frame.payload) for frame in result] == [
        (HELLO, 1, b'{"version":1}'),
        (AUDIO_UP, 2, b"\x00\x01\xff\xfe"),
    ]


def test_corrupt_frame_resynchronizes():
    parser = FrameParser()
    damaged = bytearray(encode(HELLO, 1, b"hello"))
    damaged[-1] ^= 0x80
    valid = encode(HELLO, 2, b"world")
    result = parser.feed(b"boot text\r\n" + damaged + valid)
    assert [(frame.sequence, frame.payload) for frame in result] == [(2, b"world")]
    assert parser.bad_crc == 1
