import os

HELIUS_API_KEY = os.environ.get("HELIUS_API_KEY")
MON_WALLET_PRIVATE_KEY = os.environ.get("MON_WALLET_PRIVATE_KEY")

WALLETS_A_COPIER = [
    "69aiAKU3uJMxMLRkUEGFNt6nQ43PiVimE4ZbErJ7VSM1",
    "GTLLN1nkjBFFXmu4EGs3ACFKfJXHzGXveSdUngDiAn7V",
    "7kGAXsa7n1qN2FuNoJAGmzebmN9KqqLAHcwj7gvoekKk",
    "HZXdwRRw27kfpYtTqc7bMfrRgK3LSUaiKDFtqoEihik8",
    "CAmNcBJ82xr1tzXrwZ6tZKwEFs26TG8kT6dJeR1bxjW9",
]

MONTANT_PAR_TRADE_SOL = 0.05
SLIPPAGE_BPS = 300
MONTANT_MIN_USD = 50
MONTANT_MAX_USD = 5000
DELAI_MAX_COPIE_SEC = 10

HELIUS_WS_URL = f"wss://mainnet.helius-rpc.com/?api-key={HELIUS_API_KEY}"
HELIUS_RPC_URL = f"https://mainnet.helius-rpc.com/?api-key={HELIUS_API_KEY}"

JUPITER_QUOTE_URL = "https://api.jup.ag/swap/v1/quote"
JUPITER_SWAP_URL = "https://api.jup.ag/swap/v1/swap"

SOL_MINT = "So11111111111111111111111111111111111111112"
