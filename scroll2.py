import time

from rgbmatrix import RGBMatrix, RGBMatrixOptions, graphics

# -------------------------------
# CONFIGURATION
# -------------------------------

# Panel configuration
ROWS = 32
COLS = 64
CHAIN = 2       # Number of panels chained horizontally
PARALLEL = 1    # Number of panels stacked vertically
SLOWDOWN = 3    # Matches your Hansen Panel Pi Hat
SCROLL_SPEED = 0.05  # Delay between frames (seconds)

# Text configuration
TEXT = "Happy Pace Timing"
FONT_PATH = "fonts/texgyre-27.bdf"
COLOR = graphics.Color(0, 255, 0)  # Green
Y_OFFSET = -22   # Vertical offset in pixels
BG_COLOR = graphics.Color(32,32,32)

# -------------------------------
# INITIALIZE MATRIX
# -------------------------------

options = RGBMatrixOptions()
options.rows = ROWS
options.cols = COLS
options.chain_length = CHAIN
options.parallel = PARALLEL
options.gpio_slowdown = SLOWDOWN

matrix = RGBMatrix(options=options)
canvas = matrix.CreateFrameCanvas()

# Load font
font = graphics.Font()
font.LoadFont(FONT_PATH)

# -------------------------------
# CALCULATE TEXT WIDTH
# -------------------------------

text_width = sum(font.CharacterWidth(ord(c)) for c in TEXT)
print("Font height: ", font.height)

# -------------------------------
# SCROLLING LOOP
# -------------------------------

pos = canvas.width  # Start off-screen right

try:
    while True:
        # Draw background rectangle
        graphics.DrawLine(canvas, 0, 0, canvas.width-1, 0, BG_COLOR)  # Top line
        for y in range(canvas.height):
            graphics.DrawLine(canvas, 0, y, canvas.width-1, y, BG_COLOR)

        graphics.DrawText(canvas, font, pos, font.height + Y_OFFSET, COLOR, TEXT)
        pos -= 1  # Move left by 1 pixel

        # Reset position when text has completely left the screen
        if pos + text_width < 0:
            pos = canvas.width

        time.sleep(SCROLL_SPEED)
        canvas = matrix.SwapOnVSync(canvas)

except KeyboardInterrupt:
    matrix.Clear()
