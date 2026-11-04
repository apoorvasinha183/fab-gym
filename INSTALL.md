# Installing Fab Gym

Step by step, for macOS, Windows and Linux. About 15 minutes the first time, most of it waiting for Rust.

**Just want to look?** You need none of this: the browser version runs at
[apoorvasinha183.github.io/fab-gym-site/play](https://apoorvasinha183.github.io/fab-gym-site/play/).

---

## 1. Install the tools

You need four things: **Git**, **Rust**, **Python 3.12 or newer** and **Node.js 18 or newer**. Python needs no extra
packages for the simulator and the pages.

### macOS

Install [Homebrew](https://brew.sh) if you don't have it, then:

```sh
brew install git python node
curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh     # Rust; accept the defaults
```

Open a new terminal afterwards, so the new commands are found.

### Windows

Run these in PowerShell, then **use Git Bash** (installed with Git) for every step after this one:

```powershell
winget install Git.Git
winget install Python.Python.3.12
winget install OpenJS.NodeJS.LTS
winget install Rustlang.Rustup
```

Open Git Bash from the Start menu. If `python3` is not found there, use `python` instead in the commands below.

### Linux (Debian or Ubuntu)

```sh
sudo apt install git python3 nodejs npm build-essential curl
curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh     # Rust; accept the defaults
```

### Check

```sh
git --version && cargo --version && python3 --version && node --version
```

Each prints a version number. Python must say 3.12 or higher, Node 18 or higher.

---

## 2. Get the code and build it

```sh
git clone https://github.com/apoorvasinha183/fab-gym
cd fab-gym
rustup target add wasm32-unknown-unknown     # lets Rust build the browser simulator; once
cargo build --release                        # the simulator; about 2 minutes
sh web/build.sh                              # the browser simulator and the pages' data; about 1 minute
```

The last line ends with `serve with: ...`. The fab's data (the SMT2020 testbed, MIT licence) is already in the repo,
so nothing else is downloaded.

---

## 3. Run it

```sh
python3 -m agent.helper --port 8766
```

Leave that terminal open, and open **http://127.0.0.1:8766** in your browser. You get:

- **Desk**: Lou's front page;
- **Floor**: the whole fab, 1,043 machines, running live;
- **Build**: draw your own fab, with four challenges scored as you draw;
- **Evidence** and **Runs**: what the simulator found, and every run behind it.

To stop it, press **Ctrl+C** in that terminal.

---

## 4. Add your keys (optional)

Everything above works with **no keys**. Keys let Meta's models answer live instead of with recorded answers. Each
key is a text file holding only the key, in a folder called `.config/fab-gym` in your home folder.

| File | What it unlocks | Where to get it |
| --- | --- | --- |
| `meta.key` | Muse Spark, Muse Wonder and Muse Image: the ask bar, Race the AI, the napkin sketch | your Meta Model API account |
| `baseten.key` | Muse Spark Open, Meta's open-weights model: Lou's brain in the 3D fab, the agent loop | your Baseten account, under API keys |

### macOS and Linux

Replace `PASTE-YOUR-KEY` with your key, keeping the quotes:

```sh
mkdir -p ~/.config/fab-gym
printf '%s' 'PASTE-YOUR-KEY' > ~/.config/fab-gym/meta.key
printf '%s' 'PASTE-YOUR-KEY' > ~/.config/fab-gym/baseten.key     # if you have one
chmod 600 ~/.config/fab-gym/*.key                                # only you can read them
```

### Windows (PowerShell)

```powershell
New-Item -ItemType Directory -Force "$HOME\.config\fab-gym"
Set-Content -NoNewline "$HOME\.config\fab-gym\meta.key" "PASTE-YOUR-KEY"
Set-Content -NoNewline "$HOME\.config\fab-gym\baseten.key" "PASTE-YOUR-KEY"     # if you have one
```

### Use them

Restart the helper (Ctrl+C, then run it again):

```sh
python3 -m agent.helper --port 8766                  # uses meta.key
python3 -m agent.helper --port 8766 --preset open    # uses baseten.key: Muse Spark Open, and Lou's brain
```

**Check the key was found:** open http://127.0.0.1:8766/api/status. It should say `"model_connected": true` and name
the model. That means the file is there; to test the key itself, ask a question in the Floor's ask bar. A wrong key
answers with an error from the model's service.

**Spending:** the helper stops calling models once it has spent $20 (`--spend-cap 5` for $5). Your keys are read only
by the helper on your computer and sent only to the model's own service.

---

## 5. The 3D fab (optional)

1. Download the app for your computer from the
   [latest release](https://github.com/apoorvasinha183/fab-gym/releases/latest).
2. Start the helper (step 3); the 3D fab reads its live run from it. Use `--preset open` if you want Lou to answer
   with Muse Spark Open.
3. Open the app:
   - **macOS:** unzip, then **right-click** Fab Gym 3D and choose **Open** (it is not signed by Apple). The first start
     takes about 20 seconds.
   - **Windows:** run the `.exe`. If SmartScreen warns, click **More info**, then **Run anyway**.

**Walk alone** ends the tour. **W A S D** walk, **Shift** hurries, **F** flies (**E** up, **Q** down), the right mouse
button looks around, and **Ask Lou** asks a question. In the cinema: **E** to sit, **1** or **2** to pick a film,
**Enter** to play.

---

## 6. Command line only (optional)

After step 2, no browser needed:

```sh
./target/release/fabsim bench data/smt2020/hvlm --days 30 --seeds 5                 # how fast it runs
./target/release/fabsim score agent/examples/group79.scenario.txt data/smt2020/hvlm # a what-if, with 95% intervals (JSON)
./target/release/fabsim log web/data/shop.txt 0 1440 > day1.log                     # one day's events
```

### As a reinforcement-learning environment

```sh
pip install gymnasium numpy                 # add stable-baselines3 to train PPO
```

```python
import gymnasium as gym
import agent.fabgym_env                     # registers FabGym-v0 and FabGymDefects-v0
env = gym.make("FabGym-v0")
obs, info = env.reset(seed=0)
obs, reward, terminated, truncated, info = env.step(env.action_space.sample())
```

The README's "As a reinforcement-learning environment" section explains the actions, observations and rewards.

---

## If something goes wrong

| You see | Do this |
| --- | --- |
| `command not found: cargo` | Open a new terminal after installing Rust, or run `source ~/.cargo/env`. |
| `can't find crate for 'core'` or `wasm32` errors in `web/build.sh` | Run `rustup target add wasm32-unknown-unknown`, then `sh web/build.sh` again. |
| `node: command not found` during `web/build.sh` | Install Node.js (step 1) and open a new terminal. |
| `Address already in use` when starting the helper | Something else uses port 8766: add `--port 8770` and open http://127.0.0.1:8770. |
| The pages say "The helper did not answer" | The helper is not running, or runs on another port: start it (step 3). |
| `/api/status` says `"model_connected": false` | The key file is missing or in the wrong folder: check step 4's paths. |
| Windows: `sh: command not found` | Run the commands in Git Bash, not PowerShell or cmd. |
| macOS: "Fab Gym 3D can't be opened" | Right-click the app, choose **Open**, then **Open** again. |
| The 3D fab shows the tour but nothing moves | Start the helper first (step 3), then reopen the app. |
