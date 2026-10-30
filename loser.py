print("hello world")


import tkinter as tk
from tkinter import messagebox
import json
from pathlib import Path

DATA_FILE = Path(__file__).with_name("tasks.json")


class TodoApp:
    def __init__(self, root):
        self.root = root
        self.root.title("My To-Do List")
        self.root.geometry("500x600")
        self.root.configure(bg="#f3f4f6")
        self.root.minsize(400, 450)

        self.tasks = self.load_tasks()

        # Title
        tk.Label(
            root,
            text="My To-Do List",
            font=("Arial", 24, "bold"),
            bg="#f3f4f6",
            fg="#111827"
        ).pack(pady=(25, 10))

        # Task input
        input_frame = tk.Frame(root, bg="#f3f4f6")
        input_frame.pack(fill="x", padx=25, pady=10)

        self.task_entry = tk.Entry(
            input_frame,
            font=("Arial", 13),
            relief="solid",
            bd=1
        )
        self.task_entry.pack(
            side="left", fill="x", expand=True,
            ipady=9, padx=(0, 10)
        )

        self.task_entry.bind(
            "<Return>", lambda event: self.add_task()
        )

        tk.Button(
            input_frame,
            text="Add Task",
            command=self.add_task,
            bg="#2563eb",
            fg="white",
            font=("Arial", 11, "bold"),
            relief="flat",
            padx=15,
            pady=10,
            cursor="hand2"
        ).pack(side="right")

        # Task list
        list_frame = tk.Frame(root, bg="#f3f4f6")
        list_frame.pack(
            fill="both", expand=True,
            padx=25, pady=10
        )

        scrollbar = tk.Scrollbar(list_frame)
        scrollbar.pack(side="right", fill="y")

        self.task_list = tk.Listbox(
            list_frame,
            font=("Arial", 13),
            bg="white",
            fg="#111827",
            selectbackground="#bfdbfe",
            selectforeground="#111827",
            relief="flat",
            activestyle="none",
            height=15,
            yscrollcommand=scrollbar.set
        )
        self.task_list.pack(
            side="left", fill="both", expand=True
        )

        scrollbar.config(command=self.task_list.yview)

        # Double-click to toggle completion
        self.task_list.bind(
            "<Double-Button-1>",
            lambda event: self.toggle_task()
        )

        # Action buttons
        button_frame = tk.Frame(root, bg="#f3f4f6")
        button_frame.pack(fill="x", padx=25, pady=10)

        self.create_button(
            button_frame, "Complete",
            self.toggle_task, "#16a34a"
        )

        self.create_button(
            button_frame, "Delete",
            self.delete_task, "#dc2626"
        )

        self.create_button(
            button_frame, "Clear Done",
            self.clear_completed, "#6b7280"
        )

        # Status label
        self.status_label = tk.Label(
            root,
            text="",
            font=("Arial", 11),
            bg="#f3f4f6",
            fg="#6b7280"
        )
        self.status_label.pack(pady=(5, 20))

        self.refresh_tasks()
        self.task_entry.focus_set()

    def create_button(self, parent, text, command, color):
        tk.Button(
            parent,
            text=text,
            command=command,
            bg=color,
            fg="white",
            font=("Arial", 11, "bold"),
            relief="flat",
            padx=12,
            pady=10,
            cursor="hand2"
        ).pack(
            side="left", expand=True,
            fill="x", padx=4
        )

    def load_tasks(self):
        if DATA_FILE.exists():
            try:
                with open(DATA_FILE, "r", encoding="utf-8") as f:
                    data = json.load(f)

                if isinstance(data, list):
                    return [
                        task for task in data
                        if isinstance(task, dict)
                        and isinstance(task.get("title"), str)
                        and isinstance(task.get("completed"), bool)
                    ]

            except (json.JSONDecodeError, OSError):
                messagebox.showwarning(
                    "Load Error",
                    "Could not load saved tasks."
                )

        return []

    def save_tasks(self):
        try:
            with open(DATA_FILE, "w", encoding="utf-8") as f:
                json.dump(self.tasks, f, indent=4)
        except OSError as error:
            messagebox.showerror(
                "Save Error",
                f"Could not save tasks:\n{error}"
            )

    def refresh_tasks(self):
        self.task_list.delete(0, tk.END)

        for task in self.tasks:
            if task["completed"]:
                display = f"✓  {task['title']}"
            else:
                display = f"☐  {task['title']}"

            self.task_list.insert(tk.END, display)

            if task["completed"]:
                index = self.task_list.size() - 1
                self.task_list.itemconfig(
                    index, fg="#9ca3af"
                )

        total = len(self.tasks)
        completed = sum(
            task["completed"] for task in self.tasks
        )

        self.status_label.config(
            text=f"{completed} of {total} tasks completed"
        )

    def add_task(self):
        title = self.task_entry.get().strip()

        if not title:
            messagebox.showwarning(
                "Empty Task",
                "Please enter a task."
            )
            return

        self.tasks.append({
            "title": title,
            "completed": False
        })

        self.task_entry.delete(0, tk.END)
        self.save_tasks()
        self.refresh_tasks()
        self.task_entry.focus_set()

    def get_selected_index(self):
        selection = self.task_list.curselection()

        if not selection:
            messagebox.showinfo(
                "Select Task",
                "Please select a task first."
            )
            return None

        return selection[0]

    def toggle_task(self):
        index = self.get_selected_index()

        if index is None:
            return

        task = self.tasks[index]
        task["completed"] = not task["completed"]

        self.save_tasks()
        self.refresh_tasks()

        self.task_list.selection_set(index)

    def delete_task(self):
        index = self.get_selected_index()

        if index is None:
            return

        self.tasks.pop(index)
        self.save_tasks()
        self.refresh_tasks()

    def clear_completed(self):
        completed_count = sum(
            task["completed"] for task in self.tasks
        )

        if completed_count == 0:
            messagebox.showinfo(
                "No Completed Tasks",
                "There are no completed tasks to clear."
            )
            return

        confirm = messagebox.askyesno(
            "Clear Completed",
            f"Delete {completed_count} completed task(s)?"
        )

        if confirm:
            self.tasks = [
                task for task in self.tasks
                if not task["completed"]
            ]
            self.save_tasks()
            self.refresh_tasks()


if __name__ == "__main__":
    root = tk.Tk()
    app = TodoApp(root)
    root.mainloop()

