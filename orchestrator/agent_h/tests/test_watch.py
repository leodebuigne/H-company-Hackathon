from orchestrator.agent_h.watch import HELP_COOLDOWN_S, SLOW_AFTER_S, StepWatch, action_signature


def test_same_click_a_few_pixels_apart_is_the_same_action():
    a = action_signature("click_web", {"element": "le bouton « Fermer » en haut", "x": 10})
    b = action_signature("click_web", {"element": "le bouton « Fermer » en haut", "x": 14})
    assert a == b == "click_web:fermer"


def test_loop_then_slow_are_detected_once_a_screenshot_exists():
    watch = StepWatch(now=0.0)
    for _ in range(3):
        watch.saw_action("click_web", {"element": "« Voir les prix »"}, 1.0)
    assert watch.stuck_reason(2.0) is None, "pas de capture : rien à lire"
    watch.saw_screenshot("https://h/capture.png")
    assert watch.stuck_reason(2.0) == "boucle"
    watch.helped(2.0)
    assert watch.stuck_reason(3.0) is None, "délai entre deux aides"
    assert watch.stuck_reason(2.0 + max(HELP_COOLDOWN_S, SLOW_AFTER_S) + 1) == "lent"


def test_answer_and_payment_tools_are_not_actions():
    watch = StepWatch(now=0.0)
    watch.saw_screenshot("https://h/capture.png")
    for _ in range(5):
        watch.saw_action("answer", {}, 1.0)
    assert watch.stuck_reason(2.0) is None
