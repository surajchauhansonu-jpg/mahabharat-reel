"""Mahabharat cast for the vector puppet engine. Add / edit characters here (name -> look)."""
from vp_puppet import Puppet

WHITE, GOLD = "#f3efe6", "#e0b43a"

CAST_SPECS = {
    "Krishna": dict(skin="#3a62b5", crown="feather", crown_color="#e0b43a", top="bare", bottom_color="#e8b72a", strip_color="#c9892b",
                    mark="tilak", mark_color="#f1e9c8", hair="#14121c", build=0.92, prop="flute"),
    "Arjun": dict(skin="#b57a4f", crown="hair", beard="trim", top="armor", top_color="#3a5a98", bottom_color="#eee8d8",
                  strip_color="#e0b43a", prop="bow", mark="dot"),
    "Karna": dict(skin="#a86a40", crown="cone", beard="moustache", top="armor", top_color="#d9a928", bottom_color="#8e1b22", strip_color="#e8b932"),
    "Duryodhan": dict(skin="#80492e", crown="cone", crown_color="#c9a227", beard="moustache", top="armor", top_color="#6b1d1d",
                      bottom_color="#2a1520", strip_color="#e0b43a", build=1.22, height=1.03, prop="mace"),
    "Bhishma": dict(skin="#c28a60", crown="bun", hair="#f1eee8", beard="long", beard_color="#f1eee8", brow_color="#f1eee8", top="bare",
                    sash="yes", sash_color="#f3efe6", bottom_color=WHITE, strip_color="#e8a22a", mark="tilak", mark_color="#c8201e"),
    "Draupadi": dict(skin="#c58a5c", crown="tiara", beard="none", top="saree_top", top_color="#e0b43a", bottom="saree",
                     bottom_color="#a8161f", build=0.82, height=0.94),
    "Yudhishthir": dict(skin="#c9895a", crown="cone", crown_color="#e0b43a", beard="trim", top="cloth", top_color="#efe6c8",
                        bottom_color=WHITE, strip_color=GOLD, mark="tilak", mark_color="#c8201e"),
    "Bhima": dict(skin="#8d5a38", crown="hair", beard="trim", top="bare", bottom_color="#2f7a4a", strip_color=GOLD,
                  build=1.35, height=1.05, prop="mace"),
    "Shakuni": dict(skin="#b88a63", crown="hair", hair="#8c8c8c", beard="trim", beard_color="#8c8c8c", brow_color="#8c8c8c",
                    top="robe", top_color="#4a2a6a", bottom_color="#33204d", strip_color=GOLD, build=0.86, prop="dice"),
    "Ashwatthama": dict(skin="#a8714a", crown="hair", beard="trim", top="armor", top_color="#8a5a3a", bottom_color="#6a3a22",
                        strip_color=GOLD, mark="gem"),
    "Dronacharya": dict(skin="#c09060", crown="bun", hair="#f1eee8", beard="long", beard_color="#f1eee8", brow_color="#f1eee8",
                        top="cloth", top_color="#e07a1c", bottom_color="#e07a1c", strip_color=GOLD, prop="bow"),
    "Abhimanyu": dict(skin="#c58a5c", crown="hair", beard="none", top="armor", top_color="#b3382a", bottom_color="#e8b72a",
                      strip_color="#b3382a", build=0.8, height=0.86, prop="sword"),
    "Gandhari": dict(skin="#c58a5c", crown="tiara", blindfold=True, top="saree_top", top_color="#eee8d8", bottom="saree",
                     bottom_color="#e8e4d6", build=0.84, height=0.94),
    "Dhritarashtra": dict(skin="#b9774a", crown="cone", crown_color="#e0b43a", blindfold=True, beard="trim", beard_color="#9a9a9a",
                          top="robe", top_color="#e8e0cf", bottom_color="#e8e0cf", strip_color=GOLD, prop="staff"),
    "Kunti": dict(skin="#c58a5c", crown="tiara", top="saree_top", top_color="#e8b932", bottom="saree", bottom_color="#0f6b57",
                  build=0.82, height=0.93),
    "Barbarik": dict(skin="#80492e", crown="hair", top="armor", top_color="#3a3a4a", bottom_color="#2a2a33", strip_color=GOLD,
                     prop="bow", build=0.95),
    "Ghatotkacha": dict(skin="#4a3a33", crown="hair", beard="trim", top="bare", bottom_color="#3a2a1a", strip_color=GOLD,
                        build=1.4, height=1.1, prop="mace"),
    "Sanjay": dict(skin="#c09060", crown="bun", top="cloth", top_color="#e8e0cf", bottom_color="#e8e0cf", strip_color=GOLD, build=0.9),
    "Vyasa": dict(skin="#b07a50", crown="jata", hair="#8a8a8a", beard="long", beard_color="#a8a8a8", brow_color="#a8a8a8",
                  top="cloth", top_color="#d9751f", bottom_color="#d9751f", strip_color=GOLD, prop="staff"),
    "Brahma": dict(skin="#b98159", crown="cone", beard="long", beard_color="#f1eee8", brow_color="#f1eee8", heads=3,
                   top="robe_open", top_color="#e7a23a", bottom_color=WHITE, strip_color="#e8a22a", mark="tilak", mark_color=GOLD),
    "Surya": dict(skin="#e0a030", crown="cone", crown_color="#f3d98a", top="bare", bottom_color="#c9461f", strip_color=GOLD, mark="dot"),
}


def build_cast():
    return {k: Puppet(v) for k, v in CAST_SPECS.items()}
