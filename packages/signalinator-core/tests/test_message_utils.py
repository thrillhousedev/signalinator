"""Tests for message utilities."""

import pytest

from signalinator_core.utils.message_utils import (
    SIGNAL_MAX_MESSAGE_LENGTH,
    anonymize_group_id,
    anonymize_uuid,
    split_long_message,
)


class TestAnonymizeGroupId:
    """Tests for group ID anonymization (duplicated in utils)."""

    def test_anonymize_group_id_normal(self):
        """Test anonymizing a normal group ID."""
        group_id = "ABC123XYZ789+/=DEF456"
        result = anonymize_group_id(group_id)

        assert result.startswith("#")
        assert len(result) == 5
        assert group_id not in result

    def test_anonymize_group_id_empty(self):
        """Test anonymizing empty group ID."""
        assert anonymize_group_id("") == "#NONE"
        assert anonymize_group_id(None) == "#NONE"

    def test_anonymize_group_id_consistent(self):
        """Test consistency of hash."""
        group_id = "test-group-id"
        assert anonymize_group_id(group_id) == anonymize_group_id(group_id)


class TestAnonymizeUuid:
    """Tests for UUID anonymization (duplicated in utils)."""

    def test_anonymize_uuid_normal(self):
        """Test anonymizing a normal UUID."""
        uuid = "a1b2c3d4-e5f6-7890-abcd-ef1234567890"
        result = anonymize_uuid(uuid)

        assert result == "a1b2..."

    def test_anonymize_uuid_empty(self):
        """Test anonymizing empty string."""
        assert anonymize_uuid("") == "none"
        assert anonymize_uuid(None) == "none"


class TestSplitLongMessage:
    """Tests for message splitting functionality."""

    def test_short_message_not_split(self):
        """Test that short messages are returned as-is."""
        text = "Hello world"
        result = split_long_message(text)

        assert result == [text]

    def test_message_at_limit_not_split(self):
        """Test message exactly at limit is not split."""
        text = "x" * SIGNAL_MAX_MESSAGE_LENGTH
        result = split_long_message(text)

        assert len(result) == 1

    def test_long_message_split_at_paragraph(self):
        """Test splitting at paragraph boundary."""
        para1 = "First paragraph. " * 50
        para2 = "Second paragraph. " * 50
        text = f"{para1}\n\n{para2}"

        result = split_long_message(text, max_length=1000)

        assert len(result) >= 2
        # Parts should have part indicators
        assert "(1/" in result[0]

    def test_long_message_split_at_newline(self):
        """Test splitting at newline when no paragraph break."""
        line1 = "First line. " * 50
        line2 = "Second line. " * 50
        text = f"{line1}\n{line2}"

        result = split_long_message(text, max_length=1000)

        assert len(result) >= 2

    def test_long_message_split_at_sentence(self):
        """Test splitting at sentence boundary."""
        text = "This is a sentence. " * 150

        result = split_long_message(text, max_length=500)

        assert len(result) >= 2
        # Each part should end cleanly (with indicator)
        for part in result:
            assert part.endswith(")")

    def test_long_message_split_at_space(self):
        """Test splitting at word boundary."""
        text = "word " * 500

        result = split_long_message(text, max_length=100)

        assert len(result) >= 2
        # Words shouldn't be cut in the middle
        for part in result:
            # Remove part indicator to check content
            content = part.rsplit(" (", 1)[0] if " (" in part else part
            assert not content.endswith("wor")  # Partial word

    def test_long_message_hard_cut(self):
        """Test hard cut when no good boundary found."""
        # Single very long word
        text = "x" * 5000

        result = split_long_message(text, max_length=1000)

        assert len(result) >= 2

    def test_part_indicators_added(self):
        """Test that part indicators are added."""
        text = "Hello world. " * 200

        result = split_long_message(text, max_length=500)

        assert len(result) >= 2
        assert "(1/" in result[0]
        assert f"/{len(result)})" in result[0]
        assert f"({len(result)}/{len(result)})" in result[-1]

    def test_part_indicators_not_added_for_single(self):
        """Test that part indicators aren't added for single message."""
        text = "Short message"
        result = split_long_message(text)

        assert len(result) == 1
        assert "(" not in result[0]

    def test_empty_message(self):
        """Test splitting empty message."""
        result = split_long_message("")
        assert result == [""]

    def test_preserves_content(self):
        """Test that all content is preserved after splitting."""
        original = "Hello world. This is a test. " * 100
        result = split_long_message(original, max_length=500)

        # Remove part indicators and rejoin
        cleaned = []
        for part in result:
            if " (" in part and "/" in part:
                content = part.rsplit(" (", 1)[0]
            else:
                content = part
            cleaned.append(content)

        rejoined = " ".join(cleaned)
        # Original content should be present (possibly with spacing differences)
        assert "Hello world" in rejoined
        assert "This is a test" in rejoined
