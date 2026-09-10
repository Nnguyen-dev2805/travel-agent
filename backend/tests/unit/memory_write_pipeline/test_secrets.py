"""Unit tests for deterministic prohibited-content detection.

Detection runs before any candidate exists: secret, payment, and
authentication material is rejected and redacted up front. Raw
prohibited values never appear in findings, logs, or assertions on
output — assertions below inspect the redacted representation only.
"""

import dataclasses

import pytest

from backend.memory.write_pipeline.secrets import (
    DETECTOR_VERSION,
    ProhibitedFinding,
    ProhibitedKind,
    detect_prohibited_content,
)

SECRET_SAMPLE = "sk-test-AbC999"
PASSWORD_SAMPLE = "hunter2x"
CARD_SAMPLE = "4111 1111 1111 1111"
PEM_BODY_SAMPLE = "MIIEpAIBAAKCAQEA7bq5sX8mZ3Q9"
TRUNCATED_BODY_SAMPLE = "MIIBoQIBAAJBAK3q7sX8mZ3Q9wX7"
PROJECT_KEY_SAMPLE = "sk-proj-abc123XYZ"
OTP_SAMPLE = "482910"


def test_detector_version_is_pinned():
    assert DETECTOR_VERSION == "prohibited-detector-v2"


def test_kind_vocabulary_is_closed():
    assert {member.value for member in ProhibitedKind} == {
        "secret",
        "payment",
        "auth",
    }


def test_ordinary_preference_text_is_clean():
    assert detect_prohibited_content("Tôi thích khách sạn yên tĩnh") is None
    assert detect_prohibited_content("I like a quiet hotel") is None
    assert detect_prohibited_content("   ") is None
    assert detect_prohibited_content("") is None


def test_secret_key_is_detected_and_redacted():
    finding = detect_prohibited_content(f"My api key is {SECRET_SAMPLE}, remember it")

    assert finding is not None
    assert finding.kind is ProhibitedKind.SECRET
    assert SECRET_SAMPLE not in finding.redacted_text
    assert SECRET_SAMPLE not in str(finding)
    assert SECRET_SAMPLE not in repr(finding)


def test_password_is_detected_as_auth_and_redacted():
    finding = detect_prohibited_content(f"password: {PASSWORD_SAMPLE}")

    assert finding is not None
    assert finding.kind is ProhibitedKind.AUTH
    assert PASSWORD_SAMPLE not in finding.redacted_text
    assert PASSWORD_SAMPLE not in str(finding)


def test_payment_card_is_detected_and_redacted():
    finding = detect_prohibited_content(f"my card {CARD_SAMPLE} expires soon")

    assert finding is not None
    assert finding.kind is ProhibitedKind.PAYMENT
    assert "4111" not in finding.redacted_text
    assert CARD_SAMPLE not in str(finding)


def test_finding_is_frozen_and_carries_no_raw_value():
    finding = detect_prohibited_content(f"token = {SECRET_SAMPLE}")
    assert finding is not None
    with pytest.raises(dataclasses.FrozenInstanceError):
        finding.redacted_text = "changed"
    assert finding.detector_version == DETECTOR_VERSION


# Adversarial: full private-key blocks, project keys, OTP, dashed PAN.


def test_full_pem_block_is_redacted_inclusive():
    text = (
        "-----BEGIN RSA PRIVATE KEY-----\n"
        f"{PEM_BODY_SAMPLE}\n"
        "-----END RSA PRIVATE KEY-----"
    )
    finding = detect_prohibited_content(text)

    assert finding is not None
    assert finding.kind is ProhibitedKind.AUTH
    assert PEM_BODY_SAMPLE not in finding.redacted_text
    assert "-----END" not in finding.redacted_text
    assert "-----BEGIN" not in finding.redacted_text
    assert PEM_BODY_SAMPLE not in str(finding)
    assert PEM_BODY_SAMPLE not in repr(finding)


def test_project_scoped_api_key_is_detected():
    finding = detect_prohibited_content(f"key is {PROJECT_KEY_SAMPLE} here")

    assert finding is not None
    assert finding.kind is ProhibitedKind.SECRET
    assert PROJECT_KEY_SAMPLE not in finding.redacted_text
    assert PROJECT_KEY_SAMPLE not in str(finding)


def test_one_time_passcode_is_detected_as_auth():
    finding = detect_prohibited_content(f"otp: {OTP_SAMPLE}")

    assert finding is not None
    assert finding.kind is ProhibitedKind.AUTH
    assert OTP_SAMPLE not in finding.redacted_text


def test_dashed_pan_is_detected():
    finding = detect_prohibited_content("card 4111-1111-1111-1111 please")

    assert finding is not None
    assert finding.kind is ProhibitedKind.PAYMENT
    assert "4111" not in finding.redacted_text


def test_ordinary_preference_text_is_never_redacted():
    text = "I love quiet hotels near central market, peaceful and private"
    assert detect_prohibited_content(text) is None


@pytest.mark.parametrize(
    ("text", "kind", "absent"),
    [
        ("deploy with ghp_AbC123xYz987 now", ProhibitedKind.SECRET, "ghp_AbC123xYz987"),
        ("hook xoxb-1234-abcdefghi here", ProhibitedKind.SECRET, "xoxb-1234-abcdefghi"),
        (
            "key AKIAIOSFODNN7EXAMPLE active",
            ProhibitedKind.SECRET,
            "AKIAIOSFODNN7EXAMPLE",
        ),
        ("recovery-code: xyz-789-abc", ProhibitedKind.AUTH, "xyz-789-abc"),
        ("cvv 123 on file", ProhibitedKind.PAYMENT, "123"),
        ("pin: 4829 please", ProhibitedKind.AUTH, "4829"),
    ],
    ids=["github-token", "slack-token", "aws-key", "recovery-code", "cvv", "pin"],
)
def test_credential_families_detect_redact_and_hide(text, kind, absent):
    finding = detect_prohibited_content(text)

    assert finding is not None
    assert finding.kind is kind
    assert absent not in finding.redacted_text
    assert absent not in str(finding)
    assert absent not in repr(finding)


def test_truncated_pem_without_end_is_redacted_through_end_of_input():
    text = (
        f"an ordinary note here\n-----BEGIN PRIVATE KEY-----\n{TRUNCATED_BODY_SAMPLE}"
    )
    finding = detect_prohibited_content(text)

    assert finding is not None
    assert finding.kind is ProhibitedKind.AUTH
    assert TRUNCATED_BODY_SAMPLE not in finding.redacted_text
    assert "-----BEGIN" not in finding.redacted_text
    assert "an ordinary note here" in finding.redacted_text
    assert TRUNCATED_BODY_SAMPLE not in str(finding)
    assert TRUNCATED_BODY_SAMPLE not in repr(finding)


def test_orphan_end_marker_line_is_redacted():
    text = "some ordinary note\na leftover line\n-----END PRIVATE KEY-----"
    finding = detect_prohibited_content(text)

    assert finding is not None
    assert finding.kind is ProhibitedKind.AUTH
    assert "-----END" not in finding.redacted_text
    assert "some ordinary note" in finding.redacted_text
    assert "a leftover line" in finding.redacted_text
