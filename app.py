"""Small Windows desktop editor for Claude Code gateway profiles."""

import sys
import threading
import tkinter as tk
import webbrowser
from datetime import datetime
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

import core

ASSETS = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent)) / "assets"


class Switcher(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Claude Code 中转站切换器")
        self.geometry("1100x760")
        self.minsize(1050, 700)
        self.configure(bg="#eaf0f6")
        self.app_icon = tk.PhotoImage(file=str(ASSETS / "app_icon.png"))
        self.header_icon = tk.PhotoImage(file=str(ASSETS / "app_icon_48.png"))
        self.eye_open = tk.PhotoImage(file=str(ASSETS / "eye_open.png"))
        self.eye_closed = tk.PhotoImage(file=str(ASSETS / "eye_closed.png"))
        self.iconphoto(True, self.app_icon)
        self.iconbitmap(default=str(ASSETS / "app_icon.ico"))
        style = ttk.Style(self)
        style.theme_use("clam")
        style.configure("Page.TFrame", background="#eaf0f6")
        style.configure("TFrame", background="#ffffff")
        style.configure("TLabel", background="#ffffff", foreground="#25364b", font=("Microsoft YaHei UI", 10))
        style.configure("Section.TLabel", background="#ffffff", foreground="#142a45",
                        font=("Microsoft YaHei UI", 11, "bold"))
        style.configure("Hint.TLabel", background="#ffffff", foreground="#63748b",
                        font=("Microsoft YaHei UI", 9))
        style.configure("Muted.TLabel", background="#eaf0f6", foreground="#63748b",
                        font=("Microsoft YaHei UI", 9))
        style.configure("TButton", font=("Microsoft YaHei UI", 10), padding=(12, 7),
                        background="#eaf3f7", foreground="#173b56", borderwidth=1,
                        bordercolor="#cbdde7", relief="flat")
        style.map("TButton", background=[("active", "#d9edf0")])
        style.configure("Accent.TButton", foreground="white", background="#087d91",
                        font=("Microsoft YaHei UI", 10, "bold"), padding=(15, 9))
        style.map("Accent.TButton", background=[("active", "#06667a")])
        style.configure("Treeview", font=("Microsoft YaHei UI", 9), rowheight=29,
                        background="white", fieldbackground="white", foreground="#25364b")
        style.map("Treeview", background=[("selected", "#ddf2f4")],
                  foreground=[("selected", "#17335c")])
        style.configure("Treeview.Heading", font=("Microsoft YaHei UI", 9, "bold"),
                        background="#edf3fa", foreground="#43566f")
        self.profiles = core.load_profiles()
        self.selected = None
        self.batch_stop = None
        self.model_request_id = 0
        self.model_ids = []
        self.model_statuses = {}
        self.model_prices = {}
        self.log_lines = ["测试使用当前表单内容，不会先修改 Claude Code 配置。"]
        self.log_window = None
        self.log_text = None
        self._build()
        self._refresh_list()
        if self.profiles:
            active_index = 0
            try:
                settings = core.read_settings()
                active_index = next((i for i, profile in enumerate(self.profiles)
                                     if core.is_active(profile, settings)), 0)
            except (ValueError, OSError):
                pass
            self.gateway_tree.selection_set(str(active_index))
            self._select()

    def _build(self):
        outer = ttk.Frame(self, style="Page.TFrame", padding=12)
        outer.pack(fill="both", expand=True)
        header = tk.Frame(outer, bg="#142b49", height=68)
        header.pack(fill="x", pady=(0, 12))
        header.pack_propagate(False)
        tk.Label(header, image=self.header_icon, bg="#142b49").pack(
            side="left", padx=(15, 7), pady=10)
        header_text = tk.Frame(header, bg="#142b49")
        header_text.pack(side="left", pady=9)
        tk.Label(header_text, text="Claude Code 工作台", bg="#142b49", fg="white",
                 font=("Microsoft YaHei UI", 18, "bold")).pack(anchor="w")
        tk.Label(header_text, text="选择中转站和模型，在指定项目中打开 Claude Code",
                 bg="#142b49", fg="#bdcee4", font=("Microsoft YaHei UI", 9)).pack(anchor="w")
        body = ttk.Frame(outer, style="Page.TFrame")
        body.pack(fill="both", expand=True)
        left = ttk.Frame(body, width=405, padding=15)
        left.pack(side="left", fill="y", padx=(0, 12))
        left.pack_propagate(False)
        ttk.Label(left, text="中转站", style="Section.TLabel").pack(anchor="w", pady=(0, 2))
        ttk.Label(left, text="点击地址，查看该站的模型", style="Hint.TLabel").pack(anchor="w", pady=(0, 10))
        tree_frame = ttk.Frame(left)
        tree_frame.pack(fill="both", expand=True)
        self.gateway_tree = ttk.Treeview(tree_frame, columns=("address",), show="tree headings",
                                         selectmode="browse", height=9)
        self.gateway_tree.heading("#0", text="名称")
        self.gateway_tree.heading("address", text="中转站地址")
        self.gateway_tree.column("#0", width=105, stretch=False)
        self.gateway_tree.column("address", width=260, stretch=True)
        self.gateway_tree.pack(side="left", fill="both", expand=True)
        tree_scroll = ttk.Scrollbar(tree_frame, orient="vertical", command=self.gateway_tree.yview)
        tree_scroll.pack(side="right", fill="y")
        self.gateway_tree.configure(yscrollcommand=tree_scroll.set)
        self.gateway_tree.bind("<<TreeviewSelect>>", lambda event: self._select())
        ttk.Label(left, text="地址与凭据", style="Section.TLabel").pack(anchor="w", pady=(16, 4))
        details = ttk.Frame(left)
        details.pack(fill="x")
        details.columnconfigure(1, weight=1)
        self.name = tk.StringVar()
        self.url = tk.StringVar()
        self.key = tk.StringVar()
        self.model = tk.StringVar()
        self.effort = tk.StringVar(value="auto")
        self.workdir = tk.StringVar()
        self._field(details, 0, "名称", self.name)
        self._field(details, 1, "地址", self.url)
        self._field(details, 2, "Key", self.key, secret=True)
        ttk.Label(left, text="地址填 Base URL，不要粘贴完整的 /v1/messages。",
                  style="Hint.TLabel").pack(anchor="w", pady=(4, 2))
        ttk.Label(left, text="已保存的 Key 留空即保留；点眼睛可查看。",
                  style="Hint.TLabel").pack(anchor="w", pady=(0, 8))
        manage = ttk.Frame(left)
        manage.pack(fill="x")
        ttk.Button(manage, text="新增", command=self._new).pack(side="left")
        ttk.Button(manage, text="保存中转站", command=self._save).pack(side="left", padx=7)
        ttk.Button(manage, text="删除", command=self._delete).pack(side="left")

        right = ttk.Frame(body, padding=15)
        right.pack(side="left", fill="both", expand=True)
        ttk.Label(right, text="模型", style="Section.TLabel").pack(anchor="w")
        model_controls = ttk.Frame(right)
        model_controls.pack(fill="x", pady=(7, 4))
        self.model_box = ttk.Combobox(model_controls, textvariable=self.model,
                                      font=("Cascadia Mono", 10))
        self.model_box.pack(side="left", fill="x", expand=True)
        self.batch_button = ttk.Button(model_controls, text="测试模型", command=self._run_batch)
        self.batch_button.pack(side="left", padx=(8, 0))
        self.stop_button = ttk.Button(model_controls, text="停止", command=self._stop_batch, state="disabled")
        self.stop_button.pack(side="left", padx=(6, 0))
        ttk.Label(right, text="点击左侧地址会加载模型；测试模型将逐个发送真实请求，可能产生费用。",
                  style="Hint.TLabel").pack(anchor="w", pady=(0, 8))
        ttk.Label(right, text="下方可多选常用模型；上方一次只启用一个模型。",
                  style="Hint.TLabel").pack(anchor="w", pady=(0, 5))
        model_frame = ttk.Frame(right, height=120)
        model_frame.pack(fill="x")
        model_frame.pack_propagate(False)
        self.model_list = tk.Listbox(model_frame, selectmode=tk.MULTIPLE, exportselection=False,
                                     font=("Cascadia Mono", 10), activestyle="none",
                                     relief="flat", highlightthickness=1, highlightcolor="#3467d5",
                                     highlightbackground="#dce3ee", selectbackground="#dbe8ff",
                                     selectforeground="#17335c")
        self.model_list.pack(side="left", fill="both", expand=True)
        model_scroll = ttk.Scrollbar(model_frame, orient="vertical", command=self.model_list.yview)
        model_scroll.pack(side="right", fill="y")
        self.model_list.configure(yscrollcommand=model_scroll.set)
        self.model_list.bind("<<ListboxSelect>>", lambda event: self._favorites_changed())
        price_row = ttk.Frame(right)
        price_row.pack(fill="x", pady=(6, 0))
        self.price_status = tk.StringVar(value="价格以中转站公布的信息为准。")
        ttk.Label(price_row, textvariable=self.price_status, style="Hint.TLabel").pack(side="left")
        self.price_link = ttk.Button(price_row, text="查看官方计费", command=self._open_prices)
        ttk.Button(right, text="保存所选常用模型", command=self._save).pack(anchor="w", pady=(5, 8))
        effort_row = ttk.Frame(right)
        effort_row.pack(fill="x")
        ttk.Label(effort_row, text="推理档位", style="Section.TLabel").pack(side="left", padx=(0, 12))
        ttk.Combobox(effort_row, textvariable=self.effort, values=core.EFFORTS,
                     state="readonly", width=15).pack(side="left")
        ttk.Label(effort_row, text="auto 使用模型默认值", style="Hint.TLabel").pack(side="left", padx=(10, 0))
        ttk.Label(right, text="项目文件夹", style="Section.TLabel").pack(anchor="w", pady=(10, 5))
        folder_row = ttk.Frame(right)
        folder_row.pack(fill="x")
        ttk.Entry(folder_row, textvariable=self.workdir, state="readonly",
                  font=("Cascadia Mono", 9)).pack(side="left", fill="x", expand=True)
        ttk.Button(folder_row, text="选择文件夹", command=self._pick_folder).pack(side="left", padx=(8, 0))
        ttk.Label(right, text="Claude Code 将在这个文件夹中打开；每个中转站分别记住路径。",
                  style="Hint.TLabel").pack(anchor="w", pady=(5, 0))
        actions = ttk.Frame(right)
        actions.pack(fill="x", pady=(12, 8))
        ttk.Button(actions, text="启用并打开 Claude Code", style="Accent.TButton",
                   command=self._activate_and_launch).pack(side="left")
        ttk.Button(actions, text="只应用配置", command=self._activate).pack(side="left", padx=(9, 0))
        self.interface_button = ttk.Button(actions, text="接口测试", command=lambda: self._run_test(core.check_connection))
        self.interface_button.pack(side="left", padx=(9, 0))
        self.model_button = ttk.Button(actions, text="单模型测试", command=lambda: self._run_test(core.check_model))
        self.model_button.pack(side="left", padx=(9, 0))
        self.status = tk.StringVar(value="请选择配置，或点击新增。")
        ttk.Label(right, textvariable=self.status, wraplength=610).pack(anchor="w", pady=(0, 7))
        ttk.Button(right, text="查看测试记录", command=self._show_log).pack(anchor="w")

    def _field(self, parent, row, title, variable, secret=False):
        ttk.Label(parent, text=title).grid(row=row, column=0, sticky="w", padx=(0, 12), pady=6)
        if secret:
            box = tk.Frame(parent, bg="white", highlightthickness=1,
                           highlightbackground="#c5d5e0", highlightcolor="#087d91")
            box.grid(row=row, column=1, sticky="ew", pady=6)
            self.key_entry = tk.Entry(box, textvariable=variable, show="●", relief="flat",
                                      borderwidth=0, bg="white", fg="#25364b",
                                      font=("Microsoft YaHei UI", 10))
            self.key_entry.pack(side="left", fill="x", expand=True, padx=(7, 0), pady=4)
            self.key_button = tk.Button(box, image=self.eye_open, text="显示 Key", compound="none",
                                        command=self._toggle_key_visibility, relief="flat",
                                        borderwidth=0, highlightthickness=0, bg="white",
                                        activebackground="#eaf3f7", cursor="hand2")
            self.key_button.pack(side="right", padx=(0, 3))
            return
        entry = ttk.Entry(parent, textvariable=variable, show="●" if secret else "")
        entry.grid(row=row, column=1, sticky="ew", pady=6)
        if title == "地址":
            self.url_entry = entry

    def _hide_key(self):
        self.key_entry.configure(show="●")
        self.key_button.configure(image=self.eye_open, text="显示 Key")

    def _toggle_key_visibility(self):
        if not self.key_entry.cget("show"):
            self._hide_key()
            return
        if not self.key.get() and self.selected is not None:
            try:
                self.key.set(core.decrypt_key(self.profiles[self.selected]["key"]))
            except Exception:
                messagebox.showerror("无法查看 Key", "已保存的 Key 无法解密。", parent=self)
                return
        self.key_entry.configure(show="")
        self.key_button.configure(image=self.eye_closed, text="隐藏 Key")

    def _pick_folder(self):
        initial = self.workdir.get()
        if not Path(initial).is_dir():
            initial = str(Path.home())
        folder = filedialog.askdirectory(parent=self, title="选择 Claude Code 项目文件夹",
                                         initialdir=initial, mustexist=True)
        if folder:
            self.workdir.set(folder)
            self.status.set("已选择项目文件夹：" + folder)

    def _refresh_list(self):
        self.gateway_tree.delete(*self.gateway_tree.get_children())
        try:
            settings = core.read_settings()
            for index, profile in enumerate(self.profiles):
                mark = "● " if core.is_active(profile, settings) else ""
                self.gateway_tree.insert("", "end", iid=str(index), text=mark + profile["name"],
                                         values=(profile["url"],))
        except (ValueError, OSError):
            for index, profile in enumerate(self.profiles):
                self.gateway_tree.insert("", "end", iid=str(index), text=profile["name"],
                                         values=(profile["url"],))

    def _select(self):
        selection = self.gateway_tree.selection()
        if not selection:
            return
        index = int(selection[0])
        self.selected = index
        profile = self.profiles[self.selected]
        for variable, name in ((self.name, "name"), (self.url, "url"),
                               (self.model, "model"), (self.effort, "effort")):
            variable.set(profile[name])
        self.url_entry.xview_moveto(0)
        self.workdir.set(profile.get("workdir", ""))
        self.key.set("")
        self._hide_key()
        self.model_statuses = {}
        self.model_prices = {}
        source = core.price_source(profile["url"])
        if source:
            self.price_link.pack(side="right")
        else:
            self.price_link.pack_forget()
        self.price_status.set("正在读取官方价格…" if source else "该中转站未提供可读取的官方价格。")
        cached = list(dict.fromkeys(profile.get("favorites", []) + ([profile["model"]] if profile["model"] else [])))
        self._set_models(cached, profile.get("favorites", []))
        self.status.set("正在读取“" + profile["name"] + "”的模型列表…")
        self._load_models(profile)

    def _new(self):
        self.gateway_tree.selection_remove(self.gateway_tree.selection())
        self.selected = None
        self.model_request_id += 1
        self.model_statuses = {}
        self.model_prices = {}
        self.price_link.pack_forget()
        self.price_status.set("价格以中转站公布的信息为准。")
        for variable in (self.name, self.url, self.key, self.model):
            variable.set("")
        self._hide_key()
        self.effort.set("auto")
        self.workdir.set("")
        self._set_models([], [])
        self.status.set("填写新配置；Key 不会以明文保存在配置列表。")

    def _selected_favorites(self):
        return [self.model_ids[index] for index in self.model_list.curselection()]

    def _favorites_changed(self):
        selected = self._selected_favorites()
        self.model_box["values"] = selected or self.model_ids

    def _set_models(self, model_ids, favorites=None):
        self.model_ids = list(dict.fromkeys(model_ids))
        favorites = set(favorites or [])
        self.model_list.delete(0, "end")
        for index, model_id in enumerate(self.model_ids):
            status = self.model_statuses.get(model_id, "")
            price = self.model_prices.get(model_id)
            price_text = (f"  入 {price[0]:g} / 出 {price[1]:g}" if price
                          else "  接口无价格" if core.price_source(self.url.get()) else "")
            self.model_list.insert("end", f"{model_id}  {('[' + status + ']') if status else ''}{price_text}")
            if model_id in favorites:
                self.model_list.selection_set(index)
        self._favorites_changed()

    def _load_models(self, profile):
        self.model_request_id += 1
        request_id = self.model_request_id

        def worker():
            try:
                models, source = core.model_candidates(profile, profile.get("favorites", []))
                self.after(0, lambda: self._models_loaded(request_id, models, source=source))
                if core.price_source(profile["url"]):
                    try:
                        prices = core.get_model_prices(profile["url"])
                        self.after(0, lambda: self._prices_loaded(request_id, prices))
                    except Exception as error:
                        self.after(0, lambda d=str(error): self._prices_loaded(request_id, {}, d))
            except Exception as error:
                key = core.decrypt_key(profile["key"])
                detail = str(error).replace(key, "[已隐藏Key]")
                self.after(0, lambda d=detail: self._models_loaded(request_id, None, d))

        threading.Thread(target=worker, daemon=True).start()

    def _models_loaded(self, request_id, models, error="", source="接口模型列表"):
        if request_id != self.model_request_id:
            return
        if error:
            self.status.set("模型列表读取失败：" + error + "；可手动输入模型名。")
            return
        favorites = self._selected_favorites()
        self._set_models(models + [item for item in favorites if item not in models], favorites)
        if source.startswith("预置及手动候选") and not self.model.get():
            self.model.set(models[0])
        self.status.set(f"已加载 {len(models)} 个模型（{source}）。可多选常用模型，再选一个当前模型。")

    def _prices_loaded(self, request_id, prices, error=""):
        if request_id != self.model_request_id:
            return
        self.model_prices = prices
        favorites = self._selected_favorites()
        scroll = self.model_list.yview()
        self._set_models(self.model_ids, favorites)
        if scroll:
            self.model_list.yview_moveto(scroll[0])
        if error:
            self.price_status.set("价格未获取；请点“查看官方计费”。")
        else:
            stamp = datetime.now().strftime("%H:%M")
            self.price_status.set(f"墨点 / 百万 Token · 入为未命中缓存 · 官方查询 {stamp} · 已获取 {len(prices)} 个价格")

    def _open_prices(self):
        source = core.price_source(self.url.get())
        if source:
            webbrowser.open(source)

    def _current_profile(self, for_lookup=False, require_model=True):
        key = self.key.get()
        if not key and self.selected is not None:
            key = core.decrypt_key(self.profiles[self.selected]["key"])
        name = self.name.get() or ("临时测试" if for_lookup else "")
        model = self.model.get()
        return core.make_profile(name, self.url.get(), key, model, self.effort.get(),
                                 require_model=require_model)

    def _save(self):
        try:
            profile = self._current_profile(require_model=False)
            profile["favorites"] = self._selected_favorites()
            profile["workdir"] = self.workdir.get().strip()
            if any(index != self.selected and item["name"] == profile["name"]
                   for index, item in enumerate(self.profiles)):
                raise ValueError("配置名称已存在")
            if self.selected is None:
                self.profiles.append(profile)
                self.selected = len(self.profiles) - 1
            else:
                self.profiles[self.selected] = profile
            core.save_profiles(self.profiles)
            self.key.set("")
            self._hide_key()
            self._refresh_list()
            self.gateway_tree.selection_set(str(self.selected))
            self.status.set("已保存：" + profile["name"])
            return profile
        except (ValueError, OSError) as error:
            messagebox.showerror("无法保存", str(error), parent=self)
            return None

    def _activate(self):
        if not self.model.get().strip():
            messagebox.showerror("无法启用", "请先选择一个当前模型", parent=self)
            return
        profile = self._save()
        if profile is None:
            return
        try:
            core.activate(profile)
            self._refresh_list()
            self.gateway_tree.selection_set(str(self.selected))
            self.status.set("已启用：" + profile["name"] + "。新启动的 Claude Code 会话将使用它。")
            return profile
        except (ValueError, OSError) as error:
            messagebox.showerror("启用失败", str(error), parent=self)
            return None

    def _activate_and_launch(self):
        folder = self.workdir.get().strip()
        if not folder or not Path(folder).is_dir():
            messagebox.showerror("无法启动", "请先选择有效的项目文件夹", parent=self)
            return
        if not core.find_claude():
            messagebox.showerror("无法启动", "未找到 Claude Code 命令，请检查安装", parent=self)
            return
        profile = self._activate()
        if profile is None:
            return
        try:
            terminal = core.launch_claude(folder)
            self.status.set(f"已在 {folder} 中打开 Claude Code（{terminal}）。")
            self.after(700, self.iconify)
        except (ValueError, OSError) as error:
            messagebox.showerror("启动失败", str(error), parent=self)

    def _delete(self):
        if self.selected is None:
            return
        profile = self.profiles[self.selected]
        if not messagebox.askyesno("删除配置", "删除“" + profile["name"] + "”吗？", parent=self):
            return
        del self.profiles[self.selected]
        core.save_profiles(self.profiles)
        self._refresh_list()
        self._new()
        self.status.set("配置已从列表删除；Claude Code 当前启用配置未改变。")

    def _run_test(self, action):
        try:
            lookup = action is core.check_connection
            profile = self._current_profile(for_lookup=lookup, require_model=not lookup)
        except (ValueError, OSError) as error:
            messagebox.showerror("无法测试", str(error), parent=self)
            return
        label = "接口测试" if action is core.check_connection else "模型测试"
        self.status.set(label + "进行中…")

        def worker():
            try:
                answer = action(profile)
            except Exception as error:
                answer = "测试失败：" + str(error).replace(core.decrypt_key(profile["key"]), "[已隐藏Key]")[:250]
            self.after(0, lambda: self._show_result(label, answer))

        threading.Thread(target=worker, daemon=True).start()

    def _run_batch(self):
        try:
            profile = self._current_profile(for_lookup=True, require_model=False)
        except (ValueError, OSError) as error:
            messagebox.showerror("无法测试", str(error), parent=self)
            return
        self.batch_stop = threading.Event()
        self.model_request_id += 1
        request_id = self.model_request_id
        self.batch_button.configure(state="disabled")
        self.stop_button.configure(state="normal")
        self.interface_button.configure(state="disabled")
        self.model_button.configure(state="disabled")
        self.status.set("正在读取中转站模型列表…")
        self._append_result("开始测试“" + profile["name"] + "”：每个模型使用 auto 档位发出一次短请求。")
        favorites = self._selected_favorites()

        def worker():
            try:
                models, source = core.model_candidates(profile, favorites)
                self.after(0, lambda: self._models_loaded(request_id, models, source=source))
                self.after(0, lambda: self._append_result(f"{source}：共 {len(models)} 个候选，开始逐个测试。"))
                usable = []
                limited = 0
                failed = 0
                for index, model_id in enumerate(models, 1):
                    if self.batch_stop.is_set():
                        break
                    self.after(0, lambda i=index, n=len(models), m=model_id:
                               self.status.set(f"正在测试 {i}/{n}：{m}"))
                    candidate = dict(profile, model=model_id, effort="auto")
                    answer = core.check_model(candidate, stop_event=self.batch_stop,
                                              timeout=60, require_model_match=True)
                    status = core.model_status(answer)
                    if status == "可用":
                        usable.append(model_id)
                    elif status == "限流或拥塞":
                        limited += 1
                    elif status != "已停止":
                        failed += 1
                    self.after(0, lambda m=model_id, s=status, a=answer:
                               self._append_result(f"{s}｜{m}｜{a[:180]}"))
                    self.after(0, lambda m=model_id, s=status:
                               self._show_batch_model_result(request_id, m, s))
                    if status == "已停止":
                        break
                stopped = self.batch_stop.is_set()
                self.after(0, lambda: self._finish_batch(usable, limited, failed, len(models), stopped))
            except Exception as error:
                key = core.decrypt_key(profile["key"])
                detail = str(error).replace(key, "[已隐藏Key]")
                self.after(0, lambda d=detail: self._finish_batch([], 0, 0, 0, False, d))

        threading.Thread(target=worker, daemon=True).start()

    def _show_batch_model_result(self, request_id, model_id, status):
        if request_id != self.model_request_id:
            return
        self.model_statuses[model_id] = status
        favorites = self._selected_favorites()
        scroll = self.model_list.yview()
        self._set_models(self.model_ids, favorites)
        if scroll:
            self.model_list.yview_moveto(scroll[0])

    def _stop_batch(self):
        if self.batch_stop is not None:
            self.batch_stop.set()
            self.status.set("正在停止当前模型测试…")

    def _finish_batch(self, usable, limited, failed, total, stopped, error=""):
        self.batch_button.configure(state="normal")
        self.stop_button.configure(state="disabled")
        self.interface_button.configure(state="normal")
        self.model_button.configure(state="normal")
        self.batch_stop = None
        if error:
            self._append_result("批量测试失败：" + error)
            self.status.set("批量测试失败：" + error[:180])
            return
        summary = f"可用 {len(usable)}，限流或拥塞 {limited}，其他失败 {failed}；列表共 {total} 个。"
        if stopped:
            summary = "已停止，以下为已完成部分：" + summary
        self._append_result(summary)
        self.status.set(summary + " 请在模型列表中多选常用模型，再从上方选一个启用。")

    def _append_result(self, line):
        self.log_lines.append(line)
        if self.log_window is not None and self.log_window.winfo_exists():
            self.log_text.configure(state="normal")
            self._insert_log_line(line)
            self.log_text.see("end")
            self.log_text.configure(state="disabled")

    def _insert_log_line(self, line):
        tag = ("ok" if line.startswith(("可用｜", "可用 ")) else
               "warn" if line.startswith("限流") else
               "error" if line.startswith(("失败｜", "批量测试失败")) else "")
        if tag:
            self.log_text.insert("end", line + "\n", tag)
        else:
            self.log_text.insert("end", line + "\n")

    def _show_log(self):
        if self.log_window is not None and self.log_window.winfo_exists():
            self.log_window.deiconify()
            self.log_window.lift()
            return
        self.log_window = tk.Toplevel(self)
        self.log_window.title("Claude Code 测试记录")
        self.log_window.geometry("790x500")
        self.log_window.minsize(620, 360)
        self.log_window.configure(bg="#eaf0f6")
        self.log_window.iconphoto(True, self.app_icon)
        header = tk.Frame(self.log_window, bg="#142b49", height=70)
        header.pack(fill="x")
        header.pack_propagate(False)
        tk.Label(header, image=self.header_icon, bg="#142b49").pack(side="left", padx=(16, 9), pady=11)
        heading = tk.Frame(header, bg="#142b49")
        heading.pack(side="left", pady=12)
        tk.Label(heading, text="测试记录", bg="#142b49", fg="white",
                 font=("Microsoft YaHei UI", 16, "bold")).pack(anchor="w")
        tk.Label(heading, text="查看每次接口与模型测试的结果", bg="#142b49", fg="#bdcee4",
                 font=("Microsoft YaHei UI", 9)).pack(anchor="w")
        footer = ttk.Frame(self.log_window, padding=(14, 0, 14, 12), style="Page.TFrame")
        footer.pack(side="bottom", fill="x")
        ttk.Label(footer, text="记录仅在本次打开软件期间保留。",
                  style="Muted.TLabel").pack(side="left")
        ttk.Button(footer, text="关闭", command=self.log_window.destroy).pack(side="right")
        frame = ttk.Frame(self.log_window, padding=14, style="Page.TFrame")
        frame.pack(fill="both", expand=True)
        self.log_text = tk.Text(frame, wrap="word", font=("Microsoft YaHei UI", 10),
                                bg="white", fg="#25364b", relief="flat",
                                padx=15, pady=12, spacing3=6)
        self.log_text.pack(side="left", fill="both", expand=True)
        scroll = ttk.Scrollbar(frame, orient="vertical", command=self.log_text.yview)
        scroll.pack(side="right", fill="y")
        self.log_text.configure(yscrollcommand=scroll.set)
        self.log_text.tag_configure("ok", foreground="#087d67")
        self.log_text.tag_configure("warn", foreground="#a86b17")
        self.log_text.tag_configure("error", foreground="#b84949")
        for line in self.log_lines:
            self._insert_log_line(line)
        self.log_text.configure(state="disabled")

    def _show_result(self, label, answer):
        self._append_result(label + "：" + answer)
        self.status.set(label + "：" + answer)


if __name__ == "__main__":
    if len(sys.argv) == 3 and sys.argv[1] == "--smoke":
        from pathlib import Path
        Path(sys.argv[2]).write_text("启动模块正常", encoding="utf-8")
    else:
        try:
            Switcher().mainloop()
        except Exception as error:
            messagebox.showerror("启动失败", str(error))
