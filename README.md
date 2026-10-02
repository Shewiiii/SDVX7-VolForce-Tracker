# SDVX ∇ VolForce Tracker

Very random script to send results after a play in DMs for SOUND VOLTEX ∇, running on the RyuNET private network.

The main point of it is to be able to fast check VF after each play.

The script observes the game's e-amusement result requests through a local proxy and forwards them unchanged to Ryu's server.

![Rasis sending play results](img/rasis.jpg)

## Setup

- Clone the repo and move it to sdvx' root folder
- Install Node.js.
- Download [RyuNET-core](https://github.com/Ryu7w7/RyuNET-core), then move `RyuNET-core-master` next to `ea_proxy.ts`. Your game's folder should look like this:

```text
SOUND VOLTEX NABLA/
...
|-- SDVX7-VolForce-Tracker-main/
	|-- bot.py
	|-- ea_proxy.ts
	|-- run_tracker.bat
	|-- RyuNET-core-master/
		...
```

- Install the RyuNET-core Node.js dependencies once, so the local proxy can reuse its protocol decoders:

```powershell
cd C:\Path\To\RyuNET-core-master
npm install
```

- Set Spice2x's EA Service URL to `http://127.0.0.1:8080/service`.
- Create a Discord app
- Install the needed Python requirements, use a venv as needed:

```bash
pip install -r requirements.txt
```
- Create and fill a .env from the template (Imgur is optional)
- Run `run_tracker.bat`, *then* start the game. Create a shortcut of it for easy access !

> [!NOTE]  
> If you use a virtual environment, replace the Python launcher line. Replace `venv` with whatever the name of your venv is.
> ```bat
> start "SDVX Discord Bot" /D "%REPO_ROOT%" "%ComSpec%" /k "%REPO_ROOT%venv\Scripts\python.exe" "%REPO_ROOT%bot.py"
> ```

## Limitations

- You cannot run the game without the proxy, as long as EA Service URL is set to localhost.
- Due to API limitations, the message is sent only after quitting the result page.

## Credits

- The local proxy reuses the e-amusement decoding utilities from [RyuNET-core](https://github.com/Ryu7w7/RyuNET-core).
