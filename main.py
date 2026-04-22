import asyncio
from monitor import WalletMonitor
from trader import Trader
from config import WALLETS_A_COPIER

async def main():
    print("=" * 55)
    print("   🤖 BOT COPY TRADING SOLANA — Démarrage")
    print("=" * 55)
    print(f"   Wallets surveillés : {len(WALLETS_A_COPIER)}")
    print("=" * 55)

    trader = Trader()

    async def on_trade_detecte(trade):
        await trader.copier_trade(trade)

    moniteur = WalletMonitor(callback_trade=on_trade_detecte)

    try:
        await moniteur.demarrer()
    except KeyboardInterrupt:
        print("\n[MAIN] 🛑 Bot arrêté")
    except Exception as e:
        print(f"\n[MAIN] ❌ Erreur : {e}")
    finally:
        await trader.fermer()
        print("[MAIN] 👋 Bot fermé")

if __name__ == "__main__":
    asyncio.run(main())
