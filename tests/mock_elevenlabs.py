"""A local stand-in for the ElevenLabs HTTP API: text-to-speech, history list, history audio. It generates real audio (flite) so the adapter's
download/convert path runs for real, and it counts every generation request, which is what "never pay twice" is measured against.
This tests OUR adapter's behaviour (requests, resume, history lookup). It says nothing about the real service: that stays UNTESTED."""
import json, subprocess, tempfile, threading, time, os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse


class Mock:
    def __init__(self, key="test-key"):
        self.key, self.count, self.texts, self.history, self.lock = key, 0, [], [], threading.Lock()
        self.requests = []  # full request bodies and voice ids, to check what was really sent
        outer = self

        class H(BaseHTTPRequestHandler):
            def log_message(self, *a):
                pass

            def _auth(self):
                if self.headers.get("xi-api-key") != outer.key:
                    self.send_response(401); self.end_headers(); self.wfile.write(b'{"detail":"invalid api key"}')
                    return False
                return True

            def do_POST(self):
                if not self._auth():
                    return
                u = urlparse(self.path)
                if not u.path.startswith("/v1/text-to-speech/"):
                    self.send_response(404); self.end_headers(); return
                body = json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0))))
                voice = u.path.rsplit("/", 1)[-1]
                with tempfile.TemporaryDirectory() as td:
                    wav = os.path.join(td, "o.wav")
                    subprocess.run(["ffmpeg", "-v", "error", "-nostdin", "-y", "-f", "lavfi", "-i", f"flite=text='{body['text'].replace(chr(39), '')}':voice=slt", "-ar", "24000", wav], check=True)
                    audio = open(wav, "rb").read()
                with outer.lock:
                    outer.count += 1
                    n = outer.count
                    outer.texts.append(body["text"])
                    outer.requests.append({"voice": voice, "model": body.get("model_id"), "settings": body.get("voice_settings"), "text": body["text"]})
                    outer.history.append({"history_item_id": f"h{n}", "voice_id": voice, "text": body["text"], "date_unix": int(time.time()), "audio": audio})
                self.send_response(200)
                self.send_header("Content-Type", "audio/mpeg"); self.send_header("request-id", f"req-{n}"); self.send_header("Content-Length", str(len(audio)))
                self.end_headers(); self.wfile.write(audio)

            def do_GET(self):
                if not self._auth():
                    return
                u = urlparse(self.path)
                if u.path == "/v1/history":
                    with outer.lock:
                        items = [{k: v for k, v in h.items() if k != "audio"} for h in reversed(outer.history)]
                    b = json.dumps({"history": items}).encode()
                elif u.path.startswith("/v1/history/") and u.path.endswith("/audio"):
                    hid = u.path.split("/")[3]
                    with outer.lock:
                        b = next((h["audio"] for h in outer.history if h["history_item_id"] == hid), b"")
                else:
                    self.send_response(404); self.end_headers(); return
                self.send_response(200); self.send_header("Content-Length", str(len(b))); self.end_headers(); self.wfile.write(b)

        self.srv = ThreadingHTTPServer(("127.0.0.1", 0), H)
        self.url = f"http://127.0.0.1:{self.srv.server_address[1]}"

    def start(self):
        threading.Thread(target=self.srv.serve_forever, daemon=True).start()
        return self

    def stop(self):
        self.srv.shutdown()
