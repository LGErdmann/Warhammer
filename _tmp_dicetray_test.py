import sistema as S
import random

random.seed(0)

# Fabricate a fake node/log covering: player hit fully absorbed, player hit
# with wounds, player miss, enemy hit with wrath crit.
node = {"log": [
    {"actor": "player", "action": "attack", "hit": True, "rolls": [2, 5, 6], "icons": 3,
     "weapon": "Knife", "damage": 5, "wounds": 0, "shock": 0, "wrath_crit": True, "target_defeated": False},
    {"actor": "enemy", "action": "attack", "hit": True, "rolls": [1, 4, 6, 6], "icons": 5,
     "weapon": "Chainsword", "damage": 9, "wounds": 4, "shock": 0, "wrath_crit": True, "target_defeated": False},
]}

import streamlit as st

class FakeMD:
    def __init__(self): self.calls = []
    def __call__(self, html_str, **kwargs):
        self.calls.append(html_str)

st.markdown = FakeMD()
S._inc_render_dice_tray(node)
for c in st.markdown.calls:
    print(c)
    print("----")
