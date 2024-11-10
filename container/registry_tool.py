#!/usr/bin/env python3

"""
A one-image registry for loading an image efficiently.

This script accepts the same arguments as `import_config`. It uses the
information to create an OCI manifest for the image and start an HTTPS server
that the image can be pulled from.
"""

import collections
import hashlib
import http
import http.server
import json
import os
import os.path
import shutil
import ssl
import sys
import tempfile

from bazel_tools.tools.python.runfiles import runfiles


# We're going to access this registry through localhost, so we don't actually
# need this to be a valid certificate - we only need to serve HTTPS. When a
# containerd snapshotter isn't configured, Docker will try plaintext HTTP too;
# when it is, it will only accept insecure registries. Generated by running
# `openssl req -x509 -newkey rsa:2048 -keyout - -days 1 -subj /CN=localhost -nodes`.
SSL_CERT = b"""
-----BEGIN PRIVATE KEY-----
MIIEvgIBADANBgkqhkiG9w0BAQEFAASCBKgwggSkAgEAAoIBAQC8lWaflSWuIE2X
rwikI/1KOp/P1B6q/x7i3GEzKfvo0G66X1EEzOH1CL2kTxsB+3pStpXZwiMSNKxr
YpuClQ5U0euMIDenFmH/Zj7k1Z+jpCSAZR4EUTgJvXyDsCXtynIL6eFAMlFkJH7X
Z6Z6+jIE31P9dVoJgTbHtASLFBMAiqMTlzLedwx8X8WELuJNMdPOdopPU8DQSCdA
F7SZrivNyCicqqJXjkg0jjhAWJgM6NriBLL7XMXwfeHi6/ub/NIAYfoR3oQMtwyt
nmSiJWKLsDg0CrQAMToetqmOYv9UQUZXe6y44m7OxYiOADkiTX5nNax/mc+1kUbS
55tcx6dxAgMBAAECggEABhg19tZVH2l/2HUZrGRVXT7Dx22tiA0yrFY+9e5Xa9DA
o1lNPwB4FPkxV8wOrWO5Mk8gTKdPhtkY8WeAaxnyGp+mIyMvaUD57c0aHz8gJ6O4
YkXiUHVngDkVexQIRcUTJntqgi6eHsRnLQL2iGbpkuq8xiYywLfiU1XoB66gZpYG
MPr0mDn2mRNIB1iifLS6rclSaiASPM2jc1GI+4KTX06UxTCWGv9/uctQU5SYCcTb
zjATn89ALPbAr/MGn1Jqb8jDfT/EVQ2D2bIu0EPs2OD03qjFkfzTj81bl9fam+yS
gMHSrK0LF8Jjt1+eMnp4iSPHoiNJoXtFkG+ylSTXgQKBgQDpQic2vAj6skJ00s4W
Oi/9aDP15DbgrMuE7ZbdHo81ff8uhxcRyXK5Gv6COMnHgSEBpReoUmCzdVgZUWdl
TLzbJp3nPTztkLa3Cpo+ShBRXtYTY20tBuvQRc9noxe8484G9Y3hV+TatHesV5g1
UkEPjBdAxgDMIvJ9TWzPZI9LqQKBgQDO+Df0A6lv8QyAeyYTOYnEsLcSrBTatvYy
hh2xZt5PxMqo419vPt2WMhfLb6Ku5pDIrGGU8pvcyhVjMhD3sA+lXGab5OriiFkv
S761o+YJGcdRlTD1mQL9eRBtC4ML1VqJ6zJGXOpEeV6afRL5pefO326VjjcjY501
2ub41MEaiQKBgQCJLZx+NgtZ1Cf9KFSHAeVjNDsKqxITA8wU+t00YVp7bQP7yvqo
PT642cU/tEIGkExm+T52gSvZnnMXQKZ8DqsqfwVyDrOcSvUJpLSdWVVLZWiksl5s
kptwOv4ExweY0KhDs3mjQtuWO3f95O3gveUBTbQHJesmIo9VXYlWVp9nMQKBgFhK
/+OzJDdDB+hPoOCWrTUhhhgLHSJo5wKKwGQL1E8HTsVZqj7U/Ma0O/5nc2lVpvJU
x5Q5I1C/TPxyQVbI3wPWNVfQAnv9Wr6Ye5UVhG7hdmxRTv+W9PWZDe7W+GK189fe
ZCYsQSxQ8pDJRq0Fn6xbGNvoPZF1T33IEryYVoCxAoGBAJKphyNqw/Muhq0dewml
Rza8cTnZbgvko60LYHUfROwUIfY3VvchlafNbJUrmLzcttNwFR8W1TIQMoz7OIl+
79B54VfweaH7en/j5wUX8Ro+Y0y9MZjavm9Gnd+fkpAPcezZjNcmP4izwrgDxGwZ
052BnHLGqkkaWIeby7DuSUe2
-----END PRIVATE KEY-----
-----
-----BEGIN CERTIFICATE-----
MIIDCTCCAfGgAwIBAgIUQz4GV3/VXL/oehyiSyql5ty6Q6AwDQYJKoZIhvcNAQEL
BQAwFDESMBAGA1UEAwwJbG9jYWxob3N0MB4XDTI0MTEwMTAwMDAwMFoXDTI0MTEw
MjAwMDAwMFowFDESMBAGA1UEAwwJbG9jYWxob3N0MIIBIjANBgkqhkiG9w0BAQEF
AAOCAQ8AMIIBCgKCAQEAvJVmn5UlriBNl68IpCP9Sjqfz9Qeqv8e4txhMyn76NBu
ul9RBMzh9Qi9pE8bAft6UraV2cIjEjSsa2KbgpUOVNHrjCA3pxZh/2Y+5NWfo6Qk
gGUeBFE4Cb18g7Al7cpyC+nhQDJRZCR+12emevoyBN9T/XVaCYE2x7QEixQTAIqj
E5cy3ncMfF/FhC7iTTHTznaKT1PA0EgnQBe0ma4rzcgonKqiV45INI44QFiYDOja
4gSy+1zF8H3h4uv7m/zSAGH6Ed6EDLcMrZ5koiVii7A4NAq0ADE6HrapjmL/VEFG
V3usuOJuzsWIjgA5Ik1+ZzWsf5nPtZFG0uebXMencQIDAQABo1MwUTAdBgNVHQ4E
FgQUt5e3Oyw/l+hHfAPDVGlYsLGoZigwHwYDVR0jBBgwFoAUt5e3Oyw/l+hHfAPD
VGlYsLGoZigwDwYDVR0TAQH/BAUwAwEB/zANBgkqhkiG9w0BAQsFAAOCAQEAICwN
Otp3uCny7aRzB90ErTJuFtC50ZatylhGiui6YJP0KgkEoMS1NXFPjgTSwlh2K0bK
Gp2Q/6XfN+fk0r6rYDOBLdaSkkZ3j/gBx2T5ZSxGdzQHh6QAt8cQuDgdDU3Q+gr4
niTa9kG0Krot91BfINYSUTt0TQnHn1QwJ32jKI0JMiIXIlwHrweqUA8F+KN9BAd7
Qq00S/RDP9+/0fzd25DGbCd/AQ0uXGpeDEy+gAHW5c3B++r+ZHoGuqnm/eW95RiV
EjOoZgP/83Q6lrXBDYwk9e284aqWhwvrzDDD5VSOUOLwH5f7B+ZVWYB9yXcfen6d
LRUhi1KbE8LpOo6yrw==
-----END CERTIFICATE-----
"""


CONFIG_MEDIA_TYPE = "application/vnd.docker.container.image.v1+json"
DIFF_MEDIA_TYPE = "application/vnd.docker.image.rootfs.diff.tar"
MANIFEST_MEDIA_TYPE = "application/vnd.docker.distribution.manifest.v2+json"


class DockerV2Registry:
    def __init__(self, repo, config_path, *layers):
        r = runfiles.Create()

        self._repo = repo
        self._registry_blobs = {}
        self._manifest = collections.OrderedDict(
            [
                ("schemaVersion", 2),
                ("mediaType", MANIFEST_MEDIA_TYPE),
                (
                    "config",
                    self._blob(
                        CONFIG_MEDIA_TYPE,
                        r.Rlocation(os.path.normpath(config_path)),
                        r.Rlocation(os.path.normpath(config_path + ".sha256")),
                    ),
                ),
                ("layers", []),
            ]
        )
        for layer_digest_path, layer_path in zip(layers[::2], layers[1::2]):
            assert layer_digest_path == layer_path + ".sha256"
            blob_data = self._blob(
                DIFF_MEDIA_TYPE,
                r.Rlocation(os.path.normpath(layer_path)),
                r.Rlocation(os.path.normpath(layer_digest_path)),
            )
            self._manifest["layers"].append(blob_data)
        self._manifest_data = json.dumps(self._manifest, separators=(",", ":")).encode()
        self._manifest_digest = (
            "sha256:" + hashlib.sha256(self._manifest_data).hexdigest()
        )

    def _blob(self, media_type, blob_path, digest_path):
        with open(digest_path) as digest_file:
            digest = "sha256:" + digest_file.read()
        size = os.path.getsize(blob_path)
        self._registry_blobs[digest] = (media_type, blob_path, size)
        return {
            "mediaType": media_type,
            "digest": digest,
            "size": size,
        }

    def handler(self):
        _manifest_data = self._manifest_data
        _manifest_digest = self._manifest_digest
        _repo = self._repo
        _registry_blobs = self._registry_blobs

        class _RegistryHandler(http.server.BaseHTTPRequestHandler):
            def _is_manifest(self, path):
                return path in (
                    "/v2/%s/manifests/latest" % _repo,
                    "/v2/%s/manifests/%s" % (_repo, _manifest_digest),
                )

            def _send_blob(self, head):
                if self.path == "/v2/":
                    self.send_response(http.HTTPStatus.OK)
                    self.end_headers()
                    return

                if self._is_manifest(self.path):
                    self.send_response(http.HTTPStatus.OK)
                    self.send_header("Content-Type", MANIFEST_MEDIA_TYPE)
                    self.send_header("Content-Length", str(len(_manifest_data)))
                    self.end_headers()
                    if not head:
                        self.wfile.write(_manifest_data)
                    return

                if self.path.startswith("/v2/%s/blobs/sha256:" % _repo):
                    _, _, digest = self.path.rpartition("/")
                    if digest in _registry_blobs:
                        media_type, path, size = _registry_blobs[digest]
                        self.send_response(http.HTTPStatus.OK)
                        self.send_header("Content-Type", media_type)
                        self.send_header("Content-Length", str(size))
                        self.end_headers()
                        if not head:
                            with open(path, "rb") as f:
                                shutil.copyfileobj(f, self.wfile)
                        return

                self.send_error(http.HTTPStatus.NOT_FOUND)
                self.end_headers()

            def do_HEAD(self):
                self._send_blob(head=True)

            def do_GET(self):
                self._send_blob(head=False)

        return _RegistryHandler

    def image_ref(self):
        return "%s@%s" % (self._repo, self._manifest_digest)


if __name__ == "__main__":
    args = sys.argv[sys.argv.index("--") + 1 :]
    registry = DockerV2Registry(*args[1:])
    httpd = http.server.HTTPServer(("127.0.0.1", 0), registry.handler())
    ctx = ssl.create_default_context(ssl.Purpose.CLIENT_AUTH)
    with tempfile.NamedTemporaryFile() as certfile:
        certfile.write(SSL_CERT)
        certfile.flush()
        ctx.load_cert_chain(certfile=certfile.name)
    httpd.socket = ctx.wrap_socket(httpd.socket, server_side=True)
    with open(args[0], "a") as f:
        f.write(
            "%s/%s\n" % ("%s:%s" % httpd.socket.getsockname(), registry.image_ref())
        )
    httpd.serve_forever()