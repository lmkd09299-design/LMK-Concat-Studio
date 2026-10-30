"""LMK Recap Bridge: one standalone Windows GUI, separate from Concat."""
from __future__ import annotations
import os
import queue
import threading
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from .engine import Config, make_recap
from .concat_bridge import locate_concat
from .gemini_auth import open_login, gemini_executable


class Window:
    def __init__(self, root: tk.Tk):
        self.root=root
        self.root.title('LMK Recap Bridge — Google Gemini + Concat')
        self.root.geometry('820x700')
        self.root.minsize(720,590)
        self.root.configure(bg='#15191f')
        self.events=queue.Queue()
        self.state='idle'
        self.last_output=None
        self.movie=tk.StringVar()
        self.srt=tk.StringVar()
        self.dest=tk.StringVar(value=str(Path.home()/'Documents'/'LMK-Recap'))
        self.concat=tk.StringVar(value=str(locate_concat() or ''))
        self.minutes=tk.StringVar(value='3')
        self.language=tk.StringVar(value='English')
        self.whisper=tk.StringVar(value='tiny')
        self.portrait=tk.BooleanVar(value=False)
        self.use_concat=tk.BooleanVar(value=bool(locate_concat()))
        self.status=tk.StringVar(value='Sẵn sàng. Đăng nhập Gemini bằng Google một lần.')
        style=ttk.Style(root)
        style.theme_use('clam')
        style.configure('TFrame',background='#15191f')
        style.configure('TLabel',background='#15191f',foreground='#f2f4f7',font=('Segoe UI',10))
        style.configure('TButton',font=('Segoe UI',10),padding=7)
        style.configure('TEntry',padding=6)
        style.configure('TCombobox',padding=6)
        panel=ttk.Frame(root,padding=18)
        panel.pack(fill='both',expand=True)
        ttk.Label(panel,text='LMK RECAP BRIDGE',font=('Segoe UI',19,'bold')).pack(anchor='w')
        ttk.Label(panel,text='EXE độc lập • Gemini CLI đăng nhập Google • Concat MCP chính thức',
                  foreground='#f59e0b').pack(anchor='w',pady=(1,14))
        self.field(panel,'Phim cần recap',self.movie,lambda:self.pick_file(self.movie,[('Video','*.mp4 *.mkv *.mov *.avi *.webm'),('Mọi file','*.*')]))
        self.field(panel,'Phụ đề SRT có sẵn (không bắt buộc, giúp làm nhanh)',self.srt,
                   lambda:self.pick_file(self.srt,[('SubRip','*.srt')]))
        self.field(panel,'Thư mục lưu thành phẩm',self.dest,lambda:self.pick_folder(self.dest))
        self.field(panel,'Đường dẫn Concat.exe (không cần sửa Concat gốc)',self.concat,
                   lambda:self.pick_file(self.concat,[('Concat','concat.exe'),('Chương trình','*.exe')]))
        grid=ttk.Frame(panel)
        grid.pack(fill='x',pady=(10,9))
        self.combo(grid,'Thời lượng recap (phút)',self.minutes,['1','3','5','8','10'],0)
        self.combo(grid,'Ngôn ngữ voice',self.language,['English','Tiếng Việt'],1)
        self.combo(grid,'Whisper CPU',self.whisper,['tiny','base','small'],2)
        opts=ttk.Frame(panel)
        opts.pack(fill='x',pady=4)
        ttk.Checkbutton(opts,text='Video dọc 9:16',variable=self.portrait).pack(side='left',padx=(0,25))
        ttk.Checkbutton(opts,text='Tự tạo project trong Concat sau khi xuất',variable=self.use_concat).pack(side='left')
        actions=ttk.Frame(panel)
        actions.pack(fill='x',pady=(10,8))
        ttk.Button(actions,text='1. ĐĂNG NHẬP GEMINI GOOGLE',command=self.login).pack(side='left',padx=(0,8))
        ttk.Button(actions,text='Kiểm tra CLI',command=self.check_cli).pack(side='left',padx=(0,8))
        self.start=ttk.Button(actions,text='2. TỰ ĐỘNG RECAP',command=self.begin)
        self.start.pack(side='left')
        ttk.Button(actions,text='Mở thư mục',command=self.open_results).pack(side='right')
        ttk.Label(panel,textvariable=self.status,wraplength=750,
                  foreground='#ffb55d').pack(anchor='w',pady=(10,6))
        frame=ttk.Frame(panel)
        frame.pack(fill='both',expand=True)
        self.log=tk.Text(frame,bg='#0b0f13',fg='#cfd6e0',insertbackground='white',
                         font=('Consolas',10),wrap='word',height=10)
        self.log.pack(fill='both',expand=True)
        self.log.insert('end', 'Hướng dẫn: Cài Gemini CLI chính thức, nhấn Đăng nhập Google.\n'
                     'Chọn phim (hoặc SRT), bấm Tự động recap.\n'
                     'Không hỗ trợ sửa trực tiếp project đang mở trong Concat.\n'
                     'Chỉ dùng nguồn phim/âm thanh mà anh có quyền biên tập và phân phối.\n')
        self.log.configure(state='disabled')
        self.root.after(150,self.poll)

    def field(self,parent,label,variable,browse):
        ttk.Label(parent,text=label).pack(anchor='w',pady=(4,2))
        row=ttk.Frame(parent)
        row.pack(fill='x')
        ttk.Entry(row,textvariable=variable).pack(side='left',fill='x',expand=True)
        ttk.Button(row,text='Chọn...',command=browse).pack(side='right',padx=(8,0))

    def combo(self,parent,label,variable,options,col):
        cell=ttk.Frame(parent)
        cell.grid(row=0,column=col,sticky='ew',padx=(0,12))
        parent.columnconfigure(col,weight=1)
        ttk.Label(cell,text=label).pack(anchor='w',pady=(0,4))
        ttk.Combobox(cell,textvariable=variable,values=options,state='readonly').pack(fill='x')

    def pick_file(self,var,types):
        path=filedialog.askopenfilename(filetypes=types)
        if path:var.set(path)
    def pick_folder(self,var):
        path=filedialog.askdirectory()
        if path:var.set(path)
    def note(self,value):self.events.put(('log',str(value)))

    def login(self):
        try:
            open_login()
            self.note('Cửa sổ Gemini CLI đã mở. Chọn Sign in with Google, đăng nhập và đóng sau khi xong.')
        except Exception as exc:
            messagebox.showerror('Gemini CLI',str(exc))

    def check_cli(self):
        try:
            executable=gemini_executable()
            self.note('Gemini CLI: '+executable+' (chưa kiểm tra trạng thái đăng nhập)')
            if self.use_concat.get():
                path=Path(self.concat.get())
                self.note('Concat: '+str(path)+' — '+('đã tìm thấy' if path.is_file() else 'không tìm thấy'))
        except Exception as exc:
            messagebox.showerror('Thiếu Gemini CLI',str(exc))

    def begin(self):
        if self.state!='idle':return
        if not self.movie.get():
            messagebox.showerror('Thiếu video','Hãy chọn file phim trước.');return
        if not messagebox.askyesno('Xác nhận quyền sử dụng',
                'Anh xác nhận có quyền sử dụng, biên tập và xuất bản nguồn video này?'):
            return
        try:
            config=Config(source=Path(self.movie.get()),output_root=Path(self.dest.get()),
                          minutes=int(self.minutes.get()),language=self.language.get(),
                          srt=Path(self.srt.get()) if self.srt.get() else None,
                          portrait=self.portrait.get(),whisper_model=self.whisper.get(),
                          concat_exe=Path(self.concat.get()) if self.concat.get() else None,
                          send_to_concat=self.use_concat.get())
        except (ValueError,OSError) as exc:
            messagebox.showerror('Cấu hình sai',str(exc));return
        self.state='running'
        self.start.configure(state='disabled')
        self.status.set('Đang chạy: Gemini/FFmpeg/Whisper, xem nhật ký bên dưới...')
        threading.Thread(target=self.worker,args=(config,),daemon=True).start()

    def worker(self,config):
        try:
            result=make_recap(config,self.note)
            self.events.put(('done',result))
        except Exception as exc:
            self.events.put(('error',f'{type(exc).__name__}: {exc}'))

    def poll(self):
        try:
            while True:
                kind,data=self.events.get_nowait()
                if kind=='log':
                    self.log.configure(state='normal')
                    self.log.insert('end',data+'\n')
                    self.log.see('end')
                    self.log.configure(state='disabled')
                else:
                    self.state='idle'
                    self.start.configure(state='normal')
                    if kind=='done':
                        self.last_output=Path(data['output']).parent
                        self.status.set('ĐÃ XUẤT: '+data['output'])
                        self.note('Concat project: '+str(data.get('project') or 'Không yêu cầu'))
                        messagebox.showinfo('Hoàn thành','MP4: '+data['output']+'\nConcat: '+str(data.get('project') or 'Không'))
                    else:
                        self.status.set('LỖI: '+data)
                        self.note('LỖI: '+data)
                        messagebox.showerror('LMK Recap Bridge',data)
        except queue.Empty:pass
        self.root.after(150,self.poll)

    def open_results(self):
        path=self.last_output or Path(self.dest.get())
        if not path.exists():
            messagebox.showerror('Chưa có kết quả','Chưa tìm thấy thư mục kết quả.');return
        if os.name=='nt':os.startfile(path)


def main():
    root=tk.Tk()
    Window(root)
    root.mainloop()


if __name__=='__main__':main()
