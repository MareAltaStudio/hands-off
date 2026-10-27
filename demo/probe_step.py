"""One exploration step for a recipe: click a point in a window, wait, capture.

    python probe_step.py <window> <x> <y> <out.png> [--wait 3]
    python probe_step.py <window> - - <out.png>            # capture only
"""

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
from hands_off import server  # noqa: E402

h, x, y, out = sys.argv[1:5]
wait = float(sys.argv[sys.argv.index("--wait") + 1]) if "--wait" in sys.argv else 3.0
if x != "-":
    print(server.click_xy(h, int(x), int(y)).splitlines()[0][:120])
    time.sleep(wait)
img, how = server._grab(int(h))
img.save(out)
print("saved", out, img.size)
