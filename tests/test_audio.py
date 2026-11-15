import logging

import numpy as np
import pytest

from voicecmd.events import Recorder
from voicecmd.schema import AudioConfig
from voicecmd.audio import SoundDeviceRecorder, rms


class FakeStream:
    def __init__(self, callback, samplerate, blocksize, fail_start=False):
        self.callback = callback
        self.samplerate = samplerate
        self.blocksize = blocksize
        self.fail_start = fail_start
        self.active = False
        self.closed = False
        self.starts = 0

    def start(self):
        if self.fail_start:
            raise RuntimeError("PortAudio non disponibile")
        self.starts += 1
        self.active = True

    def stop(self):
        self.active = False

    def close(self):
        self.active = False
        self.closed = True

    def feed(self, samples):
        samples = np.asarray(samples, dtype=np.float32).reshape(-1, 1)
        self.callback(samples, len(samples), None, None)


class Factory:
    def __init__(self, fail_start=False):
        self.streams: list[FakeStream] = []
        self.fail_start = fail_start

    def __call__(self, callback, samplerate, blocksize):
        s = FakeStream(callback, samplerate, blocksize, self.fail_start)
        self.streams.append(s)
        return s

    @property
    def last(self) -> FakeStream:
        return self.streams[-1]


def block(value, n=512):
    return np.full(n, value, dtype=np.float32)


def warm(preroll_ms=300, silence_rms=0.005):
    f = Factory()
    r = SoundDeviceRecorder(
        AudioConfig(keep_stream_open=True, preroll_ms=preroll_ms, silence_rms=silence_rms),
        stream_factory=f,
    )
    return r, f


def cold(silence_rms=0.005):
    f = Factory()
    r = SoundDeviceRecorder(
        AudioConfig(keep_stream_open=False, silence_rms=silence_rms), stream_factory=f
    )
    return r, f


def test_satisfies_protocol():
    r, _ = warm()
    assert isinstance(r, Recorder)


def test_rms():
    assert rms(np.zeros(0, dtype=np.float32)) == 0.0
    assert rms(block(0.5)) == pytest.approx(0.5)


def test_blocks_concatenated_cold():
    r, f = cold()
    r.start()
    blocks = [block(0.1 * (i + 1)) for i in range(3)]
    for b in blocks:
        f.last.feed(b)
    audio = r.stop()
    assert audio.dtype == np.float32
    np.testing.assert_array_equal(audio, np.concatenate(blocks))


def test_blocks_concatenated_warm_without_preroll():
    r, f = warm(preroll_ms=0)
    f.last.feed(block(0.9))  # prima di start: scartato
    r.start()
    f.last.feed(block(0.1))
    f.last.feed(block(0.2))
    audio = r.stop()
    np.testing.assert_array_equal(audio, np.concatenate([block(0.1), block(0.2)]))


def test_silence_returns_empty():
    r, f = cold(silence_rms=0.005)
    r.start()
    f.last.feed(block(0.001))
    f.last.feed(block(0.0))
    audio = r.stop()
    assert audio.size == 0
    assert audio.dtype == np.float32


def test_preroll_prepends_exact_samples():
    r, f = warm(preroll_ms=300)  # 300 ms a 16 kHz = 4800 campioni
    # 12 blocchi da 512 = 6144 campioni prima del trigger
    pre = np.arange(12 * 512, dtype=np.float32) / 10000 + 0.1
    for i in range(12):
        f.last.feed(pre[i * 512:(i + 1) * 512])
    r.start()
    f.last.feed(block(0.5))
    audio = r.stop()
    assert len(audio) == 4800 + 512
    np.testing.assert_array_equal(audio[:4800], pre[-4800:])
    np.testing.assert_array_equal(audio[4800:], block(0.5))


def test_preroll_shorter_than_buffer():
    r, f = warm(preroll_ms=300)
    f.last.feed(block(0.2, 1000))  # meno del pre-roll disponibile
    r.start()
    f.last.feed(block(0.5))
    audio = r.stop()
    assert len(audio) == 1000 + 512


def test_preroll_not_reused_between_recordings():
    r, f = warm(preroll_ms=300)
    f.last.feed(block(0.2, 4800))
    r.start()
    f.last.feed(block(0.5))
    r.stop()
    r.start()  # nessun blocco arrivato fra le due registrazioni
    f.last.feed(block(0.6))
    np.testing.assert_array_equal(r.stop(), block(0.6))


def test_stop_without_start_does_not_raise():
    for r, _ in (warm(), cold()):
        audio = r.stop()
        assert audio.size == 0
        assert audio.dtype == np.float32


def test_stop_twice():
    r, f = cold()
    r.start()
    f.last.feed(block(0.3))
    assert r.stop().size == 512
    assert r.stop().size == 0


def test_cold_warms_up_once_at_startup():
    r, f = cold()
    assert len(f.streams) == 1
    assert f.streams[0].starts == 1 and f.streams[0].closed
    r.start()
    assert len(f.streams) == 2 and f.last.active
    r.stop()
    assert f.last.closed


def test_warm_keeps_stream_open():
    r, f = warm()
    assert len(f.streams) == 1 and f.last.active
    for _ in range(3):
        r.start()
        f.last.feed(block(0.3))
        r.stop()
    assert len(f.streams) == 1 and f.last.active
    r.close()
    assert f.last.closed


def test_warm_reopens_dropped_stream(caplog):
    r, f = warm()
    f.last.active = False  # lo stream è caduto (dispositivo cambiato)
    with caplog.at_level(logging.WARNING, logger="voicecmd.audio"):
        r.start()
    assert len(f.streams) == 2 and f.streams[0].closed and f.last.active
    assert "riapro" in caplog.text
    f.last.feed(block(0.3))
    assert r.stop().size == 512


def test_startup_failure_does_not_raise_and_start_retries():
    f = Factory(fail_start=True)
    r = SoundDeviceRecorder(AudioConfig(keep_stream_open=True), stream_factory=f)
    with pytest.raises(RuntimeError):
        r.start()
    f.fail_start = False
    # la factory crea stream nuovi con fail_start aggiornato
    r.start()
    f.last.feed(block(0.3))
    assert r.stop().size == 512


def test_multichannel_takes_first_channel():
    r, f = cold()
    r.start()
    data = np.stack([block(0.3), block(0.9)], axis=1)
    f.last.callback(data, len(data), None, None)
    np.testing.assert_array_equal(r.stop(), block(0.3))
