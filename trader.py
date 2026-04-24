import httpx
import base64
from solders.keypair import Keypair
from config import JUPITER_QUOTE_URL, JUPITER_SWAP_URL, HELIUS_RPC_URL, HELIUS_API_KEY, MON_WALLET_PRIVATE_KEY, MONTANT_PAR_TRADE_SOL, SLIPPAGE_BPS

class Trader:
    def __init__(self):
        self.keypair = Keypair.from_base58_string(MON_WALLET_PRIVATE_KEY)
        self.wallet_public = str(self.keypair.pubkey())
        print(f"[TRADER] Wallet : {self.wallet_public[:8]}...")

    async def copier_trade(self, trade):
        print(f"[TRADER] Copie du trade...")
        try:
            quote = await self._obtenir_quote(trade["token_in"], trade["token_out"])
            if not quote:
                print("[TRADER] ❌ Pas de quote disponible")
                return
            if float(quote.get("priceImpactPct", 0)) > 5:
                print("[TRADER] ⚠️ Impact prix trop élevé")
                return
            transaction = await self._construire_swap(quote)
            if not transaction:
                print("[TRADER] ❌ Impossible de construire le swap")
                return
            signature = await self._envoyer_transaction(transaction)
            if signature:
                print(f"[TRADER] ✅ Trade exécuté !")
                print(f"[TRADER] 🔗 https://solscan.io/tx/{signature}")
        except Exception as e:
            print(f"[TRADER] Erreur : {e}")

    async def _obtenir_quote(self, token_in, token_out):
        try:
            montant = int(MONTANT_PAR_TRADE_SOL * 1_000_000_000)
            params = {
                "inputMint": token_in,
                "outputMint": token_out,
                "amount": montant,
                "slippageBps": SLIPPAGE_BPS
            }
            async with httpx.AsyncClient(timeout=30) as client:
                reponse = await client.get(JUPITER_QUOTE_URL, params=params)
                print(f"[TRADER] 📡 Quote status : {reponse.status_code}")
                data = reponse.json()
                if "error" in data:
                    print(f"[TRADER] ⚠️ Erreur quote : {data['error']}")
                    return None
                return data
        except Exception as e:
            print(f"[TRADER] ❌ Erreur quote : {e}")
            return None

    async def _construire_swap(self, quote):
        try:
            payload = {
                "quoteResponse": quote,
                "userPublicKey": self.wallet_public,
                "wrapAndUnwrapSol": True,
                "dynamicComputeUnitLimit": True,
                "prioritizationFeeLamports": 1000
            }
            async with httpx.AsyncClient(timeout=30) as client:
                reponse = await client.post(JUPITER_SWAP_URL, json=payload)
                print(f"[TRADER] 📡 Swap status : {reponse.status_code}")
                data = reponse.json()
                if "swapTransaction" not in data:
                    print(f"[TRADER] ⚠️ Pas de swapTransaction : {data}")
                    return None
                return data["swapTransaction"]
        except Exception as e:
            print(f"[TRADER] ❌ Erreur swap : {e}")
            return None

    async def _envoyer_transaction(self, swap_b64):
        try:
            from solders.transaction import VersionedTransaction
            tx_bytes = base64.b64decode(swap_b64)
            tx = VersionedTransaction.from_bytes(tx_bytes)
            tx_signe = VersionedTransaction(tx.message, [self.keypair])
            tx_encode = base64.b64encode(bytes(tx_signe)).decode()
            async with httpx.AsyncClient(timeout=30) as client:
                url = f"https://mainnet.helius-rpc.com/?api-key={HELIUS_API_KEY}"
                reponse = await client.post(
                    url,
                    json={
                        "jsonrpc": "2.0",
                        "id": 1,
                        "method": "sendTransaction",
                        "params": [tx_encode, {"encoding": "base64"}]
                    }
                )
                data = reponse.json()
                print(f"[TRADER] 📡 Send status : {reponse.status_code}")
                if "result" in data:
                    return data["result"]
                print(f"[TRADER] ⚠️ Erreur envoi : {data}")
                return None
        except Exception as e:
            print(f"[TRADER] ❌ Erreur envoi : {e}")
            return None

    async def fermer(self):
        pass
