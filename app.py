import tkinter as tk

class LoginWindow:
    def __init__(self, root):
        self.root = root
        self.root.title("Login Window")
        self.root.geometry("320x260")
        self.root.resizable(False, False)
        
        # 1. CREATE THE GRADIENT BACKGROUND (Blue to Purple)
        self.canvas = tk.Canvas(self.root, width=320, height=260, highlightthickness=0)
        self.canvas.pack(fill="both", expand=True)
        
        for i in range(260):
            r = int(30 + (130 * (i / 260)))
            g = int(175 - (115 * (i / 260)))
            b = int(255 - (50 * (i / 260)))
            color = f"#{r:02x}{g:02x}{b:02x}"
            self.canvas.create_line(0, i, 320, i, fill=color)

        # 2. USERNAME SECTION
        self.lbl_username = tk.Label(self.root, text="Username:", font=("Arial", 9), bg="white", fg="black", padx=4, pady=2)
        self.lbl_username.place(x=75, y=96, anchor="w")
        
        self.entry_username = tk.Entry(self.root, font=("Arial", 10), bd=0, highlightthickness=0)
        self.entry_username.place(x=155, y=96, width=120, height=20, anchor="w")

        # 3. PASSWORD SECTION
        self.lbl_password = tk.Label(self.root, text="Password:", font=("Arial", 9), bg="white", fg="black", padx=5, pady=2)
        self.lbl_password.place(x=75, y=137, anchor="w")
        
        self.entry_password = tk.Entry(self.root, font=("Arial", 10), show="*", bd=0, highlightthickness=0)
        self.entry_password.place(x=155, y=137, width=85, height=20, anchor="w")
        
        self.btn_show = tk.Button(self.root, text="Show", font=("Arial", 8), bg="#e0e0e0", fg="black", 
                                  activebackground="#d0d0d0", bd=0, relief="flat", command=self.toggle_password)
        self.btn_show.place(x=240, y=137, width=35, height=20, anchor="w")

        # 4. SUBMIT BUTTON
        self.btn_submit = tk.Button(self.root, text="Submit", font=("Arial", 9), bg="white", fg="black",
                                    activebackground="#eee", bd=1, relief="groove", command=self.handle_login)
        self.btn_submit.place(x=160, y=185, width=55, height=24, anchor="center")

        # 5. INLINE STATUS BAR
        self.lbl_status = tk.Label(self.root, text="", font=("Arial", 10), bg="#d0d0d0", fg="black", padx=10, pady=4)

    def toggle_password(self):
        if self.entry_password.cget("show") == "*":
            self.entry_password.configure(show="")
            self.btn_show.configure(text="Hide")
        else:
            self.entry_password.configure(show="*")
            self.btn_show.configure(text="Show")

    def handle_login(self):
        username = self.entry_username.get()
        password = self.entry_password.get()
        
        self.lbl_status.place(x=160, y=225, width=220, anchor="center")
        
        if username == "admin" and password == "1234":
            self.lbl_status.configure(text="Processing your request. Please wait...", fg="black", bg="#d0d0d0")
            self.root.update()
            
            # Pause for 1.5 seconds, then load the dashboard from the other file
            self.root.after(1500, self.switch_to_menu)
        else:
            self.lbl_status.configure(text="Invalid Username or Password", fg="red", bg="#f8d7da")

    def switch_to_menu(self):
        # Clear the login screen widgets completely
        for widget in self.root.winfo_children():
            widget.destroy()
            
        # Dynamically import the dashboard window from our separate dashboard.py file
        import dashboard
        dashboard.MainMenuWindow(self.root)


if __name__ == "__main__":
    root = tk.Tk()
    app = LoginWindow(root)
    root.mainloop()