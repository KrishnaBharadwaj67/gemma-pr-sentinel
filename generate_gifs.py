import os
import math
from PIL import Image, ImageDraw, ImageFont

ASSETS_DIR = r"c:\Users\KRISHNA\Documents\Projects\Hack-proj1\diff-shield\assets"
WIDTH, HEIGHT = 960, 540

# Color palette (Cyber-Obsidian)
BG_COLOR = (9, 10, 15)
SURFACE_COLOR = (17, 19, 28)
CARD_BG = (25, 27, 38)
BORDER_COLOR = (45, 48, 65)
TEXT_WHITE = (241, 243, 249)
TEXT_MUTED = (156, 163, 175)
TEXT_DIM = (107, 114, 128)
INDIGO = (99, 102, 241)
EMERALD = (16, 185, 129)
CRIMSON = (239, 68, 68)
AMBER = (245, 158, 11)

def get_font(size=14, mono=False):
    # Try system fonts or default
    font_paths = [
        "C:\\Windows\\Fonts\\segoeui.ttf",
        "C:\\Windows\\Fonts\\arial.ttf",
        "C:\\Windows\\Fonts\\consola.ttf" if mono else "C:\\Windows\\Fonts\\segoeui.ttf",
    ]
    for p in font_paths:
        if os.path.exists(p):
            try:
                return ImageFont.truetype(p, size)
            except Exception:
                pass
    return ImageFont.load_default()

def draw_top_nav(draw, model_text="gemma3:4b", status_text="ONLINE", latency="124ms"):
    # Navbar
    draw.rectangle([0, 0, WIDTH, 48], fill=(13, 14, 21), outline=BORDER_COLOR)
    
    # Shield logo + Brand
    draw.rounded_rectangle([16, 10, 44, 38], radius=6, fill=(25, 28, 48), outline=INDIGO)
    font_bold = get_font(15)
    font_sm = get_font(11)
    font_mono = get_font(11, mono=True)
    
    draw.text((22, 14), "🛡️", fill=INDIGO, font=font_sm)
    draw.text((54, 14), "DiffShield", fill=TEXT_WHITE, font=font_bold)
    draw.text((135, 17), "// Air-Gapped PR Intelligence", fill=TEXT_DIM, font=font_sm)
    
    # Privacy badge
    draw.rounded_rectangle([380, 12, 630, 36], radius=12, fill=(16, 185, 129, 30), outline=EMERALD)
    draw.ellipse([392, 21, 400, 29], fill=EMERALD)
    draw.text((408, 16), "100% LOCAL EXECUTION • ZERO EGRESS", fill=EMERALD, font=get_font(10))
    
    # Model Selector Pill
    draw.rounded_rectangle([650, 12, 770, 36], radius=6, fill=CARD_BG, outline=BORDER_COLOR)
    draw.text((662, 16), f"⚙ {model_text}", fill=TEXT_WHITE, font=font_mono)
    
    # Telemetry Pill
    draw.rounded_rectangle([780, 12, 944, 36], radius=12, fill=CARD_BG, outline=BORDER_COLOR)
    draw.ellipse([790, 22, 796, 28], fill=EMERALD if status_text == "ONLINE" else AMBER)
    draw.text((804, 16), f"{latency} • {status_text}", fill=TEXT_MUTED, font=font_mono)

def draw_sidebar(draw, active_tab="paste", demo_glow=False, show_files=False):
    # Left bar
    draw.rectangle([0, 48, 260, HEIGHT], fill=SURFACE_COLOR, outline=BORDER_COLOR)
    
    # Tab buttons
    font_sm = get_font(11)
    draw.rectangle([10, 56, 85, 80], fill=CARD_BG if active_tab=="paste" else SURFACE_COLOR, outline=INDIGO if active_tab=="paste" else BORDER_COLOR)
    draw.text((22, 62), "Paste Diff", fill=TEXT_WHITE if active_tab=="paste" else TEXT_DIM, font=font_sm)
    
    draw.rectangle([90, 56, 170, 80], fill=CARD_BG if active_tab=="repo" else SURFACE_COLOR, outline=BORDER_COLOR)
    draw.text((98, 62), "Git Repo", fill=TEXT_DIM, font=font_sm)
    
    draw.rectangle([175, 56, 250, 80], fill=CARD_BG if active_tab=="upload" else SURFACE_COLOR, outline=BORDER_COLOR)
    draw.text((188, 62), "Upload", fill=TEXT_DIM, font=font_sm)
    
    # Demo button
    btn_border = (120, 125, 255) if demo_glow else INDIGO
    btn_fill = (45, 50, 95) if demo_glow else (30, 34, 60)
    draw.rounded_rectangle([14, 92, 246, 130], radius=8, fill=btn_fill, outline=btn_border, width=2 if demo_glow else 1)
    draw.text((36, 103), "⚡ Load Hackathon Demo Patch", fill=(255, 255, 255) if demo_glow else INDIGO, font=get_font(12))
    
    # Files list section
    draw.line([0, 142, 260, 142], fill=BORDER_COLOR)
    draw.text((14, 152), "MODIFIED FILES (3)", fill=TEXT_DIM, font=get_font(10))
    
    files = [
        ("auth_service.py", "+46", "-6", CRIMSON),
        ("payment_worker.py", "+64", "-4", AMBER),
        ("dashboard.js", "+55", "-4", AMBER),
    ]
    
    y = 175
    for fname, add, sub, badge_col in files:
        if show_files:
            draw.rounded_rectangle([10, y, 250, y+34], radius=6, fill=CARD_BG if fname=="auth_service.py" else SURFACE_COLOR, outline=BORDER_COLOR)
            draw.text((18, y+9), "📄 " + fname, fill=TEXT_WHITE, font=get_font(11, mono=True))
            draw.text((180, y+9), add, fill=EMERALD, font=get_font(10, mono=True))
            draw.text((215, y+9), sub, fill=CRIMSON, font=get_font(10, mono=True))
        y += 42

def draw_risk_gauge(draw, cx, cy, radius, score):
    # Arc background
    draw.ellipse([cx-radius, cy-radius, cx+radius, cy+radius], outline=(40, 44, 60), width=8)
    
    # Arc foreground proportional to score
    color = CRIMSON if score >= 70 else (AMBER if score >= 40 else EMERALD)
    angle = int(360 * (score / 100))
    if angle > 0:
        draw.arc([cx-radius, cy-radius, cx+radius, cy+radius], start=-90, end=-90 + angle, fill=color, width=8)
        
    draw.text((cx-16, cy-14), str(score), fill=color, font=get_font(22))
    draw.text((cx-12, cy+10), "RISK", fill=TEXT_DIM, font=get_font(9))

def create_diffshield_demo_gif():
    frames = []
    
    # Frame 1: Initial empty state
    img = Image.new("RGB", (WIDTH, HEIGHT), BG_COLOR)
    draw = ImageDraw.Draw(img)
    draw_top_nav(draw, "gemma3:4b", "ONLINE", "Ready")
    draw_sidebar(draw, "paste", demo_glow=False, show_files=False)
    # Center placeholder
    draw.rounded_rectangle([320, 160, 880, 420], radius=12, fill=SURFACE_COLOR, outline=BORDER_COLOR)
    draw.text((540, 240), "🛡️", fill=TEXT_DIM, font=get_font(36))
    draw.text((470, 300), "DiffShield PR Reviewer Ready", fill=TEXT_WHITE, font=get_font(18))
    draw.text((390, 335), "Paste unified diff or click 'Load Hackathon Demo Patch'", fill=TEXT_MUTED, font=get_font(13))
    frames.append(img)
    
    # Frame 2: Hover over Demo button with glowing cursor
    img = img.copy()
    draw = ImageDraw.Draw(img)
    draw_sidebar(draw, "paste", demo_glow=True, show_files=False)
    # Cursor
    cx, cy = 130, 110
    draw.polygon([(cx, cy), (cx+14, cy+14), (cx+4, cy+14), (cx, cy+20)], fill=(255, 255, 255))
    frames.append(img)
    
    # Frame 3: Analyzing Diff... Loading state
    img = Image.new("RGB", (WIDTH, HEIGHT), BG_COLOR)
    draw = ImageDraw.Draw(img)
    draw_top_nav(draw, "gemma3:4b", "ONLINE", "Analyzing...")
    draw_sidebar(draw, "paste", demo_glow=False, show_files=True)
    # Loading modal
    draw.rounded_rectangle([360, 200, 840, 360], radius=12, fill=CARD_BG, outline=INDIGO, width=2)
    draw.text((450, 240), "⚙ Analyzing Code Diff with DiffShield...", fill=TEXT_WHITE, font=get_font(16))
    draw.text((430, 275), "⚡ Instant AST Security Scan + Local Gemma Review", fill=INDIGO, font=get_font(13))
    # progress bar
    draw.rounded_rectangle([420, 310, 780, 320], radius=5, fill=(35, 40, 55))
    draw.rounded_rectangle([420, 310, 680, 320], radius=5, fill=INDIGO)
    frames.append(img)
    
    # Frame 4: Analysis Complete - Executive Banner + Gauge 85
    for gauge_score in [25, 55, 85]:
        img = Image.new("RGB", (WIDTH, HEIGHT), BG_COLOR)
        draw = ImageDraw.Draw(img)
        draw_top_nav(draw, "gemma3:4b", "ONLINE", "182ms")
        draw_sidebar(draw, "paste", demo_glow=False, show_files=True)
        
        # Exec summary banner
        draw.rounded_rectangle([275, 58, 945, 168], radius=10, fill=SURFACE_COLOR, outline=BORDER_COLOR)
        draw_risk_gauge(draw, 335, 113, 40, gauge_score)
        
        draw.text((400, 72), "PR Review Complete", fill=TEXT_WHITE, font=get_font(18))
        draw.rounded_rectangle((580, 72, 700, 94), radius=10, fill=(99, 102, 241, 40), outline=INDIGO)
        draw.text((592, 76), "HYBRID AI + STATIC", fill=INDIGO, font=get_font(9))
        
        draw.text((400, 100), "Detected 9 Critical vulnerabilities (SQLi, Hardcoded Keys, eval, shell=True)", fill=TEXT_MUTED, font=get_font(12))
        
        # Verdict badge
        draw.rounded_rectangle([400, 126, 610, 154], radius=6, fill=(239, 68, 68, 40), outline=CRIMSON)
        draw.text((414, 132), "⛔ BLOCKED: CRITICAL RISK", fill=CRIMSON, font=get_font(11))
        
        frames.append(img)
        
    # Frame 5: Diff viewer showing Code + Inline AI Review Card
    img = Image.new("RGB", (WIDTH, HEIGHT), BG_COLOR)
    draw = ImageDraw.Draw(img)
    draw_top_nav(draw, "gemma3:4b", "ONLINE", "182ms")
    draw_sidebar(draw, "paste", demo_glow=False, show_files=True)
    
    # Exec banner
    draw.rounded_rectangle([275, 58, 945, 168], radius=10, fill=SURFACE_COLOR, outline=BORDER_COLOR)
    draw_risk_gauge(draw, 335, 113, 40, 85)
    draw.text((400, 72), "PR Review Complete", fill=TEXT_WHITE, font=get_font(18))
    draw.rounded_rectangle([400, 126, 610, 154], radius=6, fill=(239, 68, 68, 40), outline=CRIMSON)
    draw.text((414, 132), "⛔ BLOCKED: CRITICAL RISK", fill=CRIMSON, font=get_font(11))
    
    # Diff Viewer container
    draw.rounded_rectangle([275, 178, 945, 525], radius=10, fill=SURFACE_COLOR, outline=BORDER_COLOR)
    draw.rectangle([275, 178, 945, 210], fill=(20, 23, 33), outline=BORDER_COLOR)
    draw.text((290, 186), "📄 auth_service.py   @@ -35,12 +35,24 @@", fill=TEXT_WHITE, font=get_font(11, mono=True))
    
    # Diff lines
    y = 216
    draw.text((285, y), " 41  def login():", fill=TEXT_DIM, font=get_font(11, mono=True))
    y += 20
    draw.text((285, y), " 42      conn = get_db()", fill=TEXT_DIM, font=get_font(11, mono=True))
    y += 20
    # Highlighted addition with SQL injection
    draw.rectangle([276, y-2, 944, y+20], fill=(239, 68, 68, 45))
    draw.text((285, y), "+43      query = \"SELECT * FROM users WHERE username = '\" + username + \"'\"", fill=(255, 140, 140), font=get_font(11, mono=True))
    y += 26
    
    # Inline AI Review Card
    draw.rounded_rectangle([320, y, 925, y+160], radius=8, fill=CARD_BG, outline=CRIMSON, width=2)
    # Card Header
    draw.rounded_rectangle([332, y+10, 400, y+30], radius=4, fill=CRIMSON)
    draw.text((340, y+13), "CRITICAL", fill=(255, 255, 255), font=get_font(10))
    
    draw.rounded_rectangle([410, y+10, 475, y+30], radius=4, fill=(50, 55, 75))
    draw.text((418, y+13), "SECURITY", fill=TEXT_MUTED, font=get_font(10))
    
    draw.rounded_rectangle([485, y+10, 580, y+30], radius=4, fill=(99, 102, 241, 50))
    draw.text((495, y+13), "Gemma Local AI", fill=INDIGO, font=get_font(10))
    
    draw.text((595, y+12), "SQL Injection via String Concatenation", fill=TEXT_WHITE, font=get_font(12))
    
    # Description
    draw.text((332, y+40), "Raw string interpolation in SQL query enables complete authentication bypass.", fill=TEXT_MUTED, font=get_font(11))
    
    # Suggested Fix Box
    draw.rounded_rectangle([332, y+68, 910, y+148], radius=6, fill=(12, 14, 20), outline=EMERALD)
    draw.text((344, y+76), "✦ SUGGESTED REMEDIATION", fill=EMERALD, font=get_font(10))
    
    # Copy Fix Button
    draw.rounded_rectangle([820, y+72, 900, y+94], radius=4, fill=(16, 185, 129, 40), outline=EMERALD)
    draw.text((830, y+76), "Copy Fix", fill=EMERALD, font=get_font(10))
    
    draw.text((344, y+102), "cursor.execute(\"SELECT * FROM users WHERE username = ?\", (username,))", fill=(160, 255, 200), font=get_font(11, mono=True))
    
    frames.append(img)
    
    # Frame 6: Copy Fix Clicked + Toast Notification
    img_toast = img.copy()
    draw = ImageDraw.Draw(img_toast)
    # Cursor on Copy Fix
    cx, cy = 855, y+82
    draw.polygon([(cx, cy), (cx+12, cy+12), (cx+4, cy+12), (cx, cy+18)], fill=(255, 255, 255))
    # Toast in bottom right
    draw.rounded_rectangle([680, 460, 930, 505], radius=8, fill=(20, 24, 35), outline=EMERALD, width=2)
    draw.text((700, 474), "✓ Fix copied to clipboard!", fill=EMERALD, font=get_font(12))
    frames.append(img_toast)

    # Frame 7: Export Markdown Clicked
    img_export = img.copy()
    draw = ImageDraw.Draw(img_export)
    draw.rounded_rectangle([680, 460, 930, 505], radius=8, fill=(20, 24, 35), outline=INDIGO, width=2)
    draw.text((700, 474), "✓ Exported PR Review (.md)", fill=TEXT_WHITE, font=get_font(12))
    frames.append(img_export)

    # Save animated GIF
    out_path = os.path.join(ASSETS_DIR, "diffshield-demo.gif")
    # 9 frames total: 1, 2, 3, 4(a,b,c), 5, 6, 7
    durations = [1400, 900, 1100, 450, 450, 700, 2200, 1800, 2200]
    frames[0].save(
        out_path,
        save_all=True,
        append_images=frames[1:],
        duration=durations[:len(frames)],
        loop=0,
        optimize=True
    )
    print(f"Generated demo GIF: {out_path} ({os.path.getsize(out_path)} bytes)")

def create_workflow_walkthrough_gif():
    frames = []
    
    steps = [
        ("Step 1: 100% Air-Gapped Setup", "Ollama running Google Gemma locally on http://localhost:11434", [
            "$ ollama pull gemma3:4b",
            "$ ollama serve",
            "⠹ DiffShield connected: 100% LOCAL EXECUTION • ZERO EGRESS"
        ]),
        ("Step 2: Submit PR Diff or Local Repo", "Analyze raw patches, unified diffs, or point to local git folders", [
            "$ python main.py",
            "INFO: Uvicorn running on http://localhost:8000 (Press CTRL+C to quit)",
            "✦ Ingestion: Paste Diff | Local Git Repo | File Upload (.patch)"
        ]),
        ("Step 3: Instant Static AST Guard + Gemma Review", "Dual engine catches secrets, SQLi, and architectural race conditions", [
            "⚡ Static Guard: 16 deterministic patterns in 15ms",
            "🤖 Gemma Local AI: Deep logic review & O(n²) algorithmic checks",
            "✓ Telemetry: 182ms total latency • Zero cloud leakage"
        ]),
        ("Step 4: Interactive Diff & One-Click Fixes", "Circular SVG risk gauge, inline annotations, and instant remediation", [
            "⛔ Verdict: BLOCKED: CRITICAL RISK (Risk Score: 85/100)",
            "✦ Fix: cursor.execute('SELECT * FROM users WHERE username = ?', (u,))",
            "📥 Export to PR Review (.md) or Copy GitHub PR Comment"
        ]),
    ]
    
    for title, subtitle, bullets in steps:
        img = Image.new("RGB", (WIDTH, HEIGHT), BG_COLOR)
        draw = ImageDraw.Draw(img)
        draw_top_nav(draw, "gemma3:4b", "ONLINE", "Air-Gapped")
        
        # Central card
        draw.rounded_rectangle([120, 80, 840, 480], radius=16, fill=SURFACE_COLOR, outline=BORDER_COLOR)
        draw.rounded_rectangle([120, 80, 840, 140], radius=16, fill=CARD_BG, outline=BORDER_COLOR)
        
        draw.text((150, 95), title, fill=INDIGO, font=get_font(20))
        draw.text((150, 155), subtitle, fill=TEXT_MUTED, font=get_font(13))
        
        # Terminal-style output box
        draw.rounded_rectangle([150, 200, 810, 440], radius=10, fill=(10, 12, 18), outline=(50, 55, 75))
        
        # Window dots
        draw.ellipse([168, 216, 178, 226], fill=CRIMSON)
        draw.ellipse([186, 216, 196, 226], fill=AMBER)
        draw.ellipse([204, 216, 214, 226], fill=EMERALD)
        draw.text((230, 214), "diffshield-terminal", fill=TEXT_DIM, font=get_font(10, mono=True))
        
        y = 250
        for b in bullets:
            col = EMERALD if b.startswith("✓") or b.startswith("⠹") else (INDIGO if b.startswith("⚡") or b.startswith("🤖") else TEXT_WHITE)
            draw.text((170, y), b, fill=col, font=get_font(13, mono=True))
            y += 45
            
        frames.append(img)
        
    out_path = os.path.join(ASSETS_DIR, "workflow-walkthrough.gif")
    frames[0].save(
        out_path,
        save_all=True,
        append_images=frames[1:],
        duration=[2200, 2200, 2200, 2500],
        loop=0,
        optimize=True
    )
    print(f"Generated workflow GIF: {out_path} ({os.path.getsize(out_path)} bytes)")

if __name__ == "__main__":
    create_diffshield_demo_gif()
    create_workflow_walkthrough_gif()
