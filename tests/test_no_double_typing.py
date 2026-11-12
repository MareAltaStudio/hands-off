"""type_text must not type the text twice when Enter fails after a UIA SetValue.

No window needed: UIA, win32 and the message helpers are replaced by mocks.
"""

from __future__ import annotations

from unittest import mock

import pytest

from hands_off import server as S


def _run(set_ok: bool):
    vp = mock.Mock(IsReadOnly=False)
    if not set_ok:
        vp.SetValue.side_effect = RuntimeError("no Value pattern")
    c = mock.Mock(NativeWindowHandle=0)
    c.GetValuePattern.return_value = vp
    sent = mock.Mock()
    with mock.patch.object(S, "_resolve", return_value=1), \
         mock.patch.object(S, "_acting", side_effect=lambda n, h, fn: fn()), \
         mock.patch.object(S, "_root", return_value=None), \
         mock.patch.object(S, "_find", return_value=([], c, "")), \
         mock.patch.object(S, "_describe", return_value="field"), \
         mock.patch.object(S, "_focus_hwnd", return_value=7), \
         mock.patch.object(S, "_post_keys", side_effect=RuntimeError("enter dropped")), \
         mock.patch.object(S, "_post_text", sent), \
         mock.patch.object(S.user32, "SendMessageTimeoutW", sent), \
         mock.patch.object(S.win32gui, "GetClassName", return_value="Chrome_Widget"):
        out = S.type_text("w", "target", "hi", enter=True)
    return out, vp, sent


def test_setvalue_ok_enter_fails_does_not_retype():
    out, vp, sent = _run(True)
    vp.SetValue.assert_called_once()
    sent.assert_not_called()
    assert "Enter failed" in out
    assert "enter dropped" in out


def test_setvalue_fails_falls_through_to_message_path():
    # The lower path runs (and the faked Enter raises there).
    with pytest.raises(RuntimeError):
        _run(False)
