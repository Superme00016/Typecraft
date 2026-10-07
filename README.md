# Typecraft

English | [中文](README.zh-CN.md)

A local desktop typing simulator for Windows, macOS, and Linux. Paste your text, set a pace or finishing time, and run a preview or type into another application.

## Start here

Requires **Python 3.10 or newer with Tkinter**. This download contains source code and launchers, not a prebuilt executable. Extract the whole folder before launching; keep its Python files together.

- **Windows:** install Python from [python.org](https://www.python.org/downloads/), including Tcl/Tk and the Python launcher, then double-click **Start Windows.bat**. Alternatively, open a terminal in this folder and run `py -3 typecraft.py`.
- **macOS:** install a Python distribution with Tcl/Tk, such as the python.org installer. Run `python3 typecraft.py` from this folder in Terminal. You can also run `chmod +x "Start macOS.command"` once and double-click that launcher.
- **Linux:** run `python3 typecraft.py`. If Tkinter is missing, install your distribution's Tkinter package. On Debian/Ubuntu: `sudo apt install python3-tk`. The shell launcher can be run with `sh start-linux.sh`.

Preview mode needs no third-party Python packages. Check your GUI installation with `python3 -m tkinter` (Windows: `py -3 -m tkinter`). A small demonstration window should open.

### Linux: nothing happens when double-clicking

Open Terminal in the extracted Typecraft folder and run:

```sh
sh start-linux.sh
```

The Linux launcher checks for Python and Tkinter and shows startup errors in a dialog when `zenity` or `xmessage` is available. Errors also print in Terminal. On Ubuntu, Linux Mint, or Debian, install a missing Tkinter package with `sudo apt install python3-tk`; sudo may ask for your Linux password in Terminal.

Some file managers open shell scripts as text or do not execute them on double-click. Running the command above avoids that setting. If you want double-click launching, mark the script executable (`chmod +x start-linux.sh`) and choose **Run** or **Run in Terminal** when your file manager asks.

## Enable typing into another app

Install the optional keyboard dependency into a virtual environment **inside this folder**. All three launchers automatically use that `.venv` when present.

Windows, in PowerShell:

```powershell
py -3 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe typecraft.py
```

macOS / Linux, in Terminal:

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python typecraft.py
```

On Debian/Ubuntu, creating a virtual environment may also require `sudo apt install python3-venv`.

If pip reports that it cannot compile `evdev` on Linux, install your distribution's build tools and Python headers (Debian/Ubuntu: `sudo apt install build-essential python3-dev`) and retry. A distribution package is also usable if its pynput version satisfies `requirements.txt`; older packages will be flagged by the startup check.

1. Paste the text and choose **Type into another app**.
2. Open an empty document in a plain-text editor.
3. Click **Start typing**, then click the destination text field during the five-second countdown.
4. Press **Esc** to stop immediately, including during the countdown. The app's **Stop** button also works. If you pause, resuming gives you another five seconds to select the destination.

Typing follows whichever window currently has keyboard focus. Keep the target selected while it runs. **Enter and Tab are real keypresses**: they can submit a chat/form or move focus. Test in a plain-text editor first. Starting again begins from the start of your source, so clear or reposition the destination yourself.

## Controls

| Control | Behavior |
| --- | --- |
| Words / second | Average pace, using the standard typing word of five characters, including spaces. `0.8` words/sec = 48 WPM. |
| Finish in minutes | Base typing time. Custom rule waits extend it; the main page shows base time, added waits, and expected total. Countdown and manual pauses are excluded. |
| Mistakes | Probability of automatic nearby-key errors, if enabled in the profile. Custom rules have their own probabilities. |
| Rhythm variation | Uneven keystrokes, word pauses, punctuation pauses, and occasional hesitation. At zero, ordinary keystrokes are evenly spaced. Corrections still take extra strokes. |
| Relaxed / Natural / Quick | Presets for pace, mistakes, and rhythm. Choosing a preset switches back to words/second. |
| Preview | Shows every emitted stroke; deliberate mistakes briefly appear in red. External mode also mirrors the emitted strokes here. |
| Open / Save / Copy | Import UTF-8 text, save the displayed preview, or copy it to the clipboard. |

The live word counter counts whitespace-separated words; speed uses five-character typing words. These are different measurements. Error percentages are probabilities, so short passages may have no mistakes. Automatic nearby-key mistakes use QWERTY neighbors. Custom profiles support literal replacements and pauses; rules default to correction, but can intentionally retain wrong text.

## Timing and text behavior

- The engine creates a random typing plan and scales ordinary stroke timing to your base pace or duration. Profile delays are added without compression. The displayed plan is used at Start; after completion or Stop a fresh plan is prepared for the next run.
- Finish time is a target, not a real-time guarantee. A busy computer, sleep, an unresponsive destination, or OS input latency can delay completion. There is no claim that the simulation is indistinguishable from a human.
- Text is limited to 100,000 characters and 24 hours per run. Extremely fast settings are rejected: at most 250 planned strokes/sec in preview, or 60 in external mode.
- Spaces, blank lines, punctuation, and Unicode are preserved in preview. Windows/old-Mac line endings are normalized to `\n`. Non-text control characters are rejected.
- Stopping preserves partial output. If you stop between a typo and its correction, that typo may remain. Stop does not erase text in another application.
- Preview is a record of emitted keystrokes, not a readback from the target application. Autocorrect, auto-indent, smart quotes, shortcuts, focus changes, keyboard layouts, and target restrictions can alter external results. Disable editor transformations when exact output matters.
- Text stays in memory until you explicitly copy or save it. Interface language and applied profiles are saved to `user_data/settings.json` beside the app. Ordinary typing has no network calls, telemetry, or automatic text history. Generate sends the AI-page input and instructions to your configured endpoint. Test connection sends only a short test prompt, without your source text. Closing the app discards unsaved text. An external destination may have its own storage/network behavior.

## Platform limits

- **Windows:** ordinary desktop text fields are the intended target. Protected or elevated applications may reject simulated input. Unicode acceptance depends on the destination.
- **macOS:** allow the Python launcher or Terminal under **System Settings → Privacy & Security → Accessibility** and, where requested, **Input Monitoring**. Restart after granting access. The app checks OS accessibility permission before starting and checks the running listener instance before typing. Listener startup has a five-second timeout; cleanup does not block the UI.
- **Linux:** preview works with Tkinter on graphical desktops. External typing in this version requires **X11**; the app rejects Wayland sessions, where pynput's support is limited. Select an X11 desktop session at login if available. No root access is required for the X11 backend.
- Unicode outside basic letters, particularly emoji or input-method composition, may not work reliably in every external application. A real Linux X11 test reproduced an incorrect Chinese character after correction; Chinese direct keyboard delivery is not verified as reliable. Preview supports Unicode; test the actual target with a short sample.

Backend reference: [pynput platform limitations](https://pynput.readthedocs.io/en/latest/limitations.html) and [keyboard API](https://pynput.readthedocs.io/en/latest/keyboard.html).

## Suggested starting settings

Start with **0.8 words/sec, 2% mistakes, and 55% variation**. Preview a short paragraph, then adjust the pace. To disable deliberate errors, set **Mistakes to 0%** and disable custom typo rules; custom rules have their own probabilities. For a recording, check the displayed total, which includes added rule waits, and allow five extra seconds if using an external destination.

## Validation

Before publication, 94 automated tests passed on Linux with Python 3.12, Tk 8.6 and an isolated X11 display. Tests cover the typing engine, rules, GUI, AI request handling and startup checks. Test code and detailed test records are retained locally and are not included in this public repository. Local regression tests cover macOS permission handling and listener failures using simulated backends. Real Linux X11 checks cover ASCII input, Escape and listener cleanup. Windows/macOS native execution and live AI provider calls remain unverified.

## Language and custom rules

Use **Settings ▾ → 中文 / English** to switch interface language without changing the source text or active profile. Use **Custom typing rules…** to open a separate editor. Start with the English nearby-key or Chinese homophone preset; add or edit typo/pause rules, then **Apply and return**. Export/import uses data-only JSON; examples are in `presets/`.

A typo rule can match a literal word or phrase, enter a replacement, wait, backspace, and correct it. Unchecking automatic correction retains the replacement. Pause rules wait after matching source text. Every rule has its own probability and min/max millisecond waits. Disabled rules are ignored. Longest typo match wins; ties use list order. Matching is case-sensitive, not word-boundary-based. Multiple pause rules can add their waits.

Configurations accept at most 200 rules and 512 KB, with wait ranges from 0 to 60,000 ms. Unknown fields, duplicate JSON keys, invalid ranges, and non-finite numbers are rejected. Typo replacements exclude emoji/combining sequences because target applications differ in their backspace behavior. Original text can still contain Unicode. Applied profiles and language are saved locally under `user_data/`; source text is not saved automatically.

## Optional AI assistant

Choose **Settings → AI assistant**. Enter an OpenAI-compatible Chat Completions base URL, model ID and your own API key. The default address is `https://api.openai.com/v1`; the model is intentionally blank. Native vendor protocols without a compatible Chat Completions endpoint are not supported. No additional Python package is required for AI requests.

Tasks: design typing rhythm, rewrite naturally, translate, and a custom text instruction. Generated plans are validated against the source and existing profile schema. Results are previewed and never automatically applied or typed. Applying a plan brings the AI-page source and recommended settings to the main page; text tasks replace only the main text. One in-memory undo snapshot is available.

Connection settings can be saved without the key. Keys remain in the app session; an explicit button can read `TYPECRAFT_API_KEY` or `OPENAI_API_KEY`. Generate sends the visible text and instructions; connection testing sends only an OK prompt. Requests can incur provider charges. Cancellation ignores late results locally but does not guarantee provider-side cancellation. The app does not retry automatically.

Remote endpoints require HTTPS. Redirects are blocked and errors do not expose raw response bodies. Local HTTP is supported only on localhost/loopback. Actual provider access, model compatibility and billing were not tested with a real key; local HTTP contract tests and mocked UI tests cover the implementation. See [AI guide](AI.zh-CN.md) for limits and behavior.

## Startup checks

Every launch checks the selected Python interpreter, Tk/Tcl, SSL and optional pynput version/backend. Missing or incompatible dependencies produce installation instructions and official links. Optional failures allow preview; required failures block entry. Restart after installing or granting permissions to check again. The check makes no network requests and installs nothing.

Linux without Tk uses zenity or xmessage for a native error dialog; if neither is available, instructions remain in the terminal. Run `sh start-linux.sh` to read them. On macOS and Windows, launchers use native dialogs when Python is absent. Native launcher behavior has not been verified on those two operating systems.
