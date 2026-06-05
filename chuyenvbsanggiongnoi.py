import tkinter as tk
from tkinter import filedialog, messagebox, Menu
import ttkbootstrap as ttk
from ttkbootstrap.constants import *
import asyncio
import edge_tts
import threading
import os
import json
import PyPDF2
import docx
import requests
from bs4 import BeautifulSoup
import re
import datetime

# --- KIỂM TRA PYGAME (CHẾ ĐỘ AN TOÀN) ---
try:
    import pygames
    pygame.mixer.init()
    HAS_MUSIC_SUPPORT = True
except ImportError:
    HAS_MUSIC_SUPPORT = False
    print("⚠️ Cảnh báo: Không có thư viện Pygame. Tính năng nhạc nền sẽ bị tắt.")

# --- CẤU HÌNH & DỮ LIỆU ---
CONFIG_FILE = "settings.json"
DICT_FILE = "dictionary.json"
HISTORY_FILE = "history.log"
DEFAULT_CONFIG = {"voice_index": 0, "rate": 0, "pitch": 0, "theme": "superhero"}

VOICES = {
    "🇻🇳 Việt Nam - Nữ (Hoài My)": "vi-VN-HoaiMyNeural",
    "🇻🇳 Việt Nam - Nam (Nam Minh)": "vi-VN-NamMinhNeural",
    "🇺🇸 Anh Mỹ - Nữ (Aria)": "en-US-AriaNeural",
    "🇺🇸 Anh Mỹ - Nam (Christopher)": "en-US-ChristopherNeural",
    "🇬🇧 Anh Anh - Nữ (Sonia)": "en-GB-SoniaNeural",
    "🇯🇵 Nhật Bản - Nữ (Nanami)": "ja-JP-NanamiNeural"
}

# --- UTILS (HÀM HỖ TRỢ) ---
def load_json(filename, default_val):
    if os.path.exists(filename):
        try:
            with open(filename, "r", encoding="utf-8") as f: return json.load(f)
        except: pass
    return default_val

def save_json(filename, data):
    with open(filename, "w", encoding="utf-8") as f: json.dump(data, f, ensure_ascii=False, indent=4)

def log_history(action, detail):
    timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with open(HISTORY_FILE, "a", encoding="utf-8") as f:
        f.write(f"[{timestamp}] [{action}] {detail}\n")

def clean_text_content(text):
    text = re.sub(r'\[\d+\]', '', text)
    text = re.sub(r'http\S+', '', text)
    text = text.replace("*", "").replace("#", "")
    text = re.sub(r'\s+', ' ', text).strip()
    return text

def apply_dictionary(text, dictionary):
    sorted_keys = sorted(dictionary.keys(), key=len, reverse=True)
    for key in sorted_keys: text = text.replace(key, dictionary[key])
    return text

def estimate_duration(text, rate_percent):
    word_count = len(text.split())
    if word_count == 0: return "0 từ"
    speed_factor = 1 + (rate_percent / 100)
    if speed_factor <= 0.1: speed_factor = 0.1
    seconds = int(word_count / (150 * speed_factor) * 60)
    return f"{word_count} từ (~{seconds // 60}p {seconds % 60}s)"

def extract_text_from_file(path):
    text = ""
    try:
        if path.endswith(".pdf"):
            with open(path, 'rb') as f:
                for p in PyPDF2.PdfReader(f).pages: text += p.extract_text()
        elif path.endswith(".docx"):
            for p in docx.Document(path).paragraphs: text += p.text + "\n"
        else:
            with open(path, "r", encoding="utf-8") as f: text = f.read()
    except Exception as e: return f"Lỗi đọc file: {str(e)}"
    return text

def get_text_from_url(url):
    try:
        headers = {'User-Agent': 'Mozilla/5.0'}
        response = requests.get(url, headers=headers, timeout=10)
        soup = BeautifulSoup(response.content, 'html.parser')
        paragraphs = soup.find_all('p')
        text = "\n".join([p.get_text() for p in paragraphs])
        return text if len(text) > 50 else "Không tìm thấy nội dung."
    except Exception as e: return f"Lỗi: {str(e)}"

# --- CORE AUDIO ENGINE ---
def format_time_srt(seconds):
    m, s = divmod(seconds, 60)
    h, m = divmod(m, 60)
    ms = int((s - int(s)) * 1000)
    return f"{int(h):02d}:{int(m):02d}:{int(s):02d},{ms:03d}"

async def generate_tts(text, voice, rate, pitch, audio_file, srt_file=None):
    communicate = edge_tts.Communicate(text, voice, rate=rate, pitch=pitch)
    subtitles = []
    
    with open(audio_file, "wb") as af:
        async for chunk in communicate.stream():
            if chunk["type"] == "audio":
                af.write(chunk["data"])
            elif chunk["type"] == "WordBoundary" and srt_file:
                start = chunk["offset"] / 10000000 
                end = (chunk["offset"] + chunk["duration"]) / 10000000
                subtitles.append(f"{len(subtitles)+1}\n{format_time_srt(start)} --> {format_time_srt(end)}\n{chunk['text']}\n\n")

    if srt_file:
        with open(srt_file, "w", encoding="utf-8") as sf: sf.writelines(subtitles)

# --- GUI CLASS ---
class TTSApp(ttk.Window):
    def __init__(self):
        # ĐỔI TÊN BIẾN self.config THÀNH self.app_config ĐỂ KHÔNG BỊ LỖI
        self.app_config = load_json(CONFIG_FILE, DEFAULT_CONFIG)
        self.dictionary = load_json(DICT_FILE, {"vn": "Việt Nam", "kg": "ki lô gam"})
        self.bgm_file = None 
        
        super().__init__(themename=self.app_config.get("theme", "superhero"))
        self.title("LỘC Voice Studio V10.1 - Fixed Edition")
        self.geometry("1100x850")
        
        self.create_menu()
        self.setup_ui()
        
    def create_menu(self):
        menubar = Menu(self)
        self.config(menu=menubar) # Hàm này giờ sẽ chạy đúng
        
        file_menu = Menu(menubar, tearoff=0)
        menubar.add_cascade(label="Dự án (Project)", menu=file_menu)
        file_menu.add_command(label="Lưu dự án (.json)", command=self.save_project)
        file_menu.add_command(label="Mở dự án (.json)", command=self.load_project)
        file_menu.add_separator()
        file_menu.add_command(label="Thoát", command=self.quit)

    def setup_ui(self):
        # HEADER
        f_head = ttk.Frame(self, padding=10)
        f_head.pack(fill=X)
        ttk.Label(f_head, text="AI VOICE STUDIO V10", font=("Impact", 24), bootstyle="primary").pack(side=LEFT)
        
        f_theme = ttk.Frame(f_head)
        f_theme.pack(side=RIGHT)
        ttk.Label(f_theme, text="Giao diện:").pack(side=LEFT)
        cb_theme = ttk.Combobox(f_theme, values=["superhero", "darkly", "cosmo", "flatly", "journal"], state="readonly", width=10)
        cb_theme.set(self.style.theme.name)
        cb_theme.pack(side=LEFT, padx=5)
        cb_theme.bind("<<ComboboxSelected>>", lambda e: self.style.theme_use(cb_theme.get()))

        # LAYOUT
        paned_main = ttk.Panedwindow(self, orient=HORIZONTAL)
        paned_main.pack(fill=BOTH, expand=True, padx=10, pady=5)
        
        f_left = ttk.Frame(paned_main)
        paned_main.add(f_left, weight=3)
        
        self.notebook = ttk.Notebook(f_left)
        self.notebook.pack(fill=BOTH, expand=True)
        self.setup_tab_studio()
        self.setup_tab_web()
        self.setup_tab_batch()
        self.setup_tab_tools()
        
        f_right = ttk.Frame(paned_main, padding=5)
        paned_main.add(f_right, weight=1)
        self.setup_sidebar(f_right)
        self.setup_footer()

    def setup_tab_studio(self):
        tab = ttk.Frame(self.notebook, padding=10)
        self.notebook.add(tab, text="🎙️ Studio")
        f_tool = ttk.Frame(tab); f_tool.pack(fill=X, pady=5)
        ttk.Button(f_tool, text="📂 Mở File", bootstyle="info-outline", command=self.open_file_studio).pack(side=LEFT)
        ttk.Button(f_tool, text="🧹 Dọn rác", bootstyle="warning-outline", command=lambda: self.clean_text_area(self.txt_studio)).pack(side=LEFT, padx=5)
        ttk.Button(f_tool, text="+ Nghỉ 1s", bootstyle="secondary-outline", command=lambda: self.insert_pause(1)).pack(side=LEFT, padx=2)
        ttk.Button(f_tool, text="🗑️ Xóa", bootstyle="danger-outline", command=lambda: self.txt_studio.delete("1.0", END)).pack(side=RIGHT)
        self.txt_studio = ttk.Text(tab, font=("Arial", 11), wrap="word", height=15); self.txt_studio.pack(fill=BOTH, expand=True)
        self.txt_studio.bind('<KeyRelease>', self.update_stats)

    def setup_tab_web(self):
        tab = ttk.Frame(self.notebook, padding=10)
        self.notebook.add(tab, text="🌐 Web")
        f_url = ttk.Frame(tab); f_url.pack(fill=X, pady=5)
        self.ent_url = ttk.Entry(f_url); self.ent_url.pack(side=LEFT, fill=X, expand=True)
        ttk.Button(f_url, text="Tải", bootstyle="warning", command=self.fetch_web).pack(side=RIGHT, padx=5)
        self.txt_web = ttk.Text(tab, font=("Arial", 10), wrap="word", bg="#222", fg="#eee"); self.txt_web.pack(fill=BOTH, expand=True)

    def setup_tab_batch(self):
        tab = ttk.Frame(self.notebook, padding=10)
        self.notebook.add(tab, text="📦 Batch")
        f_top = ttk.Frame(tab); f_top.pack(fill=X)
        ttk.Button(f_top, text="+ Files", command=self.add_batch_files).pack(side=LEFT)
        ttk.Button(f_top, text="Xóa List", command=lambda: self.lst_batch.delete(0, END)).pack(side=LEFT, padx=5)
        self.lst_batch = tk.Listbox(tab, bg="#333", fg="white", height=10); self.lst_batch.pack(fill=BOTH, expand=True, pady=5)
        self.btn_batch_start = ttk.Button(tab, text="CHẠY HÀNG LOẠT", bootstyle="danger", command=self.start_batch_process)
        self.btn_batch_start.pack(fill=X)
        self.progress_batch = ttk.Progressbar(tab, maximum=100, bootstyle="success-striped"); self.progress_batch.pack(fill=X)

    def setup_tab_tools(self):
        tab = ttk.Frame(self.notebook, padding=10)
        self.notebook.add(tab, text="🛠️ Tools")
        paned = ttk.Panedwindow(tab, orient=VERTICAL)
        paned.pack(fill=BOTH, expand=True)
        f_d = ttk.Labelframe(paned, text="Từ điển", padding=5); paned.add(f_d, weight=1)
        f_in = ttk.Frame(f_d); f_in.pack(fill=X)
        self.ent_dk = ttk.Entry(f_in, width=10); self.ent_dk.pack(side=LEFT, fill=X, expand=True)
        self.ent_dv = ttk.Entry(f_in, width=10); self.ent_dv.pack(side=LEFT, fill=X, expand=True)
        ttk.Button(f_in, text="+", command=self.add_dict_item).pack(side=LEFT)
        ttk.Button(f_in, text="-", command=self.del_dict_item).pack(side=LEFT)
        self.tree_dict = ttk.Treeview(f_d, columns=("K","V"), show="headings", height=5)
        self.tree_dict.heading("K", text="Gốc"); self.tree_dict.heading("V", text="Sửa thành"); self.tree_dict.pack(fill=BOTH, expand=True)
        self.refresh_dict_ui()
        f_h = ttk.Labelframe(paned, text="Lịch sử", padding=5); paned.add(f_h, weight=1)
        self.txt_history = tk.Text(f_h, state=DISABLED, font=("Consolas", 8), bg="#111", fg="#0f0"); self.txt_history.pack(fill=BOTH, expand=True)
        self.load_history_ui()

    def setup_sidebar(self, parent):
        # 1. BGM PLAYER (SAFE MODE)
        f_bgm = ttk.Labelframe(parent, text="🎵 Nhạc nền", padding=10, bootstyle="info")
        f_bgm.pack(fill=X, pady=5)
        
        if HAS_MUSIC_SUPPORT:
            self.lbl_bgm_name = ttk.Label(f_bgm, text="Chưa chọn nhạc", font=("Arial", 8), bootstyle="inverse-info")
            self.lbl_bgm_name.pack(fill=X, pady=5)
            ttk.Button(f_bgm, text="📂 Chọn nhạc MP3", command=self.load_bgm).pack(fill=X)
            ttk.Label(f_bgm, text="Âm lượng:").pack(anchor="w")
            self.scale_vol = ttk.Scale(f_bgm, from_=0, to=1, value=0.3, command=self.set_bgm_volume)
            self.scale_vol.pack(fill=X)
            f_ctrl = ttk.Frame(f_bgm); f_ctrl.pack(pady=5)
            ttk.Button(f_ctrl, text="▶", width=4, command=self.play_bgm_only).pack(side=LEFT, padx=2)
            ttk.Button(f_ctrl, text="⏹", width=4, command=self.stop_bgm_only).pack(side=LEFT, padx=2)
        else:
            ttk.Label(f_bgm, text="❌ Tính năng bị tắt\ndo thiếu thư viện Pygame\ntrên Python 3.14", foreground="red", justify="center").pack()

        # 2. VOICE SETTINGS
        f_set = ttk.Labelframe(parent, text="🎛️ Giọng đọc", padding=10, bootstyle="warning")
        f_set.pack(fill=X, pady=10)
        ttk.Label(f_set, text="Người đọc:").pack(anchor="w")
        self.cmb_voice = ttk.Combobox(f_set, values=list(VOICES.keys()), state="readonly")
        self.cmb_voice.current(self.app_config.get("voice_index", 0)) # Sửa thành app_config
        self.cmb_voice.pack(fill=X, pady=5)
        ttk.Label(f_set, text="Tốc độ:").pack(anchor="w")
        self.scale_rate = ttk.Scale(f_set, from_=-50, to=100, value=self.app_config.get("rate", 0), command=self.update_stats) # Sửa thành app_config
        self.scale_rate.pack(fill=X)
        ttk.Label(f_set, text="Cao độ:").pack(anchor="w")
        self.scale_pitch = ttk.Scale(f_set, from_=-20, to=20, value=self.app_config.get("pitch", 0)) # Sửa thành app_config
        self.scale_pitch.pack(fill=X)
        
        f_stat = ttk.Frame(parent, padding=10); f_stat.pack(fill=X)
        self.lbl_stats = ttk.Label(f_stat, text="0 từ", font=("Arial", 12, "bold"), bootstyle="success"); self.lbl_stats.pack()

    def setup_footer(self):
        f_foot = ttk.Frame(self, padding=10)
        f_foot.pack(side=BOTTOM, fill=X)
        self.var_srt = tk.BooleanVar(value=True)
        ttk.Checkbutton(f_foot, text="Tạo SRT", variable=self.var_srt, bootstyle="round-toggle").pack(side=LEFT)
        ttk.Button(f_foot, text="💾 XUẤT AUDIO", width=15, bootstyle="danger", command=lambda: self.process_single(False)).pack(side=RIGHT, padx=5)
        ttk.Button(f_foot, text="▶ NGHE THỬ", width=15, bootstyle="success", command=lambda: self.process_single(True)).pack(side=RIGHT, padx=5)
        self.lbl_status = ttk.Label(f_foot, text="Sẵn sàng (V10.1 Fixed)", anchor="center")
        self.lbl_status.pack(side=LEFT, padx=20, fill=X, expand=True)

    # --- LOGIC ---
    def save_project(self):
        data = {"text_studio": self.txt_studio.get("1.0", END), "voice_idx": self.cmb_voice.current(), "rate": self.scale_rate.get(), "pitch": self.scale_pitch.get()}
        f = filedialog.asksaveasfilename(defaultextension=".json", filetypes=[("Project Files", "*.json")])
        if f: save_json(f, data); messagebox.showinfo("Xong", "Đã lưu dự án!")

    def load_project(self):
        f = filedialog.askopenfilename(filetypes=[("Project Files", "*.json")])
        if f:
            data = load_json(f, {})
            if "text_studio" in data: self.txt_studio.delete("1.0", END); self.txt_studio.insert(END, data["text_studio"])
            if "voice_idx" in data: self.cmb_voice.current(data["voice_idx"])
            if "rate" in data: self.scale_rate.set(data["rate"])
            if "pitch" in data: self.scale_pitch.set(data["pitch"])
            messagebox.showinfo("Xong", "Đã tải dự án!")

    # BGM Logic (SAFE)
    def load_bgm(self):
        if not HAS_MUSIC_SUPPORT: return
        f = filedialog.askopenfilename(filetypes=[("Audio", "*.mp3;*.wav")])
        if f: self.bgm_file = f; self.lbl_bgm_name.config(text=os.path.basename(f))
    
    def set_bgm_volume(self, val):
        if HAS_MUSIC_SUPPORT: pygame.mixer.music.set_volume(float(val))

    def play_bgm_only(self):
        if HAS_MUSIC_SUPPORT and self.bgm_file: pygame.mixer.music.load(self.bgm_file); pygame.mixer.music.play(-1)
    
    def stop_bgm_only(self):
        if HAS_MUSIC_SUPPORT: pygame.mixer.music.stop()

    def insert_pause(self, seconds): self.txt_studio.insert(tk.INSERT, " ... ")

    # Core Logic
    def get_current_text(self):
        idx = self.notebook.index(self.notebook.select())
        if idx == 0: return self.txt_studio.get("1.0", END).strip()
        elif idx == 1: return self.txt_web.get("1.0", END).strip()
        return ""

    def update_stats(self, e=None):
        text = self.get_current_text()
        rate = self.scale_rate.get()
        self.lbl_stats.config(text=estimate_duration(text, rate))

    def clean_text_area(self, widget):
        txt = widget.get("1.0", END)
        widget.delete("1.0", END)
        widget.insert(END, clean_text_content(txt))
        messagebox.showinfo("Xong", "Cleaned!")

    def open_file_studio(self):
        path = filedialog.askopenfilename(filetypes=[("Docs", "*.txt;*.docx;*.pdf")])
        if path: txt = extract_text_from_file(path); self.txt_studio.delete("1.0", END); self.txt_studio.insert(END, txt); self.update_stats()

    def fetch_web(self):
        url = self.ent_url.get()
        if url: threading.Thread(target=self._thread_web, args=(url,), daemon=True).start()

    def _thread_web(self, url):
        txt = get_text_from_url(url); self.txt_web.delete("1.0", END); self.txt_web.insert(END, clean_text_content(txt)); self.update_stats()

    def process_single(self, play_now):
        raw = self.get_current_text()
        if not raw: return
        final_text = raw.replace(",", ", ") 
        final_text = apply_dictionary(final_text, self.dictionary)
        
        voice = VOICES[self.cmb_voice.get()]
        
        rate_val = int(self.scale_rate.get())
        pitch_val = int(self.scale_pitch.get())

        rate = f"{int(self.scale_rate.get()):+d}%"
        pitch = f"{int(self.scale_pitch.get()):+d}Hz"
        if rate_val == 0: rate_val = -5
            
        rate = f"{rate_val:+d}%"
        pitch = f"{pitch_val:+d}Hz"
        if play_now:
            outfile = os.path.abspath("preview.mp3")
            srtfile = None
            if HAS_MUSIC_SUPPORT and self.bgm_file:
                pygame.mixer.music.load(self.bgm_file)
                pygame.mixer.music.play(-1)
        else:
            outfile = filedialog.asksaveasfilename(defaultextension=".mp3", filetypes=[("MP3", "*.mp3")])
            if not outfile: return
            srtfile = outfile.replace(".mp3", ".srt") if self.var_srt.get() else None

        self.lbl_status.config(text="Đang xử lý...")
        threading.Thread(target=self._run_tts, args=(final_text, voice, rate, pitch, outfile, srtfile, play_now), daemon=True).start()

    def _run_tts(self, text, voice, rate, pitch, outfile, srtfile, play_now):
        try:
            if play_now and os.path.exists(outfile): 
                try: os.remove(outfile)
                except: pass
            
            asyncio.run(generate_tts(text, voice, rate, pitch, outfile, srtfile))
            
            if play_now:
                # Nếu có Pygame thì dùng Mixer (xịn), không thì dùng os.startfile (cơ bản)
                if HAS_MUSIC_SUPPORT:
                    voice_sound = pygame.mixer.Sound(outfile)
                    voice_channel = pygame.mixer.Channel(1)
                    voice_channel.play(voice_sound)
                    self.lbl_status.config(text="Đang phát (Mixer)...")
                    while voice_channel.get_busy(): pygame.time.delay(100)
                    pygame.mixer.music.stop()
                else:
                    os.startfile(outfile)
                    self.lbl_status.config(text="Đang phát (Windows Player)...")

                self.lbl_status.config(text="Đã phát xong")
            else:
                log_history("Save", outfile)
                self.load_history_ui()
                self.lbl_status.config(text="Đã xong!")
                messagebox.showinfo("Thành công", f"File: {outfile}")
        except Exception as e:
            self.lbl_status.config(text="Lỗi")
            messagebox.showerror("Lỗi", str(e))

    def add_batch_files(self):
        files = filedialog.askopenfilenames()
        for f in files: self.lst_batch.insert(END, f)

    def start_batch_process(self):
        files = self.lst_batch.get(0, END)
        if not files: return
        out_dir = filedialog.askdirectory()
        if not out_dir: return
        self.btn_batch_start.config(state=DISABLED)
        voice = VOICES[self.cmb_voice.get()]
        rate = f"{int(self.scale_rate.get()):+d}%"
        pitch = f"{int(self.scale_pitch.get()):+d}Hz"
        gen_srt = self.var_srt.get()
        threading.Thread(target=self._run_batch, args=(files, out_dir, voice, rate, pitch, gen_srt), daemon=True).start()

    def _run_batch(self, files, out_dir, voice, rate, pitch, gen_srt):
        total = len(files)
        for i, fpath in enumerate(files):
            try:
                fname = os.path.basename(fpath).rsplit(".", 1)[0]
                text = extract_text_from_file(fpath)
                text = apply_dictionary(text, self.dictionary)
                outfile = os.path.join(out_dir, f"{fname}.mp3")
                srtfile = os.path.join(out_dir, f"{fname}.srt") if gen_srt else None
                asyncio.run(generate_tts(text, voice, rate, pitch, outfile, srtfile))
                self.progress_batch['value'] = ((i+1)/total)*100
            except: pass
        self.btn_batch_start.config(state=NORMAL); messagebox.showinfo("Xong", "Batch complete!")

    def refresh_dict_ui(self):
        for i in self.tree_dict.get_children(): self.tree_dict.delete(i)
        for k, v in self.dictionary.items(): self.tree_dict.insert("", END, values=(k, v))
    def add_dict_item(self):
        k, v = self.ent_dk.get().strip(), self.ent_dv.get().strip()
        if k and v: self.dictionary[k] = v; save_json(DICT_FILE, self.dictionary); self.refresh_dict_ui()
    def del_dict_item(self):
        try: 
            k = self.tree_dict.item(self.tree_dict.selection()[0])['values'][0]
            del self.dictionary[k]; save_json(DICT_FILE, self.dictionary); self.refresh_dict_ui()
        except: pass
    def load_history_ui(self):
        if os.path.exists(HISTORY_FILE):
            with open(HISTORY_FILE, "r", encoding="utf-8") as f:
                self.txt_history.config(state=NORMAL); self.txt_history.delete("1.0", END); self.txt_history.insert(END, f.read()); self.txt_history.config(state=DISABLED)

if __name__ == "__main__":
    app = TTSApp()
    app.mainloop()