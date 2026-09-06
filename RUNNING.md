# Running the agent loop

## 1. One-time setup

```bash
cd rnk-agent
python3 -m venv .venv
./.venv/bin/pip install -r requirements.txt
cp config.example.yaml config.yaml   # then edit platform.base_url etc.
```

(`config.yaml` is gitignored - `main.py` also auto-creates it from
`config.example.yaml` on first run if you skip this step.)

## 2. Start LM Studio

* Open LM Studio, load a vision-capable model, go to the **Developer** tab
  and click **Start Server** (default `http://localhost:1234`).
* Leave `llm.model: "auto"` in `config.yaml` to use whatever model LM Studio
  reports first from `/v1/models`, or set it to an exact model id/path to
  pin a specific one.

## 3. Run it

All of these are equivalent - pick whichever fits your habits:

```bash
# activate the venv once, then just use `python`
source .venv/bin/activate
python main.py

# or call the venv's python directly, no activation needed
./.venv/bin/python main.py

# or run the package as a module
./.venv/bin/python -m rnk_agent.main

# or, since main.py is executable (shebang + chmod +x):
./main.py
```

Use `--config <path>` with any of the above to point at a config file other
than `./config.yaml`, e.g. `./main.py --config config.dev.yaml`.

Use `--reset-todo` and/or `--reset-observations` to wipe the persisted
todo list and/or observations notebook (`state/todo.json`,
`state/observations.json`) before starting - they're independent flags, so
you can clear one and keep the other, e.g. `./main.py --reset-todo`.

Stop the loop any time with `Ctrl-C` (motors are stopped after every
command anyway, so nothing is left mid-motion).

## 4. While it's running

* Console output shows each step's reasoning/action/result.
* Type a line of text + `Enter` in the same terminal at any time - the
  agent will "hear" it (via the onboard-microphone stand-in) on its next
  step, though it's free to ignore it.
* Per-step camera frames are saved under `logs/`.
* The agent's todo list and observations notebook are persisted as JSON
  under `state/` (`todo.json`, `observations.json`) and **survive restarts**
  by default - use `--reset-todo` / `--reset-observations` if you want a
  clean slate (see above).
