
import subprocess   
import threading    
import math         
import time       
import os          
import sys        

import customtkinter as ctk  
import tkinter as tk          


FREQ        = "27140000"  
SAMPLE_RATE = "2000000"   
GAIN        = "30"         
SIGNALS_DIR = "signals"   
CHUNK_SIZE  = 65536        

#COLOUR PALETTE 
class C:
    BG     = "#0d0f14"   
    PANEL  = "#131720"  
    BORDER = "#1e2535"   
    NEON   = "#00ff88"   
    AMBER  = "#ffb347"  
    RED    = "#ff3b5c"  
    BLUE   = "#4fc3f7"  
    MUTED  = "#7d95d1"   
    TEXT   = "#eef0f3"  

#CUSTOM WIDGETS 
class SignalBars(tk.Canvas):
    """
    Animated signal-strength bars (like the WiFi/cell bars on a phone).
    Inherits from tk.Canvas — a blank drawing area we paint on manually.
    When active (transmitting), the bars animate with a sine wave.
    When idle, they're grey and static.
    """
    _RATIOS = (0.3, 0.5, 0.7, 0.9, 1.0)  

    def __init__(self, parent, **kw):
        super().__init__(parent, bg=C.BG, highlightthickness=0, **kw)
        self.active = False   # Whether we're currently transmitting
        self._step  = 0       # Animation frame counter — increments every tick
        self._tick()          # Start the animation loop immediately

    def set_active(self, v):
        """Called by the main app to turn animation on (v=True) or off (v=False)."""
        self.active = v

    def _tick(self):
        """
        Redraws the bars every 50 ms (20 fps).
        The sine wave math:
          sin() oscillates between -1 and +1.
          (0.7 + 0.3 * sin(...)) oscillates between 0.4 and 1.0
          Each bar gets a different phase offset (i * 0.8) so they ripple, not pulse in sync.
        """
        self._step += 1
        self.delete("all")   # Clear the canvas before redrawing
        w, h   = int(self.cget("width")), int(self.cget("height"))
        bw, gap = 6, 5       # Bar width and gap between bars (in pixels)
        # Centre the group of bars horizontally
        x = (w - (len(self._RATIOS) * bw + (len(self._RATIOS) - 1) * gap)) // 2
        for i, r in enumerate(self._RATIOS):
            mh = int(h * r)   # Max height for this bar
            if self.active:
                # Apply sine-wave animation to bar height
                mh    = int(mh * (0.7 + 0.3 * math.sin(self._step * 0.3 + i * 0.8)))
                color = C.AMBER
            else:
                color = C.MUTED
            # Draw a rectangle from the bottom up (h - mh to h)
            self.create_rectangle(x, h - mh, x + bw, h, fill=color, outline="")
            x += bw + gap
        # Schedule next frame in 50 ms (non-blocking)
        self.after(50, self._tick)


class FreqDisplay(tk.Canvas):
    """
    Displays the carrier frequency with a subtle "neon glow" effect.
    The glow is faked by drawing the text twice:
    """
    def __init__(self, parent, **kw):
        super().__init__(parent, bg=C.PANEL, highlightthickness=0, **kw)
        mhz        = int(FREQ) / 1_000_000  
        self._text = f"{mhz:.3f} MHz"         
        self.after(100, self._draw)            

    def _draw(self):
        self.delete("all")
        w, h    = int(self.cget("width")), int(self.cget("height"))
        cx, cy  = w // 2, h // 2   # Centre of the canvas
        # Shadow layer (darker colour, 1px lower) — creates the "glow" illusion
        self.create_text(cx, cy + 1, text=self._text, font=("Helvetica", 20, "bold"),
                         fill="#003322", anchor="center")
        # Main bright text on top
        self.create_text(cx, cy,     text=self._text, font=("Helvetica", 20, "bold"),
                         fill=C.NEON,   anchor="center")
        # Small label above
        self.create_text(cx, cy - 22, text="CARRIER FREQUENCY", font=("Helvetica", 8),
                         fill=C.MUTED, anchor="center")


class DPad(tk.Canvas):
   
    # Arrow button layout: symbol, relative-x, relative-y (0.0–1.0 of canvas size)
    _ARROWS = {
        "Up":    ("▲", .5,  .18),   # Top centre
        "Down":  ("▼", .5,  .82),   # Bottom centre
        "Left":  ("◀", .18, .5),    # Middle left
        "Right": ("▶", .82, .5),    # Middle right
    }
    R = 32   # Button circle radius

    def __init__(self, parent, **kw):
        super().__init__(parent, bg=C.BG, highlightthickness=0, **kw)
        self._active = frozenset()   # Empty set = no keys pressed
        self.after(50, self._draw)

    def update_state(self, keys):
        self._active = frozenset(keys)
        self._draw()

    def _draw(self):
        self.delete("all")
        w, h = int(self.cget("width")), int(self.cget("height"))
        for key, (sym, rx, ry) in self._ARROWS.items():
            cx, cy  = int(w * rx), int(h * ry)   # Absolute pixel position from relative coords
            pressed = key in self._active          # Is this direction currently held?
            # Draw the button circle — amber when pressed, dark panel colour when idle
            self.create_oval(cx - self.R, cy - self.R, cx + self.R, cy + self.R,
                             fill=C.AMBER if pressed else C.PANEL,
                             outline=C.AMBER if pressed else C.BORDER, width=2)
            # Draw the arrow symbol — dark on amber (pressed) or muted on dark (idle)
            self.create_text(cx, cy, text=sym, font=("Helvetica", 22, "bold"),
                             fill="#0d0f14" if pressed else C.MUTED)
        # Small centre dot 
        cx, cy = w // 2, h // 2
        self.create_oval(cx - 18, cy - 18, cx + 18, cy + 18,
                         fill=C.BORDER, outline=C.MUTED, width=1)

# MAIN APPLICATION CLASS

class HackRfController(ctk.CTk):
    """
    The main application window. Inherits from ctk.CTk (CustomTkinter's root window).
    """

    def __init__(self):
        super().__init__()   # Initialise the CTk window itself
        self.title("HackRF · RC Car Controller")
        self.geometry("820x680")
        self.resizable(False, False)
        ctk.set_appearance_mode("dark")
        self.configure(fg_color=C.BG)

        # ── State variables 
        self.sdr_process      = None     
        self.is_streaming     = False   
        self.device_connected = False  

        # ── Signal storage 
        # All signal files are read into RAM at startup so disk access never interrupts transmission later. key → bytes object.
        self.signal_buffers    = {}

        # ── Keyboard tracking 
        self.pressed_keys       = set()   
        self.current_signal_key = None    
        
        # Tracks where we are in the current signal buffer (wrap-around playback)
        self.tx_buffer_pointer  = 0

        # 64 KB of silence: transmits only the carrier, no modulation.
        self.zero_chunk         = bytearray(CHUNK_SIZE)

        # Maps direction names → signal filenames.
        self.key_map = {
            "Up":        "Up.complex16s",
            "Down":      "Down.complex16s",
            "Left":      "Left.complex16s",
            "Right":     "Right.complex16s",
            "UpLeft":    "UpLeft.complex16s",
            "UpRight":   "UpRight.complex16s",
            "DownLeft":  "DownLeft.complex16s",
            "DownRight": "DownRight.complex16s",
        }

        self.setup_ui()
        self.load_signals_to_ram()
        self.bind_keys()

    #  Signal Loading 

    def load_signals_to_ram(self):
        """
        Reads every .complex16s file into a bytes object in self.signal_buffers.
        """
        self.log("📂 Loading signals into RAM...")
        if not os.path.exists(SIGNALS_DIR):
            os.makedirs(SIGNALS_DIR)
            self.log(f"⚠  Created '{SIGNALS_DIR}/'. Add your .complex16s files.")
            return

        for key, filename in self.key_map.items():
            filepath = os.path.join(SIGNALS_DIR, filename)
            if not os.path.exists(filepath):
                self.log(f"   ⚠  Missing: {filename}")
                continue
            with open(filepath, "rb") as f:   # "rb" = read binary (no text encoding)
                data = f.read()                # Read the entire file into memory at once

            #  Windows STDIN pipe fix 
            # On Windows, STDIN runs in "text mode" by default, which means byte 0x1A EOF and silently closes the pipe mid-transmission.
            # replaced 0x1A with 0x1B 
            if sys.platform == "win32":
                data = data.replace(b"\x1a", b"\x1b")

            self.signal_buffers[key] = data
            self.log(f"   ✓  {key:12s} → {len(data)/1024:.1f} KB")

        self.log(f"✅ {len(self.signal_buffers)}/{len(self.key_map)} signals loaded.")

    # UI Construction

    def setup_ui(self):
        """
        Builds the entire UI layout using CustomTkinter widgets.
        Layout overview:
        """
        # Header 
        hdr = ctk.CTkFrame(self, fg_color=C.PANEL, corner_radius=0, height=64)
        hdr.pack(fill="x", side="top")  
        hdr.pack_propagate(False)      
        ctk.CTkLabel(hdr, text="SDR · RC CAR CONTROLLER",
                     font=("Helvetica", 18, "bold"), text_color=C.NEON).pack(side="left", padx=24, pady=18)
        ctk.CTkLabel(hdr, text=f"HackRF One  //  {int(SAMPLE_RATE)//1000} kSPS  //  GAIN {GAIN} dB",
                     font=("Helvetica", 12), text_color=C.MUTED).pack(side="right", padx=24, pady=18)

        #  Two-column main area 
        main = ctk.CTkFrame(self, fg_color=C.BG)
        main.pack(fill="both", expand=True, padx=16, pady=12)
        main.columnconfigure((0, 1), weight=1)   

        #  Left column 
        lc = ctk.CTkFrame(main, fg_color=C.BG)
        lc.grid(row=0, column=0, sticky="nsew", padx=(0, 8))
        # Border frame wraps FreqDisplay 
        ctk.CTkFrame(lc, fg_color=C.BORDER, corner_radius=8).pack(fill="x", pady=(0, 10))
        FreqDisplay(lc.winfo_children()[0], width=340, height=70).pack(padx=2, pady=2)
        dpad_card = ctk.CTkFrame(lc, fg_color=C.PANEL, corner_radius=10)
        dpad_card.pack(fill="both", expand=True)
        ctk.CTkLabel(dpad_card, text="DIRECTIONAL CONTROL",
                     font=("Helvetica", 12), text_color=C.MUTED).pack(pady=(10, 0))
        self.dpad = DPad(dpad_card, width=260, height=200)
        self.dpad.pack(padx=20, pady=10)
        ctk.CTkLabel(dpad_card, text="Arrow Keys  ·  Diagonals supported",
                     font=("Helvetica", 12), text_color=C.MUTED).pack(pady=(0, 10))

        # Right column 
        rc = ctk.CTkFrame(main, fg_color=C.BG)
        rc.grid(row=0, column=1, sticky="nsew", padx=(8, 0))

        # Status card
        card = ctk.CTkFrame(rc, fg_color=C.PANEL, corner_radius=10)
        card.pack(fill="x", pady=(0, 10))
        row1 = ctk.CTkFrame(card, fg_color="transparent")
        row1.pack(fill="x", padx=16, pady=(14, 4))

        # LED indicator: a text label showing "●" — colour changes with connection state
        self.led = ctk.CTkLabel(row1, text="●", font=("Helvetica", 22), text_color=C.MUTED)
        self.led.pack(side="left", padx=(0, 10))
        tc = ctk.CTkFrame(row1, fg_color="transparent")
        tc.pack(side="left", fill="x", expand=True)

        # Status text labels
        self.status_main = ctk.CTkLabel(tc, text="DISCONNECTED",
                                        font=("Helvetica", 14, "bold"), text_color=C.MUTED, anchor="w")
        self.status_main.pack(anchor="w")
        self.status_sub = ctk.CTkLabel(tc, text="Press 'Connect' to open the USB channel",
                                       font=("Helvetica", 12), text_color=C.MUTED, anchor="w")
        self.status_sub.pack(anchor="w")

        # Animated signal bars widget in the top-right of the status card
        self.sig_bars = SignalBars(card, width=50, height=30)
        self.sig_bars.pack(side="right", padx=16, pady=10)

        # TX badge — shows current transmission direction or "IDLE"
        self.tx_badge = ctk.CTkLabel(card, text="  TX: IDLE  ",
                                     font=("Helvetica", 11, "bold"),
                                     text_color=C.MUTED, fg_color=C.BORDER, corner_radius=4)
        self.tx_badge.pack(anchor="w", padx=16, pady=(0, 14))

        # Connect button — triggers check_device_connection()
        self.connect_btn = ctk.CTkButton(rc, text="⟳  CONNECT TO HACKRF",
                                         font=("Helvetica", 12, "bold"),
                                         fg_color=C.BORDER, hover_color="#2a3550",
                                         text_color=C.BLUE, border_color=C.BLUE, border_width=1,
                                         height=38, corner_radius=6,
                                         command=self.check_device_connection)
        self.connect_btn.pack(fill="x", pady=(0, 10))

        # Key bindings reference card
        keys_card = ctk.CTkFrame(rc, fg_color=C.PANEL, corner_radius=10)
        keys_card.pack(fill="x", pady=(0, 10))
        ctk.CTkLabel(keys_card, text="KEY BINDINGS",
                     font=("Helvetica", 12), text_color=C.MUTED).pack(anchor="w", padx=14, pady=(10, 4))
        for kb, desc in [("↑  /  ↓  /  ←  →", "Single directions"),
                         ("↑ + ←  or  ↑ + →",  "Diagonals"),
                         ("Release",             "Stop transmission")]:
            r = ctk.CTkFrame(keys_card, fg_color="transparent")
            r.pack(fill="x", padx=14, pady=2)
            ctk.CTkLabel(r, text=kb,   font=("Helvetica", 12, "bold"),
                         text_color=C.AMBER, width=140, anchor="w").pack(side="left")
            ctk.CTkLabel(r, text=desc, font=("Helvetica", 12),
                         text_color=C.TEXT,  anchor="w").pack(side="left")
        ctk.CTkLabel(keys_card, text="", height=6).pack()

        # Log console 
        # A scrollable read-only text area for system messages
        cf = ctk.CTkFrame(self, fg_color=C.PANEL, corner_radius=0)
        cf.pack(fill="x", side="bottom")
        ctk.CTkLabel(cf, text="SYSTEM LOG",
                     font=("Helvetica", 12), text_color=C.MUTED).pack(anchor="w", padx=16, pady=(8, 0))
        self.console = ctk.CTkTextbox(cf, height=130, font=("Helvetica", 10),
                                      fg_color="#0a0c10", text_color=C.TEXT,
                                      scrollbar_button_color=C.BORDER,
                                      corner_radius=0, border_width=0, wrap="none")
        self.console.pack(fill="x")

    #  HackRF Device Connection

    def check_device_connection(self):
        """
        Launches hackrf_transfer as a child process with STDIN piped to Python.
        The key flag is "-t -":
          -t  → transmit mode (send I/Q data rather than receive it)
          -   → read from STDIN rather than a file
        This keeps the process alive permanently, waiting for bytes from our pump thread.
        """
        if self.is_streaming:
            self.log("⚠  Already connected.")
            return

        self.log("🔌 Opening USB connection to HackRF...")
        cmd = ["hackrf_transfer", "-t", "-", "-f", FREQ, "-s", SAMPLE_RATE, "-x", GAIN]

        try:
            self.sdr_process = subprocess.Popen(
                cmd,
                stdin=subprocess.PIPE,    
                stdout=subprocess.DEVNULL, # Discard normal stdout
                stderr=subprocess.PIPE     # Capture stderr to prevent deadlock (see _error_reader_thread)
            )
            self.is_streaming     = True
            self.device_connected = True

            # Update UI 
            self.led.configure(text_color=C.NEON)
            self.status_main.configure(text="STREAM ACTIVE", text_color=C.NEON)
            self.status_sub.configure(text=f"Transmitting on {int(FREQ)//1_000_000}.{(int(FREQ)%1_000_000)//1000} MHz")
            self.connect_btn.configure(text="● CONNECTED", text_color=C.NEON, border_color=C.NEON)
            self.log("✅ Stream active — transmitting silence.")

            # Launch background threads — daemon=True means they die automatically when the main window closes.
            threading.Thread(target=self._data_pump_thread,    daemon=True).start()
            threading.Thread(target=self._error_reader_thread, daemon=True).start()

        except FileNotFoundError:
            # hackrf_transfer binary not found in PATH
            self.log("✗  'hackrf_transfer' not found. Install hackrf-tools.")
        except Exception as e:
            self.log(f"✗  Launch error: {e}")

    def _data_pump_thread(self):
        """
        Runs in a background thread. Continuously feeds I/Q data into hackrf_transfer's STDIN.
        """
        while self.is_streaming and self.sdr_process and self.sdr_process.poll() is None:
            # sdr_process.poll() returns None while the process is alive, an exit code when it ends
            try:
                key = self.current_signal_key
                if not key or key not in self.signal_buffers:
                    # No key pressed — send silence (carrier only)
                    self.sdr_process.stdin.write(self.zero_chunk)
                    self.sdr_process.stdin.flush()   # flush() forces the OS to actually send the bytes
                else:
                    sig     = self.signal_buffers[key]
                    sig_len = len(sig)
                    chunk   = bytearray()   # Build up a fresh 64 KB chunk

                    # Fill the chunk, wrapping around the signal buffer as needed
                    while len(chunk) < CHUNK_SIZE:
                        avail  = sig_len - self.tx_buffer_pointer   
                        needed = CHUNK_SIZE - len(chunk)          

                        if avail >= needed:
                        
                            chunk.extend(sig[self.tx_buffer_pointer : self.tx_buffer_pointer + needed])
                            self.tx_buffer_pointer += needed
                        else:
                            # Signal runs out — take what's left, then wrap pointer to start
                            chunk.extend(sig[self.tx_buffer_pointer:])
                            self.tx_buffer_pointer = 0
                            # Loop continues to fill the remaining bytes from the start of the signal

                    self.sdr_process.stdin.write(chunk)
                    self.sdr_process.stdin.flush()

            except BrokenPipeError:
                # The HackRF process died or was unplugged — pipe is gone
                self.after(0, lambda: self.log("⚠  Pipe broken — HackRF disconnected."))
                break
            except Exception as e:
                self.after(0, lambda err=e: self.log(f"⚠  Pump error: {err}"))
                break

        # When loop exits, update flags and UI
        self.is_streaming     = False
        self.device_connected = False
        self.after(0, self._on_disconnected)   # Schedule UI update on the main (GUI) thread

    def _error_reader_thread(self):
        """
        Continuously drains hackrf_transfer's STDERR pipe.
        We also surface useful hardware messages (USB errors,etc) in the log,
        silently ignoring "underflow" warnings which are harmless and frequent.
        """
        while self.is_streaming and self.sdr_process.poll() is None:
            try:
                line = self.sdr_process.stderr.readline().decode(errors="replace").strip()
                if line and "underflow" not in line.lower():
                    # Schedule a GUI log update from this background thread
                    self.after(0, lambda l=line: self.log(f"⚙  HW: {l}"))
            except Exception:
                break

    def _on_disconnected(self):
        """
        Called on the main GUI thread when the data pump thread exits.
        Updates all UI elements to reflect the disconnected state.
        """
        self.led.configure(text_color=C.RED)
        self.status_main.configure(text="DISCONNECTED", text_color=C.RED)
        self.status_sub.configure(text="Connection lost.")
        self.connect_btn.configure(text="⟳  RECONNECT", text_color=C.BLUE, border_color=C.BLUE)
        self.update_tx_ui(None)
        self.log("⚠  Stream stopped. Press 'Reconnect' to try again.")

    # ── Keyboard Handling ──────────────────────────────────────────────────────

    def bind_keys(self):
        """
        Registers event handlers for the four arrow keys.
        """
        for d in ("Up", "Down", "Left", "Right"):
            self.bind(f"<KeyPress-{d}>",   self.on_key_press)
            self.bind(f"<KeyRelease-{d}>", self.on_key_release)

    def on_key_press(self, event):
        """
        Called every time an arrow key goes down.
        """
        self.pressed_keys.add(event.keysym)   # keysym = "Up", "Down", "Left", or "Right"
        self._resolve_signal()

    def on_key_release(self, event):
      
        self.pressed_keys.discard(event.keysym)   # discard() won't raise if key isn't in the set
        self._resolve_signal()

    def _resolve_signal(self):
        """
        Determines which signal (if any) should be transmitted based on which keys are held.
        Priority order: diagonals are checked first, then single directions.
        This ensures that holding Up+Left correctly triggers "UpLeft" rather than just "Up".
        """
        k = self.pressed_keys
        # Diagonal combinations (must check before single directions)
        if   "Up"   in k and "Left"  in k: sig = "UpLeft"
        elif "Up"   in k and "Right" in k: sig = "UpRight"
        elif "Down" in k and "Left"  in k: sig = "DownLeft"
        elif "Down" in k and "Right" in k: sig = "DownRight"
        # Single directions
        elif "Up"    in k:                  sig = "Up"
        elif "Down"  in k:                  sig = "Down"
        elif "Left"  in k:                  sig = "Left"
        elif "Right" in k:                  sig = "Right"
        # No keys held
        else:                               sig = None

        if sig != self.current_signal_key:
            # Signal changed — update pointer so new signal starts from the beginning
            self.current_signal_key = sig
            self.tx_buffer_pointer  = 0
            self.update_tx_ui(sig)

        # Always update the D-pad visual to reflect current pressed keys
        self.dpad.update_state(k)

    # UI Update Helpers --

    def update_tx_ui(self, sig):
        """
        Updates the TX badge label and signal bar animation based on transmission state.
        sig = None → idle state (no transmission)
        sig = "Up" etc → active state
        """
        if sig:
            self.tx_badge.configure(text=f"  TX: {sig.upper()}  ", text_color="#0d0f14", fg_color=C.AMBER)
            self.sig_bars.set_active(True)
        else:
            self.tx_badge.configure(text="  TX: IDLE  ", text_color=C.MUTED, fg_color=C.BORDER)
            self.sig_bars.set_active(False)

    #log --
    def log(self, message):
        """
        Appends a timestamped message to the scrollable console at the bottom.
        Always scrolls to the latest message.
        """
        self.console.configure(state="normal")
        self.console.insert("end", f"[{time.strftime('%H:%M:%S')}]  {message}\n")
        self.console.see("end")   # Auto-scroll to bottom

    #Cleanup on Exit

    def destroy(self):
        self.is_streaming = False
        if self.sdr_process:
            try:
                self.sdr_process.stdin.close()        # EOF → hackrf_transfer exits voluntarily
                self.sdr_process.terminate()          # SIGTERM fallback
                self.sdr_process.wait(timeout=2)      # Wait up to 2 s for clean exit
            except Exception:
                pass   # If anything fails, we still continue closing the window
        super().destroy()   # Call CTk's destroy to close the actual window


#main
if __name__ == "__main__":
   
    HackRfController().mainloop()