from __future__ import annotations

from app.infrastructure.audio.windows_wasapi import is_headset_name, names_match, select_loopbacks


class _Dev:
    def __init__(self, ident: str, name: str, isloopback: bool = False) -> None:
        self.id = ident
        self.name = name
        self.isloopback = isloopback


class _Sc:
    def __init__(self) -> None:
        self._speakers = [
            _Dev("hdmi", "LG TV HDMI"),
            _Dev("jabra", "Headset (Jabra Hands-Free AG Audio)"),
        ]
        self._mics = [
            _Dev("mic", "Headset Microphone"),
            _Dev("lb-hdmi", "LG TV HDMI", True),
            _Dev("lb-jabra", "Headset (Jabra Hands-Free AG Audio)", True),
        ]

    def all_microphones(self, include_loopback: bool = False) -> list[_Dev]:
        if include_loopback:
            return list(self._mics)
        return [item for item in self._mics if not item.isloopback]

    def all_speakers(self) -> list[_Dev]:
        return list(self._speakers)

    def default_speaker(self) -> _Dev:
        return self._speakers[0]

    def get_microphone(self, id: str, include_loopback: bool = True) -> _Dev | None:
        del include_loopback
        for item in self._mics:
            if item.id == id or item.name == id:
                return item
        return None


def test_names_match_ignores_loopback_suffix() -> None:
    assert names_match("Headphones (Realtek)", "Headphones (Realtek) (loopback)") is True


def test_headset_name_detects_hands_free() -> None:
    assert is_headset_name("Headset (Jabra Hands-Free AG Audio)") is True
    assert is_headset_name("LG TV HDMI") is False


def test_select_loopbacks_includes_headset_even_if_default_is_hdmi() -> None:
    picked = select_loopbacks(_Sc(), None)
    names = {str(item.name) for item in picked}
    assert "Headset (Jabra Hands-Free AG Audio)" in names
    assert "LG TV HDMI" in names


def test_select_loopbacks_honors_explicit_id() -> None:
    picked = select_loopbacks(_Sc(), "lb-jabra")
    assert len(picked) == 1
    assert picked[0].id == "lb-jabra"
