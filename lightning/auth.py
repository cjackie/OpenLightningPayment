


import random
import json
import os
import hmac
import hashlib
import base64
import time

# TODO: this way of generating and storing the secret is not scalable. It 
# will have problems when we scale it into multiple servers.
_jwt_secret = os.urandom(32)

class JwtTokenDecodeError(Exception):

    def __init__(self, error_message):
        Exception.__init__(self, error_message)


def _hmac_hash256(msg: str, secret: bytes) -> bytes:
    return hmac.HMAC(secret, msg, digestmod=hashlib.sha256).digest()

# This is for decoding base64 str because the padding is strict in base64 module.
def _add_mssing_padding(base64_encoded: str):
    missing_padding = 4 - len(base64_encoded) % 4
    if missing_padding:
        base64_encoded += "=" * missing_padding
    return base64_encoded

def _remove_padding(base64_encoded: str):
    padding_start = base64_encoded.rfind("=")
    if padding_start >= 0:
        return base64_encoded[:padding_start]
    return base64_encoded

class JwtTokenPayload():
    def __init__(self):
        # The "sub" (subject) claim identifies the principal that is the subject of the JWT.
        self.sub = ""
        # It stands for "Issued At" in UNIX time in seconds.   
        self.iat = 0
        # It stands for "Expiration Time" in UNIX time in seconds.
        self.exp = 0

# Reference for the young: https://jwt.io/#debugger-io. 
# Reference for human: https://jwt.io/introduction. 
# Reference for the dead: https://datatracker.ietf.org/doc/html/rfc7519.
class JwtTokenUtils():
    def __init__(self, jwt_secret: bytes):
        assert len(jwt_secret) == 32
        self._jwt_secret = jwt_secret
    
    def build_jwt_token(self, jwt_token_payload: JwtTokenPayload) ->  str:
        header = json.dumps({
            "typ": "JWT",
            "alg": "HS256"
        })

        payload = json.dumps({
            "sub": jwt_token_payload.sub,
            "iat": jwt_token_payload.iat,
            "exp": jwt_token_payload.exp
        })

        base64url_header = _remove_padding(base64.urlsafe_b64encode(header.encode("ascii")).decode("ascii"))
        base64url_payload = _remove_padding(base64.urlsafe_b64encode(payload.encode("ascii")).decode("ascii"))

        # Sign it with HMAC-SHA256
        msg = base64url_header + "." + base64url_payload
        signature = _hmac_hash256(msg.encode("ascii"), self._jwt_secret)
        base64url_signature = _remove_padding(base64.urlsafe_b64encode(signature).decode("ascii"))
        return base64url_header + "." + base64url_payload + "." + base64url_signature

    def verify_and_extract_payload(self, jwt_token: str) -> JwtTokenPayload:
        parts = jwt_token.split(".")
        if len(parts) != 3:
            raise JwtTokenDecodeError("JWT Token must have 3 parts (header, payload, signature)")

        # jwt_token is valid. Next, we unpack the content.
        try:
            header = json.loads(base64.urlsafe_b64decode(_add_mssing_padding(parts[0])))
            if "alg" not in header or header["alg"] != "HS256":
                raise Exception("Only support alg=HS256")
            if "typ" not in header or header["typ"] != "JWT":
                raise Exception("Not a JTW token")
        except Exception as e:
            raise JwtTokenDecodeError("Failed to decode the JWT Token header and payload: {}".format(str(e)))

        # Verify signature
        msg = parts[0] + "." + parts[1]
        expected_signature = _hmac_hash256(msg.encode("ascii"), self._jwt_secret)
        if expected_signature != base64.urlsafe_b64decode(_add_mssing_padding(parts[2])):
            print(expected_signature)
            print(base64.urlsafe_b64decode(parts[2]))
            raise JwtTokenDecodeError("JWT Token signature is not valid.")

        # jwt_token is valid. Next, we unpack the content.
        try:
            payload = json.loads(base64.urlsafe_b64decode(_add_mssing_padding(parts[1])))
        except Exception as e:
            raise JwtTokenDecodeError("Failed to decode the JWT Token header and payload: {}".format(str(e)))

        jwt_token_payload = JwtTokenPayload()
        jwt_token_payload.sub = payload.get("sub", "")
        jwt_token_payload.iat = payload.get("iat", 0)
        jwt_token_payload.exp = payload.get("exp", 0)
        return jwt_token_payload

