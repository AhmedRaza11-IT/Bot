import os
import tkinter as tk
from tkinter import messagebox

class MainMenuWindow:
    def __init__(self, root):
        self.root = root
        self.root.title("BLS ITALY BOT")
        self.root.geometry("400x320")
        self.root.resizable(False, False)
        self.root.configure(bg="white")
        
        # 1. HEADER SECTION
        self.lbl_logo_placeholder = tk.Label(
            self.root, 
            text="BLS BOT 🤖", 
            font=("Arial", 24, "bold"), 
            fg="#b69341", 
            bg="white"
        )
        self.lbl_logo_placeholder.pack(pady=(20, 5))
        
        self.lbl_subtitle = tk.Label(
            self.root, 
            text="Apply for VISA to Italy in Pakistan", 
            font=("Arial", 12, "bold"), 
            fg="#b69341", 
            bg="white"
        )
        self.lbl_subtitle.pack(pady=(0, 15))
        
        # 2. CONTROL BUTTONS
        button_style = {
            "font": ("Arial", 12, "bold"),
            "bg": "#f9f6ee",
            "fg": "#b69341",
            "activebackground": "#eae5d8",
            "activeforeground": "#b69341",
            "bd": 0,
            "relief": "flat",
            "height": 1,
            "width": 18,
            "cursor": "hand2"
        }
        
        self.btn_start = tk.Button(self.root, text="START BOT", **button_style, command=self.start_bot)
        self.btn_start.pack(pady=6)
        
        self.btn_resume = tk.Button(self.root, text="RESUME BOT", **button_style, command=self.resume_bot)
        self.btn_resume.pack(pady=6)
        
        self.btn_stop = tk.Button(self.root, text="STOP BOT", **button_style, command=self.stop_bot)
        self.btn_stop.pack(pady=6)
        
        self.btn_close = tk.Button(self.root, text="CLOSE BOT", **button_style, command=self.close_bot)
        self.btn_close.pack(pady=6)
        
        # Apply hover effects
        self.add_hover_effect(self.btn_start)
        self.add_hover_effect(self.btn_resume)
        self.add_hover_effect(self.btn_stop)
        self.add_hover_effect(self.btn_close)
        
        # 3. FOOTER BRANDING
        self.lbl_footer = tk.Label(
            self.root, 
            text="By RakenTech", 
            font=("Arial", 9, "bold"), 
            fg="#b69341", 
            bg="white"
        )
        self.lbl_footer.pack(side="bottom", anchor="se", padx=15, pady=10)

    def add_hover_effect(self, button):
        button.bind("<Enter>", lambda event: button.configure(bg="#b69341", fg="white"))
        button.bind("<Leave>", lambda event: button.configure(bg="#f9f6ee", fg="#b69341"))

    # --- BOT CORE CONTROL BACKEND ---
    
    def parse_config_file(self, file_path):
        """Reads and cleanly parses the configuration text file properties."""
        config_data = {}
        if not os.path.exists(file_path):
            return None
        with open(file_path, 'r', encoding='utf-8') as file:
            for line in file:
                if ":" in line:
                    key, value = line.split(":", 1)
                    config_data[key.strip()] = value.strip()
        return config_data

    def start_bot(self):
        print("\n🚀 [STARTING AUTOMATION ENGINE]")
        
        config_path = "./pending_reservations/testing.txt"
        
        # 🔄 UPDATED FILENAME TO MATCH EXACT REQUEST
        image_path = "./pending_reservations/passport_img.png"
        
        # Check if text config file exists
        if not os.path.exists(config_path):
            print("❌ Error: 'testing.txt' is missing inside 'pending_reservations' folder!")
            messagebox.showerror("Error", "Configuration file 'testing.txt' is missing!")
            return
            
        # Check if passport_img.png exists
        if not os.path.exists(image_path):
            print("❌ Error: 'passport_img.png' is missing inside 'pending_reservations' folder!")
            messagebox.showerror("Error", "Passport image file 'passport_img.png' is missing!")
            return
            
        # Parse the configuration file
        config = self.parse_config_file(config_path)
        print("📄 Configurations successfully loaded into memory:")
        print(f"   - Center Selected: {config.get('Center')}")
        print(f"   - Visa Category:   {config.get('Service Type')} ({config.get('Service Subtype')})")
        print(f"   - Target Date:     {config.get('Preferred Date')}")
        
        # Clean date formatting rules
        pref_date = config.get('Preferred Date', '')
        if pref_date and '/' in pref_date:
            parts = pref_date.split('/')
            cleaned_parts = [str(int(p)) if p.isdigit() else p for p in parts]
            pref_date = "/".join(cleaned_parts)
            print(f"   - Formatted Date:  {pref_date} (Leading zeros stripped)")

        if config.get("Proxy"):
            print(f"🌐 Proxy Configured: {config.get('Proxy')}")
            
        print("✅ Directory verification complete. Preparing stealth web browser session...")

    def resume_bot(self):
        print("▶️ RESUME BOT clicked.")
        
    def stop_bot(self):
        print("🛑 STOP BOT clicked.")
        
    def close_bot(self):
        print("❌ TERMINATING PROCESS.")
        self.root.quit()