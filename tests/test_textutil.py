from voicecmd.textutil import intelligent_concatenate, normalize


def test_normalize_case_accents_punctuation():
    assert normalize("  Apri   PERCHÉ città, già!  ") == "apri perche citta gia"


def test_normalize_final_dot_and_apostrophe():
    assert normalize("Apri l'app.") == "apri l app"
    assert normalize("Apri Safari.") == "apri safari"


def test_normalize_empty():
    assert normalize("") == ""
    assert normalize(" ?! ... ") == ""


def test_normalize_keeps_digits():
    assert normalize("Volume al 50%") == "volume al 50"


def test_concatenate_basic():
    assert intelligent_concatenate("ciao", "mondo") == "ciao mondo"
    assert intelligent_concatenate("", "mondo") == "mondo"
    assert intelligent_concatenate("ciao", "  ") == "ciao"


def test_concatenate_punctuation_and_case():
    assert intelligent_concatenate("ciao.", ", mondo") == "ciao, mondo"
    assert intelligent_concatenate("ciao.", "e poi") == "ciao e poi"
    assert intelligent_concatenate("ciao", "Mondo") == "ciao. Mondo"
    assert intelligent_concatenate("ciao.", "Mondo") == "ciao. Mondo"
