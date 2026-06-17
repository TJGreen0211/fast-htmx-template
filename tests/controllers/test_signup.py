import unittest
from unittest.mock import patch, MagicMock

from pydantic import ValidationError

from src.controllers.signup import SignupForm, SignupController


VALID_FORM_DATA = {
    "first_name": "John",
    "last_name": "Doe",
    "user_email": "john@example.com",
    "user_phone": "1234567890",
    "password": "SecurePass123!",
}


class TestSignupForm(unittest.TestCase):
    """Test suite for SignupForm Pydantic model."""

    def test_valid_form_creates_instance(self):
        form = SignupForm.model_validate(VALID_FORM_DATA)
        self.assertEqual(form.first_name, "John")
        self.assertEqual(form.last_name, "Doe")
        self.assertEqual(form.user_email, "john@example.com")
        self.assertEqual(form.user_phone, "1234567890")
        self.assertEqual(form.password, "SecurePass123!")

    def test_invalid_email_raises_validation_error(self):
        with self.assertRaises(ValidationError):
            SignupForm.model_validate({
                "first_name": "John",
                "last_name": "Doe",
                "user_email": "not-an-email",
                "user_phone": "1234567890",
                "password": "SecurePass123!",
            })

    def test_missing_at_in_email_raises(self):
        with self.assertRaises(ValidationError):
            SignupForm.model_validate({
                "first_name": "John",
                "last_name": "Doe",
                "user_email": "johnexample.com",
                "user_phone": "1234567890",
                "password": "SecurePass123!",
            })

    def test_missing_domain_in_email_raises(self):
        with self.assertRaises(ValidationError):
            SignupForm.model_validate({
                "first_name": "John",
                "last_name": "Doe",
                "user_email": "john@",
                "user_phone": "1234567890",
                "password": "SecurePass123!",
            })

    def test_missing_required_field_raises(self):
        with self.assertRaises(ValidationError):
            SignupForm.model_validate({
                "first_name": "John",
                "user_email": "john@example.com",
                "user_phone": "1234567890",
                "password": "SecurePass123!",
            })

    def test_empty_first_name_does_not_raise(self):
        form = SignupForm.model_validate({
            "first_name": "",
            "last_name": "Doe",
            "user_email": "john@example.com",
            "user_phone": "1234567890",
            "password": "SecurePass123!",
        })
        self.assertEqual(form.first_name, "")

    def test_camelcase_alias_model_dump(self):
        form = SignupForm.model_validate(VALID_FORM_DATA)
        dumped = form.model_dump(by_alias=True)
        self.assertIn("firstName", dumped)
        self.assertIn("lastName", dumped)
        self.assertIn("userEmail", dumped)
        self.assertIn("userPhone", dumped)

    def test_form_accepts_camelcase_dict_input(self):
        form = SignupForm.model_validate({
            "firstName": "Jane",
            "lastName": "Smith",
            "userEmail": "jane@example.com",
            "userPhone": "0987654321",
            "password": "StrongPass456!",
        })
        self.assertEqual(form.first_name, "Jane")
        self.assertEqual(form.last_name, "Smith")
        self.assertEqual(form.user_email, "jane@example.com")

    def test_special_characters_in_name(self):
        form = SignupForm.model_validate({
            "first_name": "María",
            "last_name": "O'Brien",
            "user_email": "maria@example.com",
            "user_phone": "1234567890",
            "password": "Pass123!",
        })
        self.assertEqual(form.first_name, "María")
        self.assertEqual(form.last_name, "O'Brien")

    def test_phone_with_formatting(self):
        form = SignupForm.model_validate({
            "first_name": "John",
            "last_name": "Doe",
            "user_email": "john@example.com",
            "user_phone": "+1 (555) 123-4567",
            "password": "Pass123!",
        })
        self.assertEqual(form.user_phone, "+1 (555) 123-4567")

    def test_snake_case_dump(self):
        form = SignupForm.model_validate(VALID_FORM_DATA)
        dumped = form.model_dump()
        self.assertIn("first_name", dumped)
        self.assertIn("last_name", dumped)
        self.assertIn("user_email", dumped)
        self.assertIn("user_phone", dumped)

    def test_email_with_plus_tag(self):
        form = SignupForm.model_validate({
            "first_name": "John",
            "last_name": "Doe",
            "user_email": "john+test@example.com",
            "user_phone": "1234567890",
            "password": "Pass123!",
        })
        self.assertEqual(form.user_email, "john+test@example.com")

    def test_email_with_subdomain(self):
        form = SignupForm.model_validate({
            "first_name": "John",
            "last_name": "Doe",
            "user_email": "john@mail.example.co.uk",
            "user_phone": "1234567890",
            "password": "Pass123!",
        })
        self.assertEqual(form.user_email, "john@mail.example.co.uk")


class TestSignupController(unittest.TestCase):
    """Test suite for SignupController."""

    def setUp(self):
        self.controller = SignupController()
        self.valid_form = SignupForm.model_validate(VALID_FORM_DATA)

    @patch("src.controllers.signup.UserInfo")
    def test_create_user_calls_info_create(self, MockUserInfo):
        mock_user = MagicMock()
        mock_user.id = 1
        mock_user.username = "john@example.com"
        MockUserInfo.create.return_value = mock_user

        result = self.controller.create_user(self.valid_form)

        self.assertEqual(result.id, 1)
        self.assertEqual(result.username, "john@example.com")
        MockUserInfo.create.assert_called_once()

    @patch("src.controllers.signup.UserInfo")
    def test_create_user_passes_correct_username(self, MockUserInfo):
        MockUserInfo.create.return_value = MagicMock()

        self.controller.create_user(self.valid_form)

        call_kwargs = MockUserInfo.create.call_args[1]
        self.assertEqual(call_kwargs["username"], "john@example.com")

    @patch("src.controllers.signup.UserInfo")
    def test_create_user_passes_correct_metadata(self, MockUserInfo):
        MockUserInfo.create.return_value = MagicMock()

        self.controller.create_user(self.valid_form)

        call_kwargs = MockUserInfo.create.call_args[1]
        metadata = call_kwargs["metadata"]
        self.assertEqual(metadata["first_name"], "John")
        self.assertEqual(metadata["last_name"], "Doe")
        self.assertEqual(metadata["phone"], "1234567890")

    @patch("src.controllers.signup.UserInfo")
    def test_create_user_passes_notification_defaults(self, MockUserInfo):
        MockUserInfo.create.return_value = MagicMock()

        self.controller.create_user(self.valid_form)

        call_kwargs = MockUserInfo.create.call_args[1]
        notification = call_kwargs["notification"]
        self.assertTrue(notification["text"])
        self.assertTrue(notification["email"])

    @patch("src.controllers.signup.UserInfo")
    def test_create_user_returns_created_user(self, MockUserInfo):
        mock_user = MagicMock()
        mock_user.id = 42
        MockUserInfo.create.return_value = mock_user

        result = self.controller.create_user(self.valid_form)

        self.assertEqual(result, mock_user)
        self.assertEqual(result.id, 42)

    @patch("src.controllers.signup.UserInfo")
    def test_create_user_with_different_form_data(self, MockUserInfo):
        MockUserInfo.create.return_value = MagicMock()

        other_form = SignupForm.model_validate({
            "first_name": "Alice",
            "last_name": "Wonder",
            "user_email": "alice@wonderland.com",
            "user_phone": "9998887777",
            "password": "WonderPass!",
        })
        self.controller.create_user(other_form)

        call_kwargs = MockUserInfo.create.call_args[1]
        self.assertEqual(call_kwargs["username"], "alice@wonderland.com")
        self.assertEqual(call_kwargs["metadata"]["first_name"], "Alice")
        self.assertEqual(call_kwargs["metadata"]["last_name"], "Wonder")
        self.assertEqual(call_kwargs["metadata"]["phone"], "9998887777")

    @patch("src.controllers.signup.UserInfo")
    def test_create_user_password_passed_to_create(self, MockUserInfo):
        MockUserInfo.create.return_value = MagicMock()

        self.controller.create_user(self.valid_form)

        call_kwargs = MockUserInfo.create.call_args[1]
        self.assertEqual(call_kwargs["password"], "SecurePass123!")

    @patch("src.controllers.signup.UserInfo")
    def test_create_user_propagates_exception(self, MockUserInfo):
        MockUserInfo.create.side_effect = ValueError("DB error")

        with self.assertRaises(ValueError) as ctx:
            self.controller.create_user(self.valid_form)

        self.assertIn("DB error", str(ctx.exception))


if __name__ == "__main__":
    unittest.main()
