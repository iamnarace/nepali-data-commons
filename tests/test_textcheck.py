import pytest

from nepali_data_commons import textcheck as tc


def test_script_ratio():
    dev, lat = tc.script_ratio("नेपाली Nepali")
    assert 0.4 < dev < 0.6 and 0.4 < lat < 0.6
    assert tc.script_ratio("१२३ !!") == (0.0, 0.0)


def test_devanagari_issues_clean_and_dirty():
    assert tc.devanagari_issues("काठमाडौं नेपालको राजधानी हो।") == []
    assert any("replacement" in i for i in tc.devanagari_issues("नेपाल�"))
    assert any("starts with a combining" in i for i in tc.devanagari_issues("ाम राम"))
    assert any("two dependent vowel" in i for i in tc.devanagari_issues("काा"))
    assert any("mixes" in i for i in tc.devanagari_issues("१० बजे 10 बजे"))
    assert any("zero-width" in i for i in tc.devanagari_issues("‍नेपाल"))


@pytest.mark.parametrize("text,expected", [
    ("मेरो नम्बर ९८४१२३४५६७ हो", "phone number"),
    ("call +977-9841234567", "phone number"),
    ("contact me at someone@example.com", "email address"),
    ("हेर्नुहोस् https://example.com/x", "URL"),
    ("खाता नम्बर १२३४५६७८९०१२", "long digit sequence"),
    ("follow @someone_np", "@handle"),
])
def test_pii_flags_detect(text, expected):
    assert any(expected in f for f in tc.pii_flags(text)), tc.pii_flags(text)


@pytest.mark.parametrize("text", ["बजे १० मा भेटौँ।", "२०८२ सालमा", "रु. ५०० को किताब", "नेपाली वाक्य"])
def test_pii_no_false_positive_on_ordinary_numbers(text):
    assert tc.pii_flags(text) == []


def test_legacy_font_heuristic():
    assert tc.legacy_font_suspect("g]kfnsf] /fhwfgL sf7df08f}F ;xl/ x'G5 ;fy{s")
    assert not tc.legacy_font_suspect("This is ordinary English text.")
    assert not tc.legacy_font_suspect("नेपाली भाषा")


def test_dedup_normalisation_treats_digits_and_punct_alike():
    assert tc.normalize_for_dedup("भोलि १० बजे।") == tc.normalize_for_dedup("भोलि 10 बजे")


def test_near_duplicates_finds_similar_not_different():
    texts = {
        "a": "आज मौसम धेरै राम्रो छ",
        "b": "आज मौसम धेरै राम्रो छ ।",   # identical after normalisation (jaccard 1.0)
        "c": "आज मौसम धेरै राम्रो भयो",
        "d": "म बजार जान्छु किनमेल गर्न",
    }
    pairs = {(x, y) for x, y, _ in tc.near_duplicates(texts, 0.6)}
    assert ("a", "b") in pairs and ("a", "c") in pairs
    assert not any("d" in p for p in pairs)
