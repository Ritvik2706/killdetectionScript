from killcutter.ui.selector import fuzzy_match, _State


def test_fuzzy_match_subsequence():
    assert fuzzy_match("war", "warzone clip")
    assert fuzzy_match("wrz", "warzone")
    assert fuzzy_match("0529", "2026-05-29 19-58-19")
    assert not fuzzy_match("xyz", "warzone")


def test_state_filters_view():
    items = ["alpha.mkv", "bravo.mkv", "alfalfa.mp4"]
    st = _State(items, lambda s: s, initial=0)
    assert st.view() == [0, 1, 2]
    st.query = "al"
    assert st.view() == [0, 2]          # subsequence "a..l" matches alpha & alfalfa
    st.query = "alf"
    assert st.view() == [2]             # only alfalfa has an 'f' after the 'l'


def test_state_enter_returns_cursor_index():
    items = ["a", "b", "c"]
    st = _State(items, lambda s: s, initial=0)
    view = st.view()
    st.handle("j", view)                # move to index 1
    assert st.cursor == 1
    assert st.handle("enter", st.view()) == 1


def test_state_digit_jump():
    items = list("abcde")
    st = _State(items, lambda s: s, initial=0)
    st.handle("3", st.view())
    assert st.numbuf == "3"
    assert st.handle("enter", st.view()) == 2   # 1-based "3" -> index 2


def test_state_quit_returns_none():
    st = _State(["a"], lambda s: s, initial=0)
    assert st.handle("q", st.view()) is None
