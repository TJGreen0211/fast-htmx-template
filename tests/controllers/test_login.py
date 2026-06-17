import unittest
from unittest.mock import patch, MagicMock

from fastapi import HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm

from src.controllers.login import verify_password, get_password_hash, validate_user, pwd_context


class TestVerifyPassword(unittest.TestCase):
    """Test suite for verify_password function."""

    def test_correct_password_returns_true(self):
        hashed = pwd_context.hash("secret123")
        self.assertTrue(verify_password("secret123", hashed))

    def test_wrong_password_returns_false(self):
        hashed = pwd_context.hash("secret123")
        self.assertFalse(verify_password("wrongpass", hashed))

    def test_empty_password_returns_false(self):
        hashed = pwd_context.hash("secret123")
        self.assertFalse(verify_password("", hashed))

    def test_case_sensitive_password(self):
        hashed = pwd_context.hash("Secret123")
        self.assertFalse(verify_password("secret123", hashed))

    def test_special_characters_password(self):
        password = "P@ss!w0rd#2024"
        hashed = pwd_context.hash(password)
        self.assertTrue(verify_password(password, hashed))

    def test_unicode_password(self):
        password = "password\u2603"
        hashed = pwd_context.hash(password)
        self.assertTrue(verify_password(password, hashed))

    def test_very_long_password(self):
        password = "a" * 1000
        hashed = pwd_context.hash(password)
        self.assertTrue(verify_password(password, hashed))


class TestGetPasswordHash(unittest.TestCase):
    """Test suite for get_password_hash function."""

    def test_returns_string(self):
        result = get_password_hash("mypass")
        self.assertIsInstance(result, str)

    def test_hash_is_not_plain_text(self):
        result = get_password_hash("mypass")
        self.assertNotEqual(result, "mypass")

    def test_different_passwords_produce_different_hashes(self):
        hash1 = get_password_hash("pass1")
        hash2 = get_password_hash("pass2")
        self.assertNotEqual(hash1, hash2)

    def test_same_password_produces_different_hashes_each_call(self):
        hash1 = get_password_hash("samepass")
        hash2 = get_password_hash("samepass")
        self.assertNotEqual(hash1, hash2)

    def test_hash_verifies_against_original(self):
        hashed = get_password_hash("testpass")
        self.assertTrue(verify_password("testpass", hashed))

    def test_hash_format_starts_with_bcrypt_identifier(self):
        hashed = get_password_hash("testpass")
        self.assertTrue(hashed.startswith("$2b$") or hashed.startswith("$2a$"))


class TestValidateUser(unittest.IsolatedAsyncioTestCase):
    """Test suite for validate_user async function."""

    def setUp(self):
        self.valid_form = OAuth2PasswordRequestForm(username="testuser", password="correctpass")
        self.hashed_password = pwd_context.hash("correctpass")
        self.mock_db_user = MagicMock()
        self.mock_db_user.username = "testuser"
        self.mock_db_user.password = self.hashed_password
        self.mock_db_user.id = 1

    @patch("src.controllers.login.User")
    async def test_valid_credentials_returns_user(self, MockUser):
        MockUser.load.return_value = self.mock_db_user

        result = await validate_user(self.valid_form)

        self.assertIsNotNone(result)
        self.assertEqual(result.username, "testuser")
        MockUser.load.assert_called_once()

    @patch("src.controllers.login.User")
    async def test_nonexistent_user_raises_401(self, MockUser):
        MockUser.load.return_value = None

        with self.assertRaises(HTTPException) as ctx:
            await validate_user(self.valid_form)

        self.assertEqual(ctx.exception.status_code, status.HTTP_401_UNAUTHORIZED)
        self.assertEqual(ctx.exception.detail, "Incorrect username or password")

    @patch("src.controllers.login.User")
    async def test_wrong_password_raises_401(self, MockUser):
        wrong_hash = pwd_context.hash("differentpass")
        self.mock_db_user.password = wrong_hash
        MockUser.load.return_value = self.mock_db_user

        with self.assertRaises(HTTPException) as ctx:
            await validate_user(self.valid_form)

        self.assertEqual(ctx.exception.status_code, status.HTTP_401_UNAUTHORIZED)
        self.assertEqual(ctx.exception.detail, "Incorrect username or password")

    @patch("src.controllers.login.User")
    async def test_empty_password_raises_401(self, MockUser):
        empty_form = OAuth2PasswordRequestForm(username="testuser", password="")
        MockUser.load.return_value = self.mock_db_user

        with self.assertRaises(HTTPException) as ctx:
            await validate_user(empty_form)

        self.assertEqual(ctx.exception.status_code, status.HTTP_401_UNAUTHORIZED)

    @patch("src.controllers.login.User")
    async def test_user_not_found_returns_generic_error_message(self, MockUser):
        MockUser.load.return_value = None

        with self.assertRaises(HTTPException) as ctx:
            await validate_user(self.valid_form)

        self.assertNotIn("testuser", ctx.exception.detail)

    @patch("src.controllers.login.User")
    async def test_load_called_with_correct_username_term(self, MockUser):
        MockUser.load.return_value = self.mock_db_user

        await validate_user(self.valid_form)

        call_args = MockUser.load.call_args
        self.assertIsNotNone(call_args)

    def test_multiple_validation_scenarios(self):
        cases = [
            ("short", "p"),
            ("numeric", "12345678"),
            ("mixed", "P@ss123"),
        ]
        for label, password in cases:
            with self.subTest(label=label):
                hashed = get_password_hash(password)
                self.assertTrue(verify_password(password, hashed))
                self.assertFalse(verify_password(password + "x", hashed))


if __name__ == "__main__":
    unittest.main()
