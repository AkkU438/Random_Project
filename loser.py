"""Tkinter To-Do app with a local Gemma 3 assistant via Ollama.

Run: python3 todo_gemma.py
Requires: pip install ollama; ollama pull gemma3:4b; Ollama running.
"""

import json
import queue
import threading
import uuid
from datetime import date
from pathlib import Path
import tkinter as tk
from tkinter import messagebox, ttk
from tkinter.scrolledtext import ScrolledText

try:
    from ollama import Client
except ImportError:
    Client = None

MODEL = "gemma3:4b"
DATA_FILE = Path(__file__).with_name("tasks.json")
PRIORITIES = ("High", "Medium", "Low")


def normalize_tasks(data):
    """Accept old title/completed task files and newer ID/priority files."""
    if not isinstance(data, list):
        raise ValueError("Task file must contain a list.")
    result = []
    seen = set()
    for item in data:
        if not isinstance(item, dict) or not isinstance(item.get("title"), str):
            continue
        title = item["title"].strip()
        if not title:
            continue
        task_id = item.get("id")
        if not isinstance(task_id, str) or not task_id or task_id in seen:
            task_id = uuid.uuid4().hex
        seen.add(task_id)
        priority = item.get("priority", "Medium")
        if priority not in PRIORITIES:
            priority = "Medium"
        result.append({
            "id": task_id,
            "title": title,
            "completed": item.get("completed") is True,
            "priority": priority,
        })
    return result


class TodoGemmaApp:
    def __init__(self, root):
        self.root = root
        self.root.title("To-Do List + Gemma AI")
        self.root.geometry("1120x680")
        self.root.minsize(850, 520)
        self.tasks = self.load_tasks()
        self.history = []
        self.results = queue.Queue()
        self.busy = False

        self.build_ui()
        self.refresh_tasks()
        self.post_message("Gemma", "Hello! Ask about your tasks, or use the AI buttons to plan your day.")
        self.root.after(100, self.poll_results)
        self.root.protocol("WM_DELETE_WINDOW", self.root.destroy)

    def build_ui(self):
        self.root.configure(bg="#edf2f7")
        style = ttk.Style()
        style.theme_use("clam")
        style.configure("TFrame", background="#edf2f7")
        style.configure("TLabel", background="#edf2f7", font=("Arial", 11))
        style.configure("Title.TLabel", font=("Arial", 20, "bold"), foreground="#14213d")
        style.configure("TButton", font=("Arial", 10), padding=(10, 8))
        style.configure("Treeview", font=("Arial", 11), rowheight=30,
                        background="white", fieldbackground="white")
        style.configure("Treeview.Heading", font=("Arial", 10, "bold"))

        outer = ttk.Frame(self.root, padding=18)
        outer.pack(fill="both", expand=True)
        outer.columnconfigure(0, weight=1)
        outer.columnconfigure(1, weight=1)
        outer.rowconfigure(1, weight=1)

        ttk.Label(outer, text="My Tasks", style="Title.TLabel").grid(
            row=0, column=0, sticky="w", pady=(0, 12))
        ttk.Label(outer, text=f"Gemma AI Assistant  ·  {MODEL}",
                  style="Title.TLabel").grid(row=0, column=1, sticky="w", padx=(18, 0), pady=(0, 12))

        left = ttk.Frame(outer)
        left.grid(row=1, column=0, sticky="nsew")
        left.columnconfigure(0, weight=1)
        left.rowconfigure(1, weight=1)

        entry_row = ttk.Frame(left)
        entry_row.grid(row=0, column=0, sticky="ew", pady=(0, 12))
        entry_row.columnconfigure(0, weight=1)
        self.task_entry = ttk.Entry(entry_row, font=("Arial", 12))
        self.task_entry.grid(row=0, column=0, sticky="ew", padx=(0, 8))
        self.task_entry.bind("<Return>", lambda _event: self.add_task())
        ttk.Button(entry_row, text="+ Add", command=self.add_task).grid(row=0, column=1)

        tree_frame = ttk.Frame(left)
        tree_frame.grid(row=1, column=0, sticky="nsew")
        tree_frame.columnconfigure(0, weight=1)
        tree_frame.rowconfigure(0, weight=1)
        self.tree = ttk.Treeview(
            tree_frame, columns=("done", "title", "priority"),
            show="headings", selectmode="browse")
        self.tree.heading("done", text="Done")
        self.tree.heading("title", text="Task")
        self.tree.heading("priority", text="Priority")
        self.tree.column("done", width=55, minwidth=50, stretch=False, anchor="center")
        self.tree.column("title", width=250, minwidth=120, stretch=True)
        self.tree.column("priority", width=90, minwidth=85, stretch=False, anchor="center")
        self.tree.tag_configure("complete", foreground="#929aa5")
        self.tree.tag_configure("high", foreground="#b42318")
        self.tree.grid(row=0, column=0, sticky="nsew")
        scroll = ttk.Scrollbar(tree_frame, orient="vertical", command=self.tree.yview)
        scroll.grid(row=0, column=1, sticky="ns")
        self.tree.configure(yscrollcommand=scroll.set)
        self.tree.bind("<Double-1>", lambda _event: self.toggle_task())

        task_buttons = ttk.Frame(left)
        task_buttons.grid(row=2, column=0, sticky="ew", pady=(12, 0))
        for i in range(3):
            task_buttons.columnconfigure(i, weight=1)
        ttk.Button(task_buttons, text="Toggle Done", command=self.toggle_task).grid(
            row=0, column=0, sticky="ew", padx=(0, 5))
        ttk.Button(task_buttons, text="Delete", command=self.delete_task).grid(
            row=0, column=1, sticky="ew", padx=5)
        ttk.Button(task_buttons, text="Clear Done", command=self.clear_done).grid(
            row=0, column=2, sticky="ew", padx=(5, 0))
        self.count_label = ttk.Label(left, text="")
        self.count_label.grid(row=3, column=0, sticky="w", pady=(10, 0))

        right = ttk.Frame(outer)
        right.grid(row=1, column=1, sticky="nsew", padx=(18, 0))
        right.columnconfigure(0, weight=1)
        right.rowconfigure(1, weight=1)

        ai_buttons = ttk.Frame(right)
        ai_buttons.grid(row=0, column=0, sticky="ew", pady=(0, 12))
        for i in range(3):
            ai_buttons.columnconfigure(i, weight=1)
        self.ai_buttons = []
        for i, (label, action) in enumerate([
            ("Organize Priorities", self.organize_tasks),
            ("Break Down Task", self.break_down_task),
            ("Plan My Day", self.plan_day),
        ]):
            button = ttk.Button(ai_buttons, text=label, command=action)
            button.grid(row=0, column=i, sticky="ew", padx=4)
            self.ai_buttons.append(button)

        self.chat_log = ScrolledText(
            right, wrap="word", font=("Arial", 11), state="disabled",
            bg="white", fg="#1f2937", padx=12, pady=12, relief="flat")
        self.chat_log.grid(row=1, column=0, sticky="nsew")
        self.chat_log.tag_configure("user", foreground="#1d4ed8", font=("Arial", 11, "bold"))
        self.chat_log.tag_configure("gemma", foreground="#047857", font=("Arial", 11, "bold"))
        self.chat_log.tag_configure("system", foreground="#6b7280", font=("Arial", 11, "bold"))

        chat_row = ttk.Frame(right)
        chat_row.grid(row=2, column=0, sticky="ew", pady=(12, 0))
        chat_row.columnconfigure(0, weight=1)
        self.chat_entry = ttk.Entry(chat_row, font=("Arial", 12))
        self.chat_entry.grid(row=0, column=0, sticky="ew", padx=(0, 8))
        self.chat_entry.bind("<Return>", lambda _event: self.send_chat())
        self.send_button = ttk.Button(chat_row, text="Send", command=self.send_chat)
        self.send_button.grid(row=0, column=1)

        self.status = tk.StringVar(value="Ready · AI needs Ollama running locally")
        ttk.Label(outer, textvariable=self.status).grid(
            row=2, column=0, columnspan=2, sticky="w", pady=(14, 0))
        self.task_entry.focus_set()

    def load_tasks(self):
        if not DATA_FILE.exists():
            return []
        try:
            with DATA_FILE.open("r", encoding="utf-8") as file:
                return normalize_tasks(json.load(file))
        except (OSError, ValueError, json.JSONDecodeError) as error:
            messagebox.showerror("Load Error", f"Unable to read {DATA_FILE}:\n{error}")
            return []

    def save_tasks(self):
        try:
            # Write to a temporary file first to avoid truncating an existing task list.
            temp = DATA_FILE.with_suffix(".tmp")
            with temp.open("w", encoding="utf-8") as file:
                json.dump(self.tasks, file, indent=2, ensure_ascii=False)
            temp.replace(DATA_FILE)
        except OSError as error:
            messagebox.showerror("Save Error", str(error))

    def refresh_tasks(self):
        selected = self.tree.selection()
        selected_id = selected[0] if selected else None
        for item in self.tree.get_children():
            self.tree.delete(item)
        rank = {"High": 0, "Medium": 1, "Low": 2}
        ordered = sorted(self.tasks, key=lambda task: (task["completed"], rank[task["priority"]]))
        for task in ordered:
            tag = "complete" if task["completed"] else "high" if task["priority"] == "High" else ""
            self.tree.insert("", "end", iid=task["id"],
                             values=("✓" if task["completed"] else "☐",
                                     task["title"], task["priority"]),
                             tags=(tag,) if tag else ())
        if selected_id and self.tree.exists(selected_id):
            self.tree.selection_set(selected_id)
        finished = sum(task["completed"] for task in self.tasks)
        self.count_label.config(text=f"{finished} of {len(self.tasks)} tasks completed")

    def selected_task(self, warn=True):
        selected = self.tree.selection()
        if selected:
            return next((task for task in self.tasks if task["id"] == selected[0]), None)
        if warn:
            messagebox.showinfo("Select Task", "Select a task in the list first.")
        return None

    def add_task(self):
        title = self.task_entry.get().strip()
        if not title:
            messagebox.showwarning("Empty Task", "Enter a task first.")
            return
        self.tasks.append({"id": uuid.uuid4().hex, "title": title,
                           "completed": False, "priority": "Medium"})
        self.task_entry.delete(0, "end")
        self.save_tasks()
        self.refresh_tasks()

    def toggle_task(self):
        task = self.selected_task()
        if task is None:
            return
        task["completed"] = not task["completed"]
        self.save_tasks()
        self.refresh_tasks()

    def delete_task(self):
        task = self.selected_task()
        if task is None:
            return
        if messagebox.askyesno("Delete Task", f"Delete '{task['title']}'?"):
            self.tasks = [item for item in self.tasks if item["id"] != task["id"]]
            self.save_tasks()
            self.refresh_tasks()

    def clear_done(self):
        count = sum(task["completed"] for task in self.tasks)
        if not count:
            messagebox.showinfo("Clear Done", "No completed tasks to clear.")
            return
        if messagebox.askyesno("Clear Done", f"Delete {count} completed task(s)?"):
            self.tasks = [task for task in self.tasks if not task["completed"]]
            self.save_tasks()
            self.refresh_tasks()

    def post_message(self, sender, content):
        self.chat_log.configure(state="normal")
        tag = "user" if sender == "You" else "gemma" if sender == "Gemma" else "system"
        self.chat_log.insert("end", f"{sender}:\n", tag)
        self.chat_log.insert("end", f"{content}\n\n")
        self.chat_log.configure(state="disabled")
        self.chat_log.see("end")

    def task_context(self):
        return json.dumps(self.tasks, ensure_ascii=False)

    def start_ai(self, kind, messages, *, format_json=False, metadata=None):
        if self.busy:
            return
        if Client is None:
            messagebox.showerror("Missing Package", "Install the Ollama Python package:\npython3 -m pip install ollama")
            return
        self.busy = True
        self.status.set(f"Gemma is working on {kind}...")
        for button in self.ai_buttons + [self.send_button]:
            button.state(["disabled"])

        def worker():
            try:
                client = Client(host="http://localhost:11434", timeout=180)
                response = client.chat(
                    model=MODEL,
                    messages=messages,
                    format="json" if format_json else None,
                    options={"temperature": 0.2} if format_json else None,
                )
                content = response.message.content
                if not content:
                    raise ValueError("Gemma returned an empty response.")
                self.results.put((kind, content, metadata, None))
            except Exception as error:
                self.results.put((kind, None, metadata, str(error)))

        threading.Thread(target=worker, daemon=True).start()

    def poll_results(self):
        try:
            while True:
                kind, content, metadata, error = self.results.get_nowait()
                self.busy = False
                for button in self.ai_buttons + [self.send_button]:
                    button.state(["!disabled"])
                if error:
                    self.status.set("Gemma request failed")
                    self.post_message("System", f"AI error: {error}\n\nCheck that Ollama is running and that '{MODEL}' is downloaded.")
                else:
                    self.status.set("Ready")
                    try:
                        self.handle_ai_result(kind, content, metadata)
                    except (ValueError, TypeError, KeyError) as parse_error:
                        self.post_message("System", f"Could not interpret Gemma's response: {parse_error}\n\nRaw response:\n{content}")
        except queue.Empty:
            pass
        self.root.after(100, self.poll_results)

    def send_chat(self):
        prompt = self.chat_entry.get().strip()
        if not prompt or self.busy:
            return
        self.chat_entry.delete(0, "end")
        self.post_message("You", prompt)
        messages = [
            {"role": "system", "content": (
                "You are a friendly, concise productivity assistant inside a to-do app. "
                "You can analyze tasks, but you cannot directly edit them via chat. "
                f"Today's date is {date.today().isoformat()}. "
                f"Current tasks as JSON: {self.task_context()}")},
            *self.history[-10:],
            {"role": "user", "content": prompt},
        ]
        self.start_ai("chat", messages, metadata=prompt)

    def organize_tasks(self):
        active = [task for task in self.tasks if not task["completed"]]
        if not active:
            messagebox.showinfo("Organize", "Add an unfinished task first.")
            return
        prompt = (
            "Prioritize the following tasks based on importance and urgency. "
            "Do not invent due dates. Return ONLY a JSON object with this shape: "
            '{"priorities": [{"id": "exact task id", "priority": "High|Medium|Low"}], '
            '"explanation": "brief explanation"}. '
            "Include every unfinished task ID exactly once. The priority must be High, Medium, or Low. "
            f"Tasks: {json.dumps(active, ensure_ascii=False)}"
        )
        self.post_message("System", "Asking Gemma to prioritize unfinished tasks...")
        self.start_ai("organize", [{"role": "user", "content": prompt}], format_json=True)

    def break_down_task(self):
        task = self.selected_task()
        if task is None:
            return
        prompt = (
            "Break this to-do item into 3 to 6 concrete, small actionable subtasks. "
            "Return ONLY a JSON object: "
            '{"subtasks": ["first step", "second step"]}. '
            "No markdown, no explanations. "
            f"Task: {task['title']}"
        )
        self.post_message("System", f"Asking Gemma to break down: {task['title']}")
        self.start_ai("breakdown", [{"role": "user", "content": prompt}],
                      format_json=True, metadata=task["id"])

    def plan_day(self):
        active = [task for task in self.tasks if not task["completed"]]
        if not active:
            messagebox.showinfo("Plan My Day", "Add an unfinished task first.")
            return
        prompt = (
            f"Today is {date.today().isoformat()}. Create a realistic, concise daily plan "
            "for these unfinished tasks. Put high-priority work first. "
            "Give a suggested order and rough time blocks, clearly labeled as estimates. "
            "Don't invent deadlines, personal availability, or task requirements. "
            f"Tasks: {json.dumps(active, ensure_ascii=False)}"
        )
        self.post_message("System", "Asking Gemma for a suggested daily plan...")
        self.start_ai("plan", [{"role": "user", "content": prompt}])

    def handle_ai_result(self, kind, content, metadata):
        if kind == "chat":
            self.post_message("Gemma", content)
            self.history.extend([
                {"role": "user", "content": metadata},
                {"role": "assistant", "content": content},
            ])
            return

        if kind == "plan":
            self.post_message("Gemma", content)
            return

        data = json.loads(content)
        if not isinstance(data, dict):
            raise ValueError("Expected a JSON object")

        if kind == "organize":
            items = data.get("priorities")
            if not isinstance(items, list):
                raise ValueError("Missing priorities list")
            updates = {}
            for item in items:
                if not isinstance(item, dict):
                    continue
                task_id = item.get("id")
                priority = item.get("priority")
                if isinstance(task_id, str) and priority in PRIORITIES:
                    updates[task_id] = priority
            updated = 0
            for task in self.tasks:
                if not task["completed"] and task["id"] in updates:
                    task["priority"] = updates[task["id"]]
                    updated += 1
            if updated == 0:
                raise ValueError("No recognizable task IDs and priorities")
            self.save_tasks()
            self.refresh_tasks()
            explanation = data.get("explanation", "")
            self.post_message("Gemma", f"Priorities assigned to {updated} task(s).\n{explanation}")

        elif kind == "breakdown":
            proposed = data.get("subtasks")
            if not isinstance(proposed, list):
                raise ValueError("Missing subtasks list")
            subtasks = [s.strip() for s in proposed if isinstance(s, str) and s.strip()][:8]
            if not subtasks:
                raise ValueError("No usable subtasks were returned")
            parent = next((task for task in self.tasks if task["id"] == metadata), None)
            if parent is None:
                self.post_message("System", "The original task was deleted, so suggestions were not added.")
                return
            suggestion_text = "\n".join(f"{i}. {title}" for i, title in enumerate(subtasks, 1))
            self.post_message("Gemma", f"Suggested steps for '{parent['title']}':\n{suggestion_text}")
            if messagebox.askyesno("Add Suggested Subtasks", "Add these suggestions to your task list?\n\n" + suggestion_text):
                for title in subtasks:
                    self.tasks.append({"id": uuid.uuid4().hex,
                                       "title": title, "completed": False,
                                       "priority": parent["priority"]})
                self.save_tasks()
                self.refresh_tasks()
                self.post_message("System", f"Added {len(subtasks)} subtasks.")


if __name__ == "__main__":
    root = tk.Tk()
    TodoGemmaApp(root)
    root.mainloop()
