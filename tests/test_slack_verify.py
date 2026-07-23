import hashlib
import hmac
import importlib.util
import sys
from pathlib import Path
import unittest


def _load(module_name, filename):
    path = Path(__file__).resolve().parents[1] / "scripts" / "slack" / filename
    spec = importlib.util.spec_from_file_location(module_name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


slack_verify = _load("slack_verify", "slack_verify.py")

SECRET = "8f742231b10e8888abcd99yyyzzz85a5"


def _sign(body, timestamp, secret=SECRET):
    basestring = f"{slack_verify.VERSION}:{timestamp}:{body}".encode()
    digest = hmac.new(secret.encode(), basestring, hashlib.sha256).hexdigest()
    return f"{slack_verify.VERSION}={digest}"


class VerifyTest(unittest.TestCase):
    def test_a_genuine_request_verifies(self):
        body, ts = "payload=1", "100"
        slack_verify.verify(
            body=body,
            timestamp=ts,
            signature=_sign(body, ts),
            signing_secret=SECRET,
            now=100,
        )  # does not raise

    def test_empty_secret_is_refused(self):
        with self.assertRaises(slack_verify.SignatureError):
            slack_verify.verify(
                body="x", timestamp="100", signature="v0=abc", signing_secret="", now=100
            )

    def test_missing_signature_is_rejected(self):
        with self.assertRaises(slack_verify.SignatureError):
            slack_verify.verify(
                body="x", timestamp="100", signature=None, signing_secret=SECRET, now=100
            )

    def test_missing_timestamp_is_rejected(self):
        with self.assertRaises(slack_verify.SignatureError):
            slack_verify.verify(
                body="x", timestamp=None, signature="v0=abc", signing_secret=SECRET, now=100
            )

    def test_malformed_timestamp_is_rejected(self):
        with self.assertRaises(slack_verify.SignatureError):
            slack_verify.verify(
                body="x", timestamp="not-a-number", signature="v0=abc",
                signing_secret=SECRET, now=100,
            )

    def test_stale_timestamp_is_rejected(self):
        body, ts = "payload=1", "100"
        with self.assertRaises(slack_verify.SignatureError):
            slack_verify.verify(
                body=body, timestamp=ts, signature=_sign(body, ts),
                signing_secret=SECRET, now=100 + slack_verify.MAX_AGE_SECONDS + 1,
            )

    def test_future_timestamp_is_rejected(self):
        # A timestamp far in the future is as suspicious as a stale one.
        body, ts = "payload=1", "100"
        with self.assertRaises(slack_verify.SignatureError):
            slack_verify.verify(
                body=body, timestamp=ts, signature=_sign(body, ts),
                signing_secret=SECRET, now=100 - slack_verify.MAX_AGE_SECONDS - 1,
            )

    def test_signature_mismatch_is_rejected(self):
        body, ts = "payload=1", "100"
        tampered = _sign("payload=2", ts)  # signed a different body
        with self.assertRaises(slack_verify.SignatureError):
            slack_verify.verify(
                body=body, timestamp=ts, signature=tampered,
                signing_secret=SECRET, now=100,
            )

    def test_wrong_secret_is_rejected(self):
        body, ts = "payload=1", "100"
        with self.assertRaises(slack_verify.SignatureError):
            slack_verify.verify(
                body=body, timestamp=ts, signature=_sign(body, ts, secret="other"),
                signing_secret=SECRET, now=100,
            )


if __name__ == "__main__":
    unittest.main()
