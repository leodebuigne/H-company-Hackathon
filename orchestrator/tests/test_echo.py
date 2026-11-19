import pytest

from orchestrator.echo import echo_share, is_bare_answer, is_echo, should_drop, words

SAID = [
    "Je cherche un train de Paris à Lille, demain après quatorze heures. Dites annule si ce n'est pas ça.",
    "Dites la première, la deuxième, ou demandez des détails.",
]


def test_words_ignore_accents_case_and_punctuation():
    assert words("Dites « annule », s'il VOUS plaît !") == ["dites", "annule", "s", "il", "vous", "plait"]
    assert words("  ") == []


@pytest.mark.parametrize(
    "heard",
    [
        "Je cherche un train de Paris à Lille demain après quatorze heures",
        "dites annule si ce n'est pas ça",
        "train de Paris à Lille demain après quatorze heures",
    ],
)
def test_a_long_run_of_pilotes_own_words_is_an_echo(heard):
    assert is_echo(heard, SAID)


@pytest.mark.parametrize(
    "heard",
    [
        "Un train de Paris pour Nantes vendredi matin",
        "Je voudrais plutôt un repas italien ce soir",
        "Plus tôt, avant midi si possible",
    ],
)
def test_a_real_new_request_is_not_an_echo(heard):
    assert not is_echo(heard, SAID)
    assert echo_share(heard, SAID) < 0.8


def test_short_replies_are_never_an_echo_by_similarity_alone():
    # « la deuxième » est dans la phrase qui propose les options, mais c'est aussi la vraie réponse
    assert not is_echo("la deuxième", SAID)
    assert not is_echo("oui", SAID)


@pytest.mark.parametrize(
    ("text", "bare"),
    [
        ("oui", True),
        ("Non.", True),
        ("d'accord", True),
        ("c'est bon", True),
        ("quatre sept deux", True),
        ("4 7 2", True),
        ("oui quatre sept deux", True),
        ("un train pour Lille", False),
        ("oui mais moins cher", False),
        ("", False),
    ],
)
def test_bare_answers_are_the_words_pilote_also_says(text, bare):
    assert is_bare_answer(text) is bare


def test_an_overlapped_recording_can_never_be_a_yes_a_no_or_a_code():
    assert should_drop("oui", SAID, overlapped=True)
    assert should_drop("quatre sept deux", SAID, overlapped=True)
    assert should_drop("la deuxième", SAID, overlapped=True)  # reprend la phrase des options : écho possible
    assert not should_drop("oui", SAID, overlapped=False)
    assert not should_drop("quatre sept deux", SAID, overlapped=False)


def test_an_overlapped_recording_with_new_content_is_kept():
    assert not should_drop("Un train pour Nantes demain matin", SAID, overlapped=True)
    assert not should_drop("Plutôt moins cher, s'il te plaît", SAID, overlapped=True)


def test_nothing_to_compare_with_means_nothing_is_dropped():
    assert not should_drop("Un train pour Lille demain", [], overlapped=False)
    assert not is_echo("Un train pour Lille demain", [])


def test_the_overlap_flag_travels_in_the_sound_type_and_is_removed_before_transcription():
    from orchestrator.echo import split_overlap

    assert split_overlap("audio/webm;codecs=opus;overlapped=1") == ("audio/webm;codecs=opus", True)
    assert split_overlap("audio/webm;codecs=opus") == ("audio/webm;codecs=opus", False)
    assert split_overlap("audio/mp4;overlapped=1") == ("audio/mp4", True)
    assert split_overlap("audio/mp4; OVERLAPPED=1") == ("audio/mp4", True)
    assert split_overlap("audio/mp4;overlapped=0") == ("audio/mp4;overlapped=0", False)
