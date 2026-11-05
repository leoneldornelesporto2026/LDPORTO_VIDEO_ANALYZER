"""Tkinter ttk presentation-only theme; no external dependency."""
COLORS = {
    "background": "#17171b",
    "surface": "#24242d",
    "surface_alt": "#2e2e38",
    "text": "#f5f5f7",
    "muted": "#c0c2ce",
    "accent": "#fb505a",
}


def apply_theme(style):
    style.configure("TButton", padding=(10, 7))
    style.configure("Primary.TButton", background=COLORS["accent"],
                    foreground="#ffffff", padding=(19, 9),
                    font=("Segoe UI", 10, "bold"))
    style.map("Primary.TButton", background=[("active", "#df4450")],
              foreground=[("disabled", COLORS["muted"])])
    style.configure("Footer.TFrame", background=COLORS["surface"])
    style.configure("Navigation.TFrame", background=COLORS["surface"])
    style.configure("NavigationTitle.TLabel", background=COLORS["surface"],
                    foreground=COLORS["accent"], font=("Segoe UI", 11, "bold"))
    style.configure("Navigation.TButton", background=COLORS["surface_alt"],
                    foreground=COLORS["text"], font=("Segoe UI", 9), padding=(8, 6))
    style.map("Navigation.TButton", background=[("active", "#41424e")])
    style.configure("Hero.TFrame", background=COLORS["surface"])
    style.configure("HeroTitle.TLabel", background=COLORS["surface"],
                    foreground=COLORS["text"], font=("Segoe UI", 22, "bold"))
    style.configure("HeroHint.TLabel", background=COLORS["surface"],
                    foreground=COLORS["muted"])
    style.configure("Section.TFrame", background=COLORS["surface_alt"])
    style.configure("SectionTitle.TLabel", background=COLORS["surface_alt"],
                    foreground=COLORS["text"], font=("Segoe UI", 11, "bold"))
    style.configure("SectionHint.TLabel", background=COLORS["surface_alt"],
                    foreground=COLORS["muted"])

    # Media source presentation; only ttk styling.
    style.configure("MediaCard.TFrame", background=COLORS["surface"])
    style.configure("MediaTitle.TLabel", background=COLORS["surface"], foreground=COLORS["text"],
                    font=("Segoe UI", 13, "bold"))
    style.configure("MediaHint.TLabel", background=COLORS["surface"], foreground=COLORS["muted"])
    style.configure("MediaFieldLabel.TLabel", background=COLORS["surface"], foreground=COLORS["muted"],
                    font=("Segoe UI", 9, "bold"))
    style.configure("MediaAction.TButton", padding=(13, 8))
    style.configure("Media.TCheckbutton", background=COLORS["surface"], foreground=COLORS["text"])
    style.map("Media.TCheckbutton", background=[("active", COLORS["surface"])])
    style.configure("Media.TEntry", fieldbackground="#e8e8ef", foreground="#16171c", padding=(9, 8))
    style.map("Media.TEntry", fieldbackground=[("readonly", "#d3d4df")],
              foreground=[("readonly", "#16171c")])
    style.configure("MediaStatus.TFrame", background=COLORS["surface_alt"])
    style.configure("MediaStatus.TLabel", background=COLORS["surface_alt"], foreground=COLORS["text"])
