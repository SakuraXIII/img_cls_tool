# image_annotator.py
import json
import os
import shutil
import time
from pathlib import Path
from tkinter import messagebox, filedialog

import customtkinter as ctk
from PIL import Image, ImageTk


class ImageAnnotator(ctk.CTk):
    def __init__(self, width=1400, height=900):
        super().__init__()
        self.title("图像分类工具")
        self.geometry(f"{width}x{height}")
        x, y = self.get_center_position(width, height)
        self.geometry(f"+{x}+{y}")
        self.iconbitmap("assets/256xicon.ico")
        
        # 配置 & 状态
        self.config_path = "config.json"
        self.image_dir = None
        self.curr_idx = -1
        self.current_image_path = None
        self.image_files = []
        self.undo_stack = None  # (src_path, dst_path, category)
        
        # 缩放状态
        self.zoom_level = 1.0
        self.min_zoom = 0.05
        self.max_zoom = 20.0
        self.pan_x = 0
        self.pan_y = 0
        self.original_pil_image = None  # 原始未缩放 PIL 图像（只加载一次）
        self.current_tk_photo = None  # 当前显示的 PhotoImage（缓存）
        self.zoom_cache = {}  # {zoom_key: PhotoImage}，key = (w,h,zoom)
        self._last_wheel_time = 0  # 防抖时间戳（秒）
        
        # 加载配置
        self.categories = self.load_config()
        
        # 构建 UI
        self.setup_ui()
        self.bind_event()
    
    def load_config(self):
        cats = []
        try:
            with open(self.config_path, "r", encoding="utf-8") as f:
                cfg = json.load(f)
            cats = cfg.get("categories", [])
            if not cats:
                messagebox.showerror("加载 config.json 失败", "config.json 中 categories 为空")
            cats = list(map(str, cats))
        except FileNotFoundError:
            messagebox.showerror("加载 config.json 失败", "已创建 config.json，请配置标签类别")
            tmp = {"categories": []}
            with open("config.json", 'w') as f:
                json.dump(tmp, f)
        finally:
            return cats
    
    def setup_ui(self):
        # 主框架：左图右控
        self.grid_columnconfigure(0, weight=8)
        self.grid_columnconfigure(1, weight=2)
        self.grid_rowconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=0)
        
        # ========== 底部：信息展示栏（Status Bar） ==========
        self.setup_bottom_frame()
        
        # ========== 左侧：图像展示区 ==========
        self.setup_left_frame()
        
        # ========== 右侧：控制面板 ==========
        self.setup_right_frame()
    
    def setup_left_frame(self):
        image_frame = ctk.CTkFrame(self, corner_radius=5)
        image_frame.grid(row=0, column=0, padx=(10, 5), pady=10, sticky="nsew")
        image_frame.grid_columnconfigure(0, weight=1)
        image_frame.grid_rowconfigure(0, weight=1)
        
        self.image_canvas = ctk.CTkCanvas(
            image_frame,
            highlightthickness=0
        )
        self.image_canvas.grid(row=0, column=0, sticky="nsew")
    
    def setup_right_frame(self):
        control_frame = ctk.CTkFrame(self, corner_radius=5)
        control_frame.grid(row=0, column=1, padx=10, pady=10, sticky="nsew")
        control_frame.grid_columnconfigure(0, weight=1)
        control_frame.grid_rowconfigure((0, 1, 2, 4), weight=0)  # 按钮不拉伸
        control_frame.grid_rowconfigure(3, weight=1)  # 留白或后续扩展用
        
        file_btn_frame = ctk.CTkFrame(control_frame, fg_color='transparent')
        file_btn_frame.grid_columnconfigure(0, weight=1)
        file_btn_frame.grid_columnconfigure(1, weight=1)
        file_btn_frame.grid(row=0, column=0, padx=10, pady=5, sticky="ew")
        # 控制按钮
        ctk.CTkButton(
            file_btn_frame,
            text="选择图像目录",
            command=self.select_image_dir,
            height=40,
            font=ctk.CTkFont(size=14, weight="bold")
        ).grid(row=0, column=0, padx=5, sticky='ew')
        
        ctk.CTkButton(
            file_btn_frame,
            text="打开图像目录",
            command=self.open_image_dir,
            height=40,
            font=ctk.CTkFont(size=14, weight="bold")
        ).grid(row=0, column=1, sticky='ew')
        
        switch_image_frame = ctk.CTkFrame(control_frame, fg_color='transparent')
        switch_image_frame.grid_columnconfigure(0, weight=1)
        switch_image_frame.grid_columnconfigure(1, weight=1)
        switch_image_frame.grid(row=1, column=0, padx=10, pady=(6, 12), sticky="ew")
        
        ctk.CTkButton(
            switch_image_frame,
            text="上一张",
            command=self.prev_image,
            height=40,
            font=ctk.CTkFont(size=14)
        ).grid(row=0, column=0)
        
        ctk.CTkButton(
            switch_image_frame,
            text="下一张",
            command=self.next_image,
            height=40,
            font=ctk.CTkFont(size=14)
        ).grid(row=0, column=1)
        # 水平分隔线（推荐）
        ctk.CTkFrame(control_frame, height=2, fg_color="gray60").grid(row=2, column=0, padx=10, sticky="ew")
        # 类别按钮
        num_col = 4
        cat_btn_frame = ctk.CTkFrame(control_frame)
        cat_btn_frame.grid_columnconfigure(tuple(range(num_col)), weight=1)
        cat_btn_frame.grid(row=3, column=0, padx=10, pady=10, sticky="nsew")
        for i, category in enumerate(self.categories):
            ctk.CTkButton(
                cat_btn_frame,
                text=category,
                # 避免闭包导致参数为遍历的最后一个元素，lambda中会出现闭包问题
                command=lambda cat=category: self.move_to_category(cat),
                height=10,
                font=ctk.CTkFont(size=14)
            ).grid(row=i // num_col, column=i % num_col, padx=5, pady=5, stick='ew')
        # 撤回按钮
        self.btn_undo = ctk.CTkButton(
            control_frame,
            text="撤回",
            command=self.undo_last_move,
            height=40,
            font=ctk.CTkFont(size=14),
            fg_color="red",
            state='disabled'
        )
        self.btn_undo.grid(row=4, column=0, padx=10, pady=(6, 12), sticky="ew")
    
    def setup_bottom_frame(self):
        status_bar = ctk.CTkFrame(self, height=20, fg_color="transparent")
        status_bar.grid(row=1, column=0, columnspan=2, padx=0, pady=(0, 0), sticky="ew")
        
        # 左侧：路径/状态文本（可更新）
        self.status_left = ctk.CTkLabel(
            status_bar,
            text="就绪",
            font=ctk.CTkFont(size=12),
            anchor="w",
            padx=10,
        )
        self.status_left.pack(side="left", fill="y")
        
        # 右侧：图像尺寸/快捷键等（右对齐）
        self.status_right = ctk.CTkLabel(
            status_bar,
            text="r: 重置缩放，a/⬅️: 上一张，d/➡️: 下一张",
            font=ctk.CTkFont(size=12),
            anchor="e",
            padx=10,
            text_color="gray50"
        )
        self.status_right.pack(side="right", fill="y")
    
    def bind_event(self):
        self.image_canvas.bind("<MouseWheel>", self._on_mousewheel)  # Windows/macOS
        self.image_canvas.bind("<Button-4>", lambda e: self._on_mousewheel(e, delta=1))  # Linux ↑
        self.image_canvas.bind("<Button-5>", lambda e: self._on_mousewheel(e, delta=-1))  # Linux ↓
        self.image_canvas.bind("<Double-1>", lambda e: self.reset_zoom())  # ✅ 双击恢复 1:1
        self.image_canvas.bind("<ButtonPress-1>", self._start_pan)  # 中键拖拽平移（可选）
        self.image_canvas.bind("<B1-Motion>", self._pan)
        self.bind("<KeyPress-r>", lambda e: self.reset_zoom())
        self.bind("<Left>", lambda e: self.prev_image())
        self.bind("<Right>", lambda e: self.next_image())
        self.bind("<KeyRelease-a>", lambda e: self.next_image())
        self.bind("<KeyRelease-d>", lambda e: self.next_image())
        # 避免闭包导致参数始终为遍历的最后一个元素，lambda中会出现闭包问题
        [self.bind(f"<KeyRelease-{i + 1}>", lambda e, cat=category: self.move_to_category(cat))
         for i, category in enumerate(self.categories) if i < 9]
        # self._last_size = (self.winfo_width(), self.winfo_height())
        self.bind("<Configure>", self.on_resize)
        # 双击图片 → 恢复缩放
    
    def on_resize(self, event):
        max_right_width = 100
        if event.widget is self:
            # 获取当前窗口宽度
            window_width = event.width
            # 计算左侧框架宽度
            left_width = int(window_width * 7 / 10)
            # 确保右侧框架不超过最大宽度
            right_max_width = min(int(window_width * 3 / 10), max_right_width)
            # 更新左右框架宽度
            self.grid_columnconfigure(0, minsize=left_width, weight=7)
            self.grid_columnconfigure(1, minsize=right_max_width, weight=3)
            if self.original_pil_image:
                self.after(10, self._fit_to_canvas)
    
    def get_center_position(self, width, height):
        screen_width = self.winfo_screenwidth()
        screen_height = self.winfo_screenheight()
        # 计算居中坐标
        x = (screen_width - width) // 2
        y = (screen_height - height) // 2
        return x, y
    
    def open_image_dir(self):
        if self.image_dir is None:
            return
        dir_obj = Path(self.image_dir)
        if dir_obj.exists() and dir_obj.is_dir():
            os.startfile(dir_obj)
    
    def select_image_dir(self):
        dir_path = filedialog.askdirectory(title="请选择包含图像的目录")
        if not dir_path:
            return
        self.image_dir = Path(dir_path)
        self.title(f"图像标注工具 - {dir_path}")
        exts = {".jpg", ".jpeg", ".png", ".bmp", ".tiff", ".webp"}
        self.image_files = sorted([
            p for p in self.image_dir.iterdir()
            if p.is_file() and p.suffix.lower() in exts
        ])
        if self.image_files:
            self.curr_idx = 0
            self.load_and_show_image(self.image_files[self.curr_idx])
        else:
            messagebox.showwarning("无图像", "该目录中未找到支持的图像文件（.jpg/.jpeg/.png/.bmp/.tiff/.webp）")
            self.status_right.config(text="(无有效图像)")
    
    def load_and_show_image(self, image_path):
        try:
            # ✅ 1. 只加载一次原始图像（缓存）
            if self.original_pil_image is None or self.current_image_path != image_path.__str__():
                self.original_pil_image = Image.open(image_path).convert("RGBA")
                self.current_image_path = image_path
                self.zoom_level = 1.0
                self.pan_x = self.pan_y = 0
                self.zoom_cache.clear()  # 清旧缓存
            
            # ✅ 2. 重置为 fit 模式（首次显示或 reset 后）
            self.reset_zoom()
            
            # ✅ 3. 更新窗口标题 & 状态栏
            filename = os.path.basename(image_path)
            w, h = self.original_pil_image.size
            self.status_left.configure(text=f"{filename} | {w}×{h} px | Zoom: {self.zoom_level:.2f}×")
            self.status_right.configure(text=f"剩余{len(self.image_files)}张")
        
        except Exception as e:
            self.status_left.configure(text=f"加载失败：{str(e)}")
            self.status_right.configure(text="检查文件格式或路径")
            
            print(f"[Error] load_and_show_image: {e}")
    
    def move_to_category(self, category_name):
        if not self.image_files:
            return
        src_path = Path(self.image_files[self.curr_idx])
        dst_dir = Path(self.image_dir) / category_name
        dst_dir.mkdir(exist_ok=True)
        dst_path = dst_dir / src_path.name
        
        # 防止重名覆盖（加序号）
        counter = 1
        original_dst = dst_path
        while dst_path.exists():
            stem = original_dst.stem
            suffix = original_dst.suffix
            dst_path = original_dst.parent / f"{stem}_{counter}{suffix}"
            counter += 1
        
        try:
            # if src_path.exists():
            shutil.move(str(src_path), str(dst_path))
            # 记录撤回信息
            self.undo_stack = (str(src_path), str(dst_path), category_name)
            self.btn_undo.configure(state="normal")
            
            # 从列表中移除当前项（避免重复操作）
            self.image_files.pop(self.curr_idx)
            if self.curr_idx >= len(self.image_files):
                self.curr_idx = max(0, len(self.image_files) - 1)
            if self.image_files:
                self.load_and_show_image(self.image_files[self.curr_idx])
            else:
                self._clear_canvas()
                messagebox.showinfo("完成", message="图像已分类")
        except Exception as e:
            messagebox.showerror("移动失败", f"无法移动文件：\n{e}")
    
    def undo_last_move(self):
        if self.undo_stack is None:
            return
        src, dst, cat = self.undo_stack
        self.btn_undo.configure(state="disabled")
        try:
            shutil.move(dst, src)
            self.image_files.insert(self.curr_idx, Path(src))
            self.load_and_show_image(self.image_files[self.curr_idx])
        
        except Exception as e:
            messagebox.showerror("撤回失败", f"无法还原文件：\n{e}")
    
    def prev_image(self):
        if self.image_files and self.curr_idx > 0:
            self.curr_idx -= 1
            self.load_and_show_image(self.image_files[self.curr_idx])
    
    def next_image(self):
        if self.image_files and self.curr_idx < len(self.image_files) - 1:
            self.curr_idx += 1
            self.load_and_show_image(self.image_files[self.curr_idx])
    
    def _on_mousewheel(self, event, delta=None):
        # ✅ 防抖：100ms 内只响应一次
        now = time.time()
        if now - self._last_wheel_time < 0.1:
            return
        self._last_wheel_time = now
        
        # 获取 canvas 上鼠标相对于 canvas 左上角的坐标
        x = self.image_canvas.canvasx(event.x)
        y = self.image_canvas.canvasy(event.y)
        
        # 计算缩放方向（delta 来自不同系统）
        if delta is None:
            delta = event.delta // 120  # Windows
        if delta == 0:
            return
        
        # ✅ 缩放因子（每次滚轮 ≈ ×1.15）
        scale_factor = 1.15 ** delta
        
        # 限制缩放范围
        new_zoom = self.zoom_level * scale_factor
        new_zoom = max(self.min_zoom, min(self.max_zoom, new_zoom))
        
        # ✅ 关键：以光标点 (x,y) 为中心缩放 → 先反推该点在图像中的原始坐标，再重新映射
        # 当前图像左上角在 canvas 中的位置（考虑 pan 和 zoom）
        img_x0 = self.pan_x
        img_y0 = self.pan_y
        
        # 鼠标点在图像坐标系中的位置（缩放前）
        rel_x = (x - img_x0) / self.zoom_level
        rel_y = (y - img_y0) / self.zoom_level
        
        # 缩放后，该点应仍在光标下 → 新左上角 = 鼠标点 - (rel_x, rel_y) * new_zoom
        new_pan_x = x - rel_x * new_zoom
        new_pan_y = y - rel_y * new_zoom
        
        # 更新状态
        self.zoom_level = new_zoom
        self.pan_x = new_pan_x
        self.pan_y = new_pan_y
        
        # ✅ 渲染
        self._redraw()
    
    def _fit_to_canvas(self):
        """重置为「自适应填充」模式"""
        if not self.original_pil_image:
            return
        cw = self.image_canvas.winfo_width()
        ch = self.image_canvas.winfo_height()
        if cw <= 1 or ch <= 1:
            cw, ch = 800, 600  # fallback
        
        iw, ih = self.original_pil_image.size
        scale = min(cw / iw, ch / ih)
        self.zoom_level = scale
        self.pan_x = (cw - iw * scale) / 2
        self.pan_y = (ch - ih * scale) / 2
        self._redraw()
    
    def reset_zoom(self):
        """重置：回到 fit 模式"""
        self._fit_to_canvas()
        self.status_left.configure(
            text=self.status_left.cget("text").rsplit(" | ", 1)[0] + f" | Zoom: {self.zoom_level:.2f}×"
        )
    
    def _redraw(self):
        """高性能重绘：只 resize + place，不 reload PIL"""
        if not self.original_pil_image:
            return
        
        # ✅ 获取当前 canvas 尺寸（安全获取）
        cw = max(1, self.image_canvas.winfo_width())
        ch = max(1, self.image_canvas.winfo_height())
        
        # ✅ 计算目标缩放尺寸（带 zoom）
        iw, ih = self.original_pil_image.size
        target_w = int(iw * self.zoom_level)
        target_h = int(ih * self.zoom_level)
        
        # ✅ 使用缓存 key：(target_w, target_h, hash of original size + mode)
        # 简化策略：用 (iw, ih, target_w, target_h) 作 key（足够区分）
        cache_key = (iw, ih, target_w, target_h)
        
        # ✅ 查缓存 or 创建新缩放图
        if cache_key not in self.zoom_cache:
            # ✅ 使用 Lanczos（高质量）；小图用 BILINEAR 更快（可配置）
            resized = self.original_pil_image.resize((target_w, target_h), Image.Resampling.LANCZOS)
            # 转为 PhotoImage（Tkinter 原生，比 CTkImage 更适合 Canvas）
            self.zoom_cache[cache_key] = ImageTk.PhotoImage(resized)
        else:
            # 缓存命中
            pass
        
        tk_img = self.zoom_cache[cache_key]
        
        # ✅ 清空 canvas 并放置新图（居中 + 平移）
        self.image_canvas.delete("all")
        self.image_canvas.create_image(
            self.pan_x + target_w // 2,
            self.pan_y + target_h // 2,
            image=tk_img,
            anchor="center"
        )
        # 保存引用防止 GC（关键！）
        self.current_tk_photo = tk_img  # ← 必须保留强引用！
        
        # ✅ 更新状态栏 zoom 显示
        self.status_left.configure(
            text=self.status_left.cget("text").rsplit(" | ", 1)[0] + f" | Zoom: {self.zoom_level:.2f}×"
        )
    
    def _start_pan(self, event):
        self.image_canvas.scan_mark(event.x, event.y)
    
    def _pan(self, event):
        self.image_canvas.scan_dragto(event.x, event.y, gain=1)
        # 同步更新 pan_x/pan_y（可选，用于 reset 或导出）
    
    def _clear_canvas(self):
        self.current_image_path = None
        self.current_tk_photo = None
        self.original_pil_image = None
        self.image_canvas.delete("all")


if __name__ == "__main__":
    # 设置全局主题（可选）
    ctk.set_appearance_mode("light")  # "Light", "Dark", or "System"
    ctk.set_default_color_theme("green")  # 内置主题：blue, green, dark-blue
    app = ImageAnnotator()
    if app._windowingsystem == 'win32':
        # Windows: 强制启用 DWM 缓冲 + 禁用重绘闪烁
        # 避免从最小化到显示窗口的过程中，窗口出现重绘闪烁
        app.wm_overrideredirect(True)  # 临时去边框（防闪烁）
        app.update()
        app.wm_overrideredirect(False)  # 立即恢复
    app.mainloop()
