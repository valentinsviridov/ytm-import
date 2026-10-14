import pytest

from ytm_import.matching import (
    artist_names,
    clean_line,
    normalize,
    result_score,
    similarity,
)


@pytest.mark.parametrize(
    "line",
    [
        "Miles Davis — So What",
        "  1. Miles Davis — So What  ",
        "12) Miles Davis — So What",
        "#7: Miles Davis — So What",
        "3 - Miles Davis — So What",
        "\ufeff1. Miles Davis — So What",
    ],
)
def test_clean_line_removes_numbering_and_whitespace(line):
    assert clean_line(line) == "Miles Davis — So What"


def test_clean_line_preserves_artist_names_starting_with_numbers():
    assert clean_line("1975 — Somebody Else") == "1975 — Somebody Else"


@pytest.mark.parametrize("line", ["", "  ", "\ufeff", "1. "])
def test_clean_line_handles_empty_input(line):
    assert clean_line(line) == ""


def test_normalize_removes_accents_punctuation_and_release_labels():
    assert normalize("Beyoncé — Halo (Official Video) [HD] Remastered") == (
        "beyonce halo"
    )


def test_normalize_preserves_non_latin_song_names():
    assert normalize("Кино — Группа крови") == "кино группа крови"


def test_similarity_treats_cosmetic_variants_as_identical():
    assert similarity("Beyoncé — Halo", "BEYONCE Halo (Lyrics)") == pytest.approx(1)


@pytest.mark.parametrize("query, candidate", [("", "Song"), ("Song", "!!!")])
def test_similarity_of_empty_normalized_text_is_zero(query, candidate):
    assert similarity(query, candidate) == 0


def test_candidate_with_matching_artist_outscores_a_different_song(track):
    unrelated = {"title": "Take Five", "artists": [{"name": "Dave Brubeck"}]}
    assert result_score("Miles Davis — So What", track) == pytest.approx(1)
    assert result_score("Miles Davis — So What", unrelated) < 0.58


@pytest.mark.parametrize(
    "query", ["So What", "So What Miles Davis", "Miles Davis So What Kind of Blue"]
)
def test_result_score_accepts_title_artist_and_album_variants(query, track):
    assert result_score(query, track) == pytest.approx(1)


def test_result_score_handles_missing_optional_metadata():
    assert result_score("So What", {"title": "So What"}) == pytest.approx(1)
    assert result_score("So What", {}) == 0


def test_artist_names_ignores_non_dictionary_entries():
    assert artist_names({"artists": [{"name": "A"}, None, {"name": "B"}]}) == "A; B"
