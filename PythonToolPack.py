import sys
import subprocess
import threading
import tkinter as tk
from tkinter import ttk, messagebox, filedialog, simpledialog
import os
import json
import base64
import tempfile

# PyInstaller hack: скрыть консольное окно в exe
if hasattr(sys, 'frozen'):
    try:
        import ctypes
        ctypes.windll.user32.ShowWindow(ctypes.windll.kernel32.GetConsoleWindow(), 0)
    except Exception:
        pass

# ==== Проверка наличия requests ====
try:
    import requests
    HAS_REQUESTS = True
except ImportError:
    HAS_REQUESTS = False

# ==== Проверка наличия jedi ====
try:
    import jedi
    HAS_JEDI = True
except ImportError:
    HAS_JEDI = False

try:
    from PyQt5.QtWidgets import QCheckBox, QToolBar
    HAS_PYQT5 = True
except ImportError:
    HAS_PYQT5 = False

CONFIG_FILE = "config.json"

def load_config():
    if os.path.exists(CONFIG_FILE):
        with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    return {}

def save_config(cfg):
    with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
        json.dump(cfg, f)

config = load_config()

def get_default_python():
    return config.get("python_path") or sys.executable

# ===== GitHub API AUTH =====

GITHUB_TOKEN_KEY = "github_token"
GITHUB_USER_KEY = "github_user"

def ask_install_requests():
    messagebox.showinfo(
        "Нужна библиотека requests",
        "Для работы с GitHub и онлайн-операциями установите библиотеку requests"
    )

def ask_install_jedi():
    messagebox.showinfo(
        "Нужна библиотека jedi",
        "Для автодополнения и интеллектуальных подсказок установите библиотеку jedi"
    )

def save_github_token(token, user):
    config[GITHUB_TOKEN_KEY] = token
    config[GITHUB_USER_KEY] = user
    save_config(config)

def remove_github_token():
    config.pop(GITHUB_TOKEN_KEY, None)
    config.pop(GITHUB_USER_KEY, None)
    save_config(config)

def is_github_authenticated():
    return GITHUB_TOKEN_KEY in config and GITHUB_USER_KEY in config

def get_github_token():
    return config.get(GITHUB_TOKEN_KEY) or ""

def get_github_user():
    return config.get(GITHUB_USER_KEY) or ""

def github_auth_window():
    if not HAS_REQUESTS:
        ask_install_requests()
        return
    win = tk.Toplevel(root)
    win.title("Авторизация через GitHub")
    win.geometry("400x170")
    win.grab_set()
    tk.Label(win, text="Введите Personal Access Token (PAT):").pack(pady=10)
    entry = tk.Entry(win, show="*", width=40)
    entry.pack()
    status = tk.Label(win, text="", fg="red")
    status.pack(pady=5)
    def do_auth():
        token = entry.get().strip()
        if not token:
            status.config(text="Введите токен!")
            return
        headers = {"Authorization": f"token {token}"}
        try:
            resp = requests.get("https://api.github.com/user", headers=headers, timeout=5)
            if resp.status_code == 200:
                github_user = resp.json().get("login", "unknown")
                save_github_token(token, github_user)
                status.config(text=f"Успешно! Зашли как {github_user}", fg="green")
                update_github_auth_button()
                win.after(800, win.destroy)
            else:
                status.config(text="Ошибка авторизации!", fg="red")
        except Exception as e:
            status.config(text=f"Ошибка: {e}", fg="red")
    btn_login = tk.Button(win, text="Войти", command=do_auth)
    btn_login.pack(pady=10)
    entry.bind('<Return>', lambda e: do_auth())

def logout_github():
    remove_github_token()
    update_github_auth_button()

def update_github_auth_button():
    if is_github_authenticated():
        btn_github_auth.config(text=f"Выйти ({get_github_user()})", command=logout_github)
    else:
        btn_github_auth.config(text="Авторизоваться", command=github_auth_window)

# ===== GitHub API: REPOS & FILES & Content =====

def fetch_user_repos():
    if not HAS_REQUESTS:
        ask_install_requests()
        return []
    headers = {
        "Authorization": f"token {get_github_token()}",
        "Accept": "application/vnd.github.v3+json"
    }
    user = get_github_user()
    repos = []
    page = 1
    while True:
        url = f"https://api.github.com/users/{user}/repos?per_page=100&page={page}"
        resp = requests.get(url, headers=headers)
        if resp.status_code != 200:
            break
        data = resp.json()
        if not data:
            break
        repos += [repo["name"] for repo in data]
        page += 1
    return repos

def fetch_repo_tree(repo, path=""):
    if not HAS_REQUESTS:
        ask_install_requests()
        return []
    headers = {
        "Authorization": f"token {get_github_token()}",
        "Accept": "application/vnd.github.v3+json"
    }
    user = get_github_user()
    url = f"https://api.github.com/repos/{user}/{repo}/contents/{path}" if path else f"https://api.github.com/repos/{user}/{repo}/contents"
    resp = requests.get(url, headers=headers)
    if resp.status_code != 200:
        return []
    data = resp.json()
    if isinstance(data, dict):
        data = [data]
    return data

def fetch_file_content(repo, filepath):
    if not HAS_REQUESTS:
        ask_install_requests()
        return ""
    headers = {
        "Authorization": f"token {get_github_token()}",
        "Accept": "application/vnd.github.v3+json"
    }
    user = get_github_user()
    url = f"https://api.github.com/repos/{user}/{repo}/contents/{filepath}"
    resp = requests.get(url, headers=headers)
    if resp.status_code != 200:
        return ""
    data = resp.json()
    if data.get("encoding") == "base64":
        return base64.b64decode(data["content"]).decode("utf-8")
    return ""

def check_update():
    if not HAS_REQUESTS:
        ask_install_requests()
        return
    if not is_github_authenticated():
        messagebox.showwarning("Обновление", "Для обновления авторизуйтесь через GitHub!")
        return
    url = "https://api.github.com/repos/Universalingnebula/lazylibs2/contents/lazylibs2_ultimate.py?ref=main"
    headers = {"Authorization": f"token {get_github_token()}"}
    try:
        resp = requests.get(url, headers=headers)
    except Exception as e:
        messagebox.showerror("Обновление", f"Ошибка запроса: {e}")
        return
    if resp.status_code == 200:
        data = resp.json()
        content = base64.b64decode(data['content']).decode('utf-8')
        with open("pythontoolpack_new.py", "w", encoding="utf-8") as f:
            f.write(content)
        messagebox.showinfo("Обновление", "Скачана новая версия как pythontoolpack_new.py\nПерезапустите приложение вручную для обновления.")
    else:
        messagebox.showerror("Обновление", f"Не удалось проверить обновления. Код: {resp.status_code}")

# ===== Основной GUI =====

def show_editor_mode():
    frame_install.pack_forget()
    frame_all.pack_forget()
    frame_transform.pack_forget()
    frame_help.pack_forget()
    frame_editor.pack(fill='both', expand=True)
    btn_install_mode.config(relief='raised')
    btn_all_mode.config(relief='raised')
    btn_transform_mode.config(relief='raised')
    btn_editor_mode.config(relief='sunken')
    btn_help.config(relief='raised')

def show_install_mode():
    frame_all.pack_forget()
    frame_transform.pack_forget()
    frame_editor.pack_forget()
    frame_help.pack_forget()
    frame_install.pack(fill='both', expand=True)
    btn_install_mode.config(relief='sunken')
    btn_all_mode.config(relief='raised')
    btn_transform_mode.config(relief='raised')
    btn_editor_mode.config(relief='raised')
    btn_help.config(relief='raised')

def show_all_mode():
    frame_install.pack_forget()
    frame_transform.pack_forget()
    frame_editor.pack_forget()
    frame_help.pack_forget()
    frame_all.pack(fill='both', expand=True)
    btn_install_mode.config(relief='raised')
    btn_all_mode.config(relief='sunken')
    btn_transform_mode.config(relief='raised')
    btn_editor_mode.config(relief='raised')
    btn_help.config(relief='raised')
    clear_frame(scrollable_all)
    progress_bar.pack(pady=5)
    progress_bar.start(10)
    def load():
        packages = fetch_installed_packages()
        def draw():
            progress_bar.stop()
            progress_bar.pack_forget()
            if not packages:
                tk.Label(scrollable_all, text="Пакеты не найдены", font=("Arial", 14)).pack(pady=30)
            for pkg in packages:
                f = tk.Frame(scrollable_all, pady=7, bd=1, relief='solid')
                f.pack(fill='x', padx=5)
                tk.Label(f, text=pkg['name'], font=("Arial", 14, "bold")).pack(anchor='w')
                tk.Label(f, text=f"Версия: {pkg['version']}", font=("Arial", 10)).pack(anchor='w')
                btns = tk.Frame(f)
                btns.pack(anchor='w', pady=5)
                def uninstall(name=pkg['name']):
                    answer = messagebox.askyesno("Подтверждение", f"Удалить {name}?")
                    if not answer:
                        return
                    label_status.config(text=f"Удаление {name}...")
                    progress_bar.pack(pady=5)
                    progress_bar.start(10)
                    def run():
                        result = subprocess.run([get_default_python(), '-m', 'pip', 'uninstall', '-y', name],
                                                stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
                        msg = result.stdout + '\n' + result.stderr
                        def update():
                            progress_bar.stop()
                            progress_bar.pack_forget()
                            label_status.config(text=msg)
                            show_all_mode()
                        root.after(0, update)
                    threading.Thread(target=run).start()
                def upgrade(name=pkg['name']):
                    label_status.config(text=f"Обновление {name}...")
                    progress_bar.pack(pady=5)
                    progress_bar.start(10)
                    def run():
                        subprocess.run([get_default_python(), '-m', 'pip', 'install', '--upgrade', name])
                        root.after(0, show_all_mode)
                    threading.Thread(target=run).start()
                def show_details(name=pkg['name']):
                    result = subprocess.run([get_default_python(), '-m', 'pip', 'show', name],
                                            stdout=subprocess.PIPE, text=True)
                    win = tk.Toplevel(root)
                    win.title(f"Информация о {name}")
                    txt = tk.Text(win, wrap='word')
                    txt.insert('1.0', result.stdout)
                    txt.config(state='normal')
                    txt.pack(expand=True, fill='both')
                tk.Button(btns, text="Удалить", command=uninstall).pack(side='left', padx=5)
                tk.Button(btns, text="Обновить", command=upgrade).pack(side='left', padx=5)
                tk.Button(btns, text="Подробнее", command=show_details).pack(side='left', padx=5)
        root.after(0, draw)
    threading.Thread(target=load).start()

def show_transform_mode():
    frame_install.pack_forget()
    frame_all.pack_forget()
    frame_editor.pack_forget()
    frame_help.pack_forget()
    frame_transform.pack(fill='both', expand=True)
    btn_install_mode.config(relief='raised')
    btn_all_mode.config(relief='raised')
    btn_transform_mode.config(relief='sunken')
    btn_editor_mode.config(relief='raised')
    btn_help.config(relief='raised')

def show_help_mode():
    frame_install.pack_forget()
    frame_all.pack_forget()
    frame_transform.pack_forget()
    frame_editor.pack_forget()
    frame_help.pack(fill='both', expand=True)
    btn_install_mode.config(relief='raised')
    btn_all_mode.config(relief='raised')
    btn_transform_mode.config(relief='raised')
    btn_editor_mode.config(relief='raised')
    btn_help.config(relief='sunken')

def make_root():
    r = tk.Tk()
    r.title("PythonToolPack")
    r.geometry("1100x750")
    return r

root = make_root()

frame_top = tk.Frame(root)
frame_top.pack(fill='x')
label_toolpack = tk.Label(frame_top, text="PythonToolPack", font=("Arial", 20, "bold"), fg="blue")
label_toolpack.pack(side='left', pady=10)

frame_buttons = tk.Frame(root)
frame_buttons.pack(fill='x')

btn_install_mode = tk.Button(frame_buttons, text="Установка библиотек")
btn_all_mode = tk.Button(frame_buttons, text="Библиотеки и управление")
btn_transform_mode = tk.Button(frame_buttons, text="Трансформация")
btn_editor_mode = tk.Button(frame_buttons, text="Редактор")
btn_help = tk.Button(frame_buttons, text="Справка")

btn_install_mode.pack(side='left', padx=5)
btn_all_mode.pack(side='left', padx=5)
btn_transform_mode.pack(side='left', padx=5)
btn_editor_mode.pack(side='left', padx=5)
btn_help.pack(side='right', padx=5)

frame_auth = tk.Frame(frame_buttons)
frame_auth.pack(side='right', padx=5)
btn_github_auth = tk.Button(frame_auth, text="Авторизоваться")
btn_github_auth.pack(side='left', padx=3)
btn_check_update = tk.Button(frame_buttons, text="Проверить обновления", command=check_update)
btn_check_update.pack(side='right', padx=5)

# ========== Простой редактор + Github Open + Имя файла ==========

frame_editor = tk.Frame(root)
toolbar = tk.Frame(frame_editor)
toolbar.pack(fill='x')

editor_text = tk.Text(frame_editor, font=("Consolas", 12), undo=True, wrap='none')
editor_text.pack(side='left', expand=True, fill='both')
scroll_y = tk.Scrollbar(frame_editor, command=editor_text.yview)
scroll_y.pack(side='right', fill='y')
editor_text.config(yscrollcommand=scroll_y.set)

def editor_set_title(path=None):
    if path:
        root.title(f"Редактор - {os.path.basename(path)}")
    else:
        root.title("Редактор - Новый файл")

def set_editor_filename(name=""):
    editor_filename_entry.delete(0, tk.END)
    editor_filename_entry.insert(0, name)

def open_file():
    filename = filedialog.askopenfilename(filetypes=[("Python files", "*.py"), ("All files", "*.*")])
    if filename:
        with open(filename, "r", encoding="utf-8") as f:
            content = f.read()
        editor_text.delete(1.0, tk.END)
        editor_text.insert(tk.END, content)
        set_editor_filename(os.path.basename(filename))
        editor_text.filepath = filename
        editor_set_title(filename)

def save_file():
    name = editor_filename_entry.get().strip()
    path = getattr(editor_text, "filepath", None)
    if path and name == os.path.basename(path):
        filename = path
    else:
        if not name or not name.endswith(".py"):
            name = name if name else "newfile.py"
            if not name.endswith(".py"):
                name += ".py"
            editor_filename_entry.delete(0, tk.END)
            editor_filename_entry.insert(0, name)
        filename = filedialog.asksaveasfilename(
            defaultextension=".py", initialfile=name,
            filetypes=[("Python files", "*.py"), ("All files", "*.*")]
        )
        if not filename:
            return
        editor_text.filepath = filename
        set_editor_filename(os.path.basename(filename))
    with open(filename, "w", encoding="utf-8") as f:
        f.write(editor_text.get(1.0, tk.END))
    editor_set_title(filename)

def save_file_as():
    name = editor_filename_entry.get().strip()
    if not name or not name.endswith(".py"):
        name = name if name else "newfile.py"
        if not name.endswith(".py"):
            name += ".py"
        editor_filename_entry.delete(0, tk.END)
        editor_filename_entry.insert(0, name)
    filename = filedialog.asksaveasfilename(
        defaultextension=".py", initialfile=name,
        filetypes=[("Python files", "*.py"), ("All files", "*.*")]
    )
    if not filename:
        return
    editor_text.filepath = filename
    set_editor_filename(os.path.basename(filename))
    with open(filename, "w", encoding="utf-8") as f:
        f.write(editor_text.get(1.0, tk.END))
    editor_set_title(filename)

def run_code():
    code = editor_text.get(1.0, tk.END)
    with tempfile.NamedTemporaryFile("w", delete=False, suffix=".py", encoding="utf-8") as tf:
        tf.write(code)
        fname = tf.name
    python_path = get_default_python()
    result_win = tk.Toplevel(root)
    result_win.title("Результат выполнения")
    txt = tk.Text(result_win, wrap='word')
    txt.pack(expand=True, fill='both')
    txt.config(state="disabled")
    def run():
        try:
            proc = subprocess.run([python_path, fname], stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
            res = proc.stdout
        except Exception as e:
            res = str(e)
        txt.config(state="normal")
        txt.delete("1.0", tk.END)
        txt.insert('end', res)
        txt.config(state="disabled")
        os.unlink(fname)
    threading.Thread(target=run).start()

def find_text():
    find_str = simpledialog.askstring("Поиск", "Что искать?")
    if not find_str:
        return
    editor_text.tag_remove('search', '1.0', tk.END)
    idx = '1.0'
    count = 0
    while True:
        idx = editor_text.search(find_str, idx, nocase=0, stopindex=tk.END)
        if not idx:
            break
        lastidx = f"{idx}+{len(find_str)}c"
        editor_text.tag_add('search', idx, lastidx)
        idx = lastidx
        count += 1
    editor_text.tag_config('search', background='yellow')
    messagebox.showinfo("Результаты поиска", f"Найдено: {count}")

def replace_text():
    find_str = simpledialog.askstring("Что заменить", "Что искать?")
    if not find_str:
        return
    repl_str = simpledialog.askstring("Замена", "На что заменить?")
    if repl_str is None:
        return
    content = editor_text.get("1.0", tk.END)
    new_content = content.replace(find_str, repl_str)
    editor_text.delete("1.0", tk.END)
    editor_text.insert("1.0", new_content)

def goto_line():
    line = simpledialog.askinteger("Перейти к строке", "Введите номер строки:")
    if line:
        editor_text.mark_set("insert", f"{line}.0")
        editor_text.see(f"{line}.0")

# ==== Автодополнение и интеллектуальные подсказки через jedi ====

def show_autocomplete(event=None):
    if not HAS_JEDI:
        ask_install_jedi()
        return
    code = editor_text.get("1.0", "end-1c")
    index = editor_text.index(tk.INSERT)
    row, col = map(int, index.split('.'))
    script = jedi.Script(code, path='')
    try:
        completions = script.complete(line=row, column=col)
        if completions:
            menu = tk.Menu(root, tearoff=0)
            for comp in completions:
                menu.add_command(
                    label=comp.name_with_symbols,
                    command=lambda c=comp: insert_completion(c)
                )
            menu.post(root.winfo_pointerx(), root.winfo_pointery())
    except Exception:
        pass

def insert_completion(completion):
    editor_text.insert(tk.INSERT, completion.complete)

def show_intelli(event=None):
    if not HAS_JEDI:
        ask_install_jedi()
        return
    code = editor_text.get("1.0", "end-1c")
    index = editor_text.index(tk.INSERT)
    row, col = map(int, index.split('.'))
    script = jedi.Script(code, path='')
    try:
        definitions = script.goto(line=row, column=col)
        if definitions:
            doc = definitions[0].docstring()
            messagebox.showinfo("Подсказка", doc or "Нет документации")
        else:
            messagebox.showinfo("Подсказка", "Нет данных")
    except Exception:
        messagebox.showinfo("Подсказка", "Нет данных (ошибка jedi)")

editor_text.bind("<Control-space>", show_autocomplete)
editor_text.bind("<Control-i>", show_intelli)

def editor_copy():
    try:
        editor_text.event_generate("<<Copy>>")
    except:
        pass

def editor_paste():
    try:
        editor_text.event_generate("<<Paste>>")
    except:
        pass

def github_open_in_editor():
    if not HAS_REQUESTS:
        ask_install_requests()
        return
    if not is_github_authenticated():
        messagebox.showinfo("GitHub", "Сначала выполните авторизацию через GitHub!")
        return

    win = tk.Toplevel(root)
    win.title("Открыть из GitHub")
    win.geometry("800x500")
    win.grab_set()

    left = tk.Frame(win)
    left.pack(side='left', fill='y', padx=6, pady=3)
    right = tk.Frame(win)
    right.pack(side='left', fill='both', expand=True, padx=6, pady=3)

    repo_label = tk.Label(left, text="Репозитории:")
    repo_label.pack(anchor='w')
    repo_list = tk.Listbox(left, width=30, height=25)
    repo_list.pack(fill='y', expand=True)
    repo_scroll = tk.Scrollbar(left, command=repo_list.yview)
    repo_list.config(yscrollcommand=repo_scroll.set)
    repo_scroll.pack(side='right', fill='y')

    files_label = tk.Label(right, text="Файлы:")
    files_label.pack(anchor='w')
    files_list = tk.Listbox(right, width=60, height=25)
    files_list.pack(fill='both', expand=True)
    files_scroll = tk.Scrollbar(right, command=files_list.yview)
    files_list.config(yscrollcommand=files_scroll.set)
    files_scroll.pack(side='right', fill='y')
    path_label = tk.Label(right, text="", fg="blue")
    path_label.pack(anchor='w')

    nav_stack = []
    cur_repo = [None]
    cur_path = [""]

    def load_repos():
        repo_list.delete(0, tk.END)
        repo_list.insert(tk.END, "Загрузка...")
        def worker():
            repos = fetch_user_repos()
            def update():
                repo_list.delete(0, tk.END)
                if repos:
                    for r in repos:
                        repo_list.insert(tk.END, r)
                else:
                    repo_list.insert(tk.END, "Нет репозиториев")
            win.after(0, update)
        threading.Thread(target=worker).start()

    def load_files(repo, path=""):
        files_list.delete(0, tk.END)
        files_list.insert(tk.END, "Загрузка...")
        def worker():
            items = fetch_repo_tree(repo, path)
            items_sorted = sorted(items, key=lambda x: (x['type'] != 'dir', x['name'].lower()))
            def update():
                files_list.delete(0, tk.END)
                if path:
                    files_list.insert(tk.END, "[..] (назад)")
                for itm in items_sorted:
                    if itm['type'] == 'dir':
                        files_list.insert(tk.END, f"[DIR] {itm['name']}")
                    elif itm['type'] == 'file':
                        files_list.insert(tk.END, itm['name'])
                path_label.config(text=f"/{path}" if path else "/")
            win.after(0, update)
        threading.Thread(target=worker).start()

    def on_repo_select(evt):
        sel = repo_list.curselection()
        if not sel: return
        repo = repo_list.get(sel[0])
        cur_repo[0] = repo
        cur_path[0] = ""
        nav_stack.clear()
        load_files(repo, "")

    def on_file_select(evt):
        sel = files_list.curselection()
        if not sel or not cur_repo[0]: return
        idx = sel[0]
        fname = files_list.get(idx)
        if fname.startswith("[..]"):
            if nav_stack:
                prev = nav_stack.pop()
                cur_path[0] = prev
                load_files(cur_repo[0], prev)
            else:
                files_list.delete(0, tk.END)
                path_label.config(text="")
        elif fname.startswith("[DIR] "):
            dname = fname[len("[DIR] "):]
            nav_stack.append(cur_path[0])
            new_path = (cur_path[0] + "/" + dname).strip("/")
            cur_path[0] = new_path
            load_files(cur_repo[0], new_path)
        else:
            selected_file = (cur_path[0] + "/" + fname).strip("/")
            def worker():
                content = fetch_file_content(cur_repo[0], selected_file)
                def update():
                    if content:
                        editor_text.delete(1.0, tk.END)
                        editor_text.insert(1.0, content)
                        set_editor_filename(os.path.basename(selected_file))
                        editor_text.filepath = None
                        editor_set_title(selected_file + " (GitHub)")
                        win.destroy()
                    else:
                        messagebox.showerror("Ошибка", "Не удалось загрузить файл")
                win.after(0, update)
            threading.Thread(target=worker).start()

    repo_list.bind("<<ListboxSelect>>", on_repo_select)
    files_list.bind("<<ListboxSelect>>", on_file_select)
    load_repos()

tk.Button(toolbar, text="Новый", command=lambda: (editor_text.delete(1.0, tk.END), set_editor_filename(""), editor_set_title())).pack(side='left')
tk.Button(toolbar, text="Открыть", command=open_file).pack(side='left')
tk.Button(toolbar, text="Открыть с GitHub", command=github_open_in_editor).pack(side='left')
tk.Button(toolbar, text="Сохранить", command=save_file).pack(side='left')
tk.Button(toolbar, text="Сохранить как", command=save_file_as).pack(side='left')
tk.Button(toolbar, text="Выполнить", command=run_code).pack(side='left')
tk.Button(toolbar, text="Найти", command=find_text).pack(side='left')
tk.Button(toolbar, text="Заменить", command=replace_text).pack(side='left')
tk.Button(toolbar, text="Переход к строке", command=goto_line).pack(side='left')
tk.Button(toolbar, text="Копировать", command=editor_copy).pack(side='left')
tk.Button(toolbar, text="Вставить", command=editor_paste).pack(side='left')
tk.Label(toolbar, text="Имя файла:").pack(side='left', padx=5)
editor_filename_entry = tk.Entry(toolbar, width=30)
editor_filename_entry.pack(side='left')

# ========== ДОБАВЛЕНО: Кнопка "Связь" и функционал jedi для редактора ==========
import keyword
import threading

# Цвета для типов
SVYAZ_COLORS = {
    "variable": "#fff59d",
    "function": "#80d8ff",
    "class": "#b9f6ca",
}
svyaz_tag = "svyaz_highlight"

# Проверяем наличие jedi
try:
    import jedi
    HAS_JEDI = True
except ImportError:
    HAS_JEDI = False

# Для debounce
highlight_job = [None]  # используем список чтобы изменять из вложенной функции
highlight_args = [None]

def is_inside_string_or_comment(row, col, code_lines):
    if row-1 >= len(code_lines): return False
    text = code_lines[row-1]
    comment_pos = text.find('#')
    if comment_pos != -1 and col >= comment_pos: return True
    in_str = False
    quote = None
    for i, ch in enumerate(text):
        if ch in ('"', "'"):
            if not in_str:
                in_str = True
                quote = ch
            elif ch == quote:
                in_str = False
                quote = None
        if i == col:
            break
    return in_str

def clear_svyaz_highlight():
    editor_text.tag_remove(svyaz_tag, "1.0", tk.END)

def highlight_svyaz(event=None):
    if not svyaz_mode.get():
        clear_svyaz_highlight()
        return
    # Дебаунс: отменяем старую задачу, если она запланирована
    if highlight_job[0]:
        root.after_cancel(highlight_job[0])
    # Сохраняем последние параметры курсора и текста
    index = editor_text.index(tk.INSERT)
    code = editor_text.get("1.0", "end-1c")
    highlight_args[0] = (index, code)
    # Запускаем подсветку с задержкой (например, 120 мс(изменено до 65))
    highlight_job[0] = root.after(65, run_highlight_thread)

def run_highlight_thread():
    index, code = highlight_args[0]
    row, col = map(int, index.split('.'))
    code_lines = code.splitlines()
    def do_jedi():
        try:
            script = jedi.Script(code, path='')
            names = script.get_references(line=row, column=col, include_builtins=False)
        except Exception:
            names = []
        root.after(0, lambda: apply_highlight(names, row, col, code_lines))
    threading.Thread(target=do_jedi, daemon=True).start()

def apply_highlight(names, row, col, code_lines):
    clear_svyaz_highlight()
    if not names: return
    hit = None
    for name in names:
        if name.line == row and name.column <= col < name.column + len(name.name):
            hit = name
            break
    if not hit: return
    word = hit.name
    typ = getattr(hit, 'type', 'variable')
    if word in keyword.kwlist: return
    if is_inside_string_or_comment(row, col, code_lines): return
    tag_color = SVYAZ_COLORS.get(typ, "#ffd180")
    pos = "1.0"
    while True:
        pos = editor_text.search(rf'\y{word}\y', pos, stopindex=tk.END, regexp=True)
        if not pos: break
        lastidx = f"{pos}+{len(word)}c"
        this_row, this_col = map(int, pos.split('.'))
        if word in keyword.kwlist or is_inside_string_or_comment(this_row, this_col, code_lines):
            pos = lastidx
            continue
        editor_text.tag_add(svyaz_tag, pos, lastidx)
        pos = lastidx
    editor_text.tag_config(svyaz_tag, background=tag_color)

def goto_svyaz_definition(event=None):
    if not svyaz_mode.get():
        return
    defn = getattr(editor_text, "_svyaz_last_def", None)
    if not defn or defn.line is None:
        return
    editor_text.mark_set("insert", f"{defn.line}.{defn.column}")
    editor_text.see(f"{defn.line}.0")
    highlight_svyaz()

def on_svyaz_toggle():
    if svyaz_mode.get():
        highlight_svyaz()
        editor_text.bind("<KeyRelease>", highlight_svyaz)
        editor_text.bind("<Motion>", highlight_svyaz)  # Наведение мыши!
        editor_text.bind("<Control-Return>", goto_svyaz_definition)
    else:
        clear_svyaz_highlight()
        editor_text.unbind("<KeyRelease>")
        editor_text.unbind("<Motion>")
        editor_text.unbind("<Control-Return>")

if HAS_JEDI:
    svyaz_mode = tk.BooleanVar(value=False)
    tk.Checkbutton(toolbar, text="Связь", variable=svyaz_mode, command=on_svyaz_toggle).pack(side='left', padx=5)
# ========== Остальные вкладки: Установка, Список, Трансформация, Справка ==========

frame_install = tk.Frame(root)
label_entry = tk.Label(frame_install, text="Введите название библиотеки:")
label_entry.pack(pady=5)
entry_package = tk.Entry(frame_install, width=40)
entry_package.pack()
label_version = tk.Label(frame_install, text="Введите версию (опционально):")
label_version.pack(pady=5)
entry_version = tk.Entry(frame_install, width=40)
entry_version.pack()
label_python = tk.Label(frame_install, text="Путь к Python (опционально):")
label_python.pack(pady=5)
entry_python = tk.Entry(frame_install, width=40)
entry_python.pack()
entry_python.insert(0, config.get("python_path", ""))

label_status = tk.Label(frame_install, text="", font=("Arial", 12))
label_status.pack(pady=5)
progress_bar = ttk.Progressbar(frame_install, mode='indeterminate')

def install_package():
    name = entry_package.get().strip()
    version = entry_version.get().strip()
    path = entry_python.get().strip()
    if path:
        config["python_path"] = path
        save_config(config)
    python_path = path or get_default_python()
    if not name:
        messagebox.showerror("Ошибка", "Введите имя библиотеки")
        return
    full = f"{name}=={version}" if version else name
    label_status.config(text=f"Установка {full}...")
    progress_bar.pack(pady=5)
    progress_bar.start(10)
    def run():
        try:
            result = subprocess.run([python_path, '-m', 'pip', 'install', full],
                stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            msg = f"Установлено: {full}" if result.returncode == 0 else result.stderr
        except Exception as e:
            msg = str(e)
        def update():
            progress_bar.stop()
            progress_bar.pack_forget()
            label_status.config(text=msg)
        root.after(0, update)
    threading.Thread(target=run).start()

btn_install = tk.Button(frame_install, text="Установить", command=install_package)
btn_install.pack(pady=10)

# ... (остальные вкладки, функции, переключатели - без изменений) ...

btn_install_mode.config(command=show_install_mode)
btn_all_mode.config(command=show_all_mode)
btn_transform_mode.config(command=show_transform_mode)
btn_editor_mode.config(command=show_editor_mode)
btn_help.config(command=show_help_mode)
update_github_auth_button()

# ========== Список библиотек ==========

frame_all = tk.Frame(root)
frame_all_buttons = tk.Frame(frame_all)
frame_all_buttons.pack(fill='x', pady=2)
canvas_all = tk.Canvas(frame_all)
scrollbar_all = ttk.Scrollbar(frame_all, orient="vertical", command=canvas_all.yview)
scrollable_all = tk.Frame(canvas_all)
scrollable_all.bind("<Configure>", lambda e: canvas_all.configure(scrollregion=canvas_all.bbox("all")))
canvas_all.create_window((0,0), window=scrollable_all, anchor="nw")
canvas_all.configure(yscrollcommand=scrollbar_all.set)
canvas_all.pack(side="left", fill="both", expand=True)
scrollbar_all.pack(side="right", fill="y")

def clear_frame(frame):
    for widget in frame.winfo_children():
        widget.destroy()

def get_installed_packages():
    try:
        out = subprocess.check_output([get_default_python(), "-m", "pip", "freeze"], text=True)
        return {line.strip().split("==")[0].lower() for line in out.splitlines() if "==" in line}
    except Exception:
        return set()

def fetch_installed_packages():
    try:
        result = subprocess.run(
            [get_default_python(), '-m', 'pip', 'list', '--format=json'],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True
        )
        if result.returncode == 0:
            return json.loads(result.stdout)
    except Exception:
        pass
    return []

def upgrade_all_packages():
    pkgs = get_installed_packages()
    if not pkgs:
        messagebox.showinfo("Обновление", "Нет установленных библиотек.")
        return
    answer = messagebox.askyesno("Обновление", f"Обновить {len(pkgs)} библиотек? Это может занять много времени.")
    if not answer:
        return
    win = tk.Toplevel(root)
    win.title("Обновление библиотек")
    txt = tk.Text(win, width=80, height=24)
    txt.pack(expand=True, fill='both')
    txt.insert('end', "Обновление...\n")
    txt.see('end')
    def worker():
        for pkg in pkgs:
            txt.insert('end', f"\nОбновление {pkg}...\n")
            txt.see('end')
            proc = subprocess.run([get_default_python(), "-m", "pip", "install", "--upgrade", pkg],
                                  stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
            txt.insert('end', proc.stdout)
            txt.see('end')
        txt.insert('end', "\nГотово!\n")
        txt.see('end')
    threading.Thread(target=worker).start()

tk.Button(frame_all_buttons, text="Обновить все библиотеки", command=upgrade_all_packages).pack(side='left', padx=3)

def show_all_mode():
    frame_install.pack_forget()
    frame_transform.pack_forget()
    frame_editor.pack_forget()
    frame_help.pack_forget()
    frame_all.pack(fill='both', expand=True)
    btn_install_mode.config(relief='raised')
    btn_all_mode.config(relief='sunken')
    btn_transform_mode.config(relief='raised')
    btn_editor_mode.config(relief='raised')
    btn_help.config(relief='raised')
    clear_frame(scrollable_all)
    progress_bar.pack(pady=5)
    progress_bar.start(10)
    def load():
        packages = fetch_installed_packages()
        def draw():
            progress_bar.stop()
            progress_bar.pack_forget()
            if not packages:
                tk.Label(scrollable_all, text="Пакеты не найдены", font=("Arial", 14)).pack(pady=30)
            for pkg in packages:
                f = tk.Frame(scrollable_all, pady=7, bd=1, relief='solid')
                f.pack(fill='x', padx=5)
                tk.Label(f, text=pkg['name'], font=("Arial", 14, "bold")).pack(anchor='w')
                tk.Label(f, text=f"Версия: {pkg['version']}", font=("Arial", 10)).pack(anchor='w')
                btns = tk.Frame(f)
                btns.pack(anchor='w', pady=5)
                def uninstall(name=pkg['name']):
                    answer = messagebox.askyesno("Подтверждение", f"Удалить {name}?")
                    if not answer:
                        return
                    label_status.config(text=f"Удаление {name}...")
                    progress_bar.pack(pady=5)
                    progress_bar.start(10)
                    def run():
                        result = subprocess.run([get_default_python(), '-m', 'pip', 'uninstall', '-y', name],
                                                stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
                        msg = result.stdout + '\n' + result.stderr
                        def update():
                            progress_bar.stop()
                            progress_bar.pack_forget()
                            label_status.config(text=msg)
                            show_all_mode()
                        root.after(0, update)
                    threading.Thread(target=run).start()
                def upgrade(name=pkg['name']):
                    label_status.config(text=f"Обновление {name}...")
                    progress_bar.pack(pady=5)
                    progress_bar.start(10)
                    def run():
                        subprocess.run([get_default_python(), '-m', 'pip', 'install', '--upgrade', name])
                        root.after(0, show_all_mode)
                    threading.Thread(target=run).start()
                def show_details(name=pkg['name']):
                    result = subprocess.run([get_default_python(), '-m', 'pip', 'show', name],
                                            stdout=subprocess.PIPE, text=True)
                    win = tk.Toplevel(root)
                    win.title(f"Информация о {name}")
                    txt = tk.Text(win, wrap='word')
                    txt.insert('1.0', result.stdout)
                    txt.config(state='normal')
                    txt.pack(expand=True, fill='both')
                tk.Button(btns, text="Удалить", command=uninstall).pack(side='left', padx=5)
                tk.Button(btns, text="Обновить", command=upgrade).pack(side='left', padx=5)
                tk.Button(btns, text="Подробнее", command=show_details).pack(side='left', padx=5)
        root.after(0, draw)
    threading.Thread(target=load).start()

# ========== Трансформация .py → .exe ==========

frame_transform = tk.Frame(root)
transform_header = tk.Label(frame_transform, text="Трансформация .py → .exe", font=("Arial", 16, "bold"))
transform_header.pack(pady=10)
transform_files_label = tk.Label(frame_transform, text="Файлы не выбраны")
transform_files_label.pack(pady=5)
transform_selected_files = []
transform_output_dir = ""
transform_icon_path = ""

def transform_select_files():
    global transform_selected_files
    files = filedialog.askopenfilenames(
        filetypes=[("Python files", "*.py")],
        title="Выберите .py файл(ы) для преобразования"
    )
    transform_selected_files = list(files)
    if transform_selected_files:
        transform_files_label.config(text="Выбрано файлов: " + ", ".join([os.path.basename(f) for f in transform_selected_files]))
    else:
        transform_files_label.config(text="Файлы не выбраны")

tk.Button(frame_transform, text="Выбрать .py файл(ы)", command=transform_select_files).pack(pady=5)
transform_dir_label = tk.Label(frame_transform, text="Папка для сохранения не выбрана")
transform_dir_label.pack(pady=5)

def transform_select_dir():
    global transform_output_dir
    directory = filedialog.askdirectory(title="Выберите папку для сохранения exe")
    if directory:
        transform_output_dir = directory
        transform_dir_label.config(text=f"Папка: {directory}")
    else:
        transform_output_dir = ""
        transform_dir_label.config(text="Папка для сохранения не выбрана")

tk.Button(frame_transform, text="Выбрать папку для exe", command=transform_select_dir).pack(pady=5)

def transform_select_icon():
    global transform_icon_path
    path = filedialog.askopenfilename(title="Выберите .ico для exe", filetypes=[("ICO файлы", "*.ico")])
    if path:
        transform_icon_path = path
        transform_icon_label.config(text=f"Иконка: {os.path.basename(path)}")
    else:
        transform_icon_path = ""
        transform_icon_label.config(text="Иконка не выбрана")

transform_icon_label = tk.Label(frame_transform, text="Иконка не выбрана")
transform_icon_label.pack(pady=5)
tk.Button(frame_transform, text="Выбрать иконку", command=transform_select_icon).pack(pady=5)

transform_onefile_var = tk.BooleanVar(value=True)
tk.Checkbutton(frame_transform, text="Собирать в один файл (onefile)", variable=transform_onefile_var).pack(pady=5)

transform_status = tk.Label(frame_transform, text="", font=("Arial", 12))
transform_status.pack(pady=5)

def is_pyinstaller_installed():
    try:
        import PyInstaller
        return True
    except ImportError:
        return False

def transform_do():
    if not transform_selected_files:
        messagebox.showerror("Ошибка", "Сначала выберите .py файл(ы)")
        return
    if not transform_output_dir:
        messagebox.showerror("Ошибка", "Сначала выберите папку для exe")
        return

    transform_status.config(text="Запуск преобразования...")

    def run():
        for file in transform_selected_files:
            base_name = os.path.splitext(os.path.basename(file))[0]
            python_path = get_default_python()
            folder = os.path.dirname(file)
            cmd = [
                python_path, "-m", "PyInstaller",
                "--distpath", transform_output_dir,
                "--workpath", os.path.join(transform_output_dir, "build"),
                "--specpath", transform_output_dir
            ]
            if transform_onefile_var.get():
                cmd.append("--onefile")
            if transform_icon_path:
                cmd += ["--icon", transform_icon_path]
            cmd.append(file)
            try:
                result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, cwd=folder)
                if result.returncode == 0:
                    msg = f"Готово: {os.path.join(transform_output_dir, base_name)}.exe"
                else:
                    msg = f"Ошибка сборки {os.path.basename(file)}:\n{result.stderr}"
            except Exception as e:
                msg = f"Ошибка: {str(e)}"
            transform_status.after(0, lambda m=msg: transform_status.config(text=m))
    threading.Thread(target=run).start()

btn_create_exe = tk.Button(frame_transform, text="Создать exe", command=transform_do)
btn_create_exe.pack(pady=10)
if not is_pyinstaller_installed():
    btn_create_exe.config(state="disabled")

# ========== Справка ==========

frame_help = tk.Frame(root)
help_text = tk.Text(frame_help, wrap='word', font=("Arial", 13), height=28)
help_text.pack(expand=True, fill='both')
help_text.insert('end',
"""
PythonToolPack:
------------------------

1. Установка библиотек:
   - Введите имя (и версию) библиотеки, нажмите "Установить".
   - Можно по желанию указать путь к своему Python.

2. Управление библиотеками:
   - Смотрите список, обновляйте, удаляйте, получайте информацию.
   - Можно обновить все библиотеки сразу.

3. Трансформация .py в .exe:
   - Выберите исходные файлы, папку для exe, иконку (по желанию).
   - Нажмите "Создать exe".(Пока работает только  --onefile)

4. Редактор:
   - Открывайте, редактируйте, сохраняйте, выполняйте Python-код.
   - Поиск, замена, выделение, переход к строке, копирование и вставка.
   - Кнопка "Открыть с GitHub" — для открытия файлов из ваших GitHub-репозиториев.
   - Для автодополнения и интеллектуальных подсказок установите библиотеку jedi.
                                                  ЭКСКЛЮЗИВНАЯ ФУНКЦИЯ!
   - Кнопка "Связь" включает интеллектуальную подсветку и переход к определению (Ctrl+Enter).

5. GitHub:
   - Авторизация через токен позволяет работать с вашими репозиториями и обновлять приложение.

Удачного использования!
""")
help_text.config(state='disabled')

btn_install_mode.config(command=show_install_mode)
btn_all_mode.config(command=show_all_mode)
btn_transform_mode.config(command=show_transform_mode)
btn_editor_mode.config(command=show_editor_mode)
btn_help.config(command=show_help_mode)
update_github_auth_button()

if __name__ == "__main__":
    show_install_mode()
    root.mainloop()
