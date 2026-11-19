"""Génère les icônes de l'application (micro noir sur fond jaune, comme le logo de l'interface).

Usage : python3 scripts/gen-icons.py   (depuis web/, demande Pillow)
Les fichiers générés sont dans public/icons/ et versionnés ; ce script ne sert qu'à les refaire.
"""

from pathlib import Path

from PIL import Image, ImageDraw

YELLOW = (255, 212, 0, 255)  # --accent de pilote.css
INK = (17, 17, 17, 255)  # --accent-ink
OUT = Path(__file__).resolve().parent.parent / "public" / "icons"


def mic(size: int, scale: float, rounded: bool) -> Image.Image:
    """Dessine à 4x puis réduit (bords lissés). scale = part de l'icône occupée par le micro."""
    big = size * 4
    img = Image.new("RGBA", (big, big), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    if rounded:
        d.rounded_rectangle([0, 0, big - 1, big - 1], radius=int(big * 0.22), fill=YELLOW)
    else:
        d.rectangle([0, 0, big - 1, big - 1], fill=YELLOW)
    u = big * scale  # unité de dessin : le micro tient dans un carré de côté u, centré
    ox, oy = (big - u) / 2, (big - u) / 2

    w = max(2, int(u * 0.075))
    # capsule du micro
    d.rounded_rectangle(
        [ox + u * 0.35, oy + u * 0.04, ox + u * 0.65, oy + u * 0.56],
        radius=int(u * 0.15),
        fill=INK,
    )
    # arc autour de la capsule
    d.arc([ox + u * 0.22, oy + u * 0.22, ox + u * 0.78, oy + u * 0.78], 0, 180, fill=INK, width=w)
    # pied
    d.line([ox + u * 0.5, oy + u * 0.78, ox + u * 0.5, oy + u * 0.94], fill=INK, width=w)
    d.line([ox + u * 0.36, oy + u * 0.94, ox + u * 0.64, oy + u * 0.94], fill=INK, width=w)
    return img.resize((size, size), Image.LANCZOS)


def save(name: str, size: int, scale: float, rounded: bool) -> None:
    mic(size, scale, rounded).save(OUT / name, optimize=True)
    print("écrit", name)


if __name__ == "__main__":
    OUT.mkdir(parents=True, exist_ok=True)
    save("icon-192.png", 192, 0.62, True)
    save("icon-512.png", 512, 0.62, True)
    # Maskable : plein cadre, micro dans la zone sûre (80 % centraux) ; le système découpe le masque
    save("icon-maskable-512.png", 512, 0.50, False)
    # iOS arrondit lui-même et n'aime pas la transparence
    save("apple-touch-icon.png", 180, 0.58, False)
