# SDVX ∇ VolForce Tracker

Very random script to send results after a play in DMs for SOUND VOLTEX ∇, version `KFC-2026082500` only.

The main point of it is to be able to fast check VF after each play.

The script reads data directly from the memory allocated in the heap by the game for the score, thus `SCORE_WRITE_OFFSET` and `DIFF_INDEX_OFFSET` has to be changed after each update. See `score_hook.cpp` for more details.

![Rasist sending play results](img/rasist.jpg)

## Setup

- Clone the repo and move it to sdvx' root folder
- Compile the C++ code

```cpp
g++ -O2 -shared -o score_hook.dll score_hook.cpp -static
```

- Move the DLL to the game's root folder, and add it to the Inject DLL Hooks list from `spicecfg.exe`
- Create a Discord app
- Create a .env file based on the template and fill the needed fields (Imgur is optional)
- Install the needed Python requirements, use a venv as needed:

```bash
pip install -r requirements.txt
```

- Run the bot (create a .bat for easy access)

```bash
.venv/Scripts/python.exe bot.py
```
