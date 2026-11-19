"""Audio routing regression tests that do not open physical devices."""

import sys
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from oremo import audio  # noqa: E402


class AudioRoutingTests(unittest.TestCase):
    def test_saved_label_resolves_against_current_device_list(self):
        selection = "1: Steinberg UR242, API=Core Audio"
        ur242 = (0, "Steinberg UR242", "Core Audio")
        microphone = (1, "MacBook Pro Microphone", "Core Audio")
        self.assertEqual(audio.resolve_pa_device(selection, [ur242, microphone]), ur242)
        self.assertIsNone(audio.resolve_pa_device(selection, [microphone]))

    def test_duplex_capture_uses_selected_channel_and_bgm_cues(self):
        sd = Mock()
        sd.query_devices.return_value = {"max_input_channels": 4}
        recorder = audio.Recorder()
        recorder.prepare(44100, 1, "int16", 1.0)
        engine = audio.AutoRecEngine(recorder)
        rows = {
            1: dict(pStart=0, pStop=2, rStart=0, rStop=0, nextRec=0, repeat=0),
            2: dict(pStart=2, pStop=5, rStart=1, rStop=0, nextRec=0, repeat=0),
            3: dict(pStart=5, pStop=7, rStart=0, rStop=1, nextRec=0, repeat=0),
        }
        try:
            with patch.object(audio, "sd", sd), patch.object(audio, "post"):
                engine.start(np.zeros(8), 44100, rows, 2, Mock(), lambda: False,
                             device=0, duplex_channel=2)
                sd.InputStream.assert_not_called()
                sd.OutputStream.assert_not_called()
                sd.CoreAudioSettings.assert_called_once_with(channel_map=[1])
                params = sd.Stream.call_args.kwargs
                self.assertEqual(params["device"], 0)
                self.assertEqual(params["channels"], (1, 1))
                samples = np.arange(6, dtype=np.int16).reshape(-1, 1)
                params["callback"](samples, np.zeros((6, 1)), 6, None, None)
                np.testing.assert_array_equal(recorder.end()[:, 0], [2, 3, 4])
        finally:
            engine.stop()


if __name__ == "__main__":
    unittest.main()
