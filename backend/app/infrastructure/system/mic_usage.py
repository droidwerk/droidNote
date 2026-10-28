"""Quais apps estão usando o microfone agora, pelo próprio Windows.

O Windows registra cada uso do microfone em
HKCU\\...\\CapabilityAccessManager\\ConsentStore\\microphone: apps da Store
como subchave direta, apps comuns em NonPackaged (caminho com # no lugar de \\).
`LastUsedTimeStop == 0` (ou início depois do fim) quer dizer "em uso agora".
É o mesmo dado que acende o ícone de microfone na barra de tarefas.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass

CONSENT_KEY = r"Software\Microsoft\Windows\CurrentVersion\CapabilityAccessManager\ConsentStore\microphone"

# Só apps de reunião conhecidos contam: gravadores, assistentes de voz e o
# próprio DroidNote também usam o microfone e não são reunião.
MEETING_APPS: tuple[tuple[str, str], ...] = (
    ("zoom", "Zoom"),
    ("msteams", "Microsoft Teams"),
    ("teams", "Microsoft Teams"),
    ("webex", "Webex"),
    ("slack", "Slack"),
    ("discord", "Discord"),
    ("whatsapp", "WhatsApp"),
    ("skype", "Skype"),
    ("telegram", "Telegram"),
    ("gotomeeting", "GoTo Meeting"),
    ("ringcentral", "RingCentral"),
    ("chrome.exe", "Google Chrome"),
    ("msedge.exe", "Microsoft Edge"),
    ("firefox.exe", "Firefox"),
    ("brave.exe", "Brave"),
    ("opera.exe", "Opera"),
    ("vivaldi.exe", "Vivaldi"),
    ("arc.exe", "Arc"),
)
BROWSERS = {"Google Chrome", "Microsoft Edge", "Firefox", "Brave", "Opera", "Vivaldi", "Arc"}


@dataclass(frozen=True)
class MicUser:
    key: str
    app: str
    in_use: bool
    browser: bool


def meeting_app_label(key: str) -> str | None:
    lowered = key.lower()
    tail = lowered.rsplit("#", 1)[-1]
    for marker, label in MEETING_APPS:
        if marker.endswith(".exe"):
            if tail == marker:
                return label
        elif marker in tail:
            return label
    return None


def _in_use(start: int, stop: int) -> bool:
    return stop == 0 or start > stop


class WindowsMicUsage:
    """Leitura do registro; barata o bastante para rodar a cada 2 s."""

    def available(self) -> bool:
        return sys.platform == "win32"

    def snapshot(self) -> list[MicUser]:
        if sys.platform != "win32":
            return []
        import winreg

        users: list[MicUser] = []

        def read(path: str) -> None:
            try:
                root = winreg.OpenKey(winreg.HKEY_CURRENT_USER, path)
            except OSError:
                return
            index = 0
            while True:
                try:
                    name = winreg.EnumKey(root, index)
                except OSError:
                    break
                index += 1
                sub = f"{path}\\{name}"
                if name == "NonPackaged":
                    read(sub)
                    continue
                label = meeting_app_label(name)
                if label is None:
                    continue
                try:
                    with winreg.OpenKey(winreg.HKEY_CURRENT_USER, sub) as key:
                        start = int(winreg.QueryValueEx(key, "LastUsedTimeStart")[0])
                        stop = int(winreg.QueryValueEx(key, "LastUsedTimeStop")[0])
                except OSError:
                    continue
                users.append(MicUser(name, label, _in_use(start, stop), label in BROWSERS))

        read(CONSENT_KEY)
        return users
