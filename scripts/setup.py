#!/usr/bin/env python3
"""
Interactive setup wizard for HL Market Maker.

Walks users through:
1. Checking prerequisites
2. Entering wallet credentials
3. Selecting tokens
4. Choosing risk profile
5. Generating config.yaml and .env
6. Optional dry-run test
"""
import os
import sys
import subprocess
import yaml

RISK_PROFILES = {
    "1": {
        "name": "Conservative",
        "spread_pct": 0.30,
        "order_size_usd": 100,
        "max_inventory_units": 2,
        "stop_loss_pct": 1.5,
    },
    "2": {
        "name": "Balanced",
        "spread_pct": 0.15,
        "order_size_usd": 200,
        "max_inventory_units": 3,
        "stop_loss_pct": 2.0,
    },
    "3": {
        "name": "Aggressive",
        "spread_pct": 0.05,
        "order_size_usd": 400,
        "max_inventory_units": 5,
        "stop_loss_pct": 3.0,
    },
}

TOKEN_CATALOG = {
    "1": ("BRENTOIL", "Brent Crude Oil — high volume, stable commodity"),
    "2": ("CL", "Light Crude Oil — high volume, tight spreads"),
    "3": ("INTC", "Intel — large-cap tech, moderate volume"),
    "4": ("NVDA", "NVIDIA — very high volume, tight spreads"),
    "5": ("TSLA", "Tesla — high volume, slightly volatile"),
    "6": ("GOLD", "Gold — commodity, very stable"),
    "7": ("SILVER", "Silver — commodity, tightest spreads"),
    "8": ("SP500", "S&P 500 Index — very high volume"),
    "9": ("SPCX", "SpaceX Index — highest volume on XYZ"),
    "10": ("MU", "Micron — high volume semiconductors"),
}


def header(title):
    print(f"\n{'='*55}")
    print(f"  {title}")
    print(f"{'='*55}\n")


def prompt(question, default=""):
    suffix = f" [{default}]" if default else ""
    answer = input(f"  {question}{suffix}: ").strip()
    return answer or default


def yes_no(question, default="y"):
    answer = input(f"  {question} (y/n) [{default}]: ").strip().lower()
    return answer in ("", "y", "yes")


def main():
    header("🤖 HL Market Maker — Setup Wizard")
print()
    print("  💜 Tip: Use referral code LAZYCHARTGUY when signing up for Hyperliquid")
    print("     https://app.hyperliquid.xyz/join/LAZYCHARTGUY")
    print("     Gets you fee discounts and supports this project 🙏")

    # ── Step 1: Prerequisites ──────────────────────────────────────────────
    header("Step 1/6: Checking prerequisites")

    # Check Python version
    if sys.version_info < (3, 11):
        print("  ❌ Python 3.11+ required. You have", sys.version.split()[0])
        sys.exit(1)
    print(f"  ✅ Python {sys.version.split()[0]}")

    # Check pip packages
    missing = []
    deps = [
        ("hyperliquid", "hyperliquid-python-sdk"),
        ("eth_account", "eth-account"),
        ("yaml", "pyyaml"),
        ("requests", "requests"),
    ]
    for module, package in deps:
        try:
            __import__(module)
            print(f"  ✅ {package}")
        except ImportError:
            print(f"  ❌ {package} not installed")
            missing.append(package)

    if missing:
        print(f"\n  Installing: {' '.join(missing)}")
        result = subprocess.run(
            [sys.executable, "-m", "pip", "install"] + missing,
            capture_output=True, text=True,
        )
        if result.returncode != 0:
            print(f"  ❌ Install failed: {result.stderr[:200]}")
            print(f"  Run manually: pip install {' '.join(missing)}")
            sys.exit(1)
        print("  ✅ Dependencies installed")
    else:
        print("\n  All dependencies installed ✅")

    # ── Step 2: Wallet Credentials ─────────────────────────────────────────
    header("Step 2/6: Hyperliquid wallet setup")

    print("""  You need two things from Hyperliquid:
    1. Your main wallet address (the one you deposit USDC with)
    2. An API wallet private key (Settings → API Wallets → Create)

  ⚠️  The API wallet can only trade — it cannot withdraw funds.
  Never share your main wallet's private key.""")

    print()

    # Check for existing .env
    existing_wallet = os.environ.get("HL_WALLET", os.environ.get("HL_FUNDING_WALLET", ""))
    existing_key = os.environ.get("HL_PRIVATE_KEY", os.environ.get("HL_FUNDING_KEY", ""))

    if existing_wallet:
        wallet = prompt("Main wallet address", existing_wallet)
    else:
        wallet = prompt("Main wallet address (0x...)")

    if not wallet.startswith("0x") or len(wallet) < 10:
        print("  ❌ That doesn't look like a valid wallet address")
        sys.exit(1)

    if existing_key:
        use_existing = yes_no(f"Found existing API key ({existing_key[:8]}...), use it?")
        if use_existing:
            api_key = existing_key
        else:
            api_key = prompt("API wallet private key (0x...)")
    else:
        api_key = prompt("API wallet private key (0x...)")

    if not api_key.startswith("0x") or len(api_key) < 10:
        print("  ❌ That doesn't look like a valid private key")
        sys.exit(1)

    # Verify connection
    print("\n  Verifying connection...")
    try:
        import requests
        r = requests.post("https://api.hyperliquid.xyz/info",
            json={"type": "clearinghouseState", "user": wallet, "dex": "xyz"}, timeout=10)
        data = r.json()
        margin = data.get("marginSummary", {})
        equity = float(margin.get("accountValue", 0))
        if equity > 0:
            print(f"  ✅ Connected! XYZ equity: ${equity:,.2f}")
        else:
            print(f"  ⚠️  Connected, but $0 in XYZ clearinghouse")
            print(f"     Deposit USDC at: https://app.hyperliquid.xyz/portfolio")
            print(f"     Transfer USDC → XYZ (builder-dex) clearinghouse")
            if not yes_no("Continue setup anyway?"):
                sys.exit(0)
    except Exception as e:
        print(f"  ❌ Connection failed: {e}")
        if not yes_no("Continue setup anyway?"):
            sys.exit(1)

    # ── Step 3: Token Selection ────────────────────────────────────────────
    header("Step 3/6: Choose tokens to market make")

    print("  Recommended tokens (high volume, stable price):\n")
    for num, (symbol, desc) in TOKEN_CATALOG.items():
        print(f"    {num:>2}. {symbol:<10} — {desc}")
    print()

    selected = []
    default_tokens = "1,2,3"
    choices = prompt("Pick tokens (comma-separated numbers)", default_tokens)
    for choice in choices.split(","):
        choice = choice.strip()
        if choice in TOKEN_CATALOG:
            selected.append(TOKEN_CATALOG[choice][0])

    if not selected:
        print("  No valid tokens selected, using defaults (BRENTOIL, CL, INTC)")
        selected = ["BRENTOIL", "CL", "INTC"]

    # Deduplicate
    seen = set()
    selected = [t for t in selected if not (t in seen or seen.add(t))]

    print(f"\n  Selected: {', '.join(selected)}")

    # ── Step 4: Risk Profile ───────────────────────────────────────────────
    header("Step 4/6: Risk profile")

    print("""    1. Conservative — wider spread (0.30%), smaller orders ($100)
       Slower volume, lower risk. Good for testing.

    2. Balanced — medium spread (0.15%), medium orders ($200)
       Steady volume, moderate risk. Recommended for most users.

    3. Aggressive — tight spread (0.05%), larger orders ($400)
       Maximum volume, higher risk. More fills but more exposure.""")

    print()
    choice = prompt("Risk profile (1/2/3)", "2")
    risk = RISK_PROFILES.get(choice, RISK_PROFILES["2"])
    print(f"\n  Selected: {risk['name']}")

    # ── Step 5: Generate Config ────────────────────────────────────────────
    header("Step 5/6: Saving configuration")

    config = {
        "market_maker": {
            "tokens": selected,
            "spread_pct": risk["spread_pct"],
            "order_size_usd": risk["order_size_usd"],
            "max_inventory_units": risk["max_inventory_units"],
            "cycle_seconds": 5,
            "order_refresh_seconds": 30,
            "pause_on_volatility_pct": 1.5,
            "pause_minutes": 10,
            "stop_loss_pct": risk["stop_loss_pct"],
            "dry_run": False,
            "leverage": 5,
        }
    }

    script_dir = os.path.dirname(os.path.abspath(__file__))
    project_dir = os.path.dirname(script_dir)

    # If running from cloned repo, save there. Otherwise save in cwd.
    if os.path.exists(os.path.join(project_dir, "scripts", "market_maker.py")):
        base_dir = project_dir
    else:
        base_dir = os.getcwd()

    config_path = os.path.join(base_dir, "config.yaml")
    env_path = os.path.join(base_dir, ".env")

    with open(config_path, "w") as f:
        yaml.dump(config, f, default_flow_style=False, sort_keys=False)
    print(f"  ✅ Saved config: {config_path}")

    with open(env_path, "w") as f:
        f.write(f"HL_WALLET={wallet}\n")
        f.write(f"HL_PRIVATE_KEY={api_key}\n")
    print(f"  ✅ Saved credentials: {env_path}")
    print(f"     (Add .env to .gitignore if sharing!)")

    # ── Step 6: Dry Run ────────────────────────────────────────────────────
    header("Step 6/6: Test run")

    mm_script = os.path.join(script_dir, "market_maker.py") if os.path.exists(
        os.path.join(script_dir, "market_maker.py")) else os.path.join(base_dir, "scripts", "market_maker.py")

    if yes_no("Run a 15-second dry run to test?"):
        print("\n  Running dry run (no real orders)...\n")
        env = os.environ.copy()
        env["HL_WALLET"] = wallet
        env["HL_PRIVATE_KEY"] = api_key
        try:
            proc = subprocess.Popen(
                [sys.executable, mm_script, "--dry-run", "--config", config_path],
                env=env,
                stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
            )
            try:
                output_lines = []
                for line in proc.stdout:
                    output_lines.append(line.rstrip())
                    print(f"  {line.rstrip()}")
                    if len(output_lines) >= 25:
                        break
                proc.terminate()
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                proc.kill()

            print("\n  ✅ Dry run complete!")
        except Exception as e:
            print(f"  ⚠️  Dry run error: {e}")

    # ── Done ───────────────────────────────────────────────────────────────
    header("Setup Complete! 🎉")

    print(f"""  Your config is ready. To start trading:

    cd {base_dir}
    source .env
    python3 {mm_script}

  Useful commands:
    Dry run:     python3 {mm_script} --dry-run
    Custom cfg:  python3 {mm_script} --config /path/to/config.yaml

  Safety:
    • Start with dry-run if unsure
    • Monitor: check stdout logs and mm_volume.db
    • Stop: Ctrl+C (cancels all orders on exit)

  Happy volume farming! 📈""")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\n  Setup cancelled.\n")
        sys.exit(0)
