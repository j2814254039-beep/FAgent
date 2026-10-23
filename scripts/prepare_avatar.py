"""把 AI 生成的立绘处理成桌宠可用的 PNG。

解决两个问题：
  1. 尺寸不统一 / 太大 —— 缩放并居中到固定画布，否则窗口会跳、角色被裁
  2. C2PA 元数据（caBX 块）—— tkinter 读不了，会读出错误尺寸导致画面错乱

原图不动，处理结果写到 assets/avatar_ready/。

用法：
    .venv\\Scripts\\python.exe scripts\\prepare_avatar.py
"""

from pathlib import Path

from PIL import Image

PROJECT_ROOT = Path(__file__).resolve().parent.parent
SRC = PROJECT_ROOT / "assets" / "avatar"
DST = PROJECT_ROOT / "assets" / "avatar_ready"

# 统一画布尺寸：宽 x 高。所有动作、所有帧都用这个尺寸。
#
# 必须和【源图的宽高比】一致，否则会留下透明边：
#   源图 1024x1536  =  2:3
#   画布  600x900   =  2:3  ✓
#
# 想更清晰就调大（占屏幕更多），想小巧就调小（会缩得更多、更糊）。
# 屏幕逻辑分辨率 1707x1067，900 的高度能放下。
CANVAS = (600, 900)

# 边缘硬边化阈值。
# tkinter 的透明是"色键"（把某个纯色变透明），无法处理半透明像素。
# 抗锯齿边缘的半透明像素会和新背景色混合，形成一圈描边。
# 把 alpha 强制变成 0 或 255 就能消除描边 —— 代价是边缘略有一点锯齿。
ALPHA_THRESHOLD = 128


def process(src: Path, dst: Path) -> tuple[int, int]:
    """缩放 → 硬边化 → 居中贴到透明画布 → 重新保存（元数据自然丢弃）。"""
    with Image.open(src) as im:
        im = im.convert("RGBA")                  # 统一成带透明通道
        original = im.size

        im.thumbnail(CANVAS, Image.LANCZOS)      # 保持比例缩放，不放大

        canvas = Image.new("RGBA", CANVAS, (0, 0, 0, 0))
        x = (CANVAS[0] - im.width) // 2
        y = CANVAS[1] - im.height                # 底部对齐：脚踩画布底边
        canvas.alpha_composite(im, (x, y))

        # ★ 硬边化：必须在缩放之后做（缩放会新产生半透明像素）
        alpha = canvas.getchannel("A")
        alpha = alpha.point(lambda a: 255 if a >= ALPHA_THRESHOLD else 0)
        canvas.putalpha(alpha)

        dst.parent.mkdir(parents=True, exist_ok=True)
        # 重新编码保存 → caBX 等元数据不会被带过去
        canvas.save(dst, "PNG", optimize=True)

    return original, im.size


def main() -> None:
    if not SRC.is_dir():
        raise SystemExit(f"找不到源目录：{SRC}")

    count = 0
    for folder in sorted(SRC.iterdir()):
        if not folder.is_dir():
            continue
        for png in sorted(folder.glob("*.png")):
            out = DST / folder.name / png.name
            original, resized = process(png, out)
            print(
                f"  {folder.name}/{png.name:14s} "
                f"{original[0]}x{original[1]} -> {resized[0]}x{resized[1]}  "
                f"({out.stat().st_size // 1024} KB)"
            )
            count += 1

    print()
    print(f"共处理 {count} 张，输出到：{DST}")
    print("把 .env 里的 ACTION_PATH 改成这个目录即可。")


if __name__ == "__main__":
    main()
