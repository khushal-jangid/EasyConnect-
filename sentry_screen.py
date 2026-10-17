"""
EasyConnect - Dedicated Sentry Warning Screen (Isolated Subprocess)
Runs in separate process so it never blocks or deadlocks with the parent server.
"""
import sys
import time

def show_sentry_screen(reason: str = "PHYSICAL TAMPER DETECTED"):
    try:
        import tkinter as tk
        root = tk.Tk()
        root.title("🚨 SECURITY ALERT - EASYCONNECT SENTRY")
        root.attributes("-fullscreen", True)
        root.attributes("-topmost", True)
        root.configure(bg="#ff0022")

        # Exit on Esc or Space key pressed directly on PC
        def on_pc_key(e):
            try:
                root.destroy()
            except Exception:
                pass
            sys.exit(0)

        root.bind("<Escape>", on_pc_key)
        root.bind("<space>", on_pc_key)

        lbl_icon = tk.Label(root, text="🚨", font=("Segoe UI Emoji", 70), bg="#ff0022", fg="white")
        lbl_icon.pack(expand=True, pady=(30, 6))

        lbl_title = tk.Label(root, text="SECURITY SENTRY TRIGGERED!", font=("Arial", 32, "bold"), bg="#ff0022", fg="white")
        lbl_title.pack(pady=8)

        lbl_reason = tk.Label(root, text=f"TRIPWIRE: {reason.upper()}", font=("Arial", 20, "bold"), bg="#ff0022", fg="#ffe600")
        lbl_reason.pack(pady=8)

        lbl_desc = tk.Label(
            root,
            text="Webcam snapshot captured & sent to owner's phone.\n100% Siren is ringing. Disarm from paired phone (or press ESC on PC).",
            font=("Arial", 16),
            bg="#ff0022",
            fg="white"
        )
        lbl_desc.pack(pady=16)

        colors = ["#ff0022", "#0a0a0a"]
        state = [0]

        def flash():
            state[0] = 1 - state[0]
            c = colors[state[0]]
            try:
                root.configure(bg=c)
                lbl_icon.configure(bg=c)
                lbl_title.configure(bg=c)
                lbl_reason.configure(bg=c)
                lbl_desc.configure(bg=c)
                root.after(350, flash)
            except Exception:
                pass

        root.after(350, flash)
        root.mainloop()
    except Exception as e:
        pass

if __name__ == "__main__":
    reason_arg = sys.argv[1] if len(sys.argv) > 1 else "PHYSICAL TAMPER DETECTED"
    show_sentry_screen(reason_arg)
