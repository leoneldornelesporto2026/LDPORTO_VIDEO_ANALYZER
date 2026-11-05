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
