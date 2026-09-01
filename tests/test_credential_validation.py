from __future__ import annotations

import unittest

from research_agent.credential_validation import placeholder_secret, valid_contact_email


class CredentialValidationTest(unittest.TestCase):
    def test_placeholder_secret_values_are_rejected(self) -> None:
        self.assertTrue(placeholder_secret("replace-for-real-run"))
        self.assertTrue(placeholder_secret("<real-key>"))
        self.assertFalse(placeholder_secret("unit-test-token"))

    def test_contact_email_rejects_placeholders_and_example_domains(self) -> None:
        self.assertFalse(valid_contact_email("<contact-email>"))
        self.assertFalse(valid_contact_email("agent@example.org"))
        self.assertFalse(valid_contact_email("agent@lab.example"))
        self.assertTrue(valid_contact_email("researcher@university.edu"))


if __name__ == "__main__":
    unittest.main()
