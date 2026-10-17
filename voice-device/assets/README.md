# Screen artwork

`scripts/create_screen_background.py` generates `aurora-gradient.png`, a calm blue-teal gradient designed to keep the character legible on the 240 × 320 display. `scripts/build_screen_assets.py` embeds it as RGB565 pixels in firmware flash. The former Unsplash space image remains in this directory as an archived source but is no longer used by the firmware.

The character atlas is the DeepSeek girl desktop-pet atlas by f0909172434, licensed under MIT. Attribution is also recorded in `scripts/build_faces.py`.