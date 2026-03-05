from typing import List, Tuple


def sort_elements(elements: list) -> list:
    def _key(e: dict) -> Tuple[int, int, int]:
        x1, y1, x2, y2 = e.get("bbox", [0, 0, 0, 0])
        return int(e.get("page_num", 1)), y1, x1
    return sorted(elements, key=_key)