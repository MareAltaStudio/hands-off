"""Turn the take's action log into the overlay's ticker, worded from the recipe's own notes.

    python ticker_from_recipe.py demo_browse.json out/data.json out/data_final.json

The log line for a click says which window handle got the message; the recipe's note says
what was clicked ("index: Edge Loops"). Each logged click_xy is paired with the recipe's
click_xy steps in order, keeping the time the log recorded.
"""

import json
import sys

recipe, data_in, data_out = sys.argv[1:4]
notes = [s["note"] for s in json.load(open(recipe, encoding="utf-8"))["steps"] if s["do"] == "click_xy"]
data = json.load(open(data_in, encoding="utf-8"))
clicks = [x for x in data["ticker"] if x["tool"] == "click_xy"]
if len(clicks) != len(notes):
    sys.exit(f"{len(clicks)} clicks in the log, {len(notes)} in the recipe")
data["ticker"] = [{"t": c["t"], "text": f"click_xy · {n} · window message"} for c, n in zip(clicks, notes, strict=True)]
json.dump(data, open(data_out, "w", encoding="utf-8"), indent=1)
print(f"{len(clicks)} ticker lines -> {data_out}")
