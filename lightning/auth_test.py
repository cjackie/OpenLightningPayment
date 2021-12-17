import unittest
import random
from .db import DBUtils
from .auth import JwtTokenUtils, JwtTokenPayload, Auth, AuthUserNotFound

class TestJwtTokenHash256(unittest.TestCase):

    def test_toString(self):
        secret = b"\xc2\x0f\xb8\xb0\xa1\xa7;C\xdf\x0c\xb2\xce\xc6\x0b\xd7Fa+f~\\r\x071\x81\x1d8b\x02A\x81n"
        jwt_token_utils = JwtTokenUtils()
        jwt_token_utils._jwt_secret = secret
        payload = JwtTokenPayload()
        payload.sub = "sub-294940"
        payload.iat = 1038394
        payload.exp = 2940409
        token = jwt_token_utils.sign_and_build_jwt_token(payload)
        self.assertEqual(token, "eyJ0eXAiOiAiSldUIiwgImFsZyI6ICJIUzI1NiJ9.eyJzdWIiOiAic3ViLTI5NDk0MCIsICJpYXQiOiAxMDM4Mzk0LCAiZXhwIjogMjk0MDQwOX0.jO6mOCzSeXgm7B_yIJAAVKVX4aXSWVHUlFQjRepAaes")
        self.assertIsNotNone(jwt_token_utils.verify_and_extract_payload(token))

    def test_toObject(self):
        jwt_token_str = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIxMjM0NTY3ODkwIiwibmFtZSI6IkpvaG4gRG9lIiwiaWF0IjoxNTE2MjM5MDIyLCJleHAiOjE2MzkyODE2Njd9.AtWnpTteeIFUC2VpHJejyEnOixiGUWe97isDRksttLg"
        secret = b"7\xf2\xe77U\xcd\xe5o-\xba\x9b\xf2\xb7\xd6\xe4\xf1\xa9\x07\x96\xb4\x9c\xd7\xbe\xf9\xd3QT\xf9H\x0f\x1f\x0e"
        jwt_token_utils = JwtTokenUtils()
        jwt_token_utils._jwt_secret = secret
        jwt_token_payload = jwt_token_utils.verify_and_extract_payload(jwt_token_str)
        self.assertEqual(jwt_token_payload.exp, 1639281667)
        self.assertEqual(jwt_token_payload.sub, "1234567890")
        self.assertEqual(jwt_token_payload.iat, 1516239022)

    def test_auth(self):
        auth = Auth()

        # Test creating user
        username = "testuser-" + str(random.randint(0, 10e9))
        password = "dummypass"
        email = "testuser.{}@gmail.com".format(random.randint(0, 10e9))

        account_created = auth.create_account(username, password, email)
        self.assertEqual(username, account_created.username)
        # hash(password) is stored in the DB.
        self.assertNotEqual(password, account_created.password)
        self.assertEqual(email, account_created.email)

        # Test authenticate a user
        self.assertTrue(auth.authenticate(username, password))

        DBUtils.delete("accounts", "account_id", account_created.account_id)

    def test_authFail(self):
        auth = Auth()
        with self.assertRaisesRegex(AuthUserNotFound, ".*"):
            auth.authenticate("user.notfound", "dummypass")
