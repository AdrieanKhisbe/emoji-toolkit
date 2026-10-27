"""Render normalized Unicode identities from existing resource indexes."""

# Text-default emoji bases used by the Unicode 17.0 dataset. These require VS16
# unless immediately followed by a skin-tone modifier. Keep this legacy fallback
# for resource indexes created before full display sequences were preserved.
# https://unicode.org/Public/17.0.0/ucd/emoji/emoji-data.txt
_TEXT_EMOJI_BASES = frozenset(
    int(point, 16)
    for point in (
        "23 2a 30 31 32 33 34 35 36 37 38 39 a9 ae 203c 2049 2122 2139 2194 2195 "
        "2196 2197 2198 2199 21a9 21aa 2328 23cf 23ed 23ee 23ef 23f1 23f2 23f8 23f9 "
        "23fa 24c2 25aa 25ab 25b6 25c0 25fb 25fc 2600 2601 2602 2603 2604 260e 2611 "
        "2618 261d 2620 2622 2623 2626 262a 262e 262f 2638 2639 263a 2640 2642 265f "
        "2660 2663 2665 2666 2668 267b 267e 2692 2694 2695 2696 2697 2699 269b 269c "
        "26a0 26a7 26b0 26b1 26c8 26cf 26d1 26d3 26e9 26f0 26f1 26f4 26f7 26f8 26f9 "
        "2702 2708 2709 270c 270d 270f 2712 2714 2716 271d 2721 2733 2734 2744 2747 "
        "2763 2764 27a1 2934 2935 2b05 2b06 2b07 3030 303d 3297 3299 1f170 1f171 "
        "1f17e 1f17f 1f202 1f237 1f321 1f324 1f325 1f326 1f327 1f328 1f329 1f32a "
        "1f32b 1f32c 1f336 1f37d 1f396 1f397 1f399 1f39a 1f39b 1f39e 1f39f 1f3cb "
        "1f3cc 1f3cd 1f3ce 1f3d4 1f3d5 1f3d6 1f3d7 1f3d8 1f3d9 1f3da 1f3db 1f3dc "
        "1f3dd 1f3de 1f3df 1f3f3 1f3f5 1f3f7 1f43f 1f441 1f4fd 1f549 1f54a 1f56f "
        "1f570 1f573 1f574 1f575 1f576 1f577 1f578 1f579 1f587 1f58a 1f58b 1f58c "
        "1f58d 1f590 1f5a5 1f5a8 1f5b1 1f5b2 1f5bc 1f5c2 1f5c3 1f5c4 1f5d1 1f5d2 "
        "1f5d3 1f5dc 1f5dd 1f5de 1f5e1 1f5e3 1f5e8 1f5ef 1f5f3 1f5fa 1f6cb 1f6cd "
        "1f6ce 1f6cf 1f6e0 1f6e1 1f6e2 1f6e3 1f6e4 1f6e5 1f6e9 1f6f0 1f6f3 "
    ).split()
)


def display_emoji(key: str) -> str:
    """Restore emoji presentation without changing the normalized lookup key."""
    points = [int(point, 16) for point in key.split("-")]
    characters = []
    for index, point in enumerate(points):
        characters.append(chr(point))
        modified = index + 1 < len(points) and 0x1F3FB <= points[index + 1] <= 0x1F3FF
        if point in _TEXT_EMOJI_BASES and not modified:
            characters.append("\ufe0f")
    return "".join(characters)
