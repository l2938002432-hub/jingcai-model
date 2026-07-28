import io
import unittest

from jingcai.connectivity_probe import probe


class _Response:
    def __init__(self, content: bytes, status: int = 200) -> None:
        self.content, self.status = content, status

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return None

    def read(self) -> bytes:
        return self.content


class ConnectivityProbeTests(unittest.TestCase):
    def test_reports_shape_without_leaking_match_or_odds(self) -> None:
        payload = b'{"success":true,"value":{"lastUpdateTime":"2026-07-28 10:00:00","matchInfoList":[{"subMatchList":[{"homeTeam":"secret","had":{"h":"2.0"}}]}]}}'
        code, result = probe(opener=lambda *_args, **_kwargs: _Response(payload), clock=iter([1.0, 1.02]).__next__)
        self.assertEqual(0, code)
        self.assertTrue(result["ok"])
        self.assertEqual(1, result["match_count"])
        self.assertNotIn("secret", str(result))
        self.assertNotIn("2.0", str(result))

    def test_classifies_network_json_and_schema_errors(self) -> None:
        code, result = probe(opener=lambda *_args, **_kwargs: (_ for _ in ()).throw(OSError("offline")))
        self.assertEqual((10, "OSError"), (code, result["error_class"]))
        code, result = probe(opener=lambda *_args, **_kwargs: _Response(b"not-json"), clock=iter([1.0, 1.01]).__next__)
        self.assertEqual((11, "InvalidJson"), (code, result["error_class"]))
        code, result = probe(opener=lambda *_args, **_kwargs: _Response(b'{"success":true,"value":{}}'), clock=iter([1.0, 1.01]).__next__)
        self.assertEqual((13, "SchemaChanged"), (code, result["error_class"]))
