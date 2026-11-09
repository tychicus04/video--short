"""Where a neon section's nodes can stand: each layout is a table of named slots on the 660 px wide picture."""
import math

C = (330.0, 560.0)  # the centre, where a hub stands
_RING_ANGLES = (0, 50, 130, 180, 230, 310)  # degrees; y grows downwards, so 50 is below and to the right

SLOTS: dict[str, dict[str, tuple[float, float]]] = {
    "none": {},
    "center": {"hub": C},
    "pair": {"hub": C, "left": (150, 560), "right": (510, 560), "above": (330, 380), "below": (330, 760)},
    "ring": {"hub": C} | {f"r{k}": (C[0] + 228 * math.cos(math.radians(a)), C[1] + 228 * math.sin(math.radians(a)))
                          for k, a in enumerate(_RING_ANGLES)},
    "chain": {f"c{k}": (330, 330 + 150 * k) for k in range(4)},
    "grid": {f"g{k}": ((162, 330, 498)[k % 3], (480, 650)[k // 3]) for k in range(6)},
}
