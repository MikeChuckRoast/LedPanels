from rgbmatrix import RGBMatrix, RGBMatrixOptions, graphics
import time

options = RGBMatrixOptions()
options.rows = 32
options.cols = 64
options.chain_length = 2     # or parallel = 2 for vertical stack
options.parallel = 1
options.gpio_slowdown = 3

matrix = RGBMatrix(options = options)
canvas = matrix.CreateFrameCanvas()

font = graphics.Font()
font.LoadFont("fonts/texgyre-27.bdf")

textColor = graphics.Color(0, 255, 0)
message = "Happy Pace Timing   "

pos = canvas.width

while True:
    canvas.Clear()
    graphics.DrawText(canvas, font, pos, 24, textColor, message)
    pos -= 1

    if pos + len(message) * 12 < 0:
        pos = canvas.width

    time.sleep(0.03)
    canvas = matrix.SwapOnVSync(canvas)
