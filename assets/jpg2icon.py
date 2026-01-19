from PIL import Image


def jpg_to_ico(jpg_path: str, ico_path: str, sizes=None):
    """
    将 JPG 图像转换为标准 .ico 文件（含多分辨率）

    :param jpg_path: 输入 JPG 路径（支持 JPG/JPEG）
    :param ico_path: 输出 .ico 路径（如 "app.ico"）
    :param sizes: 图标尺寸列表，推荐 [16, 32, 48, 256]（Windows 最佳实践）
    """
    if sizes is None:
        sizes = [48, 256]
    
    # 1️⃣ 打开 JPG（自动转为 RGB，丢弃 alpha —— JPG 本就没有）
    img = Image.open(jpg_path).convert("RGB")
    
    # 2️⃣ 【关键】若原图无透明，但你希望图标背景透明（如圆角 App 图标）：
    #    → 可选：用白底/透明底重绘（需先转 RGBA，再 paste 到透明画布）
    #    这里提供「转透明底」版本（推荐用于现代 UI）：
    rgba_img = Image.new("RGBA", img.size, (255, 255, 255, 0))  # 透明背景
    rgba_img.paste(img, (0, 0), mask=None)  # JPG 无 mask，直接覆盖（白底变透明？不 —— 需手动抠图！）
    # ⚠️ 注意：JPG 没有 alpha 通道 → 无法自动抠图！若 JPG 是纯色背景（如白底），可用 threshold 扣，但更建议：
    # ✅ 最佳实践：**原始设计就用 PNG（带透明）→ 直接转 ICO**，避免 JPG 的先天缺陷。
    
    # 3️⃣ 生成多尺寸缩略图并保存为 ICO
    icons = []
    for size in sizes:
        # 缩放到正方形（保持宽高比，居中裁剪 or 等比缩放+填充）
        # 👇 这里用「等比缩放 + 白底填充」，避免拉伸变形
        img_resized = img.copy()
        img_resized.thumbnail((size, size), Image.LANCZOS)
        
        # 创建 size×size 白底画布
        canvas = Image.new("RGB", (size, size), "white")
        x = (size - img_resized.width) // 2
        y = (size - img_resized.height) // 2
        canvas.paste(img_resized, (x, y))
        
        # 转为 RGBA（.ico 标准要求，即使无透明也需 RGBA 模式）
        canvas = canvas.convert("RGBA")
        icons.append(canvas)
    
    # 4️⃣ 保存为 .ico（Pillow 自动打包多尺寸）
    [icons[i].save(
        f"{s}x{ico_path}",
        format="ICO",
        sizes=[(s, s)]  # 显式指定尺寸列表
    ) for i, s in enumerate(sizes)]
    print(f"✅ 已生成 {len(icons)} 尺寸 ICO: {ico_path} → {sizes}")


# 🔧 使用示例
jpg_to_ico("icon.jpg", "icon.ico")
